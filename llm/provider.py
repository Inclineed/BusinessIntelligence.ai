"""
llm/provider.py â€” Backend-agnostic LLM provider abstraction.

Engines call LLMProvider.complete() and LLMProvider.embed(); the concrete
backend (Ollama today, cloud later) is injected at startup with zero engine
changes (Requirement 19.5).

OllamaProvider:
  â€¢ Default model  : qwen3:8b
  â€¢ Fallback model : gemma3:12b  (used on timeout/connection error with default)
  â€¢ Embed model    : bge-m3
  â€¢ Default timeout: 30 s
  â€¢ On second failure after fallback: raises LLMUnavailableError

Requirements: 10.5, 10.6, 19.5
"""

from __future__ import annotations

import abc
import re
import time
from dataclasses import dataclass

import httpx


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


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------

class LLMProvider(abc.ABC):
    """
    Backend-agnostic interface for LLM interactions.

    Engines depend only on this ABC; replacing the concrete implementation
    (e.g. OllamaProvider â†’ a cloud provider) requires zero engine source edits
    (Requirement 19.5).
    """

    @abc.abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        model: str,
        system: str = "",
        temperature: float = 0.0,
        max_tokens: int = 1000,
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

class LLMUnavailableError(Exception):
    """Raised when the LLM provider is unavailable after all fallbacks."""


class OllamaProvider(LLMProvider):
    """
    Concrete LLMProvider backed by a local Ollama instance.

    Default model â†’ fallback model â†’ LLMUnavailableError if both fail.
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
                    f"({primary!r} â†’ {fallback!r}): {exc}"
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
        )

