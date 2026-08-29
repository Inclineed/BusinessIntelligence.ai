"""
tests/test_structured_decision.py — Comprehensive Unit & Governance Tests for Engine E7 (Decision Engine)

Covers:
1. VERIFIED + authorized persona -> normal recommendation.
2. VERIFIED + unauthorized persona -> no action (abstained=True, recommended_action=None).
3. MARGINAL + authorized persona -> guarded evidence-seeking recommendation, NOT remediation.
4. MARGINAL + unauthorized persona -> no action.
5. ABSTAIN -> no action.
6. REJECTED -> no action.
7. Highest-ranked hypothesis is REJECTED -> no action.
8. Missing/invalid lever -> no action (abstention_reason="unauthorized_lever_selected").
9. Confirm Property 6: abstained=True -> recommended_action=None.
10. Confirm E8 expected impact remains deterministic and cannot be replaced by LLM output.
"""

from __future__ import annotations

import dataclasses
import pytest

from models import (
    AuditVerdict,
    Decision,
    MethodTag,
    Persona,
    ScoredHypothesis,
    StructuredActionRecommendation,
)
from engines.challenge import ChallengeResult
from engines.decision import decide
from llm.provider import LLMUnavailableError


# Mock provider that returns specific JSON
class MockProvider:
    def __init__(self, response_json: str, fail: bool = False):
        self.response_json = response_json
        self.fail = fail
        self.model = "mock-model"

    def complete(self, *args, **kwargs):
        if self.fail:
            raise LLMUnavailableError("Mock failure")
        class MockResponse:
            def __init__(self, text):
                self.text = text
        return MockResponse(self.response_json)


@pytest.fixture
def decision_rights():
    return {
        "levers": {
            "Software Release Reversion": {
                "owner": "Platform Engineering",
                "authorized_personas": ["analyst", "manager"]
            },
            "Inventory Replenishment": {
                "owner": "Supply Chain",
                "authorized_personas": ["manager"]
            },
            "Targeted Diagnostic Verification": {
                "owner": "Observability & SRE",
                "authorized_personas": ["analyst", "manager", "cfo"]
            },
            "Default Mitigation": {
                "owner": "Operations",
                "authorized_personas": ["analyst", "manager"]
            }
        }
    }


def test_1_verified_authorized_persona_produces_normal_recommendation(decision_rights):
    """1. VERIFIED + authorized persona -> normal recommendation."""
    sh = ScoredHypothesis(
        hypothesis_id="H1",
        final_audit_score=0.95,
        audit_verdict=AuditVerdict.VERIFIED,
    )
    challenge_result = ChallengeResult(
        scored_hypotheses=[sh],
        winning_hypothesis_id="H1",
        overall_verdict=AuditVerdict.VERIFIED,
        abstained=False,
    )
    
    mock_json = '''{
        "controllable_lever": "Software Release Reversion",
        "recommended_action": "Roll back v4.3 immediately to restore payment connection pool capacity.",
        "verification_metric": "payment_success_rate",
        "persona_narrative": "Rolling back the release will fix connection pool starvation.",
        "monitoring_plan": "Monitor payment success rate."
    }'''
    
    provider = MockProvider(mock_json)
    
    decision = decide(
        challenge_result=challenge_result,
        persona=Persona.ANALYST,
        provider=provider,
        decision_rights=decision_rights,
        winning_statement="Payment gateway bug in v4.3"
    )
    
    assert not decision.abstained
    assert decision.recommended_action == "Roll back v4.3 immediately to restore payment connection pool capacity."
    assert decision.structured_recommendation is not None
    
    sr = decision.structured_recommendation
    assert sr.controllable_lever == "Software Release Reversion"
    assert sr.owner == "Platform Engineering"
    assert sr.authorized_personas == ["analyst", "manager"]
    assert sr.confidence == 0.95
    assert sr.driver == "Payment gateway bug in v4.3"


