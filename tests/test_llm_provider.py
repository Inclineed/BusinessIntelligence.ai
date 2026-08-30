"""
tests/test_llm_provider.py — Provider abstraction, Groq integration, and telemetry tests.

Tests:
  A. Provider selection = ollama
  B. Provider selection = groq
  C. Missing GROQ_API_KEY fails clearly
  D. Groq success response parses correctly
  E. Malformed response fails safely
  F. HTTP 429 rate limit handling with backoff
  G. Transient 5xx retry
  H. Timeout handling
  I. Usage metadata extraction
  J. Cost calculation when pricing exists
  K. Cost remains null when pricing unavailable
  L. Ollama fallback logic remains functional
  M. Embedding delegation on GroqProvider delegates to Ollama
"""

import os
from unittest.mock import MagicMock, patch

import httpx
import pytest

from llm.cost_estimator import (
    estimate_cloud_cost,
    estimate_model_cost,
    format_cost_comparison,
)
from llm.provider import (
    AnthropicAPIError,
    AnthropicProvider,
    GroqAPIError,
    GroqProvider,
    LLMProvider,
    LLMResponse,
    LLMUnavailableError,
    OllamaProvider,
    OpenAIAPIError,
    OpenAIProvider,
    get_llm_provider,
)
from models import Telemetry
from pipeline.telemetry import TelemetryService


# ---------------------------------------------------------------------------
# Provider Selection Tests
# ---------------------------------------------------------------------------

