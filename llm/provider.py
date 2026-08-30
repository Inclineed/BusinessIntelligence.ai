"""
llm/provider.py — Backend-agnostic LLM provider abstraction.

Engines call LLMProvider.complete() and LLMProvider.embed(); the concrete
backend (Ollama or Groq) is injected at startup with zero engine
changes (Requirement 19.5).

OllamaProvider:
  • Default model  : qwen3:8b
  • Fallback model : gemma3:12b  (used on timeout/connection error with default)
  • Embed model    : bge-m3
  • Default timeout: 180 s
  • On second failure after fallback: raises LLMUnavailableError

GroqProvider:
  • Default model  : llama-3.3-70b-versatile
  • Embed model    : bge-m3 (delegated to Ollama)
  • Default timeout: 30 s
  • Handles rate limits (HTTP 429) and transient 5xx errors with bounded backoff
  • On failure after retries: raises GroqAPIError / LLMUnavailableError

Requirements: 10.5, 10.6, 16.2, 19.5
"""

from __future__ import annotations

import abc
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx

try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(_env_path, override=False)
except Exception:
    pass

logger = logging.getLogger(__name__)



# ---------------------------------------------------------------------------
# Response dataclass
# ---------------------------------------------------------------------------

@dataclass
class LLMResponse:
    """Structured response returned by every LLMProvider.complete() call."""

    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    model: str
    provider: str = "ollama"

    @property
    def total_tokens(self) -> int:
        """Sum of prompt and completion tokens."""
        return self.prompt_tokens + self.completion_tokens


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class LLMUnavailableError(Exception):
    """Raised when the LLM provider is unavailable after all fallbacks / retries."""


class GroqAPIError(LLMUnavailableError):
    """Raised when the Groq API fails or encounters an unrecoverable error."""


class OpenAIAPIError(LLMUnavailableError):
    """Raised when the OpenAI API fails or encounters an unrecoverable error."""


class AnthropicAPIError(LLMUnavailableError):
    """Raised when the Anthropic API fails or encounters an unrecoverable error."""


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------