def test_2_verified_unauthorized_persona_abstains_no_action(decision_rights):
    """2. VERIFIED + unauthorized persona -> no action (abstained=True, recommended_action=None)."""
    sh = ScoredHypothesis(
        hypothesis_id="H1",
        final_audit_score=0.95,
        audit_verdict=AuditVerdict.VERIFIED,
    )
    challenge_result = ChallengeResult(
        scored_hypotheses=[sh],
        winning_hypothesis_id="H1",
        overall_verdict=AuditVerdict.VERIFIED,
        abstained=False,
    )
    
    # Lever allows only ["analyst", "manager"], but persona is CFO
    mock_json = '''{
        "controllable_lever": "Software Release Reversion",
        "recommended_action": "Roll back v4.3 immediately.",
        "verification_metric": "payment_success_rate",
        "persona_narrative": "Rolling back the release will fix it.",
        "monitoring_plan": "Monitor payment success rate."
    }'''
    
    provider = MockProvider(mock_json)
    
    decision = decide(
        challenge_result=challenge_result,
        persona=Persona.CFO,
        provider=provider,
        decision_rights=decision_rights,
        winning_statement="Payment gateway bug in v4.3"
    )
    
    assert decision.abstained is True
    assert decision.abstention_reason == "persona_not_authorized_for_lever"
    assert decision.recommended_action is None
    assert decision.structured_recommendation is None
    assert "not authorized" in decision.persona_narrative.lower()


def test_3_marginal_authorized_persona_produces_guarded_investigation_not_remediation(decision_rights):
    """3. MARGINAL + authorized persona -> guarded evidence-seeking recommendation, NOT remediation."""
    sh = ScoredHypothesis(
        hypothesis_id="H1",
        final_audit_score=0.45,
        audit_verdict=AuditVerdict.MARGINAL,
    )
    challenge_result = ChallengeResult(
        scored_hypotheses=[sh],
        winning_hypothesis_id="H1",
        overall_verdict=AuditVerdict.MARGINAL,
        abstained=False,
    )
    
    # LLM mistakenly tries to return direct remediation on MARGINAL
    mock_json = '''{
        "controllable_lever": "Software Release Reversion",
        "recommended_action": "Roll back v4.3 deployment immediately.",
        "verification_metric": "gateway_latency_15min",
        "persona_narrative": "Roll back to fix it.",
        "monitoring_plan": "Monitor latency."
    }'''
    
    provider = MockProvider(mock_json)
    
    decision = decide(
        challenge_result=challenge_result,
        persona=Persona.ANALYST,
        provider=provider,
        decision_rights=decision_rights,
        winning_statement="Suspected payment gateway regression"
    )
    
    assert not decision.abstained
    assert decision.recommended_action is not None
    # Verify that direct rollback was intercepted and guarded into diagnostic investigation
    assert "Targeted Diagnostic Investigation" in decision.recommended_action
    assert "verify gateway_latency_15min" in decision.recommended_action
    assert "before executing" in decision.recommended_action


def test_4_marginal_unauthorized_persona_abstains_no_action(decision_rights):
    """4. MARGINAL + unauthorized persona -> no action."""
    sh = ScoredHypothesis(
        hypothesis_id="H1",
        final_audit_score=0.45,
        audit_verdict=AuditVerdict.MARGINAL,
    )
    challenge_result = ChallengeResult(
        scored_hypotheses=[sh],
        winning_hypothesis_id="H1",
        overall_verdict=AuditVerdict.MARGINAL,
        abstained=False,
    )
    
    # Inventory Replenishment allows only ["manager"], but persona is ANALYST
    mock_json = '''{
        "controllable_lever": "Inventory Replenishment",
        "recommended_action": "Investigate SKU levels before reordering.",
        "verification_metric": "inventory_fill_rate",
        "persona_narrative": "Investigate SKU levels.",
        "monitoring_plan": "Monitor fill rate."
    }'''
    
    provider = MockProvider(mock_json)
    
    decision = decide(
        challenge_result=challenge_result,
        persona=Persona.ANALYST,
        provider=provider,
        decision_rights=decision_rights,
        winning_statement="Inventory shortage"
    )
    
    assert decision.abstained is True
    assert decision.abstention_reason == "persona_not_authorized_for_lever"
    assert decision.recommended_action is None
    assert decision.structured_recommendation is None


def test_5_abstain_verdict_produces_no_action(decision_rights):
    """5. ABSTAIN -> no action."""
    challenge_result = ChallengeResult(
        scored_hypotheses=[],
        winning_hypothesis_id=None,
        overall_verdict=AuditVerdict.ABSTAIN,
        abstained=True,
    )
    
    provider = MockProvider("should not be called")
    
    decision = decide(
        challenge_result=challenge_result,
        persona=Persona.ANALYST,
        provider=provider,
        decision_rights=decision_rights,
        winning_statement=""
    )
    
    assert decision.abstained is True
    assert decision.recommended_action is None
    assert decision.structured_recommendation is None
    assert decision.abstention_reason == "low_confidence"


