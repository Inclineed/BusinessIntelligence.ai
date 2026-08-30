"""
llm/cost_estimator.py — Cost estimation and comparison for LLM runs.

Provides:
  • CLOUD_COST_PER_1K_TOKENS — rate table (USD per 1 000 tokens, blended or model-specific)
  • MODEL_PRICING_PER_1M     — precise input/output pricing per 1M tokens
  • estimate_model_cost()    — computes accurate cost for provider, model, and token counts
  • estimate_cloud_cost()    — legacy helper for single model total token lookup
  • format_cost_comparison() — human-readable cost-avoidance string

Local Ollama runs incur zero external cost (Telemetry.external_cost_usd = 0.00).
Groq runs compute actual API cost based on official token pricing.
When pricing is unavailable for an unknown model, estimate returns None (Requirement 16.5).

Requirements: 16.3, 16.4, 16.5
"""

from __future__ import annotations

from typing import Optional

from models import Telemetry


# ---------------------------------------------------------------------------
# Rate table — USD per 1M tokens (input_per_million, output_per_million)
# ---------------------------------------------------------------------------

MODEL_PRICING_PER_1M: dict[str, tuple[float, float]] = {
    # Groq Cloud Models
    "llama-3.3-70b-versatile":   (0.59, 0.79),
    "llama-3.1-70b-versatile":   (0.59, 0.79),
    "llama-3.1-8b-instant":      (0.05, 0.08),
    "llama3-70b-8192":           (0.59, 0.79),
    "llama3-8b-8192":            (0.05, 0.08),
    "mixtral-8x7b-32768":        (0.24, 0.24),
    "gemma2-9b-it":              (0.20, 0.20),
    "qwen-2.5-32b":              (0.79, 0.79),
    "qwen/qwen3.6-27b":          (0.59, 0.79),
    "qwen3.6-27b":               (0.59, 0.79),
    "qwen/qwen-2.5-32b":         (0.79, 0.79),
    # OpenAI Models
    "gpt-4o":                    (2.50, 10.00),
    "gpt-4o-2024-08-06":         (2.50, 10.00),
    "gpt-4o-mini":               (0.15, 0.60),
    "gpt-4o-mini-2024-07-18":    (0.15, 0.60),
    "gpt-4-turbo":               (10.00, 30.00),
    "gpt-4":                     (30.00, 60.00),
    "gpt-3.5-turbo":             (0.50, 1.50),
    "o1":                        (15.00, 60.00),
    "o1-mini":                   (3.00, 12.00),
    "o1-preview":                (15.00, 60.00),
    "o3-mini":                   (1.10, 4.40),
    "text-embedding-3-small":    (0.02, 0.00),
    "text-embedding-3-large":    (0.13, 0.00),
    # Anthropic Models
    "claude-3-5-sonnet-20241022":(3.00, 15.00),
    "claude-3-5-sonnet-20240620":(3.00, 15.00),
    "claude-3-5-sonnet":         (3.00, 15.00),
    "claude-3-5-haiku-20241022": (0.80, 4.00),
    "claude-3-5-haiku":          (0.80, 4.00),
    "claude-3-opus-20240229":    (15.00, 75.00),
    "claude-3-opus":             (15.00, 75.00),
    "claude-3-haiku-20240307":   (0.25, 1.25),
    "claude-3-haiku":            (0.25, 1.25),
    # Local Ollama models — zero external cost
    "qwen3:8b":                  (0.0, 0.0),
    "gemma3:12b":                (0.0, 0.0),
    "bge-m3":                    (0.0, 0.0),
}


# ---------------------------------------------------------------------------
# Blended Rate table — USD per 1 000 tokens (for backward compatibility)
# ---------------------------------------------------------------------------

CLOUD_COST_PER_1K_TOKENS: dict[str, float] = {
    "claude-3-5-sonnet":         0.003,
    "claude-3-5-sonnet-20241022":0.003,
    "claude-3-5-haiku":          0.000_800,
    "claude-3-5-haiku-20241022": 0.000_800,
    "claude-3-opus":             0.015,
    "claude-3-haiku":            0.000_250,
    "gpt-4o":                    0.005,
    "gpt-4o-mini":               0.000_150,
    "gpt-4-turbo":               0.010,
    "o1":                        0.015,
    "o1-mini":                   0.003,
    "o3-mini":                   0.001_100,
    "llama-3.3-70b-versatile":   0.000_690,
    "llama-3.1-70b-versatile":   0.000_690,
    "llama-3.1-8b-instant":      0.000_065,
    "llama3-70b-8192":           0.000_690,
    "llama3-8b-8192":            0.000_065,
    "mixtral-8x7b-32768":        0.000_240,
    "gemma2-9b-it":              0.000_200,
    "qwen-2.5-32b":              0.000_790,
    "qwen3:8b":                  0.0,
    "gemma3:12b":                0.0,
    "bge-m3":                    0.0,
}


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def estimate_model_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    provider: str = "ollama",
) -> Optional[float]:
    """
    Return estimated cost in USD for the given provider, model, and token split.

    - For local Ollama: returns 0.0.
    - For Groq / Cloud providers: returns computed USD cost from pricing table.
    - If model is unpriced / not in rate table: returns None (marking unavailable).
    """
    if provider.lower() == "ollama" or model in ("qwen3:8b", "gemma3:12b", "bge-m3"):
        return 0.0

    pricing = MODEL_PRICING_PER_1M.get(model)
    if pricing is not None:
        in_rate, out_rate = pricing
        cost = (prompt_tokens * in_rate / 1_000_000.0) + (completion_tokens * out_rate / 1_000_000.0)
        return round(cost, 6)

    # Fallback to blended 1K rate if model is in CLOUD_COST_PER_1K_TOKENS
    blended_rate = CLOUD_COST_PER_1K_TOKENS.get(model)
    if blended_rate is not None:
        total_tokens = prompt_tokens + completion_tokens
        return round(total_tokens * blended_rate / 1_000.0, 6)

    return None


def estimate_cloud_cost(model: str, total_tokens: int) -> Optional[float]:
    """
    Return the estimated cloud cost in USD for *total_tokens* tokens on *model*.

    Returns None when *model* is not present in CLOUD_COST_PER_1K_TOKENS,
    which signals "unavailable" per Requirement 16.5.
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
    Produce a human-readable cost-avoidance or cost-summary string.

    Parameters
    ----------
    telemetry:        Telemetry collected during the investigation.
    equivalent_model: Cloud model to compare against (default claude-3-5-sonnet).
    """
    total_tokens = telemetry.llm_tokens_in + telemetry.llm_tokens_out
    external_cost = telemetry.external_cost_usd

    cloud_estimate = estimate_cloud_cost(equivalent_model, total_tokens)
    if cloud_estimate is None:
        cloud_str = f"N/A (model {equivalent_model!r} not in rate table)"
    else:
        cloud_str = f"${cloud_estimate:.2f}"

    return (
        f"Incurred run cost: ${external_cost:.4f}  |  "
        f"Equivalent {equivalent_model} cost: {cloud_str}  "
        f"({total_tokens:,} tokens total, {telemetry.llm_calls} LLM call"
        f"{'s' if telemetry.llm_calls != 1 else ''})"
    )