class LLMProvider(abc.ABC):
    """
    Backend-agnostic interface for LLM interactions.

    Engines depend only on this ABC; replacing the concrete implementation
    (e.g. OllamaProvider → GroqProvider) requires zero engine source edits
    (Requirement 19.5).
    """

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Identifier of the provider (e.g. 'ollama', 'groq')."""

    @abc.abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str = "",
        temperature: float = 0.0,
        max_tokens: int = 1000,
        format_json: bool = False,
    ) -> LLMResponse:
        """
        Send a completion request and return an LLMResponse.

        Parameters
        ----------
        prompt:      The user-turn text.
        model:       Model identifier (backend-specific name).
        system:      Optional system prompt.
        temperature: Sampling temperature (0.0 = deterministic).
        max_tokens:  Maximum tokens to generate.
        format_json: Force JSON output structure.
        """

    @abc.abstractmethod
    def embed(
        self,
        texts: list[str],
        *,
        model: str = "bge-m3",
    ) -> list[list[float]]:
        """
        Embed a list of texts and return a list of float vectors.

        Parameters
        ----------
        texts: Input strings to embed.
        model: Embedding model identifier.
        """


# ---------------------------------------------------------------------------
# Ollama implementation
# ---------------------------------------------------------------------------

class OllamaProvider(LLMProvider):
    """
    Concrete LLMProvider backed by a local Ollama instance.

    Default model → fallback model → LLMUnavailableError if both fail.
    Token counts and latency are returned in every LLMResponse so callers
    can record them into Telemetry without any extra instrumentation.
    """

    provider_name: str = "ollama"
    provider: str = "ollama"
    DEFAULT_MODEL: str = "qwen3:8b"
    FALLBACK_MODEL: str = "gemma3:12b"
    EMBED_MODEL: str = "bge-m3"
    DEFAULT_TIMEOUT: float = 180.0  # seconds

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        timeout: float = DEFAULT_TIMEOUT,
        model: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self.model = model or os.getenv("LLM_MODEL", self.DEFAULT_MODEL)
        self._model = self.model

    @property
    def provider_name(self) -> str:
        return "ollama"

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str = "",
        temperature: float = 0.0,
        max_tokens: int = 1000,
        format_json: bool = False,
    ) -> LLMResponse:
        """
        POST to /api/generate with fallback from DEFAULT_MODEL to FALLBACK_MODEL.

        Raises LLMUnavailableError when both attempts fail (Requirements 10.5, 10.6).
        """
        primary = model if model is not None else self.DEFAULT_MODEL

        try:
            return self._generate(primary, prompt, system, temperature, max_tokens, format_json)
        except (httpx.TimeoutException, httpx.ConnectError):
            # First failure: retry once with FALLBACK_MODEL if primary was DEFAULT
            fallback = self.FALLBACK_MODEL if primary == self.DEFAULT_MODEL else primary
            try:
                return self._generate(fallback, prompt, system, temperature, max_tokens, format_json)
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                raise LLMUnavailableError(
                    f"LLM provider unavailable after fallback "
                    f"({primary!r} → {fallback!r}): {exc}"
                ) from exc

    def embed(
        self,
        texts: list[str],
        *,
        model: str = "bge-m3",
    ) -> list[list[float]]:
        """
        POST to /api/embed and return a list of embedding vectors.

        Raises LLMUnavailableError on any HTTP or connection error.
        Uses 0.5s connection timeout so offline Ollama fails immediately without blocking.
        """
        url = f"{self._base_url}/api/embed"
        payload: dict = {"model": model, "input": texts}

        try:
            response = httpx.post(url, json=payload, timeout=5.0)
            response.raise_for_status()
            data = response.json()
            return data["embeddings"]
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError, Exception) as exc:
            raise LLMUnavailableError(
                f"Embedding request to Ollama failed ({model!r}): {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate(
        self,
        model: str,
        prompt: str,
        system: str,
        temperature: float,
        max_tokens: int,
        format_json: bool = False,
    ) -> LLMResponse:
        """
        Single (non-retrying) POST to /api/generate.

        May raise httpx.TimeoutException or httpx.ConnectError, which the
        caller (complete) handles for fallback logic.
        """
        url = f"{self._base_url}/api/generate"
        payload: dict = {
            "model": model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if format_json:
            payload["format"] = "json"
        if model.lower().startswith(("qwen3", "deepseek-r1", "qwq")):
            payload["think"] = False

        t0 = time.perf_counter()
        response = httpx.post(url, json=payload, timeout=self._timeout)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        response.raise_for_status()
        data = response.json()

        _text = data.get("response", "") or ""
        _text = re.sub(r"<think>.*?</think>", "", _text, flags=re.DOTALL).strip()

        return LLMResponse(
            text=_text,
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            latency_ms=round(latency_ms, 3),
            model=model,
            provider="ollama",
        )


# ---------------------------------------------------------------------------
# Groq implementation
# ---------------------------------------------------------------------------

class GroqProvider(LLMProvider):
    """
    Concrete LLMProvider backed by the Groq Cloud API.

    Provides high-throughput, low-latency cloud inference with bounded retries,
    rate limit (HTTP 429) backoff, and full telemetry tracking.
    Embeddings are delegated to local Ollama (bge-m3) to maintain ChromaDB consistency.
    """

    provider_name: str = "groq"
    provider: str = "groq"
    DEFAULT_MODEL: str = "groq/compound-mini"
    DEFAULT_BASE_URL: str = "https://api.groq.com/openai/v1"
    DEFAULT_TIMEOUT: float = 45.0  # seconds
    DEFAULT_MAX_RETRIES: int = 15

    def __init__(
        self,
        api_key: str | list[str] | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        ollama_embed_host: str | None = None,
        credential_mode: str | None = None,
    ) -> None:
        self._credential_mode = (credential_mode or os.getenv("GROQ_CREDENTIAL_MODE", "pool")).lower()

        raw_keys = api_key or os.getenv("GROQ_API_KEYS") or os.getenv("GROQ_API_KEY", "")
        if isinstance(raw_keys, list):
            parsed_keys = [str(k).strip() for k in raw_keys if str(k).strip()]
        else:
            parsed_keys = [k.strip() for k in raw_keys.split(",") if k.strip()]

        if not parsed_keys:
            raise ValueError(
                "GROQ_API_KEY is required for GroqProvider. "
                "Set GROQ_API_KEY in your local environment or untracked .env file."
            )

        # Use full pool when in pool mode or multiple keys provided
        if self._credential_mode == "single" and len(parsed_keys) > 1 and api_key is None:
            self._api_keys = [parsed_keys[0]]
        else:
            self._api_keys = parsed_keys

        self._current_key_idx = 0
        self._api_key = self._api_keys[0]
        self._model = model or os.getenv("GROQ_MODEL", self.DEFAULT_MODEL)
        self.model = self._model
        self.DEFAULT_MODEL = self._model
        self._base_url = (base_url or os.getenv("GROQ_BASE_URL", self.DEFAULT_BASE_URL)).rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._ollama_embed_host = (
            ollama_embed_host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        )
        self._embedder = OllamaProvider(base_url=self._ollama_embed_host, timeout=self._timeout)

    @property
    def provider_name(self) -> str:

        return "groq"

    def _get_active_key(self) -> str:
        return self._api_keys[self._current_key_idx % len(self._api_keys)]

    def _rotate_key(self) -> str:
        if len(self._api_keys) > 1:
            self._current_key_idx = (self._current_key_idx + 1) % len(self._api_keys)
            logger.info("Rotated Groq credential pool to index %d of %d", self._current_key_idx, len(self._api_keys))
        return self._get_active_key()

    @staticmethod
    def _sanitize_error_text(text: str) -> str:
        """Sanitize error messages to ensure no tokens or authorization secrets are reflected."""
        if not text:
            return ""
        return re.sub(r"gsk_[A-Za-z0-9_\-]+", "gsk_****", text)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str = "",
        temperature: float = 0.0,
        max_tokens: int = 1000,
        format_json: bool = False,
    ) -> LLMResponse:
        """
        Execute chat completion via Groq OpenAI-compatible API.

        Handles HTTP 429 rate limits (with local key rotation if configured in pool mode),
        5xx server errors, and network timeouts with exponential backoff up to max_retries.
        """
        # When engines pass generic default model or None, use instance's configured Groq model
        if model is None or model in ("qwen3:8b", "default", "groq/compound-mini", "groq/compound") or not model:
            target_model = self._model
        else:
            target_model = model
        url = f"{self._base_url}/chat/completions"

        is_reasoning_model = any(r in target_model.lower() for r in ("qwen", "deepseek", "r1", "qwq"))

        messages: list[dict[str, str]] = []
        effective_system = system
        if format_json and "json" not in (system + prompt).lower():
            effective_system = (system + "\nYou MUST respond in valid JSON format.").strip()
        if is_reasoning_model:
            effective_system = (effective_system + "\nCRITICAL: Keep your thinking process concise and output valid JSON matching the exact schema immediately.").strip()

        if effective_system:
            messages.append({"role": "system", "content": effective_system})

        user_content = prompt
        if is_reasoning_model:
            user_content = prompt + "\n\nCRITICAL INSTRUCTION: Keep thinking process brief. Output ONLY valid JSON matching the schema immediately."
        messages.append({"role": "user", "content": user_content})

        # Stay safely within Groq's 6000 TPM limit (e.g. ~1000 prompt + 1000 completion = 2000 < 6000)
        actual_max_tokens = min(max_tokens, 1000)

        payload: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": actual_max_tokens,
        }
        if format_json and not is_reasoning_model:
            payload["response_format"] = {"type": "json_object"}
        if is_reasoning_model:
            payload["reasoning_format"] = "parsed"

        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            t0 = time.perf_counter()
            headers = {
                "Authorization": f"Bearer {self._get_active_key()}",
                "Content-Type": "application/json",
            }
            try:
                response = httpx.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self._timeout,
                )
                latency_ms = (time.perf_counter() - t0) * 1000.0

                # Check for rate limiting
                if response.status_code == 429:
                    retry_after_sec = self._parse_retry_after(response.headers, attempt, response.text)
                    if len(self._api_keys) > 1:
                        self._rotate_key()
                        logger.warning(
                            "Groq rate limit (429) hit on attempt %d/%d (credential_index=%d). Rotating to next credential...",
                            attempt + 1,
                            self._max_retries + 1,
                            self._current_key_idx,
                        )
                        # Sleep proportional backoff so rate limit window clears
                        sleep_time = max(2.0, retry_after_sec / len(self._api_keys))
                        time.sleep(sleep_time)
                        continue

                    logger.warning(
                        "Groq rate limit (429) hit on attempt %d/%d (credential_index=%d). Retrying after %.2fs...",
                        attempt + 1,
                        self._max_retries + 1,
                        self._current_key_idx,
                        retry_after_sec,
                    )
                    if attempt < self._max_retries:
                        time.sleep(retry_after_sec)
                        continue
                    sanitized_err = self._sanitize_error_text(response.text)
                    raise GroqAPIError(
                        f"Groq rate limit (HTTP 429) exceeded after {self._max_retries} retries: {sanitized_err}"
                    )

                # Check for transient server errors (500, 502, 503, 504)
                if response.status_code in (500, 502, 503, 504):
                    backoff = 0.5 * (2 ** attempt)
                    logger.warning(
                        "Groq server error (%d) on attempt %d/%d. Retrying after %.2fs...",
                        response.status_code,
                        attempt + 1,
                        self._max_retries + 1,
                        backoff,
                    )
                    if attempt < self._max_retries:
                        time.sleep(backoff)
                        continue
                    sanitized_err = self._sanitize_error_text(response.text)
                    raise GroqAPIError(
                        f"Groq server error (HTTP {response.status_code}) after {self._max_retries} retries: {sanitized_err}"
                    )

                # If model failed strict json_validate, retry without response_format constraint
                if response.status_code == 400 and "json_validate_failed" in response.text:
                    if "response_format" in payload:
                        logger.warning("Groq json_validate_failed; retrying with prompt-based JSON instructions...")
                        del payload["response_format"]
                        continue

                # Client error
                if response.status_code >= 400:
                    sanitized_err = self._sanitize_error_text(response.text)
                    raise GroqAPIError(
                        f"Groq API error (HTTP {response.status_code}): {sanitized_err}"
                    )

                # Success
                try:
                    data = response.json()
                except Exception as json_err:
                    raise GroqAPIError(
                        f"Failed to decode Groq JSON response: {response.text}"
                    ) from json_err

                choices = data.get("choices")
                if not choices or not isinstance(choices, list):
                    raise GroqAPIError(f"Malformed Groq response (no choices): {data}")

                content = choices[0].get("message", {}).get("content", "") or ""
                if "<think>" in content:
                    if "</think>" in content:
                        content = content.split("</think>", 1)[1].strip()
                    else:
                        first_brace = content.find("{")
                        if first_brace != -1:
                            content = content[first_brace:].strip()
                        else:
                            content = re.sub(r"^<think>.*", "", content, flags=re.DOTALL).strip()
                elif "</think>" in content:
                    content = content.split("</think>", 1)[1].strip()

                if not content and choices[0].get("message", {}).get("reasoning"):
                    content = choices[0]["message"]["reasoning"].strip()

                if format_json:
                    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
                    if fence_match:
                        content = fence_match.group(1).strip()

                usage = data.get("usage", {}) or {}
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)

                return LLMResponse(
                    text=content,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    latency_ms=round(latency_ms, 3),
                    model=target_model,
                    provider="groq",
                )

            except (httpx.TimeoutException, httpx.ConnectError) as net_err:
                last_error = net_err
                backoff = 0.5 * (2 ** attempt)
                logger.warning(
                    "Groq network error (%s) on attempt %d/%d. Retrying after %.2fs...",
                    net_err.__class__.__name__,
                    attempt + 1,
                    self._max_retries + 1,
                    backoff,
                )
                if attempt < self._max_retries:
                    time.sleep(backoff)
                    continue
                raise LLMUnavailableError(
                    f"Groq request failed after {self._max_retries} retries ({net_err.__class__.__name__}): {net_err}"
                ) from net_err
            except GroqAPIError:
                raise
            except Exception as unk_err:
                raise GroqAPIError(f"Unexpected Groq client error: {unk_err}") from unk_err

        if last_error:
            raise LLMUnavailableError(
                f"Groq unavailable after {self._max_retries} retries: {last_error}"
            ) from last_error

        raise GroqAPIError("Groq request failed after retry loop.")

    def embed(
        self,
        texts: list[str],
        *,
        model: str = "bge-m3",
    ) -> list[list[float]]:
        """
        Embed a list of texts using local Ollama (bge-m3).

        Preserves 100% ChromaDB compatibility without modifying memory engines.
        """
        return self._embedder.embed(texts, model=model)

    @staticmethod
    def _parse_retry_after(headers: httpx.Headers, attempt: int, response_text: str = "") -> float:
        """Parse Retry-After header or rate limit reset values if available, or compute backoff."""
        raw_header = headers.get("retry-after")
        if raw_header:
            try:
                return max(0.5, float(raw_header))
            except ValueError:
                pass
        for header_key in ("x-ratelimit-reset-tokens", "x-ratelimit-reset-requests"):
            raw_reset = headers.get(header_key)
            if raw_reset:
                try:
                    if raw_reset.endswith("ms"):
                        return max(0.2, float(raw_reset[:-2]) / 1000.0)
                    if raw_reset.endswith("s"):
                        return max(0.5, float(raw_reset[:-1]))
                    return max(0.5, float(raw_reset))
                except ValueError:
                    pass

        # Try parsing "Please try again in X.XXs" from error response text
        if response_text:
            match = re.search(r"try again in ([\d\.]+)s", response_text)
            if match:
                try:
                    return max(1.0, float(match.group(1)) + 0.5)
                except ValueError:
                    pass

        return float(1.0 * (2 ** attempt))


# ---------------------------------------------------------------------------
# OpenAI implementation
# ---------------------------------------------------------------------------

class OpenAIProvider(LLMProvider):
    """
    Concrete LLMProvider backed by OpenAI's REST API.

    Features:
      • Default model  : gpt-4o-mini (configurable via OPENAI_MODEL env)
      • Embed model    : text-embedding-3-small (with fallback to local Ollama bge-m3)
      • JSON Mode      : native response_format={"type": "json_object"}
      • Error Handling : HTTP 429 rate limit backoff and 5xx retries
      • Secret redaction: sk-****
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        embed_model: str | None = None,
        ollama_embed_host: str | None = None,
    ):
        raw_key = api_key or os.getenv("OPENAI_API_KEY", "")
        raw_keys = os.getenv("OPENAI_API_KEYS", "")

        keys: list[str] = []
        if raw_keys:
            keys.extend([k.strip() for k in raw_keys.split(",") if k.strip()])
        if raw_key and raw_key not in keys:
            keys.append(raw_key.strip())

        if not keys:
            raise ValueError(
                "OPENAI_API_KEY environment variable (or api_key constructor argument) is required for OpenAIProvider."
            )

        self._api_keys = keys
        self._current_key_idx = 0
        self._model = (
            model
            or os.getenv("OPENAI_MODEL")
            or "gpt-4o-mini"
        )
        self._embed_model = (
            embed_model
            or os.getenv("OPENAI_EMBED_MODEL")
            or "text-embedding-3-small"
        )
        self._base_url = (
            base_url
            or os.getenv("OPENAI_BASE_URL")
            or os.getenv("OPENAI_API_BASE")
            or "https://api.openai.com/v1"
        ).rstrip("/")
        self._timeout = timeout if timeout is not None else float(os.getenv("OPENAI_TIMEOUT", "60.0"))
        self._max_retries = max_retries if max_retries is not None else int(os.getenv("OPENAI_MAX_RETRIES", "4"))

        # Fallback local embedder if requested or needed
        self._ollama_embed_host = (
            ollama_embed_host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        )
        self._fallback_embedder = OllamaProvider(base_url=self._ollama_embed_host, timeout=self._timeout)

    @property
    def provider_name(self) -> str:
        return "openai"

    def _get_active_key(self) -> str:
        return self._api_keys[self._current_key_idx % len(self._api_keys)]

    def _rotate_key(self) -> str:
        if len(self._api_keys) > 1:
            self._current_key_idx = (self._current_key_idx + 1) % len(self._api_keys)
            logger.info("Rotated OpenAI credential pool to index %d of %d", self._current_key_idx, len(self._api_keys))
        return self._get_active_key()

    @staticmethod
    def _sanitize_error_text(text: str) -> str:
        """Sanitize error messages to ensure no OpenAI API keys are reflected."""
        if not text:
            return ""
        return re.sub(r"sk-[A-Za-z0-9_\-]+", "sk-****", text)

    def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str = "",
        temperature: float = 0.0,
        max_tokens: int = 1000,
        format_json: bool = False,
    ) -> LLMResponse:
        target_model = model or self._model
        if target_model in ("qwen3:8b", "default", "groq/compound-mini", "groq/compound") or not target_model:
            target_model = self._model

        url = f"{self._base_url}/chat/completions"

        messages: list[dict[str, str]] = []
        effective_system = system
        if format_json and "json" not in (system + prompt).lower():
            effective_system = (system + "\nYou MUST respond in valid JSON format.").strip()

        if effective_system:
            messages.append({"role": "system", "content": effective_system})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        # Handling for reasoning models (e.g. o1, o1-mini, o3-mini)
        if any(r in target_model.lower() for r in ("o1", "o3")):
            payload.pop("temperature", None)
            payload.pop("max_tokens", None)
            payload["max_completion_tokens"] = max_tokens

        if format_json:
            payload["response_format"] = {"type": "json_object"}

        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            t0 = time.perf_counter()
            headers = {
                "Authorization": f"Bearer {self._get_active_key()}",
                "Content-Type": "application/json",
            }
            try:
                response = httpx.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self._timeout,
                )
                latency_ms = (time.perf_counter() - t0) * 1000.0

                # Rate limiting
                if response.status_code == 429:
                    self._rotate_key()
                    retry_after = self._parse_retry_after(response.headers, attempt, response.text)
                    logger.warning(
                        "OpenAI rate limit (429). Retrying in %.2fs (attempt %d/%d)...",
                        retry_after,
                        attempt + 1,
                        self._max_retries + 1,
                    )
                    if attempt < self._max_retries:
                        time.sleep(retry_after)
                        continue
                    raise OpenAIAPIError(
                        f"OpenAI rate limit (429) exceeded after {self._max_retries} retries: {self._sanitize_error_text(response.text)}"
                    )

                # Server errors
                if response.status_code >= 500:
                    backoff = 0.5 * (2 ** attempt)
                    logger.warning("OpenAI server error (%d). Retrying in %.2fs...", response.status_code, backoff)
                    if attempt < self._max_retries:
                        time.sleep(backoff)
                        continue
                    raise OpenAIAPIError(
                        f"OpenAI server error (HTTP {response.status_code}): {self._sanitize_error_text(response.text)}"
                    )

                # Client error
                if response.status_code >= 400:
                    sanitized = self._sanitize_error_text(response.text)
                    raise OpenAIAPIError(f"OpenAI API error (HTTP {response.status_code}): {sanitized}")

                data = response.json()
                choices = data.get("choices")
                if not choices or not isinstance(choices, list):
                    raise OpenAIAPIError(f"Malformed OpenAI response (no choices): {data}")

                content = choices[0].get("message", {}).get("content", "") or ""
                if format_json:
                    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
                    if fence_match:
                        content = fence_match.group(1).strip()

                usage = data.get("usage", {}) or {}
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)

                return LLMResponse(
                    text=content,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    latency_ms=round(latency_ms, 3),
                    model=target_model,
                    provider="openai",
                )

            except (httpx.TimeoutException, httpx.ConnectError) as net_err:
                last_error = net_err
                backoff = 0.5 * (2 ** attempt)
                logger.warning(
                    "OpenAI network error (%s) on attempt %d/%d. Retrying after %.2fs...",
                    net_err.__class__.__name__,
                    attempt + 1,
                    self._max_retries + 1,
                    backoff,
                )
                if attempt < self._max_retries:
                    time.sleep(backoff)
                    continue
                raise LLMUnavailableError(
                    f"OpenAI request failed after {self._max_retries} retries ({net_err.__class__.__name__}): {net_err}"
                ) from net_err
            except OpenAIAPIError:
                raise
            except Exception as unk_err:
                raise OpenAIAPIError(f"Unexpected OpenAI client error: {unk_err}") from unk_err

        if last_error:
            raise LLMUnavailableError(f"OpenAI unavailable after {self._max_retries} retries: {last_error}") from last_error

        raise OpenAIAPIError("OpenAI request failed after retry loop.")

    def embed(
        self,
        texts: list[str],
        *,
        model: str = "text-embedding-3-small",
    ) -> list[list[float]]:
        """
        Embed a list of texts using OpenAI's embedding API.
        Falls back to local Ollama bge-m3 if model='bge-m3' or API call fails.
        """
        if model == "bge-m3":
            try:
                return self._fallback_embedder.embed(texts, model=model)
            except Exception as exc:
                logger.warning("Local Ollama bge-m3 embedding failed (%s), using OpenAI embeddings.", exc)

        url = f"{self._base_url}/embeddings"
        target_model = self._embed_model if model == "bge-m3" else model
        payload = {
            "model": target_model,
            "input": texts,
        }
        headers = {
            "Authorization": f"Bearer {self._get_active_key()}",
            "Content-Type": "application/json",
        }
        try:
            response = httpx.post(url, json=payload, headers=headers, timeout=self._timeout)
            if response.status_code == 200:
                data = response.json()
                items = data.get("data", [])
                items.sort(key=lambda x: x.get("index", 0))
                return [item["embedding"] for item in items]
            raise OpenAIAPIError(f"OpenAI embedding error ({response.status_code}): {self._sanitize_error_text(response.text)}")
        except Exception as exc:
            logger.warning("OpenAI embedding API call failed (%s); trying fallback Ollama embedder...", exc)
            return self._fallback_embedder.embed(texts, model="bge-m3")

    @staticmethod
    def _parse_retry_after(headers: httpx.Headers, attempt: int, response_text: str = "") -> float:
        raw_header = headers.get("retry-after")
        if raw_header:
            try:
                return max(0.5, float(raw_header))
            except ValueError:
                pass
        return float(1.0 * (2 ** attempt))


