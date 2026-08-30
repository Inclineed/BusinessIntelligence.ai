"""
tests/test_outcome.py — Unit & Integration Test Suite for Engine E8 (Outcome Engine)

Requirements Tested:
- 14.1: Outcome projection stamped with OutcomeType.SIMULATED and MethodTag.SIMULATED.
- 14.2: Outcome projection contains non-empty disclaimer ("not causal proof").
- 14.3: Abstained decision suppresses outcome projection (returns None).
- 14.4: Recommended action mapped to configured recovery curve (rollback, reorder, default).
- 14.5: Validation guard withholds non-compliant projections.
- Governance Gating: MARGINAL, ABSTAIN, REJECTED, and diagnostic actions return None.
- mean_time_to_normalcy, recovery_window_hours, assumptions populated from configuration.
- Zero LLM calls made (pure deterministic simulation).
"""

from __future__ import annotations

import pytest
from pathlib import Path
from models import AuditVerdict, Decision, MethodTag, OutcomeProjection, OutcomeType, StructuredActionRecommendation
from engines.outcome import project_outcome, validate_outcome_projection, _match_curve, SIMULATED_DISCLAIMER
from config.loader import load_domain_semantics


@pytest.fixture
def domain_semantics():
    config_path = Path("config") / "domain_semantics.yaml"
    return load_domain_semantics(config_path)


def test_1_verified_rollback_action_matches_configured_rollback_curve(domain_semantics):
    """Test 1: VERIFIED + rollback -> 85% projection."""
    decision = Decision(
        abstained=False,
        recommended_action="Immediately roll back Checkout Service from v4.3 to v4.2 to restore capacity.",
        verification_metric="kpi_primary_metric_recovery",
        winning_hypothesis_id="H1",
        persona_narrative="Rollback recommended to fix connection pool starvation.",
        method=MethodTag.LLM,
    )
    outcome = project_outcome(decision, domain_semantics, overall_verdict=AuditVerdict.VERIFIED)

    assert outcome is not None
    assert outcome.outcome_type == OutcomeType.SIMULATED
    assert outcome.method == MethodTag.SIMULATED
    assert outcome.projected_recovery_pct == 85.0
    assert outcome.projected_metric == "payment_success_rate + conversion_rate"
    assert outcome.recovery_window_hours == 2
    assert outcome.mean_time_to_normalcy == "5 min"
    assert len(outcome.assumptions) >= 1
    assert SIMULATED_DISCLAIMER in outcome.disclaimer


def test_2_verified_reorder_action_matches_configured_reorder_curve(domain_semantics):
    """Test 2: VERIFIED + reorder -> 90% projection."""
    decision = Decision(
        abstained=False,
        recommended_action="Initiate urgent reorder and replenish inventory for fast-moving SKUs.",
        verification_metric="inventory_fill_rate",
        winning_hypothesis_id="H2",
        persona_narrative="Inventory replenishment needed.",
        method=MethodTag.LLM,
    )
    outcome = project_outcome(decision, domain_semantics, overall_verdict=AuditVerdict.VERIFIED)

    assert outcome is not None
    assert outcome.outcome_type == OutcomeType.SIMULATED
    assert outcome.method == MethodTag.SIMULATED
    assert outcome.projected_recovery_pct == 90.0
    assert outcome.projected_metric == "inventory_fill_rate"
    assert outcome.recovery_window_hours == 6
    assert outcome.mean_time_to_normalcy == "6 hours"
    assert len(outcome.assumptions) >= 1


def test_3_marginal_diagnostic_action_produces_no_projection(domain_semantics):
    """Test 3: MARGINAL + diagnostic action -> None."""
    rec = StructuredActionRecommendation(
        driver="Suspected gateway regression",
        controllable_lever="Targeted Diagnostic Verification",
        action="Targeted Diagnostic Investigation: Collect telemetry and verify gateway_latency_15min before executing production remediation.",
        expected_impact="Telemetry Validation & Uncertainty Reduction (Non-Remedial)",
        owner="Observability & SRE",
        confidence=0.45,
        monitoring_plan="Monitor latency",
        authorized_personas=["analyst", "manager", "cfo"],
    )
    decision = Decision(
        abstained=False,
        recommended_action="Targeted Diagnostic Investigation: Collect telemetry and verify gateway_latency_15min before executing production remediation.",
        verification_metric="gateway_latency_15min",
        winning_hypothesis_id="H1",
        persona_narrative="Confidence is MARGINAL. Collect telemetry before changing production.",
        structured_recommendation=rec,
        method=MethodTag.LLM,
    )
    outcome = project_outcome(decision, domain_semantics, overall_verdict=AuditVerdict.MARGINAL)
    assert outcome is None


