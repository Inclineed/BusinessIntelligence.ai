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
from typing import Any, Optional

import httpx

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

    DEFAULT_MODEL: str = "qwen3:8b"
    FALLBACK_MODEL: str = "gemma3:12b"
    EMBED_MODEL: str = "bge-m3"
    DEFAULT_TIMEOUT: float = 180.0  # seconds

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

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
        """
        url = f"{self._base_url}/api/embed"
        payload: dict = {"model": model, "input": texts}

        try:
            response = httpx.post(url, json=payload, timeout=self._timeout)
            response.raise_for_status()
            data = response.json()
            return data["embeddings"]
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as exc:
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

    DEFAULT_MODEL: str = "llama-3.3-70b-versatile"
    DEFAULT_BASE_URL: str = "https://api.groq.com/openai/v1"
    DEFAULT_TIMEOUT: float = 45.0  # seconds
    DEFAULT_MAX_RETRIES: int = 5

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
        self._credential_mode = credential_mode or os.getenv("GROQ_CREDENTIAL_MODE", "single").lower()

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

        # In production single mode, use strictly a single credential
        if self._credential_mode == "single" and len(parsed_keys) > 1 and api_key is None:
            self._api_keys = [parsed_keys[0]]
        else:
            self._api_keys = parsed_keys

        self._current_key_idx = 0
        self._api_key = self._api_keys[0]
        self._model = model or os.getenv("GROQ_MODEL", self.DEFAULT_MODEL)
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
        if model is None or model in ("qwen3:8b", "default"):
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

        # For reasoning models, provide enough headroom for thinking chain + JSON output
        actual_max_tokens = max(max_tokens, 6000) if is_reasoning_model else max_tokens

        payload: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": actual_max_tokens,
        }
        # Only attach response_format for non-reasoning models (reasoning models fail json_validate)
        if format_json and not is_reasoning_model:
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

                # Check for rate limiting
                if response.status_code == 429:
                    if len(self._api_keys) > 1:
                        self._rotate_key()
                        logger.warning(
                            "Groq rate limit (429) hit on attempt %d/%d (credential_index=%d). Rotating to next credential...",
                            attempt + 1,
                            self._max_retries + 1,
                            self._current_key_idx,
                        )
                        time.sleep(0.2)
                        continue

                    retry_after_sec = self._parse_retry_after(response.headers, attempt, response.text)
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
                if "</think>" in content:
                    content = content.split("</think>", 1)[1].strip()
                elif content.startswith("<think>"):
                    content = re.sub(r"^<think>.*", "", content, flags=re.DOTALL).strip()
                else:
                    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

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
# Factory function
# ---------------------------------------------------------------------------

def get_llm_provider(provider_type: str | None = None) -> LLMProvider:
    """
    Return the configured LLMProvider instance.

    Reads provider from *provider_type* argument or LLM_PROVIDER env variable.
    Default: 'ollama'.
    """
    name = (provider_type or os.getenv("LLM_PROVIDER", "ollama")).strip().lower()

    if name == "ollama":
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        return OllamaProvider(base_url=ollama_host)

    if name == "groq":
        return GroqProvider()

    raise ValueError(
        f"Unsupported LLM_PROVIDER: {name!r}. "
        f"Supported providers are 'ollama' and 'groq'."
    )
