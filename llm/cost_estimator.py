"""
llm/cost_estimator.py — Cloud-cost estimation for local LLM runs.

Provides:
  • CLOUD_COST_PER_1K_TOKENS — rate table (USD per 1 000 tokens, total in+out)
  • estimate_cloud_cost()    — looks up cost for a given model and token count
  • format_cost_comparison() — human-readable cost-avoidance string

Local Ollama runs incur zero external cost (Telemetry.external_cost_usd = 0.00).
The equivalent cloud cost is estimated so the demo can surface cost avoidance.
When a model is absent from the rate table the estimate is None / unavailable
(Requirement 16.5).

Requirements: 16.3, 16.4, 16.5
"""

from __future__ import annotations

from typing import Optional

from models import Telemetry


# ---------------------------------------------------------------------------
# Rate table — USD per 1 000 tokens (blended input + output rate for simplicity)
# ---------------------------------------------------------------------------

CLOUD_COST_PER_1K_TOKENS: dict[str, float] = {
    # Major cloud models (approximate public list prices as of 2025)
    "claude-3-5-sonnet": 0.003,
    "claude-3-opus":     0.015,
    "gpt-4o":            0.005,
    "gpt-4o-mini":       0.000_150,
    "gpt-4-turbo":       0.010,
    # Local Ollama models — zero external cost
    "qwen3:8b":          0.0,
    "gemma3:12b":        0.0,
    "bge-m3":            0.0,
}


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def estimate_cloud_cost(model: str, total_tokens: int) -> Optional[float]:
    """
    Return the estimated cloud cost in USD for *total_tokens* tokens on *model*.

    Returns None when *model* is not present in CLOUD_COST_PER_1K_TOKENS,
    which signals "unavailable" per Requirement 16.5.

    Parameters
    ----------
    model:        Model identifier as it appears in the rate table.
    total_tokens: Combined input + output token count.
    """
    rate = CLOUD_COST_PER_1K_TOKENS.get(model)
    if rate is None:
        return None
    return round(rate * total_tokens / 1000.0, 2)


def format_cost_comparison(
    telemetry: Telemetry,
    equivalent_model: str = "claude-3-5-sonnet",
) -> str:
    """
    Produce a human-readable cost-avoidance string.

    Example output:
        "Local run cost: $0.00  |  Equivalent claude-3-5-sonnet cost: $0.04
         (1 234 tokens total, 1 LLM call)"

    If the equivalent model is not in the rate table, the cloud estimate is
    shown as "N/A (model not in rate table)".

    Parameters
    ----------
    telemetry:        Telemetry collected during the investigation.
    equivalent_model: Cloud model to compare against (default claude-3-5-sonnet).
    """
    total_tokens = telemetry.llm_tokens_in + telemetry.llm_tokens_out
    local_cost = telemetry.external_cost_usd  # always 0.00 for Ollama

    cloud_estimate = estimate_cloud_cost(equivalent_model, total_tokens)
    if cloud_estimate is None:
        cloud_str = f"N/A (model {equivalent_model!r} not in rate table)"
    else:
        cloud_str = f"${cloud_estimate:.2f}"

    return (
        f"Local run cost: ${local_cost:.2f}  |  "
        f"Equivalent {equivalent_model} cost: {cloud_str}  "
        f"({total_tokens:,} tokens total, {telemetry.llm_calls} LLM call"
        f"{'s' if telemetry.llm_calls != 1 else ''})"
    )
