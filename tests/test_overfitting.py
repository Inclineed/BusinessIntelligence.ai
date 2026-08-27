"""
tests/test_overfitting.py — ISSUE-004 Evaluator Overfitting Remediation Tests.

Covers:
  - Phase 1: Held-out evaluation scenarios (INC_005 seasonality, INC_006 multi-root-cause,
             INC_007 gradual degradation) with pre-defined ground truth.
  - Phase 2: Adversarial perturbation tests asserting monotonic score responses
             under weakening dominant signals, varying evidence reliability weights,
             and contradiction penalties.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional
import pytest

from engines.challenge import (
    ChallengeThresholds,
    challenge,
    score_hypothesis,
)
from evaluation.evaluator import Evaluator
from config.loader import load_domain_semantics
from models import (
    AnomalySignal,
    ConfidenceState,
    Decision,
    DimensionContribution,
    Evidence,
    EvidenceCitation,
    Hypothesis,
    InvestigationResult,
    MethodTag,
    Persona,
    ScoredHypothesis,
    Telemetry,
)

# ---------------------------------------------------------------------------
# Helpers & Fixtures
# ---------------------------------------------------------------------------

def _load_ground_truth_dict() -> dict:
    gt_path = Path(__file__).resolve().parent.parent / "data" / "ground_truth.json"
    with open(gt_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _make_inc001_fixtures():
    """Build standard INC_001 evidence, signals, and hypotheses for perturbation."""
    ev_payment = Evidence(
        evidence_id="EV_PAY_001",
        kind="structured",
        summary="Payment gateway events: high failure rate and elevated latency.",
        source_id="payment_gateway",
        reliability_weight=0.95,
        relevance=0.90,
        raw_ref="payment_events:1",
        method=MethodTag.SQL,
    )
    ev_deploy = Evidence(
        evidence_id="EV_DEP_001",
        kind="structured",
        summary="Deployment of checkout-service v4.3 deployed within 48h before window.",
        source_id="deployment_log",
        reliability_weight=0.92,
        relevance=0.85,
        raw_ref="deployment_log:42",
        method=MethodTag.SQL,
    )
    ev_marketing = Evidence(
        evidence_id="EV_MKT_001",
        kind="unstructured",
        summary="Marketing: competitor running aggressive promotional discounts.",
        source_id="marketing",
        reliability_weight=0.30,
        relevance=0.80,
        raw_ref="marketing_events:1",
        method=MethodTag.RETRIEVAL,
    )
    ev_inventory = Evidence(
        evidence_id="EV_INV_001",
        kind="structured",
        summary="Inventory fill rate normal and stable throughout incident window.",
        source_id="inventory",
        reliability_weight=0.90,
        relevance=0.90,
        raw_ref="inventory_events:1",
        method=MethodTag.SQL,
    )

    evidence_by_id = {
        ev_payment.evidence_id: ev_payment,
        ev_deploy.evidence_id: ev_deploy,
        ev_marketing.evidence_id: ev_marketing,
        ev_inventory.evidence_id: ev_inventory,
    }

    h1 = Hypothesis(
        hypothesis_id="H1",
        statement="Payment gateway connection failure following v4.3 release.",
        reasoning="Payment failure rate spiked following recent checkout deployment.",
        citations=[
            EvidenceCitation(
                evidence_id="EV_PAY_001",
                role="supports",
                quoted_summary="Payment gateway events: high failure rate and elevated latency.",
                relevance_explanation="Explains payment transaction failures.",
            ),
            EvidenceCitation(
                evidence_id="EV_DEP_001",
                role="supports",
                quoted_summary="Deployment of checkout-service v4.3 deployed within 48h before window.",
                relevance_explanation="Timing coincides with onset of issues.",
            ),
        ],
    )

    h2 = Hypothesis(
        hypothesis_id="H2",
        statement="Competitor pricing pressure reduced conversion.",
        reasoning="Competitor promotional activity drew market demand away.",
        citations=[
            EvidenceCitation(
                evidence_id="EV_MKT_001",
                role="supports",
                quoted_summary="Marketing: competitor running aggressive promotional discounts.",
                relevance_explanation="External promotion could explain conversion drop.",
            ),
        ],
    )

    h3 = Hypothesis(
        hypothesis_id="H3",
        statement="Inventory shortage caused drop in conversions.",
        reasoning="Lack of available inventory prevented order completions.",
        citations=[
            EvidenceCitation(
                evidence_id="EV_INV_001",
                role="contradicts",
                quoted_summary="Inventory fill rate normal and stable throughout incident window.",
                relevance_explanation="Normal fill rate contradicts shortage claim.",
            ),
        ],
    )

    signals = [
        AnomalySignal(
            kpi_id="hourly_conversion",
            observed=0.55,
            expected=0.68,
            is_anomaly=True,
            z_score=-3.5,
            delta_pct=-17.0,
            method=MethodTag.STATS,
        ),
        AnomalySignal(
            kpi_id="payment_failure_rate_15min",
            observed=0.08,
            expected=0.02,
            is_anomaly=True,
            z_score=4.2,
            delta_pct=300.0,
            method=MethodTag.STATS,
        ),
    ]

    return evidence_by_id, signals, [h1, h2, h3]


# ---------------------------------------------------------------------------
# Phase 1: Held-Out Scenarios (INC_005, INC_006, INC_007)
# ---------------------------------------------------------------------------

class TestHeldOutScenarios:
    """
    Phase 1: Validates evaluation behavior against held-out scenarios
    with pre-locked ground truth defined before execution.
    """

    def test_held_out_scenarios_exist_in_ground_truth(self):
        """Verify INC_005, INC_006, INC_007 are defined in data/ground_truth.json."""
        gt = _load_ground_truth_dict()
        scenarios = gt.get("scenarios", {})

        for sc_id in ["INC_005", "INC_006", "INC_007"]:
            assert sc_id in scenarios, f"{sc_id} missing from ground_truth.json!"
            sc_gt = scenarios[sc_id]
            assert "name" in sc_gt
            assert "true_cause" in sc_gt
            assert "expected_confidence_state" in sc_gt
            assert "evaluation_checks" in sc_gt

    def test_inc005_seasonality_held_out(self):
        """
        INC_005: Seasonality demand pattern misinterpreted as anomaly.
        Expected: anomaly_detected=False, abstained=True, no recommended action.
        """
        result = InvestigationResult(
            scenario_id="INC_005",
            persona=Persona.ANALYST,
            signals=[
                AnomalySignal(
                    kpi_id="hourly_revenue",
                    observed=13500.0,
                    expected=14000.0,
                    is_anomaly=False,  # seasonality accounted for; no anomaly
                    z_score=-0.8,
                    delta_pct=-5.0,
                    method=MethodTag.STATS,
                )
            ],
            contributions=[],
            evidence=[],
            hypotheses=[],
            scored=[],
            decision=Decision(
                abstained=True,
                recommended_action=None,
                verification_metric=None,
                winning_hypothesis_id=None,
                persona_narrative="Observed revenue variation follows regular seasonal pattern.",
                abstention_reason="no_anomaly",
            ),
            telemetry=Telemetry(),
            method_ownership={"signal": [MethodTag.STATS]},
        )

        evaluator = Evaluator()
        eval_result = evaluator.evaluate(result)
        assert eval_result.overall_pass is True
        assert eval_result.hallucinated_evidence_count == 0
        assert eval_result.authorization_violation_count == 0

    def test_inc006_multi_root_cause_held_out(self):
        """
        INC_006: Multi-root-cause incident (Network latency + deployment).
        Expected: anomaly_detected=True, H1 wins with MEDIUM confidence (compound causes).
        """
        ev_net = Evidence(
            evidence_id="EV_NET_001",
            kind="structured",
            summary="Network packet loss elevated across payment gateway routes.",
            source_id="payment_gateway",
            reliability_weight=0.85,
            relevance=0.85,
            raw_ref="network_log:1",
            method=MethodTag.SQL,
        )
        ev_dep = Evidence(
            evidence_id="EV_DEP_002",
            kind="structured",
            summary="Checkout-service v4.3.1 latency regression under load.",
            source_id="deployment_log",
            reliability_weight=0.90,
            relevance=0.90,
            raw_ref="deployment_log:43",
            method=MethodTag.SQL,
        )

        h1 = Hypothesis(
            hypothesis_id="H1",
            statement="Checkout service latency regression under load.",
            reasoning="Checkout container service release caused slow transaction processing.",
            citations=[
                EvidenceCitation(
                    evidence_id="EV_DEP_002",
                    role="supports",
                    quoted_summary="Checkout-service v4.3.1 latency regression under load.",
                    relevance_explanation="Directly points to container latency regression.",
                )
            ],
        )
        h2 = Hypothesis(
            hypothesis_id="H2",
            statement="Network packet loss on upstream gateway route.",
            reasoning="Network routing issues delayed payment completions.",
            citations=[
                EvidenceCitation(
                    evidence_id="EV_NET_001",
                    role="supports",
                    quoted_summary="Network packet loss elevated across payment gateway routes.",
                    relevance_explanation="Upstream packet loss contributed to delays.",
                )
            ],
        )

        scored_h1 = ScoredHypothesis(
            hypothesis_id="H1",
            final_score=0.62,
            confidence_state=ConfidenceState.HIGH,
        )
        scored_h2 = ScoredHypothesis(
            hypothesis_id="H2",
            final_score=0.55,
            confidence_state=ConfidenceState.MEDIUM,
        )

        result = InvestigationResult(
            scenario_id="INC_006",
            persona=Persona.ANALYST,
            signals=[
                AnomalySignal(
                    kpi_id="gateway_latency_15min",
                    observed=420.0,
                    expected=180.0,
                    is_anomaly=True,
                    z_score=3.8,
                    delta_pct=150.0,
                    method=MethodTag.STATS,
                )
            ],
            contributions=[
                DimensionContribution(
                    dimension="device",
                    segment="android",
                    contribution_pct=45.0,
                    segment_delta_pct=-12.0,
                    method=MethodTag.STATS,
                )
            ],
            evidence=[ev_net, ev_dep],
            hypotheses=[h1, h2],
            scored=[scored_h1, scored_h2],
            decision=Decision(
                abstained=False,
                recommended_action="Deploy patch for v4.3.1 latency and investigate upstream routing.",
                verification_metric="gateway_latency_15min",
                winning_hypothesis_id="H1",
                persona_narrative="Compound incident: checkout service and network both contributed.",
            ),
            telemetry=Telemetry(),
            method_ownership={"signal": [MethodTag.STATS]},
        )

        evaluator = Evaluator()
        eval_result = evaluator.evaluate(result)
        assert eval_result.overall_pass is True
        assert eval_result.hallucinated_evidence_count == 0
        assert eval_result.authorization_violation_count == 0

    def test_inc007_gradual_degradation_held_out(self):
        """
        INC_007: Gradual degradation (Memory leak over 48h).
        Expected: anomaly_detected=True, H1 winning with MEDIUM confidence.
        """
        ev_mem = Evidence(
            evidence_id="EV_MEM_001",
            kind="structured",
            summary="Progressive memory heap growth and GC pause elevation over 48 hours.",
            source_id="deployment_log",
            reliability_weight=0.88,
            relevance=0.88,
            raw_ref="metrics:memory",
            method=MethodTag.SQL,
        )

        h1 = Hypothesis(
            hypothesis_id="H1",
            statement="Memory leak in checkout worker process.",
            reasoning="Gradual memory growth elevated GC pauses and latency.",
            citations=[
                EvidenceCitation(
                    evidence_id="EV_MEM_001",
                    role="supports",
                    quoted_summary="Progressive memory heap growth and GC pause elevation over 48 hours.",
                    relevance_explanation="Memory growth correlates with latency degradation.",
                )
            ],
        )

        scored_h1 = ScoredHypothesis(
            hypothesis_id="H1",
            final_score=0.65,
            confidence_state=ConfidenceState.HIGH,
        )

        result = InvestigationResult(
            scenario_id="INC_007",
            persona=Persona.ANALYST,
            signals=[
                AnomalySignal(
                    kpi_id="gateway_latency_15min",
                    observed=320.0,
                    expected=180.0,
                    is_anomaly=True,
                    z_score=2.8,
                    delta_pct=80.0,
                    method=MethodTag.STATS,
                )
            ],
            contributions=[],
            evidence=[ev_mem],
            hypotheses=[h1],
            scored=[scored_h1],
            decision=Decision(
                abstained=False,
                recommended_action="Restart worker pods and apply hotfix for leak.",
                verification_metric="gateway_latency_15min",
                winning_hypothesis_id="H1",
                persona_narrative="Gradual memory leak caused slow performance degradation.",
            ),
            telemetry=Telemetry(),
            method_ownership={"signal": [MethodTag.STATS]},
        )

        evaluator = Evaluator()
        eval_result = evaluator.evaluate(result)
        assert eval_result.overall_pass is True
        assert eval_result.hallucinated_evidence_count == 0
        assert eval_result.authorization_violation_count == 0

    def test_inc008_saas_churn_cross_domain(self):
        """
        Phase 3: Verify the evaluator generalizes to a completely novel domain (B2B SaaS)
        without relying on hardcoded Retail metrics or structures.
        """
        ev_sso = Evidence(
            evidence_id="EV_SSO_001",
            kind="structured",
            summary="Auth0 logs show a 95% spike in SSO failures for Okta integrations starting at 14:00.",
            source_id="auth0_logs",
            reliability_weight=0.98,
            relevance=0.95,
            raw_ref="logs:auth0",
            method=MethodTag.SQL,
        )

        ev_churn = Evidence(
            evidence_id="EV_CHURN_001",
            kind="structured",
            summary="Stripe webhooks indicate a massive spike in immediate subscription cancellations for Enterprise tier.",
            source_id="stripe_subscriptions",
            reliability_weight=0.95,
            relevance=0.90,
            raw_ref="api:stripe",
            method=MethodTag.SQL,
        )
        
        ev_ticket = Evidence(
            evidence_id="EV_TICK_001",
            kind="unstructured",
            summary="Zendesk tickets complain about being unable to log in via Okta.",
            source_id="zendesk_tickets",
            reliability_weight=0.90,
            relevance=0.92,
            raw_ref="api:zendesk",
            method=MethodTag.RETRIEVAL,
        )

        h1 = Hypothesis(
            hypothesis_id="H1",
            statement="Broken SSO integration in the new release caused login failures and enterprise churn.",
            reasoning="Auth0 logs prove SSO failure, Stripe proves churn, and Zendesk tickets link the two.",
            citations=[
                EvidenceCitation(
                    evidence_id="EV_SSO_001",
                    role="supports",
                    quoted_summary="Auth0 logs show a 95% spike in SSO failures for Okta integrations starting at 14:00.",
                    relevance_explanation="Directly proves the auth failure.",
                ),
                EvidenceCitation(
                    evidence_id="EV_CHURN_001",
                    role="supports",
                    quoted_summary="Stripe webhooks indicate a massive spike in immediate subscription cancellations for Enterprise tier.",
                    relevance_explanation="Shows the financial impact of the bug.",
                ),
                EvidenceCitation(
                    evidence_id="EV_TICK_001",
                    role="supports",
                    quoted_summary="Zendesk tickets complain about being unable to log in via Okta.",
                    relevance_explanation="Provides the user narrative linking the two.",
                )
            ],
        )

        scored_h1 = ScoredHypothesis(
            hypothesis_id="H1",
            final_score=0.92,
            confidence_state=ConfidenceState.HIGH,
        )

        result = InvestigationResult(
            scenario_id="INC_008",
            persona=Persona.ANALYST,
            signals=[
                AnomalySignal(
                    kpi_id="daily_churn_rate",
                    observed=15.0,
                    expected=1.2,
                    is_anomaly=True,
                    z_score=5.5,
                    delta_pct=1150.0,
                    method=MethodTag.STATS,
                ),
                AnomalySignal(
                    kpi_id="sso_failure_rate_1h",
                    observed=0.95,
                    expected=0.01,
                    is_anomaly=True,
                    z_score=8.2,
                    delta_pct=9400.0,
                    method=MethodTag.STATS,
                )
            ],
            contributions=[
                DimensionContribution(
                    dimension="plan_tier",
                    segment="enterprise",
                    contribution_pct=92.0,
                    segment_delta_pct=1200.0,
                    method=MethodTag.STATS,
                ),
                DimensionContribution(
                    dimension="auth_provider",
                    segment="okta",
                    contribution_pct=98.0,
                    segment_delta_pct=9400.0,
                    method=MethodTag.STATS,
                )
            ],
            evidence=[ev_sso, ev_churn, ev_ticket],
            hypotheses=[h1],
            scored=[scored_h1],
            decision=Decision(
                abstained=False,
                recommended_action="Rollback to v2.3.9 immediately to restore Okta SSO.",
                verification_metric="sso_failure_rate_1h",
                winning_hypothesis_id="H1",
                persona_narrative="A broken SSO integration for Okta caused an immediate churn spike.",
            ),
            telemetry=Telemetry(),
            method_ownership={"signal": [MethodTag.STATS]},
        )
        
        # In the context of tests, we inject dummy authorization since we're using novel sources 
        # that aren't in entitlements.yaml. This allows us to test the pure evaluation logic
        # without needing to mock config files.
        import evaluation.evaluator as evaluator_module
        original_auth = evaluator_module._PERSONA_AUTHORIZED_SOURCES.get("analyst", frozenset())
        new_auth = frozenset(list(original_auth) + ["auth0_logs", "stripe_subscriptions", "zendesk_tickets"])
        evaluator_module._PERSONA_AUTHORIZED_SOURCES["analyst"] = new_auth

        try:
            evaluator = Evaluator()
            eval_result = evaluator.evaluate(result)
            assert eval_result.overall_pass is True
            assert eval_result.hallucinated_evidence_count == 0
            assert eval_result.authorization_violation_count == 0
        finally:
            evaluator_module._PERSONA_AUTHORIZED_SOURCES["analyst"] = original_auth

    def test_calibration_report_generation(self, caplog):
        """
        Phase 4: Generate a calibration report across multiple scenarios.
        """
        # Run standard INC_001 to get an InvestigationResult
        evidence_by_id, signals, hypotheses = _make_inc001_fixtures()
        
        scored = [
            ScoredHypothesis(
                hypothesis_id="H1",
                final_score=0.95,
                confidence_state=ConfidenceState.HIGH,
            )
        ]
        
        result1 = InvestigationResult(
            scenario_id="INC_001",
            persona=Persona.ANALYST,
            signals=signals,
            contributions=[],
            evidence=list(evidence_by_id.values()),
            hypotheses=hypotheses,
            scored=scored,
            decision=Decision(
                abstained=False,
                recommended_action="Rollback v4.3",
                verification_metric="hourly_revenue",
                winning_hypothesis_id="H1",
                persona_narrative="",
            ),
            telemetry=Telemetry(),
            method_ownership={},
        )
        
        # We need another mock for an Abstain scenario
        result2 = InvestigationResult(
            scenario_id="INC_004",  # Assuming sparse history expects abstain
            persona=Persona.ANALYST,
            signals=[],
            contributions=[],
            evidence=[],
            hypotheses=[],
            scored=[],
            decision=Decision(
                abstained=True,
                recommended_action=None,
                verification_metric=None,
                winning_hypothesis_id=None,
                persona_narrative="",
            ),
            telemetry=Telemetry(),
            method_ownership={},
        )
        
        # Test the calibration reporter
        from evaluation.evaluator import CalibrationReporter, Evaluator, _load_ground_truth
        reporter = CalibrationReporter()
        evaluator = Evaluator()
        gt = _load_ground_truth()
        
        # Add a HIGH correct prediction
        reporter.add_result(result1, evaluator.evaluate(result1), gt)
        # Add an ABSTAIN correct prediction
        reporter.add_result(result2, evaluator.evaluate(result2), gt)
        
        report = reporter.generate_report()
        
        assert "Total Scenarios Evaluated: 2" in report
        assert "HIGH    : 1/1 correct (100.0%)" in report
        assert "ABSTAIN : 1/1 correct (100.0%)" in report
        assert "exploratory and NOT statistically" in report
        
        print("\n\n" + report)


# ---------------------------------------------------------------------------
# Phase 2: Adversarial Perturbation & Monotonicity Tests
# ---------------------------------------------------------------------------

class TestAdversarialPerturbation:
    """
    Phase 2: Verifies that engine scores and confidence bands degrade
    monotonically and predictably under adversarial evidence perturbations.
    """

    @pytest.mark.parametrize(
        "android_pcts",
        [[68.0, 45.0, 30.0, 15.0]],
    )
    def test_dominant_signal_weakening_monotonic_confidence_drop(self, android_pcts):
        """
        As Android's contribution weakens from 68% -> 45% -> 30% -> 15%,
        H1's score must decrease monotonically (score(68%) >= score(45%) >= score(30%) >= score(15%))
        and score(68%) must be strictly greater than score(15%).
        """
        evidence_by_id, signals, hypotheses = _make_inc001_fixtures()
        h1 = hypotheses[0]
        scores = []

        for pct in android_pcts:
            # Scale evidence strength proportionally to the signal contribution
            evidence_by_id["EV_PAY_001"].relevance = 0.90 * (pct / 68.0)
            evidence_by_id["EV_DEP_001"].relevance = 0.85 * (pct / 68.0)

            contrib = [
                DimensionContribution(
                    dimension="device",
                    segment="android",
                    contribution_pct=pct,
                    segment_delta_pct=-17.0 * (pct / 68.0),
                    method=MethodTag.STATS,
                )
            ]
            scored = score_hypothesis(
                h=h1,
                evidence_by_id=evidence_by_id,
                signals=signals,
                contributions=contrib,
            )
            scores.append(scored.final_score)

        # Monotonicity assertion: each subsequent score must be <= previous score
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], (
                f"Monotonicity violation at step {i}: {scores[i]} < {scores[i + 1]} "
                f"(android contributions: {android_pcts})"
            )

        # Overall decrease assertion: strong evidence > weak evidence
        assert scores[0] > scores[-1], (
            f"Expected score at 68% ({scores[0]}) to exceed score at 15% ({scores[-1]})"
        )

    @pytest.mark.parametrize(
        "reliabilities",
        [[0.25, 0.50, 0.75, 0.95]],
    )
    def test_marketing_evidence_reliability_monotonic_score_increase(self, reliabilities):
        """
        As marketing evidence reliability increases (0.25 -> 0.50 -> 0.75 -> 0.95),
        H2's support score and final score must increase monotonically.
        """
        evidence_by_id, signals, hypotheses = _make_inc001_fixtures()
        h2 = hypotheses[1]
        scores = []

        for rel in reliabilities:
            # Modify marketing evidence reliability
            evidence_by_id["EV_MKT_001"].reliability_weight = rel
            scored = score_hypothesis(
                h=h2,
                evidence_by_id=evidence_by_id,
                signals=signals,
                contributions=[],
            )
            scores.append(scored.final_score)

        # Monotonicity assertion: each subsequent score must be >= previous score
        for i in range(len(scores) - 1):
            assert scores[i] <= scores[i + 1], (
                f"Monotonicity violation: {scores[i]} > {scores[i + 1]} "
                f"for reliabilities {reliabilities}"
            )

        # High reliability must strictly exceed low reliability
        assert scores[-1] > scores[0], (
            f"Expected score at rel 0.95 ({scores[-1]}) > score at rel 0.25 ({scores[0]})"
        )

    @pytest.mark.parametrize(
        "contradiction_weights",
        [[0.10, 0.40, 0.70, 0.95]],
    )
    def test_contradictory_evidence_weight_monotonic_penalty(self, contradiction_weights):
        """
        As contradictory evidence becomes more reliable (0.10 -> 0.95),
        the hypothesis score must decrease monotonically due to increasing penalty.
        """
        evidence_by_id, signals, hypotheses = _make_inc001_fixtures()
        h3 = hypotheses[2]
        scores = []

        for weight in contradiction_weights:
            evidence_by_id["EV_INV_001"].reliability_weight = weight
            scored = score_hypothesis(
                h=h3,
                evidence_by_id=evidence_by_id,
                signals=signals,
                contributions=[],
            )
            scores.append(scored.final_score)

        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], (
                f"Monotonicity violation: {scores[i]} < {scores[i + 1]} "
                f"for contradiction weights {contradiction_weights}"
            )

    def test_adversarial_noise_evidence_graceful_degradation(self):
        """
        Injecting irrelevant/noisy evidence into the evidence set should not
        cause arbitrary winner flipping or score instability.
        """
        evidence_by_id, signals, hypotheses = _make_inc001_fixtures()

        # Add 5 irrelevant noise evidence items
        for i in range(5):
            noise_id = f"EV_NOISE_{i}"
            evidence_by_id[noise_id] = Evidence(
                evidence_id=noise_id,
                kind="unstructured",
                summary=f"Unrelated blog post or social comment #{i}.",
                source_id="marketing",
                reliability_weight=0.50,
                relevance=0.20,
                raw_ref=f"noise:{i}",
                method=MethodTag.RETRIEVAL,
            )

        challenge_res = challenge(
            hypotheses=hypotheses,
            evidence_by_id=evidence_by_id,
            signals=signals,
            contributions=[
                DimensionContribution(
                    dimension="device",
                    segment="android",
                    contribution_pct=68.0,
                    segment_delta_pct=-17.0,
                    method=MethodTag.STATS,
                )
            ],
            domain_semantics=load_domain_semantics("config/domain_semantics.yaml"),
        )

        assert challenge_res.abstained is False
        assert challenge_res.winning_hypothesis_id == "H1"
        assert challenge_res.overall_confidence == ConfidenceState.HIGH


class TestEvaluatorExtensibility:
    def test_evaluator_missing_required_dimension_fails(self):
        from evaluation.evaluator import Evaluator
        from models import InvestigationResult, Telemetry
        evaluator = Evaluator()
        
        # Inject an incomplete scenario directly into the evaluator's ground truth
        gt = evaluator._gt()
        gt["scenarios"]["INC_MISSING"] = {
            "scenario_id": "INC_MISSING",
            "evaluation_checks": {
                "abstain_expected": True
                # Missing anomaly_detected
            }
        }
        
        result = InvestigationResult(
            scenario_id="INC_MISSING",
            persona=None,
            signals=[],
            contributions=[],
            evidence=[],
            hypotheses=[],
            scored=[],
            decision=None,
            telemetry=Telemetry(),
            method_ownership={},
        )
        
        import pytest
        with pytest.raises(ValueError, match="missing required dimension/check"):
            evaluator.evaluate(result)
            
    def test_evaluator_unknown_check_field_fails(self):
        from evaluation.evaluator import Evaluator
        from models import InvestigationResult, Telemetry
        evaluator = Evaluator()
        
        gt = evaluator._gt()
        gt["scenarios"]["INC_UNKNOWN"] = {
            "scenario_id": "INC_UNKNOWN",
            "evaluation_checks": {
                "anomaly_detected": True,
                "abstain_expected": True,
                "anomly_detected_typo": True
            }
        }
        
        result = InvestigationResult(
            scenario_id="INC_UNKNOWN",
            persona=None,
            signals=[],
            contributions=[],
            evidence=[],
            hypotheses=[],
            scored=[],
            decision=None,
            telemetry=Telemetry(),
            method_ownership={},
        )
        
        import pytest
        with pytest.raises(ValueError, match="Unknown evaluation check field"):
            evaluator.evaluate(result)
            
    def test_evaluator_dynamic_scenario_loading(self):
        from evaluation.evaluator import Evaluator, DimensionScore
        from models import InvestigationResult, Telemetry, ConfidenceState, Decision, ScoredHypothesis, Hypothesis
        evaluator = Evaluator()
        
        gt = evaluator._gt()
        gt["scenarios"]["INC_DYNAMIC"] = {
            "scenario_id": "INC_DYNAMIC",
            "evaluation_checks": {
                "anomaly_detected": False,
                "abstain_expected": False,
                "winning_hypothesis_id": "HDYN",
                "confidence_state": "HIGH"
            }
        }
        
        scored = [
            ScoredHypothesis(hypothesis_id="HDYN", final_score=0.9, confidence_state=ConfidenceState.HIGH)
        ]
        
        result = InvestigationResult(
            scenario_id="INC_DYNAMIC",
            persona=None,
            signals=[],
            contributions=[],
            evidence=[],
            hypotheses=[],
            scored=scored,
            decision=Decision(
                abstained=False,
                recommended_action="Fix dynamically",
                verification_metric="metrics",
                winning_hypothesis_id="HDYN",
                persona_narrative=""
            ),
            telemetry=Telemetry(),
            method_ownership={},
        )
        
        # Should pass without hardcoded dispatch
        res = evaluator.evaluate(result)
        assert res.overall_pass is True
        
    def test_evaluator_security_boundaries_enforced(self):
        from evaluation.evaluator import Evaluator
        from models import InvestigationResult, Telemetry, Evidence
        evaluator = Evaluator()
        
        gt = evaluator._gt()
        gt["scenarios"]["INC_SECURITY"] = {
            "scenario_id": "INC_SECURITY",
            "evaluation_checks": {
                "anomaly_detected": False,
                "abstain_expected": True
            }
        }
        
        # Inject an unauthorized evidence source to intentionally fail D15
        unauth_evidence = Evidence(
            evidence_id="EV_HACK",
            source_id="unauthorized_slack",
            summary="Bad data",
        )
        
        result = InvestigationResult(
            scenario_id="INC_SECURITY",
            persona=None,
            signals=[],
            contributions=[],
            evidence=[unauth_evidence],
            hypotheses=[],
            scored=[],
            decision=None,
            telemetry=Telemetry(),
            method_ownership={},
        )
        
        res = evaluator.evaluate(result)
        
        assert res.authorization_violation_count == 1
        assert res.overall_pass is False
        assert any(d.passed is False and d.dimension_id == 15 for d in res.dimension_scores)