# ---------------------------------------------------------------------------
# Anthropic implementation
# ---------------------------------------------------------------------------

class AnthropicProvider(LLMProvider):
    """
    Concrete LLMProvider backed by Anthropic's Messages REST API.

    Features:
      • Default model  : claude-3-5-haiku-20241022 (configurable via ANTHROPIC_MODEL)
      • Embed model    : delegates to local Ollama (bge-m3) preserving ChromaDB compatibility
      • Messages format: top-level system parameter + strict JSON extraction
      • Error Handling : HTTP 429 / 529 (overloaded) backoff and 5xx retries
      • Secret redaction: sk-ant-****
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        ollama_embed_host: str | None = None,
    ):
        raw_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        raw_keys = os.getenv("ANTHROPIC_API_KEYS", "")

        keys: list[str] = []
        if raw_keys:
            keys.extend([k.strip() for k in raw_keys.split(",") if k.strip()])
        if raw_key and raw_key not in keys:
            keys.append(raw_key.strip())

        if not keys:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable (or api_key constructor argument) is required for AnthropicProvider."
            )

        self._api_keys = keys
        self._current_key_idx = 0
        self._model = (
            model
            or os.getenv("ANTHROPIC_MODEL")
            or "claude-3-5-haiku-20241022"
        )
        self._base_url = (
            base_url
            or os.getenv("ANTHROPIC_BASE_URL")
            or "https://api.anthropic.com/v1"
        ).rstrip("/")
        self._timeout = timeout if timeout is not None else float(os.getenv("ANTHROPIC_TIMEOUT", "60.0"))
        self._max_retries = max_retries if max_retries is not None else int(os.getenv("ANTHROPIC_MAX_RETRIES", "4"))

        # Embeddings delegated to local Ollama bge-m3
        self._ollama_embed_host = (
            ollama_embed_host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        )
        self._embedder = OllamaProvider(base_url=self._ollama_embed_host, timeout=self._timeout)

    @property
    def provider_name(self) -> str:
        return "anthropic"

    def _get_active_key(self) -> str:
        return self._api_keys[self._current_key_idx % len(self._api_keys)]

    def _rotate_key(self) -> str:
        if len(self._api_keys) > 1:
            self._current_key_idx = (self._current_key_idx + 1) % len(self._api_keys)
            logger.info("Rotated Anthropic credential pool to index %d of %d", self._current_key_idx, len(self._api_keys))
        return self._get_active_key()

    @staticmethod
    def _sanitize_error_text(text: str) -> str:
        """Sanitize error messages to ensure no Anthropic API keys are reflected."""
        if not text:
            return ""
        return re.sub(r"sk-ant-[A-Za-z0-9_\-]+", "sk-ant-****", text)

    def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str = "",
        temperature: float = 0.0,
        max_tokens: int = 1000,
        format_json: bool = False,
    ) -> LLMResponse:
        target_model = model or self._model
        if target_model in ("qwen3:8b", "default", "groq/compound-mini", "groq/compound") or not target_model:
            target_model = self._model

        url = f"{self._base_url}/messages"

        effective_system = system
        if format_json:
            json_instruction = (
                "You MUST output valid, raw JSON only matching the schema. "
                "Do not include markdown codeblocks or conversational commentary."
            )
            effective_system = f"{system}\n{json_instruction}".strip() if system else json_instruction

        user_content = prompt
        if format_json and "json" not in prompt.lower():
            user_content = f"{prompt}\n\nRespond with valid JSON matching the required schema."

        payload: dict[str, Any] = {
            "model": target_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": user_content}],
        }
        if effective_system:
            payload["system"] = effective_system

        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            t0 = time.perf_counter()
            headers = {
                "x-api-key": self._get_active_key(),
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            try:
                response = httpx.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self._timeout,
                )
                latency_ms = (time.perf_counter() - t0) * 1000.0

                # Rate limiting or overloaded (529)
                if response.status_code in (429, 529):
                    self._rotate_key()
                    retry_after = self._parse_retry_after(response.headers, attempt, response.text)
                    logger.warning(
                        "Anthropic rate limit/overload (%d). Retrying in %.2fs (attempt %d/%d)...",
                        response.status_code,
                        retry_after,
                        attempt + 1,
                        self._max_retries + 1,
                    )
                    if attempt < self._max_retries:
                        time.sleep(retry_after)
                        continue
                    raise AnthropicAPIError(
                        f"Anthropic rate limit/overload ({response.status_code}) after {self._max_retries} retries: {self._sanitize_error_text(response.text)}"
                    )

                # Server errors
                if response.status_code >= 500:
                    backoff = 0.5 * (2 ** attempt)
                    logger.warning("Anthropic server error (%d). Retrying in %.2fs...", response.status_code, backoff)
                    if attempt < self._max_retries:
                        time.sleep(backoff)
                        continue
                    raise AnthropicAPIError(
                        f"Anthropic server error (HTTP {response.status_code}): {self._sanitize_error_text(response.text)}"
                    )

                # Client error
                if response.status_code >= 400:
                    sanitized = self._sanitize_error_text(response.text)
                    raise AnthropicAPIError(f"Anthropic API error (HTTP {response.status_code}): {sanitized}")

                data = response.json()
                content_blocks = data.get("content", [])
                text_parts = [block.get("text", "") for block in content_blocks if block.get("type") == "text"]
                content = "\n".join(text_parts).strip()

                if format_json:
                    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
                    if fence_match:
                        content = fence_match.group(1).strip()
                    elif content.startswith("{") and content.endswith("}"):
                        pass
                    else:
                        first_brace = content.find("{")
                        last_brace = content.rfind("}")
                        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                            content = content[first_brace:last_brace + 1].strip()

                usage = data.get("usage", {}) or {}
                prompt_tokens = usage.get("input_tokens", 0)
                completion_tokens = usage.get("output_tokens", 0)

                return LLMResponse(
                    text=content,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    latency_ms=round(latency_ms, 3),
                    model=target_model,
                    provider="anthropic",
                )

            except (httpx.TimeoutException, httpx.ConnectError) as net_err:
                last_error = net_err
                backoff = 0.5 * (2 ** attempt)
                logger.warning(
                    "Anthropic network error (%s) on attempt %d/%d. Retrying after %.2fs...",
                    net_err.__class__.__name__,
                    attempt + 1,
                    self._max_retries + 1,
                    backoff,
                )
                if attempt < self._max_retries:
                    time.sleep(backoff)
                    continue
                raise LLMUnavailableError(
                    f"Anthropic request failed after {self._max_retries} retries ({net_err.__class__.__name__}): {net_err}"
                ) from net_err
            except AnthropicAPIError:
                raise
            except Exception as unk_err:
                raise AnthropicAPIError(f"Unexpected Anthropic client error: {unk_err}") from unk_err

        if last_error:
            raise LLMUnavailableError(f"Anthropic unavailable after {self._max_retries} retries: {last_error}") from last_error

        raise AnthropicAPIError("Anthropic request failed after retry loop.")

    def embed(
        self,
        texts: list[str],
        *,
        model: str = "bge-m3",
    ) -> list[list[float]]:
        """
        Embed a list of texts using local Ollama (bge-m3).
        Preserves 100% ChromaDB retrieval compatibility.
        """
        return self._embedder.embed(texts, model=model)

    @staticmethod
    def _parse_retry_after(headers: httpx.Headers, attempt: int, response_text: str = "") -> float:
        raw_header = headers.get("retry-after")
        if raw_header:
            try:
                return max(0.5, float(raw_header))
            except ValueError:
                pass
        return float(1.0 * (2 ** attempt))


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

def get_llm_provider(provider_type: str | None = None) -> LLMProvider:
    """
    Return the configured LLMProvider instance.

    Reads provider from *provider_type* argument or LLM_PROVIDER env variable.
    Supported providers: 'ollama', 'groq', 'openai', 'anthropic' (or 'claude').
    Default: 'ollama'.
    """
    name = (provider_type or os.getenv("LLM_PROVIDER", "ollama")).strip().lower()

    if name == "groq":
        return GroqProvider()

    if name in ("openai", "gpt"):
        return OpenAIProvider()

    if name in ("anthropic", "claude"):
        return AnthropicProvider()

    if name == "ollama":
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        return OllamaProvider(base_url=ollama_host)

    raise ValueError(
        f"Unsupported LLM_PROVIDER: {name!r}. "
        f"Supported providers are 'ollama', 'groq', 'openai', and 'anthropic'."
    )
