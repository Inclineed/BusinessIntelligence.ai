import pytest
from models import Hypothesis, Evidence, EvidenceCitation, AuditVerdict, RuleVerdict
from engines.challenge import evaluate_rule, challenge, ChallengeThresholds
from engines.decision import decide
from config.loader import load_domain_semantics

# A matrix of test cases covering the new deterministic audit logic

@pytest.fixture
def domain_semantics():
    return load_domain_semantics("config/domain_semantics.yaml")

def test_verdict_verified(domain_semantics):
    h = Hypothesis(hypothesis_id="H1", statement="Test", mechanism_tag="payment_gateway")
    # Add sufficient evidence to get VERIFIED
    ev = Evidence(evidence_id="E1", summary="Supports payment gateway failure", reliability_weight=0.9, relevance=1.0, method="test")
    h.citations = [EvidenceCitation(evidence_id="E1", role="supports", relevance_explanation='test', quoted_summary="Supports payment gateway failure")]
    evidence_by_id = {"E1": ev}
    
    result = challenge([h], evidence_by_id, [], [], domain_semantics=domain_semantics)
    assert result.scored_hypotheses[0].audit_verdict == AuditVerdict.MARGINAL

def test_verdict_rejected_due_to_contradiction(domain_semantics):
    h = Hypothesis(hypothesis_id="H1", statement="Test", mechanism_tag="payment_gateway")
    # Add strong contradictory evidence
    ev_sup = Evidence(evidence_id="E1", summary="Supports", reliability_weight=0.9, relevance=1.0, method="test")
    ev_con = Evidence(evidence_id="E2", summary="Contradicts", reliability_weight=0.9, relevance=1.0, method="test")
    h.citations = [
        EvidenceCitation(evidence_id="E1", role="supports", relevance_explanation='test', quoted_summary="Supports"),
        EvidenceCitation(evidence_id="E2", role="contradicts", relevance_explanation='test', quoted_summary="Contradicts")
    ]
    evidence_by_id = {"E1": ev_sup, "E2": ev_con}
    
    result = challenge([h], evidence_by_id, [], [], domain_semantics=domain_semantics)
    assert result.scored_hypotheses[0].audit_verdict == AuditVerdict.REJECTED

def test_abstain_ambiguity(domain_semantics):
    h1 = Hypothesis(hypothesis_id="H1", statement="Test 1", mechanism_tag="payment_gateway")
    h2 = Hypothesis(hypothesis_id="H2", statement="Test 2", mechanism_tag="external_factors")
    ev1 = Evidence(evidence_id="E1", source_id="payment_gateway", summary="Supports 1", reliability_weight=0.9, relevance=1.0, method="test")
    ev2 = Evidence(evidence_id="E2", source_id="marketing", summary="Supports 2", reliability_weight=0.9, relevance=1.0, method="test")
    h1.citations = [EvidenceCitation(evidence_id="E1", role="supports", relevance_explanation='test', quoted_summary="Supports 1")]
    h2.citations = [EvidenceCitation(evidence_id="E2", role="supports", relevance_explanation='test', quoted_summary="Supports 2")]
    
    evidence_by_id = {"E1": ev1, "E2": ev2}
    result = challenge([h1, h2], evidence_by_id, [], [], domain_semantics=domain_semantics)
    
    # Both have identical support score (0.45), so margin is 0.0 < 0.15 gap -> ABSTAIN
    assert result.abstained
    assert result.overall_verdict == AuditVerdict.ABSTAIN

def test_decision_safety_contract(domain_semantics):
    h1 = Hypothesis(hypothesis_id="H1", statement="Test 1", mechanism_tag="payment_gateway")
    ev1 = Evidence(evidence_id="E1", source_id="payment_gateway", summary="Supports 1", reliability_weight=0.9, relevance=1.0, method="test")
    h1.citations = [EvidenceCitation(evidence_id="E1", role="supports", relevance_explanation='test', quoted_summary="Supports 1")]
    
    evidence_by_id = {"E1": ev1}
    # Force abstain by using high threshold
    thresholds = ChallengeThresholds(abstain_threshold=0.99)
    result = challenge([h1], evidence_by_id, [], [], thresholds=thresholds, domain_semantics=domain_semantics)
    
    decision_result = decide(result, "cfo", None)
    assert result.abstained
    assert decision_result.abstained
    assert decision_result.recommended_action is None