def test_provider_selection_default_ollama(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    provider = get_llm_provider()
    assert isinstance(provider, OllamaProvider)
    assert provider.provider_name == "ollama"


def test_provider_selection_explicit_ollama():
    provider = get_llm_provider("ollama")
    assert isinstance(provider, OllamaProvider)
    assert provider.provider_name == "ollama"


def test_provider_selection_groq(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_mock_key_12345")
    provider = get_llm_provider()
    assert isinstance(provider, GroqProvider)
    assert provider.provider_name == "groq"


def test_provider_selection_openai(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-mock-openai-key-12345")
    provider = get_llm_provider()
    assert isinstance(provider, OpenAIProvider)
    assert provider.provider_name == "openai"


def test_provider_selection_anthropic(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-mock-anthropic-key-12345")
    provider = get_llm_provider()
    assert isinstance(provider, AnthropicProvider)
    assert provider.provider_name == "anthropic"


def test_provider_selection_unsupported():
    with pytest.raises(ValueError, match="Unsupported LLM_PROVIDER"):
        get_llm_provider("unsupported_cloud")


def test_groq_missing_api_key_fails(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEYS", raising=False)
    with pytest.raises(ValueError, match="GROQ_API_KEY.*is required"):
        GroqProvider(api_key=None)


def test_openai_missing_api_key_fails(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEYS", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY.*is required"):
        OpenAIProvider(api_key=None)


def test_anthropic_missing_api_key_fails(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEYS", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY.*is required"):
        AnthropicProvider(api_key=None)


# ---------------------------------------------------------------------------
# Groq Provider Execution & Parsing Tests
# ---------------------------------------------------------------------------

@patch("llm.provider.httpx.post")
def test_groq_success_response_parsing(mock_post):
    mock_post.return_value = httpx.Response(
        status_code=200,
        json={
            "choices": [
                {
                    "message": {
                        "content": '{"analysis": "Latency spike in payment gateway."}'
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 35,
                "total_tokens": 155,
            },
        },
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )

    provider = GroqProvider(api_key="gsk_test_mock_key")
    response = provider.complete(
        "Analyze anomaly",
        model="llama-3.3-70b-versatile",
        system="Be concise",
        temperature=0.0,
        format_json=True,
    )

    assert isinstance(response, LLMResponse)
    assert response.text == '{"analysis": "Latency spike in payment gateway."}'
    assert response.prompt_tokens == 120
    assert response.completion_tokens == 35
    assert response.total_tokens == 155
    assert response.model == "llama-3.3-70b-versatile"
    assert response.provider == "groq"
    assert response.latency_ms >= 0.0

    # Verify JSON format payload was passed
    called_payload = mock_post.call_args[1]["json"]
    assert called_payload["response_format"] == {"type": "json_object"}
    assert called_payload["messages"][0]["role"] == "system"
    assert called_payload["messages"][1]["role"] == "user"


@patch("llm.provider.httpx.post")
def test_groq_malformed_response_fails(mock_post):
    mock_post.return_value = httpx.Response(
        status_code=200,
        json={"choices": []},  # Empty choices
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )

    provider = GroqProvider(api_key="gsk_test_mock_key")
    with pytest.raises(GroqAPIError, match="Malformed Groq response"):
        provider.complete("Test prompt")


# ---------------------------------------------------------------------------
# Groq Rate Limit (HTTP 429) & Transient Retry Tests
# ---------------------------------------------------------------------------

@patch("time.sleep", return_value=None)
@patch("llm.provider.httpx.post")
def test_groq_429_retry_and_recover(mock_post, mock_sleep):
    # Attempt 1: 429 rate limited with Retry-After: 0.1
    # Attempt 2: 200 OK
    resp_429 = httpx.Response(
        status_code=429,
        text="Rate limit exceeded",
        headers={"retry-after": "0.1"},
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )
    resp_200 = httpx.Response(
        status_code=200,
        json={
            "choices": [{"message": {"content": "Recovered response"}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 10},
        },
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )
    mock_post.side_effect = [resp_429, resp_200]

    provider = GroqProvider(api_key="gsk_test_mock_key", max_retries=2)
    response = provider.complete("Test prompt")

    assert response.text == "Recovered response"
    assert mock_post.call_count == 2
    assert mock_sleep.call_count == 1


@patch("time.sleep", return_value=None)
@patch("llm.provider.httpx.post")
def test_groq_5xx_retry_and_exhaustion(mock_post, mock_sleep):
    resp_503 = httpx.Response(
        status_code=503,
        text="Service Unavailable",
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )
    mock_post.return_value = resp_503

    provider = GroqProvider(api_key="gsk_test_mock_key", max_retries=2)
    with pytest.raises(GroqAPIError, match="Groq server error \\(HTTP 503\\)"):
        provider.complete("Test prompt")

    # 1 initial attempt + 2 retries = 3 calls
    assert mock_post.call_count == 3


@patch("time.sleep", return_value=None)
@patch("llm.provider.httpx.post")
def test_groq_timeout_retry(mock_post, mock_sleep):
    mock_post.side_effect = httpx.TimeoutException("Read timed out")

    provider = GroqProvider(api_key="gsk_test_mock_key", max_retries=1)
    with pytest.raises(LLMUnavailableError, match="Groq request failed after 1 retries"):
        provider.complete("Test prompt")

    assert mock_post.call_count == 2


# ---------------------------------------------------------------------------
# Embeddings & Delegation Tests
# ---------------------------------------------------------------------------

@patch("llm.provider.httpx.post")
def test_groq_embed_delegation(mock_post):
    mock_post.return_value = httpx.Response(
        status_code=200,
        json={"embeddings": [[0.1, 0.2, 0.3]]},
        request=httpx.Request("POST", "http://localhost:11434/api/embed"),
    )

    provider = GroqProvider(api_key="gsk_test_mock_key")
    vecs = provider.embed(["sample query text"], model="bge-m3")

    assert len(vecs) == 1
    assert vecs[0] == [0.1, 0.2, 0.3]
    # Check that it called the local Ollama embedding endpoint
    assert "api/embed" in str(mock_post.call_args[0][0])


# ---------------------------------------------------------------------------
# Cost Estimation Tests
# ---------------------------------------------------------------------------

def test_cost_estimation_groq_model():
    # llama-3.3-70b-versatile: $0.59/1M in ($0.00059/1K), $0.79/1M out ($0.00079/1K)
    cost = estimate_model_cost(
        model="llama-3.3-70b-versatile",
        prompt_tokens=1000,
        completion_tokens=1000,
        provider="groq",
    )
    assert cost is not None
    # 1000 * 0.59/1M = 0.00059; 1000 * 0.79/1M = 0.00079 => Total = 0.00138
    assert round(cost, 6) == 0.00138


def test_cost_estimation_ollama_is_zero():
    cost = estimate_model_cost(
        model="qwen3:8b",
        prompt_tokens=5000,
        completion_tokens=2000,
        provider="ollama",
    )
    assert cost == 0.0


def test_cost_estimation_unpriced_model_returns_none():
    cost = estimate_model_cost(
        model="nonexistent-custom-model-v99",
        prompt_tokens=1000,
        completion_tokens=1000,
        provider="groq",
    )
    assert cost is None


# ---------------------------------------------------------------------------
# Telemetry Integration Tests
# ---------------------------------------------------------------------------

def test_telemetry_service_groq_call():
    svc = TelemetryService()
    svc.record_llm_call(
        prompt_tokens=2000,
        completion_tokens=500,
        model="llama-3.3-70b-versatile",
        latency_ms=150.0,
        provider="groq",
    )
    telemetry = svc.get_telemetry()

    assert telemetry.llm_calls == 1
    assert telemetry.llm_tokens_in == 2000
    assert telemetry.llm_tokens_out == 500
    assert telemetry.llm_provider == "groq"
    assert telemetry.llm_model == "llama-3.3-70b-versatile"
    assert telemetry.external_cost_usd > 0.0
    assert telemetry.equivalent_cloud_cost_usd is not None


def test_telemetry_service_ollama_call():
    svc = TelemetryService()
    svc.record_llm_call(
        prompt_tokens=2000,
        completion_tokens=500,
        model="qwen3:8b",
        latency_ms=1200.0,
        provider="ollama",
    )
    telemetry = svc.get_telemetry()

    assert telemetry.llm_calls == 1
    assert telemetry.llm_tokens_in == 2000
    assert telemetry.llm_tokens_out == 500
    assert telemetry.llm_provider == "ollama"
    assert telemetry.llm_model == "qwen3:8b"
    assert telemetry.external_cost_usd == 0.0
    assert telemetry.equivalent_cloud_cost_usd is not None


# ---------------------------------------------------------------------------
# Ollama Provider Fallback Tests
# ---------------------------------------------------------------------------

@patch("llm.provider.httpx.post")
def test_ollama_fallback_on_primary_failure(mock_post):
    # Primary qwen3:8b times out -> Fallback gemma3:12b succeeds
    resp_success = httpx.Response(
        status_code=200,
        json={"response": "Fallback answer", "prompt_eval_count": 10, "eval_count": 5},
        request=httpx.Request("POST", "http://localhost:11434/api/generate"),
    )
    mock_post.side_effect = [httpx.TimeoutException("Timeout on primary"), resp_success]

    provider = OllamaProvider()
    response = provider.complete("Test prompt")

    assert response.text == "Fallback answer"
    assert response.model == "gemma3:12b"
    assert mock_post.call_count == 2


# ---------------------------------------------------------------------------
# Multi-Key Rotation Tests
# ---------------------------------------------------------------------------

@patch("time.sleep", return_value=None)
@patch("llm.provider.httpx.post")
def test_groq_multi_key_rotation_on_429(mock_post, mock_sleep):
    # Key 1 hits 429 -> Rotates to Key 2 which succeeds with 200 OK
    resp_429 = httpx.Response(
        status_code=429,
        text="Rate limit exceeded on Key 1",
        headers={"retry-after": "10"},
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )
    resp_200 = httpx.Response(
        status_code=200,
        json={
            "choices": [{"message": {"content": "Success from Key 2"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10},
        },
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )
    mock_post.side_effect = [resp_429, resp_200]

    provider = GroqProvider(api_key=["gsk_key1", "gsk_key2", "gsk_key3"], max_retries=2)
    response = provider.complete("Test prompt")

    assert response.text == "Success from Key 2"
    assert mock_post.call_count == 2
    # Verify Authorization header changed on retry
    first_call_auth = mock_post.call_args_list[0][1]["headers"]["Authorization"]
    second_call_auth = mock_post.call_args_list[1][1]["headers"]["Authorization"]
    assert first_call_auth == "Bearer gsk_key1"
    assert second_call_auth == "Bearer gsk_key2"


def test_groq_single_credential_mode(monkeypatch):
    monkeypatch.setenv("GROQ_CREDENTIAL_MODE", "single")
    monkeypatch.setenv("GROQ_API_KEYS", "gsk_test1,gsk_test2,gsk_test3")
    provider = GroqProvider()
    assert len(provider._api_keys) == 1
    assert provider._get_active_key() == "gsk_test1"


def test_groq_local_pool_credential_mode(monkeypatch):
    monkeypatch.setenv("GROQ_CREDENTIAL_MODE", "local_pool")
    monkeypatch.setenv("GROQ_API_KEYS", "gsk_test1,gsk_test2,gsk_test3")
    provider = GroqProvider()
    assert len(provider._api_keys) == 3


@patch("llm.provider.httpx.post")
def test_groq_sanitizes_error_messages(mock_post):
    mock_post.return_value = httpx.Response(
        status_code=400,
        text="Invalid request with token gsk_secret_token_12345 in header",
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )
    provider = GroqProvider(api_key="gsk_test_key")
    with pytest.raises(GroqAPIError) as exc_info:
        provider.complete("Test")
    err_str = str(exc_info.value)
    assert "gsk_****" in err_str
    assert "gsk_secret_token_12345" not in err_str


# ---------------------------------------------------------------------------
# OpenAI Provider Execution & Parsing Tests
# ---------------------------------------------------------------------------

@patch("llm.provider.httpx.post")
def test_openai_success_response_parsing(mock_post):
    mock_post.return_value = httpx.Response(
        status_code=200,
        json={
            "choices": [
                {
                    "message": {
                        "content": '{"summary": "Payment failure spike identified."}'
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 150,
                "completion_tokens": 45,
                "total_tokens": 195,
            },
        },
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )

    provider = OpenAIProvider(api_key="sk-test-key-openai")
    response = provider.complete(
        "Analyze payment incident",
        model="gpt-4o-mini",
        system="Return JSON",
        format_json=True,
    )

    assert response.provider == "openai"
    assert response.model == "gpt-4o-mini"
    assert response.prompt_tokens == 150
    assert response.completion_tokens == 45
    assert response.total_tokens == 195
    assert "Payment failure spike" in response.text
    assert mock_post.call_count == 1

    # Verify JSON response format flag in payload
    call_payload = mock_post.call_args[1]["json"]
    assert call_payload["response_format"] == {"type": "json_object"}
    assert call_payload["model"] == "gpt-4o-mini"


@patch("time.sleep", return_value=None)
@patch("llm.provider.httpx.post")
def test_openai_rate_limit_and_retry(mock_post, mock_sleep):
    resp_429 = httpx.Response(
        status_code=429,
        text="Rate limit exceeded",
        headers={"retry-after": "1"},
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )
    resp_200 = httpx.Response(
        status_code=200,
        json={
            "choices": [{"message": {"content": "Success after rate limit"}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10},
        },
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )
    mock_post.side_effect = [resp_429, resp_200]

    provider = OpenAIProvider(api_key="sk-key1", max_retries=2)
    response = provider.complete("Test prompt")
    assert response.text == "Success after rate limit"
    assert mock_post.call_count == 2


@patch("llm.provider.httpx.post")
def test_openai_sanitizes_error_messages(mock_post):
    mock_post.return_value = httpx.Response(
        status_code=401,
        text="Incorrect API key provided: sk-proj-super_secret_openai_key_12345.",
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )
    provider = OpenAIProvider(api_key="sk-test-key")
    with pytest.raises(OpenAIAPIError) as exc_info:
        provider.complete("Test")
    err_str = str(exc_info.value)
    assert "sk-****" in err_str
    assert "sk-proj-super_secret_openai_key_12345" not in err_str


@patch("llm.provider.httpx.post")
def test_openai_embed_success(mock_post):
    mock_post.return_value = httpx.Response(
        status_code=200,
        json={
            "data": [
                {"embedding": [0.1, 0.2, 0.3], "index": 0},
                {"embedding": [0.4, 0.5, 0.6], "index": 1},
            ]
        },
        request=httpx.Request("POST", "https://api.openai.com/v1/embeddings"),
    )
    provider = OpenAIProvider(api_key="sk-test-key")
    vectors = provider.embed(["sample 1", "sample 2"], model="text-embedding-3-small")
    assert len(vectors) == 2
    assert vectors[0] == [0.1, 0.2, 0.3]
    assert vectors[1] == [0.4, 0.5, 0.6]


# ---------------------------------------------------------------------------
# Anthropic Provider Execution & Parsing Tests
# ---------------------------------------------------------------------------

@patch("llm.provider.httpx.post")
def test_anthropic_success_response_parsing(mock_post):
    mock_post.return_value = httpx.Response(
        status_code=200,
        json={
            "id": "msg_01XFDUDYJgAACQQabb5xQH8u",
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "text", "text": '{"cause": "Timeout failure in checkout microservice"}'}
            ],
            "model": "claude-3-5-haiku-20241022",
            "usage": {
                "input_tokens": 110,
                "output_tokens": 40,
            },
        },
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
    )

    provider = AnthropicProvider(api_key="sk-ant-test-key-anthropic")
    response = provider.complete(
        "Analyze root cause",
        model="claude-3-5-haiku-20241022",
        system="You are an expert diagnostic assistant.",
        format_json=True,
    )

    assert response.provider == "anthropic"
    assert response.model == "claude-3-5-haiku-20241022"
    assert response.prompt_tokens == 110
    assert response.completion_tokens == 40
    assert response.total_tokens == 150
    assert "Timeout failure in checkout" in response.text
    assert mock_post.call_count == 1

    # Verify Anthropic headers and top-level system parameter
    headers = mock_post.call_args[1]["headers"]
    assert headers["x-api-key"] == "sk-ant-test-key-anthropic"
    assert headers["anthropic-version"] == "2023-06-01"

    payload = mock_post.call_args[1]["json"]
    assert payload["model"] == "claude-3-5-haiku-20241022"
    assert "system" in payload
    assert "You are an expert diagnostic assistant" in payload["system"]


@patch("time.sleep", return_value=None)
@patch("llm.provider.httpx.post")
def test_anthropic_overloaded_529_retry(mock_post, mock_sleep):
    resp_529 = httpx.Response(
        status_code=529,
        text="Anthropic API is currently overloaded",
        headers={"retry-after": "2"},
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
    )
    resp_200 = httpx.Response(
        status_code=200,
        json={
            "content": [{"type": "text", "text": "Success after 529 overload recovery"}],
            "usage": {"input_tokens": 15, "output_tokens": 12},
        },
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
    )
    mock_post.side_effect = [resp_529, resp_200]

    provider = AnthropicProvider(api_key="sk-ant-key1", max_retries=2)
    response = provider.complete("Test prompt")
    assert response.text == "Success after 529 overload recovery"
    assert mock_post.call_count == 2


@patch("llm.provider.httpx.post")
def test_anthropic_sanitizes_error_messages(mock_post):
    mock_post.return_value = httpx.Response(
        status_code=401,
        text="Invalid x-api-key: sk-ant-api03-super_secret_anthropic_key_98765.",
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
    )
    provider = AnthropicProvider(api_key="sk-ant-test-key")
    with pytest.raises(AnthropicAPIError) as exc_info:
        provider.complete("Test")
    err_str = str(exc_info.value)
    assert "sk-ant-****" in err_str
    assert "sk-ant-api03-super_secret_anthropic_key_98765" not in err_str


# ---------------------------------------------------------------------------
# Cloud Model Cost Calculation Tests (OpenAI & Anthropic)
# ---------------------------------------------------------------------------

def test_cost_calculation_openai_models():
    # gpt-4o-mini: $0.15/1M input, $0.60/1M output
    # 1,000 prompt + 500 completion
    cost_mini = estimate_model_cost("gpt-4o-mini", prompt_tokens=1000, completion_tokens=500, provider="openai")
    expected_mini = (1000 * 0.15 / 1_000_000) + (500 * 0.60 / 1_000_000)
    assert cost_mini == round(expected_mini, 6)

    # gpt-4o: $2.50/1M input, $10.00/1M output
    cost_4o = estimate_model_cost("gpt-4o", prompt_tokens=2000, completion_tokens=1000, provider="openai")
    expected_4o = (2000 * 2.50 / 1_000_000) + (1000 * 10.00 / 1_000_000)
    assert cost_4o == round(expected_4o, 6)


def test_cost_calculation_anthropic_models():
    # claude-3-5-haiku-20241022: $0.80/1M input, $4.00/1M output
    cost_haiku = estimate_model_cost("claude-3-5-haiku-20241022", prompt_tokens=1000, completion_tokens=500, provider="anthropic")
    expected_haiku = (1000 * 0.80 / 1_000_000) + (500 * 4.00 / 1_000_000)
    assert cost_haiku == round(expected_haiku, 6)

    # claude-3-5-sonnet: $3.00/1M input, $15.00/1M output
    cost_sonnet = estimate_model_cost("claude-3-5-sonnet", prompt_tokens=2000, completion_tokens=1000, provider="anthropic")
    expected_sonnet = (2000 * 3.00 / 1_000_000) + (1000 * 15.00 / 1_000_000)
    assert cost_sonnet == round(expected_sonnet, 6)
