"""
llm/telemetry_wrapper.py — Telemetry recording helpers for LLM calls.

record_llm_call() is the single place that writes LLM usage into Telemetry so
every engine can instrument itself with one import rather than duplicating field
arithmetic.

Requirements: 16.1, 16.2, 16.3
"""

from __future__ import annotations

from models import Telemetry
from llm.provider import LLMResponse


def record_llm_call(
    telemetry: Telemetry,
    response: LLMResponse,
    engine_name: str = "llm",
) -> None:
    """
    Accumulate LLM call statistics into *telemetry* in-place.

    Parameters
    ----------
    telemetry:   The Telemetry instance for the current investigation.
    response:    The LLMResponse returned by LLMProvider.complete().
    engine_name: Key used when accumulating latency in latency_ms_by_engine
                 (default "llm"; callers should pass their engine name, e.g.
                 "hypothesis_engine" or "decision_engine").

    Updates
    -------
    - telemetry.llm_calls        += 1
    - telemetry.llm_tokens_in    += response.prompt_tokens
    - telemetry.llm_tokens_out   += response.completion_tokens
    - telemetry.latency_ms_by_engine[engine_name] += response.latency_ms
    """
    telemetry.llm_calls += 1
    telemetry.llm_tokens_in += response.prompt_tokens
    telemetry.llm_tokens_out += response.completion_tokens

    prior = telemetry.latency_ms_by_engine.get(engine_name, 0.0)
    telemetry.latency_ms_by_engine[engine_name] = prior + response.latency_ms