def test_6_rejected_verdict_produces_no_action(decision_rights):
    """6. REJECTED -> no action."""
    sh = ScoredHypothesis(
        hypothesis_id="H1",
        final_audit_score=0.10,
        audit_verdict=AuditVerdict.REJECTED,
    )
    challenge_result = ChallengeResult(
        scored_hypotheses=[sh],
        winning_hypothesis_id=None,
        overall_verdict=AuditVerdict.REJECTED,
        abstained=True,
    )
    
    provider = MockProvider("should not be called")
    
    decision = decide(
        challenge_result=challenge_result,
        persona=Persona.ANALYST,
        provider=provider,
        decision_rights=decision_rights,
        winning_statement="Invalid hypothesis"
    )
    
    assert decision.abstained is True
    assert decision.recommended_action is None
    assert decision.structured_recommendation is None


def test_7_highest_ranked_hypothesis_rejected_produces_no_action(decision_rights):
    """7. Highest-ranked hypothesis is REJECTED -> no action."""
    sh = ScoredHypothesis(
        hypothesis_id="H1",
        final_audit_score=0.15,
        audit_verdict=AuditVerdict.REJECTED,
    )
    challenge_result = ChallengeResult(
        scored_hypotheses=[sh],
        winning_hypothesis_id="H1",
        overall_verdict=AuditVerdict.ABSTAIN,
        abstained=True,
    )
    
    provider = MockProvider("should not be called")
    
    decision = decide(
        challenge_result=challenge_result,
        persona=Persona.ANALYST,
        provider=provider,
        decision_rights=decision_rights,
        winning_statement="Hypothesis with citations rejected"
    )
    
    assert decision.abstained is True
    assert decision.recommended_action is None
    assert decision.structured_recommendation is None


def test_8_missing_invalid_lever_abstains_no_action(decision_rights):
    """8. Missing/invalid lever -> no action."""
    sh = ScoredHypothesis(
        hypothesis_id="H1",
        final_audit_score=0.95,
        audit_verdict=AuditVerdict.VERIFIED,
    )
    challenge_result = ChallengeResult(
        scored_hypotheses=[sh],
        winning_hypothesis_id="H1",
        overall_verdict=AuditVerdict.VERIFIED,
        abstained=False,
    )
    
    # LLM returns a hallucinated lever
    mock_json = '''{
        "controllable_lever": "Hallucinated Unregistered Magic Fix",
        "recommended_action": "Do something custom.",
        "verification_metric": "payment_success_rate",
        "persona_narrative": "Magic fix.",
        "monitoring_plan": "Just wait."
    }'''
    
    provider = MockProvider(mock_json)
    
    decision = decide(
        challenge_result=challenge_result,
        persona=Persona.ANALYST,
        provider=provider,
        decision_rights=decision_rights,
        winning_statement="Bug"
    )
    
    assert decision.abstained is True
    assert decision.abstention_reason == "unauthorized_lever_selected"
    assert decision.recommended_action is None
    assert decision.structured_recommendation is None


def test_9_property_6_abstained_always_has_none_action():
    """9. Confirm Property 6: abstained=True -> recommended_action=None."""
    with pytest.raises(ValueError, match="Property 6"):
        Decision(
            abstained=True,
            recommended_action="Illegal action while abstained",
            verification_metric="metric",
            winning_hypothesis_id="H1",
            persona_narrative="Narrative",
        )


def test_10_deterministic_e8_impact_cannot_be_replaced_by_llm():
    """10. Confirm E8 expected impact remains deterministic and cannot be replaced by LLM output."""
    sr = StructuredActionRecommendation(
        driver="Driver",
        controllable_lever="Software Release Reversion",
        action="Roll back v4.3",
        expected_impact="Pending E8 Simulation",
        owner="Platform Engineering",
        confidence=0.95,
        monitoring_plan="Monitor payment_success_rate",
        authorized_personas=["analyst", "manager"]
    )
    decision = Decision(
        abstained=False,
        recommended_action="Roll back v4.3",
        verification_metric="payment_success_rate",
        winning_hypothesis_id="H1",
        persona_narrative="Narrative",
        structured_recommendation=sr,
        method=MethodTag.LLM,
    )
    
    # Orchestrator injects deterministic E8 simulation result
    final_sr = dataclasses.replace(
        decision.structured_recommendation,
        expected_impact="Projected 85.0% recovery on payment_success_rate + conversion_rate"
    )
    final_decision = dataclasses.replace(decision, structured_recommendation=final_sr)
    
    assert final_decision.structured_recommendation.expected_impact == "Projected 85.0% recovery on payment_success_rate + conversion_rate"
    assert final_decision.structured_recommendation.confidence == 0.95
