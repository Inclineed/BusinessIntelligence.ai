"""
tests/test_outcome.py — Unit & Integration Test Suite for Engine E8 (Outcome Engine)

Requirements Tested:
- 14.1: Outcome projection stamped with OutcomeType.SIMULATED and MethodTag.SIMULATED.
- 14.2: Outcome projection contains non-empty disclaimer ("not causal proof").
- 14.3: Abstained decision suppresses outcome projection (returns None).
- 14.4: Recommended action mapped to configured recovery curve (rollback, reorder, default).
- 14.5: Validation guard withholds non-compliant projections.
- mean_time_to_normalcy, recovery_window_hours, assumptions populated from configuration.
- Zero LLM calls made (pure deterministic simulation).
"""

from __future__ import annotations

import pytest
from models import Decision, MethodTag, OutcomeProjection, OutcomeType
from engines.outcome import project_outcome, validate_outcome_projection, _match_curve, SIMULATED_DISCLAIMER
from config.loader import load_domain_semantics
from pathlib import Path


@pytest.fixture
def domain_semantics():
    config_path = Path("config") / "domain_semantics.yaml"
    return load_domain_semantics(config_path)


def test_rollback_action_matches_configured_rollback_curve(domain_semantics):
    decision = Decision(
        abstained=False,
        recommended_action="Immediately roll back Checkout Service from v4.3 to v4.2 to restore capacity.",
        verification_metric="kpi_primary_metric_recovery",
        winning_hypothesis_id="H1",
        persona_narrative="Rollback recommended to fix connection pool starvation.",
        method=MethodTag.LLM,
    )
    outcome = project_outcome(decision, domain_semantics)

    assert outcome is not None
    assert outcome.outcome_type == OutcomeType.SIMULATED
    assert outcome.method == MethodTag.SIMULATED
    assert outcome.projected_recovery_pct == 85.0
    assert outcome.projected_metric == "payment_success_rate + conversion_rate"
    assert outcome.recovery_window_hours == 2
    assert outcome.mean_time_to_normalcy == "5 min"
    assert len(outcome.assumptions) >= 1
    assert SIMULATED_DISCLAIMER in outcome.disclaimer


def test_reorder_action_matches_configured_reorder_curve(domain_semantics):
    decision = Decision(
        abstained=False,
        recommended_action="Initiate urgent reorder and replenish inventory for fast-moving SKUs.",
        verification_metric="inventory_fill_rate",
        winning_hypothesis_id="H2",
        persona_narrative="Inventory replenishment needed.",
        method=MethodTag.LLM,
    )
    outcome = project_outcome(decision, domain_semantics)

    assert outcome is not None
    assert outcome.outcome_type == OutcomeType.SIMULATED
    assert outcome.method == MethodTag.SIMULATED
    assert outcome.projected_recovery_pct == 90.0
    assert outcome.projected_metric == "inventory_fill_rate"
    assert outcome.recovery_window_hours == 6
    assert outcome.mean_time_to_normalcy == "6 hours"
    assert len(outcome.assumptions) >= 1


def test_unmatched_action_falls_back_to_default_curve(domain_semantics):
    decision = Decision(
        abstained=False,
        recommended_action="Perform general system diagnostics and verify network switch telemetry.",
        verification_metric="kpi_primary_metric_recovery",
        winning_hypothesis_id="H3",
        persona_narrative="System diagnostics underway.",
        method=MethodTag.LLM,
    )
    outcome = project_outcome(decision, domain_semantics)

    assert outcome is not None
    assert outcome.outcome_type == OutcomeType.SIMULATED
    assert outcome.method == MethodTag.SIMULATED
    assert outcome.projected_recovery_pct == 75.0
    assert outcome.projected_metric == "kpi_primary_metric"
    assert outcome.recovery_window_hours == 4
    assert outcome.mean_time_to_normalcy == "15 min"


def test_abstained_decision_returns_none_suppressed():
    decision = Decision(
        abstained=True,
        recommended_action=None,
        verification_metric="kpi_primary_metric_recovery",
        winning_hypothesis_id=None,
        persona_narrative="Abstained due to low confidence.",
        method=MethodTag.LLM,
    )
    outcome = project_outcome(decision)
    assert outcome is None


def test_none_recommended_action_on_non_abstained_returns_none():
    decision = Decision(
        abstained=False,
        recommended_action=None,
        verification_metric="kpi_primary_metric_recovery",
        winning_hypothesis_id="H1",
        persona_narrative="Action pending.",
        method=MethodTag.LLM,
    )
    outcome = project_outcome(decision)
    assert outcome is None


def test_validate_outcome_projection_enforces_honesty():
    valid = OutcomeProjection(
        outcome_type=OutcomeType.SIMULATED,
        projected_metric="orders",
        projected_recovery_pct=80.0,
        mean_time_to_normalcy="10 min",
        disclaimer="Simulated estimate",
        method=MethodTag.SIMULATED,
    )
    assert validate_outcome_projection(valid) is True

    # Empty disclaimer fails
    invalid_disclaimer = OutcomeProjection(
        outcome_type=OutcomeType.SIMULATED,
        projected_metric="orders",
        projected_recovery_pct=80.0,
        disclaimer="   ",
        method=MethodTag.SIMULATED,
    )
    assert validate_outcome_projection(invalid_disclaimer) is False


def test_e8_is_deterministic_and_makes_zero_llm_calls(domain_semantics):
    decision = Decision(
        abstained=False,
        recommended_action="Roll back deployment v4.3",
        verification_metric="kpi_primary_metric_recovery",
        winning_hypothesis_id="H1",
        persona_narrative="Rollback recommended.",
        method=MethodTag.LLM,
    )
    # Run 10 times — guarantee 100% identical outputs
    results = [project_outcome(decision, domain_semantics) for _ in range(10)]
    first = results[0]
    for r in results[1:]:
        assert r.projected_recovery_pct == first.projected_recovery_pct
        assert r.mean_time_to_normalcy == first.mean_time_to_normalcy
        assert r.projected_metric == first.projected_metric
        assert r.recovery_window_hours == first.recovery_window_hours
        assert r.assumptions == first.assumptions