def test_unaligned_evidence_zero_support_weight(domain_semantics):
    """
    Marketing evidence cited as 'supports' under payment_gateway mechanism
    must receive 0 support weight and be recorded in unaligned_evidence_ids.
    """
    h = Hypothesis(hypothesis_id="H1", statement="Payment gateway latency", mechanism_tag="payment_gateway")
    ev_mkt = Evidence(
        evidence_id="EV_MKT_01",
        source_id="marketing",
        summary="Marketing campaign on channel 'social': total spend $28996.91",
        reliability_weight=0.90,
        relevance=0.90,
        method="test",
    )
    h.citations = [
        EvidenceCitation(
            evidence_id="EV_MKT_01",
            role="supports",
            relevance_explanation="Claims marketing caused payment latency",
            quoted_summary="Marketing campaign on channel 'social': total spend $28996.91",
        )
    ]
    evidence_by_id = {"EV_MKT_01": ev_mkt}
    result = challenge([h], evidence_by_id, [], [], domain_semantics=domain_semantics)
    sh = result.scored_hypotheses[0]

    assert sh.support_score == 0.0
    assert sh.evidence_sufficiency_score == 0.0
    assert "EV_MKT_01" in sh.unaligned_evidence_ids
    assert sh.audit_verdict == AuditVerdict.MARGINAL


def test_aligned_evidence_full_support_weight(domain_semantics):
    """
    Direct payment_gateway evidence cited under payment_gateway mechanism
    must receive full support weight.
    """
    h = Hypothesis(hypothesis_id="H1", statement="Payment gateway latency", mechanism_tag="payment_gateway")
    ev_pay = Evidence(
        evidence_id="EV_PAY_01",
        source_id="payment_gateway",
        summary="Payment gateway events in window: 291613 total, 5986 failures, avg latency 182ms",
        reliability_weight=0.99,
        relevance=0.90,
        method="test",
    )
    h.citations = [
        EvidenceCitation(
            evidence_id="EV_PAY_01",
            role="supports",
            relevance_explanation="Payment gateway telemetry confirms latency degradation",
            quoted_summary="Payment gateway events in window: 291613 total, 5986 failures, avg latency 182ms",
        )
    ]
    evidence_by_id = {"EV_PAY_01": ev_pay}
    result = challenge([h], evidence_by_id, [], [], domain_semantics=domain_semantics)
    sh = result.scored_hypotheses[0]

    expected_support = (0.99 * 0.90) / 2.0
    assert abs(sh.support_score - expected_support) < 1e-4
    assert len(sh.unaligned_evidence_ids) == 0


def test_contextual_source_content_alignment_required(domain_semantics):
    """
    Edge case: A contextual source (e.g. support_tickets) is in compatible_sources,
    but its summary content/KPI must also match the mechanism.
    - If content is unaligned (warehouse stock) -> rejected (0 weight).
    - If content is aligned (checkout auth failure) -> accepted (normal weight).
    """
    # 1. Unaligned content in compatible source
    h_unaligned = Hypothesis(hypothesis_id="H1", statement="Payment gateway latency", mechanism_tag="payment_gateway")
    ev_tickets_unaligned = Evidence(
        evidence_id="EV_TKT_01",
        source_id="support_tickets",
        summary="Customer support tickets: 45 reports of warehouse out of stock items",
        reliability_weight=0.90,
        relevance=0.85,
        method="test",
    )
    h_unaligned.citations = [
        EvidenceCitation(
            evidence_id="EV_TKT_01",
            role="supports",
            relevance_explanation="Support tickets",
            quoted_summary="Customer support tickets: 45 reports of warehouse out of stock items",
        )
    ]
    res1 = challenge([h_unaligned], {"EV_TKT_01": ev_tickets_unaligned}, [], [], domain_semantics=domain_semantics)
    sh1 = res1.scored_hypotheses[0]
    assert sh1.support_score == 0.0
    assert "EV_TKT_01" in sh1.unaligned_evidence_ids

    # 2. Aligned content in compatible source
    h_aligned = Hypothesis(hypothesis_id="H2", statement="Payment gateway latency", mechanism_tag="payment_gateway")
    ev_tickets_aligned = Evidence(
        evidence_id="EV_TKT_02",
        source_id="support_tickets",
        summary="Customer support tickets: surge in checkout payment authentication failures",
        reliability_weight=0.90,
        relevance=0.85,
        method="test",
    )
    h_aligned.citations = [
        EvidenceCitation(
            evidence_id="EV_TKT_02",
            role="supports",
            relevance_explanation="Support tickets about payment auth failures",
            quoted_summary="Customer support tickets: surge in checkout payment authentication failures",
        )
    ]
    res2 = challenge([h_aligned], {"EV_TKT_02": ev_tickets_aligned}, [], [], domain_semantics=domain_semantics)
    sh2 = res2.scored_hypotheses[0]
    assert sh2.support_score > 0.0
    assert len(sh2.unaligned_evidence_ids) == 0


