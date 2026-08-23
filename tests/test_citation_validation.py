from engines.challenge import validate_citations, score_hypothesis, ChallengeThresholds
from models import Hypothesis, EvidenceCitation, Evidence, MethodTag

def test_citation_formatting_mismatch_is_non_fatal():
    ev = Evidence(
        evidence_id="E1",
        kind="structured",
        summary="Exact Summary",
        source_id="test",
        reliability_weight=0.9,
        relevance=1.0,
        raw_ref="test",
        method=MethodTag.SQL
    )
    evidence_by_id = {"E1": ev}
    
    # 1. Exact match
    h_exact = Hypothesis(
        hypothesis_id="H1",
        statement="Test",
        reasoning="Test",
        citations=[EvidenceCitation("E1", "Exact Summary", "supports", "")]
    )
    v_exact = validate_citations(h_exact, evidence_by_id)
    assert len(v_exact) == 0
    score_exact = score_hypothesis(h_exact, evidence_by_id)
    assert score_exact.final_score > 0
    
    # 2. Formatting drift (minor spacing, punctuation, case)
    h_drift = Hypothesis(
        hypothesis_id="H2",
        statement="Test",
        reasoning="Test",
        citations=[EvidenceCitation("E1", "Exact  Summary.", "supports", "")] # Whitespace + punctuation drift
    )
    v_drift = validate_citations(h_drift, evidence_by_id)
    assert len(v_drift) == 0 # Caught by normalization, no violation
    score_drift = score_hypothesis(h_drift, evidence_by_id)
    assert score_drift.final_score > 0
    
    # 3. Material mismatch (hallucinated content)
    h_material = Hypothesis(
        hypothesis_id="H3",
        statement="Test",
        reasoning="Test",
        citations=[EvidenceCitation("E1", "Completely different text", "supports", "")]
    )
    v_material = validate_citations(h_material, evidence_by_id)
    assert len(v_material) == 1
    assert v_material[0].violation_type == "summary_mismatch"
    score_material = score_hypothesis(h_material, evidence_by_id)
    assert score_material.final_score == 0.0 # Fatal
    
    # 4. Phantom ID
    h_phantom = Hypothesis(
        hypothesis_id="H4",
        statement="Test",
        reasoning="Test",
        citations=[EvidenceCitation("E_PHANTOM", "Phantom", "supports", "")]
    )
    v_phantom = validate_citations(h_phantom, evidence_by_id)
    assert len(v_phantom) == 1
    assert v_phantom[0].violation_type == "phantom_id"
    score_phantom = score_hypothesis(h_phantom, evidence_by_id)
    assert score_phantom.final_score == 0.0 # Fatal
    v_phantom = validate_citations(h_phantom, evidence_by_id)
    assert len(v_phantom) == 1
    assert v_phantom[0].violation_type == "phantom_id"
    score_phantom = score_hypothesis(h_phantom, evidence_by_id)
    assert score_phantom.final_score == 0.0 # Fatal, score is 0