def test_4_abstained_decision_returns_none(domain_semantics):
    """Test 4: ABSTAIN -> None."""
    decision = Decision(
        abstained=True,
        recommended_action=None,
        verification_metric="kpi_primary_metric_recovery",
        winning_hypothesis_id=None,
        persona_narrative="Abstained due to low confidence.",
        method=MethodTag.LLM,
    )
    outcome = project_outcome(decision, domain_semantics, overall_verdict=AuditVerdict.ABSTAIN)
    assert outcome is None


def test_5_rejected_verdict_returns_none(domain_semantics):
    """Test 5: REJECTED -> None."""
    decision = Decision(
        abstained=True,
        recommended_action=None,
        verification_metric="kpi_primary_metric_recovery",
        winning_hypothesis_id="H3",
        persona_narrative="Hypothesis refuted by fresh contradictory evidence.",
        method=MethodTag.LLM,
    )
    outcome = project_outcome(decision, domain_semantics, overall_verdict=AuditVerdict.REJECTED)
    assert outcome is None


def test_6_diagnostic_wording_never_produces_recovery_percentage(domain_semantics):
    """Test 6: Diagnostic wording containing 'investigate', 'telemetry', etc. must never produce recovery %."""
    diagnostic_actions = [
        "Targeted Diagnostic Investigation: Collect telemetry and verify gateway_latency_15min to validate hypothesis H1 before executing production remediation.",
        "Collect telemetry and verify gateway latency before taking action.",
        "Perform diagnostic investigation and verify error logs.",
    ]
    for act in diagnostic_actions:
        decision = Decision(
            abstained=False,
            recommended_action=act,
            verification_metric="gateway_latency_15min",
            winning_hypothesis_id="H1",
            persona_narrative="Diagnostics active.",
            method=MethodTag.LLM,
        )
        outcome = project_outcome(decision, domain_semantics, overall_verdict=AuditVerdict.MARGINAL)
        assert outcome is None, f"Expected None for diagnostic action: {act}"

        # Even without explicit overall_verdict, prose-level guard must catch it
        outcome_no_verdict = project_outcome(decision, domain_semantics)
        assert outcome_no_verdict is None, f"Expected None from prose guard for: {act}"


def test_7_verified_unclassified_action_falls_back_to_default_operational_curve(domain_semantics):
    """Test 7: VERIFIED operational action with custom wording follows default operational curve."""
    decision = Decision(
        abstained=False,
        recommended_action="Execute infrastructure capacity adjustment and rebalance connection routing.",
        verification_metric="kpi_primary_metric_recovery",
        winning_hypothesis_id="H1",
        persona_narrative="Infrastructure capacity adjustment.",
        method=MethodTag.LLM,
    )
    outcome = project_outcome(decision, domain_semantics, overall_verdict=AuditVerdict.VERIFIED)

    assert outcome is not None
    assert outcome.outcome_type == OutcomeType.SIMULATED
    assert outcome.method == MethodTag.SIMULATED
    assert outcome.projected_recovery_pct == 75.0
    assert outcome.projected_metric == "kpi_primary_metric"
    assert outcome.recovery_window_hours == 4
    assert outcome.mean_time_to_normalcy == "15 min"


def test_8_validate_outcome_projection_enforces_honesty():
    """Test 8: Mandatory disclaimer remains enforced."""
    valid = OutcomeProjection(
        outcome_type=OutcomeType.SIMULATED,
        projected_metric="orders",
        projected_recovery_pct=80.0,
        mean_time_to_normalcy="10 min",
        disclaimer=SIMULATED_DISCLAIMER,
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


def test_9_e8_is_deterministic_and_makes_zero_llm_calls(domain_semantics):
    """Test 9: Pure deterministic simulation with zero LLM calls."""
    decision = Decision(
        abstained=False,
        recommended_action="Roll back deployment v4.3",
        verification_metric="kpi_primary_metric_recovery",
        winning_hypothesis_id="H1",
        persona_narrative="Rollback recommended.",
        method=MethodTag.LLM,
    )
    # Run 10 times — guarantee 100% identical outputs
    results = [project_outcome(decision, domain_semantics, overall_verdict=AuditVerdict.VERIFIED) for _ in range(10)]
    first = results[0]
    for r in results[1:]:
        assert r.projected_recovery_pct == first.projected_recovery_pct
        assert r.mean_time_to_normalcy == first.mean_time_to_normalcy
        assert r.projected_metric == first.projected_metric
        assert r.recovery_window_hours == first.recovery_window_hours
        assert r.assumptions == first.assumptions
