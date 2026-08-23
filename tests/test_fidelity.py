"""
tests/test_fidelity.py — Citation fidelity and hallucination prevention tests (ISSUE-001).
"""

import pytest
from models import (
    ConfidenceState,
    Decision,
    Evidence,
    EvidenceCitation,
    Hypothesis,
    InvestigationResult,
    MethodTag,
    Persona,
    Telemetry,
)
from engines.challenge import (
    CitationViolation,
    score_hypothesis,
    validate_citations,
)
from evaluation.evaluator import Evaluator


def test_exact_match_no_violations():
    ev = Evidence(id="ev_001", summary="Inventory fill rate is normal and stable.")
    h = Hypothesis(
        hypothesis_id="H1",
        statement="Inventory is normal.",
        citations=[
            EvidenceCitation(
                evidence_id="ev_001",
                quoted_summary="Inventory fill rate is normal and stable.",
                role="supports",
                relevance_explanation="Stable inventory rules out a stockout cause.",
            )
        ],
    )
    assert validate_citations(h, {"ev_001": ev}) == []


def test_summary_mismatch_produces_violation():
    ev = Evidence(id="ev_001", summary="Inventory fill rate is normal and stable.")
    h = Hypothesis(
        hypothesis_id="H1",
        statement="Inventory is dangerously low.",
        citations=[
            EvidenceCitation(
                evidence_id="ev_001",
                quoted_summary="inventory levels are dangerously low",
                role="supports",
                relevance_explanation="Low inventory caused revenue drop.",
            )
        ],
    )
    violations = validate_citations(h, {"ev_001": ev})
    assert len(violations) == 1
    assert violations[0].violation_type == "summary_mismatch"


def test_phantom_id_produces_violation():
    h = Hypothesis(
        hypothesis_id="H1",
        statement="Unknown evidence cause.",
        citations=[
            EvidenceCitation(
                evidence_id="FAKE_ID_999",
                quoted_summary="anything",
                role="supports",
                relevance_explanation="Doesn't matter.",
            )
        ],
    )
    violations = validate_citations(h, {})
    assert len(violations) == 1
    assert violations[0].violation_type == "phantom_id"


def test_duplicate_citation_produces_violation():
    ev = Evidence(id="ev_001", summary="Inventory fill rate is normal and stable.")
    citation = EvidenceCitation(
        evidence_id="ev_001",
        quoted_summary="Inventory fill rate is normal and stable.",
        role="supports",
        relevance_explanation="Stable inventory rules out a stockout cause.",
    )
    h = Hypothesis(
        hypothesis_id="H1",
        statement="Inventory check.",
        citations=[citation, citation],
    )
    violations = validate_citations(h, {"ev_001": ev})
    assert any(v.violation_type == "duplicate_citation" for v in violations)


def test_citation_violation_disqualifies_hypothesis():
    ev = Evidence(id="ev_001", summary="Inventory fill rate is normal and stable.")
    h = Hypothesis(
        hypothesis_id="H1",
        statement="Inventory failure.",
        citations=[
            EvidenceCitation(
                evidence_id="ev_001",
                quoted_summary="inventory levels are dangerously low",
                role="supports",
                relevance_explanation="Low inventory caused revenue drop.",
            )
        ],
    )
    score = score_hypothesis(h, {"ev_001": ev})
    assert score.confidence == ConfidenceState.ABSTAIN
    assert score.final_score == 0.0
    assert score.violations


def test_supporting_ids_derived_from_citations():
    ev_a = Evidence(id="ev_001", summary="Summary A.")
    ev_b = Evidence(id="ev_002", summary="Summary B.")
    h = Hypothesis(
        hypothesis_id="H1",
        citations=[
            EvidenceCitation("ev_001", "Summary A.", "supports", "Reason A."),
            EvidenceCitation("ev_002", "Summary B.", "contradicts", "Reason B."),
        ],
    )
    assert h.supporting_evidence_ids == ["ev_001"]
    assert h.contradictory_evidence_ids == ["ev_002"]


def test_neutral_excluded_from_derived_fields():
    ev = Evidence(id="ev_001", summary="Summary A.")
    h = Hypothesis(
        hypothesis_id="H1",
        citations=[
            EvidenceCitation("ev_001", "Summary A.", "neutral", "Contextual only.")
        ],
    )
    assert h.supporting_evidence_ids == []
    assert h.contradictory_evidence_ids == []


