import pytest
import dataclasses
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

def test_structured_decision_valid_lever():
    """Test that a valid lever selection correctly builds the StructuredActionRecommendation."""
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
    
    decision_rights = {
        "levers": {
            "Software Release Reversion": {
                "owner": "Platform Engineering",
                "authorized_personas": ["analyst", "manager"]
            }
        }
    }
    
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
        persona=Persona.ANALYST,
        provider=provider,
        decision_rights=decision_rights,
        winning_statement="Payment gateway bug in v4.3"
    )
    
    assert not decision.abstained
    assert decision.structured_recommendation is not None
    
    sr = decision.structured_recommendation
    assert sr.controllable_lever == "Software Release Reversion"
    assert sr.owner == "Platform Engineering"
    assert sr.authorized_personas == ["analyst", "manager"]
    assert sr.confidence == 0.95
    assert sr.driver == "Payment gateway bug in v4.3"
    assert sr.action == "Roll back v4.3 immediately."
    assert sr.expected_impact == "Pending E8 Simulation"

def test_structured_decision_invalid_lever_abstains():
    """Test that if the LLM hallucinates a lever, E7 strictly abstains."""
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
    
    decision_rights = {
        "levers": {
            "Software Release Reversion": {
                "owner": "Platform Engineering",
                "authorized_personas": ["analyst"]
            }
        }
    }
    
    # LLM returns a lever not in decision_rights
    mock_json = '''{
        "controllable_lever": "Hallucinated Magic Fix",
        "recommended_action": "Do something.",
        "verification_metric": "payment_success_rate",
        "persona_narrative": "It will fix it.",
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

def test_immutable_orchestrator_injection():
    """Test that dataclasses.replace correctly injects expected_impact into a frozen dataclass."""
    sr = StructuredActionRecommendation(
        driver="Test",
        controllable_lever="Lever",
        action="Action",
        expected_impact="Pending E8 Simulation",
        owner="Owner",
        confidence=0.9,
        monitoring_plan="Plan",
        authorized_personas=["analyst"]
    )
    decision = Decision(
        abstained=False,
        recommended_action="Action",
        verification_metric="metric",
        winning_hypothesis_id="H1",
        persona_narrative="Narrative",
        structured_recommendation=sr,
        method=MethodTag.LLM,
    )
    
    # Simulate E8 result
    final_sr = dataclasses.replace(
        decision.structured_recommendation,
        expected_impact="Projected 50.0% recovery on metric"
    )
    final_decision = dataclasses.replace(decision, structured_recommendation=final_sr)
    
    assert final_decision.structured_recommendation.expected_impact == "Projected 50.0% recovery on metric"
    # Original should be unchanged
    assert decision.structured_recommendation.expected_impact == "Pending E8 Simulation"