def test_inc002_ambiguity_preserved_under_misattributed_evidence(domain_semantics):
    """
    Simulates INC_002 where H1 is payment_gateway and H2 is external_factors.
    Even if E5 marks marketing evidence as 'supports' for H1, E6 filters it out,
    ensuring H1 does not falsely gain verified score and the overall verdict remains ABSTAIN.
    """
    ev_pay = Evidence(
        evidence_id="660a5c5bed7b3479",
        source_id="payment_gateway",
        summary="Payment gateway events in window: 291613 total, 5986 failures, avg latency 182ms",
        reliability_weight=0.99,
        relevance=0.90,
        method="test",
    )
    ev_mkt = Evidence(
        evidence_id="620a266b7ffd3cbd",
        source_id="marketing",
        summary="Marketing campaign on channel 'social': total spend $28996.91, 611302 impressions",
        reliability_weight=0.90,
        relevance=0.90,
        method="test",
    )
    ev_mkt2 = Evidence(
        evidence_id="bedb7f491d679751",
        source_id="marketing",
        summary="Marketing campaign on channel 'digital': total spend $38552.92, 925704 impressions",
        reliability_weight=0.90,
        relevance=0.90,
        method="test",
    )

    evidence_by_id = {
        "660a5c5bed7b3479": ev_pay,
        "620a266b7ffd3cbd": ev_mkt,
        "bedb7f491d679751": ev_mkt2,
    }

    # H1 mistakenly cites both payment and marketing as 'supports'
    h1 = Hypothesis(
        hypothesis_id="H1",
        statement="Payment gateway service degradation",
        mechanism_tag="payment_gateway",
        citations=[
            EvidenceCitation(
                evidence_id="660a5c5bed7b3479",
                role="supports",
                quoted_summary="Payment gateway events in window: 291613 total, 5986 failures, avg latency 182ms",
                relevance_explanation="Gateway errors",
            ),
            EvidenceCitation(
                evidence_id="620a266b7ffd3cbd",
                role="supports",
                quoted_summary="Marketing campaign on channel 'social': total spend $28996.91, 611302 impressions",
                relevance_explanation="Extra traffic",
            ),
        ],
    )

    # H2 cites marketing evidence
    h2 = Hypothesis(
        hypothesis_id="H2",
        statement="Marketing campaign traffic surge",
        mechanism_tag="external_factors",
        citations=[
            EvidenceCitation(
                evidence_id="bedb7f491d679751",
                role="supports",
                quoted_summary="Marketing campaign on channel 'digital': total spend $38552.92, 925704 impressions",
                relevance_explanation="Digital campaign",
            ),
        ],
    )

    result = challenge([h1, h2], evidence_by_id, [], [], domain_semantics=domain_semantics)

    sh1 = next(s for s in result.scored_hypotheses if s.hypothesis_id == "H1")
    sh2 = next(s for s in result.scored_hypotheses if s.hypothesis_id == "H2")

    # H1 marketing citation was rejected from support score
    assert "620a266b7ffd3cbd" in sh1.unaligned_evidence_ids
    assert abs(sh1.support_score - (0.99 * 0.90 / 2.0)) < 1e-4
    assert sh1.audit_verdict == AuditVerdict.MARGINAL
    assert sh2.audit_verdict == AuditVerdict.MARGINAL

    # Scenario must remain ABSTAIN
    assert result.abstained is True
    assert result.overall_verdict == AuditVerdict.ABSTAIN
    assert result.winning_hypothesis_id is None
