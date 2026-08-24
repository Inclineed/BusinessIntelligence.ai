"""
pipeline/telemetry.py — Per-investigation telemetry recorder.

Records per-engine latency, LLM call/token counts, external cost (always $0.00
for local Ollama), and equivalent cloud cost from a per-1K-token rate table.

Any individual metric failure is captured in _metric_errors without aborting
the investigation (Requirements 16.1–16.6).
"""

from __future__ import annotations

import copy
import time
from contextlib import contextmanager
from typing import Generator, Optional

from models import Telemetry

# ---------------------------------------------------------------------------
# Cloud cost rate table  (USD per 1 000 tokens — input + output combined)
# ---------------------------------------------------------------------------

CLOUD_COST_PER_1K_TOKENS: dict[str, float] = {
    "claude-3-5-sonnet-20241022": 0.003,
    "gpt-4o": 0.005,
    "gpt-4o-mini": 0.00015,
    "gemini-1.5-pro": 0.00125,
}

# Default model used when computing the equivalent cloud cost estimate.
EQUIVALENT_MODEL = "claude-3-5-sonnet-20241022"


# ---------------------------------------------------------------------------
# TelemetryService
# ---------------------------------------------------------------------------

class TelemetryService:
    """
    Per-investigation telemetry recorder (Requirements 16.1–16.7).

    Usage
    -----
    svc = TelemetryService()

    with svc.measure_engine("kpi_store"):
        ...  # engine work

    svc.record_llm_call(prompt_tokens=512, completion_tokens=128,
                        model="qwen3:8b", latency_ms=420.0)

    result.telemetry = svc.get_telemetry()
    """

    def __init__(self, equivalent_model: str = EQUIVALENT_MODEL) -> None:
        self._telemetry = Telemetry()
        self._equivalent_model = equivalent_model
        self._metric_errors: list[str] = []

    # ------------------------------------------------------------------
    # Context manager: per-engine latency
    # ------------------------------------------------------------------

    @contextmanager
    def measure_engine(self, engine_name: str) -> Generator[None, None, None]:
        """
        Context manager that records per-engine latency at 1 ms resolution
        (Requirement 16.1).

        On any exception *inside the recording logic* the metric is marked
        unavailable and the exception is suppressed so the caller is not
        interrupted.  Exceptions raised by the *caller's own code* are
        re-raised normally.
        """
        start_ns: Optional[int] = None
        try:
            start_ns = time.perf_counter_ns()
        except Exception as exc:  # noqa: BLE001
            self._metric_errors.append(
                f"measure_engine({engine_name!r}): failed to start timer — {exc}"
            )
            yield
            return

        caller_exc: Optional[BaseException] = None
        try:
            yield
        except BaseException as exc:  # noqa: BLE001
            caller_exc = exc
        finally:
            try:
                end_ns = time.perf_counter_ns()
                elapsed_ms = (end_ns - start_ns) / 1_000_000.0  # ns → ms, 1 ms res
                self._telemetry.latency_ms_by_engine[engine_name] = elapsed_ms
            except Exception as exc:  # noqa: BLE001
                self._metric_errors.append(
                    f"measure_engine({engine_name!r}): failed to record latency — {exc}"
                )

        if caller_exc is not None:
            raise caller_exc

    # ------------------------------------------------------------------
    # Record one LLM call
    # ------------------------------------------------------------------

    def record_llm_call(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        model: str,  # the LLM model name
        latency_ms: float,  # noqa: ARG002  (kept for API completeness; not summed here)
        provider: str = "ollama",
    ) -> None:
        """
        Record one LLM call's token usage and update the equivalent cloud cost
        and external cost estimates (Requirements 16.2, 16.3, 16.4, 16.5).

        - Increments llm_calls.
        - Adds prompt_tokens to llm_tokens_in and completion_tokens to
          llm_tokens_out.
        - Computes external_cost_usd based on provider and model.
        - Recomputes equivalent_cloud_cost_usd from the running totals using
          the EQUIVALENT_MODEL rate; sets it to None when the rate is absent.
        - On any recording error: appends to _metric_errors, does not raise.
        """
        try:
            self._telemetry.llm_calls += 1
            self._telemetry.llm_tokens_in += prompt_tokens
            self._telemetry.llm_tokens_out += completion_tokens
            if provider:
                self._telemetry.llm_provider = provider
            if model:
                self._telemetry.llm_model = model

            # Compute external cost for cloud providers or 0.0 for local Ollama
            from llm.cost_estimator import estimate_model_cost
            call_cost = estimate_model_cost(
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                provider=provider,
            )
            if call_cost is not None:
                self._telemetry.external_cost_usd = round(
                    self._telemetry.external_cost_usd + call_cost, 6
                )

            total_tokens = (
                self._telemetry.llm_tokens_in + self._telemetry.llm_tokens_out
            )
            rate = CLOUD_COST_PER_1K_TOKENS.get(self._equivalent_model)
            if rate is None:
                # Rate table does not contain the model → mark unavailable (Req 16.5)
                self._telemetry.equivalent_cloud_cost_usd = None
                self._metric_errors.append(
                    f"record_llm_call: equivalent cost unavailable — "
                    f"model {self._equivalent_model!r} not in rate table"
                )
            else:
                self._telemetry.equivalent_cloud_cost_usd = round(
                    total_tokens * rate / 1_000.0, 2
                )
        except Exception as exc:  # noqa: BLE001
            self._metric_errors.append(f"record_llm_call: failed to record — {exc}")

    def set_provider_info(self, provider: str, model: str) -> None:
        """Set default provider and model metadata if not already recorded."""
        if not self._telemetry.llm_provider:
            self._telemetry.llm_provider = provider
        if not self._telemetry.llm_model:
            self._telemetry.llm_model = model

    def record_rate_limit_event(self) -> None:
        """Increment rate limit retry count."""
        self._telemetry.rate_limit_events += 1


    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_telemetry(self) -> Telemetry:
        """Return a deep copy of the current telemetry snapshot."""
        return copy.deepcopy(self._telemetry)

    @property
    def live_telemetry(self) -> Telemetry:
        """
        Return the internal Telemetry object by reference (not a copy).

        Use this when passing telemetry to LLM engines so that their
        record_llm_call() writes accumulate into the service's own state
        and appear in the final get_telemetry() snapshot.  Never expose
        this reference outside the orchestrator.
        """
        return self._telemetry

    def get_metric_errors(self) -> list[str]:
        """Return the list of metrics that failed to record."""
        return list(self._metric_errors)

    # ------------------------------------------------------------------
    # Sidebar formatter
    # ------------------------------------------------------------------

    def format_sidebar(self) -> str:
        """
        Render the telemetry sidebar in the format shown in the spec
        (Requirement 16.7).

        Example output
        --------------
        ━━━━━━━━━━━━━━━━━━━━━━━
          Investigation Telemetry
        ━━━━━━━━━━━━━━━━━━━━━━━
          Total time:          4.2s
          LLM calls:           2
          Tokens in:           1 024
          Tokens out:          256
          External cost:       $0.00
          Equiv. cloud cost:   $0.00
          Deterministic steps: 5 / 7
          LLM steps:           2 / 7
        ━━━━━━━━━━━━━━━━━━━━━━━
        """
        t = self._telemetry
        sep = "━" * 25

        total_ms = sum(t.latency_ms_by_engine.values())
        total_s = total_ms / 1_000.0

        total_engines = len(t.latency_ms_by_engine)

        # Engines are considered "LLM steps" only if their name ends in one of
        # the known LLM-tagged engine identifiers; everything else is deterministic.
        LLM_ENGINE_TOKENS = ("hypothesis", "decision", "memory", "llm", "narrative")
        llm_steps = sum(
            1
            for name in t.latency_ms_by_engine
            if any(tok in name.lower() for tok in LLM_ENGINE_TOKENS)
        )
        det_steps = total_engines - llm_steps

        equiv_cost_str: str
        if t.equivalent_cloud_cost_usd is None:
            equiv_cost_str = "unavailable"
        else:
            equiv_cost_str = f"${t.equivalent_cloud_cost_usd:.2f}"

        lines = [
            sep,
            "  Investigation Telemetry",
            sep,
            f"  Total time:          {total_s:.1f}s",
            f"  LLM calls:           {t.llm_calls}",
            f"  Tokens in:           {t.llm_tokens_in:,}",
            f"  Tokens out:          {t.llm_tokens_out:,}",
            f"  External cost:       ${t.external_cost_usd:.2f}",
            f"  Equiv. cloud cost:   {equiv_cost_str}",
            f"  Deterministic steps: {det_steps} / {total_engines}",
            f"  LLM steps:           {llm_steps} / {total_engines}",
            sep,
        ]
        return "\n".join(lines)
