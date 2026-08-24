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
    GroqAPIError,
    GroqProvider,
    LLMProvider,
    LLMResponse,
    LLMUnavailableError,
    OllamaProvider,
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


def test_provider_selection_unsupported():
    with pytest.raises(ValueError, match="Unsupported LLM_PROVIDER"):
        get_llm_provider("unsupported_cloud")


def test_groq_missing_api_key_fails(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEYS", raising=False)
    with pytest.raises(ValueError, match="GROQ_API_KEY.*is required"):
        GroqProvider(api_key=None)


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