def test_d16_hard_requirement_fails_overall_pass():
    # Construct a minimal InvestigationResult where D16 fails.
    # Assert result.overall_pass is False even if D01-D15 all pass.
    ev = Evidence(
        evidence_id="ev_001",
        kind="structured",
        summary="Payment gateway timeout spike.",
        source_id="payment_gateway",
        reliability_weight=0.9,
        relevance=0.9,
        raw_ref="ref_1",
        method=MethodTag.SQL,
    )
    h_mismatched = Hypothesis(
        hypothesis_id="H1",
        statement="Payment gateway failure.",
        citations=[
            EvidenceCitation(
                evidence_id="ev_001",
                quoted_summary="completely wrong quote",
                role="supports",
                relevance_explanation="Mismatch reason.",
            )
        ],
        reasoning="Payment gateway timeouts occurred.",
        method=MethodTag.LLM,
    )

    inv_result = InvestigationResult(
        scenario_id="INC_001",
        persona=Persona.ANALYST,
        signals=[],
        contributions=[],
        evidence=[ev],
        hypotheses=[h_mismatched],
        scored=[],
        decision=Decision(
            abstained=False,
            recommended_action="Rollback v4.3",
            verification_metric="payment_success_rate",
            winning_hypothesis_id="H1",
            persona_narrative="Action needed.",
        ),
        outcome=None,
        precedents=[],
        telemetry=Telemetry(),
        method_ownership={},
    )

    evaluator = Evaluator()
    eval_res = evaluator.evaluate(inv_result)

    # D16 must fail
    d16 = next((d for d in eval_res.dimension_scores if d.dimension_id == 16), None)
    assert d16 is not None
    assert not d16.passed
    assert d16.is_hard_requirement
    # overall_pass must be False
    assert not eval_res.overall_pass


def test_legacy_field_consistency_with_citations():
    # Verify that supporting_evidence_ids on a hypothesis with two supporting
    # citations returns exactly those two IDs and nothing else.
    # Exists to catch any regression where these fields become independent
    # of citations again.
    h = Hypothesis(
        hypothesis_id="H1",
        citations=[
            EvidenceCitation("ev_001", "Summary 1.", "supports", "Reason 1."),
            EvidenceCitation("ev_002", "Summary 2.", "supports", "Reason 2."),
            EvidenceCitation("ev_003", "Summary 3.", "contradicts", "Reason 3."),
            EvidenceCitation("ev_004", "Summary 4.", "neutral", "Reason 4."),
        ],
    )
    assert h.supporting_evidence_ids == ["ev_001", "ev_002"]
    assert h.contradictory_evidence_ids == ["ev_003"]


def test_malformed_citations_field_rejected():
    from engines.hypothesis import validate_hypothesis
    raw = {
        "hypothesis_id": "H1",
        "statement": "Statement",
        "reasoning": "Reasoning",
        "citations": "not a list",
    }
    is_valid, reason = validate_hypothesis(raw, frozenset(["ev_001"]))
    assert not is_valid
    assert "citations field is present but not a list" in reason


def test_invalid_citation_role_rejected():
    from engines.hypothesis import validate_hypothesis
    raw = {
        "hypothesis_id": "H1",
        "statement": "Statement",
        "reasoning": "Reasoning",
        "citations": [
            {
                "evidence_id": "ev_001",
                "quoted_summary": "Summary 1.",
                "role": "invalid_role_name",
                "relevance_explanation": "Explanation",
            }
        ],
    }
    is_valid, reason = validate_hypothesis(raw, frozenset(["ev_001"]))
    assert not is_valid
    assert "invalid role" in reason


def test_evidence_id_in_reasoning_rejected():
    from engines.hypothesis import validate_hypothesis
    raw = {
        "hypothesis_id": "H1",
        "statement": "Statement",
        "reasoning": "As shown in ev_001, the system failed.",
        "citations": [
            {
                "evidence_id": "ev_001",
                "quoted_summary": "Summary 1.",
                "role": "supports",
                "relevance_explanation": "Explanation",
            }
        ],
    }
    is_valid, reason = validate_hypothesis(raw, frozenset(["ev_001"]))
    assert not is_valid
    assert "reasoning contains prohibited evidence ID reference" in reason


def test_zero_citations_rejected_when_evidence_available():
    from engines.hypothesis import validate_hypothesis
    raw = {
        "hypothesis_id": "H1",
        "statement": "Statement",
        "reasoning": "Reasoning",
        "citations": [],
    }
    is_valid, reason = validate_hypothesis(raw, frozenset(["ev_001"]))
    assert not is_valid
    assert "hypothesis contains zero citations when evidence is available" in reason

