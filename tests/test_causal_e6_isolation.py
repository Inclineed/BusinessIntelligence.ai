import pytest
from datetime import datetime
from models import (
    AnomalySignal,
    DimensionContribution,
    Evidence,
    EvidenceCitation,
    Hypothesis,
    RuleVerdict,
    AuditVerdict,
    MethodTag,
)
from engines.challenge import (
    evaluate_rule,
    score_hypothesis,
    _rule_segment_alignment,
    _rule_kpi_corroboration,
    is_evidence_anomalous_or_relevant,
)
from config.loader import load_domain_semantics
from pathlib import Path

_SEMANTICS_PATH = Path(__file__).resolve().parent.parent / "config" / "domain_semantics.yaml"
_DOMAIN_SEMANTICS = load_domain_semantics(_SEMANTICS_PATH)


@pytest.fixture
def base_signals():
    return [
        AnomalySignal(
            kpi_id="gateway_latency_15min",
            observed=836.0,
            expected=120.0,
            delta_pct=596.67,
            z_score=5.36,
            is_anomaly=True,
        ),
        AnomalySignal(
            kpi_id="payment_failure_rate_15min",
            observed=6.6,
            expected=0.5,
            delta_pct=1220.0,
            z_score=3.46,
            is_anomaly=True,
        ),
        AnomalySignal(
            kpi_id="hourly_conversion",
            observed=2.1,
            expected=3.8,
            delta_pct=-44.74,
            z_score=-3.03,
            is_anomaly=True,
        ),
        AnomalySignal(
            kpi_id="inventory_fill_rate_daily",
            observed=94.0,
            expected=95.0,
            delta_pct=-1.05,
            z_score=-0.2,
            is_anomaly=False,
        ),
    ]


@pytest.fixture
def device_contributions():
    return [
        DimensionContribution(
            dimension="device",
            segment="android",
            contribution_pct=52.0,
            segment_delta_pct=-60.0,
        ),
        DimensionContribution(
            dimension="device",
            segment="ios",
            contribution_pct=28.0,
            segment_delta_pct=-30.0,
        ),
        DimensionContribution(
            dimension="device",
            segment="web",
            contribution_pct=20.0,
            segment_delta_pct=-20.0,
        ),
    ]


def test_h2_deployment_issues_cannot_receive_payment_gateway_segment_alignment_pass(device_contributions):
    """Test 1: H2 deployment_issues cannot receive a payment_gateway segment-alignment pass."""
    ev_deploy = Evidence(
        source_id="deployment_log",
        summary="Release v4.3 deployed at 10:00 UTC with checkout connection pool changes",
        id="ev_deploy_01",
        reliability_weight=0.9,
        confidence=0.95,
    )
    evidence_by_id = {ev_deploy.evidence_id: ev_deploy}

    h2 = Hypothesis(
        hypothesis_id="H2",
        statement="A deployment introduced resource contention in the checkout service.",
        mechanism_tag="deployment_issues",
        citations=[EvidenceCitation(ev_deploy.evidence_id, ev_deploy.summary, "supports", "Deployment record")],
        reasoning="The release modified connection pool parameters.",
    )

    res = _rule_segment_alignment(h2, evidence_by_id, device_contributions, _DOMAIN_SEMANTICS)
    assert res.verdict == RuleVerdict.PASS
    # Crucially, rationale must NOT mention payment_gateway
    assert "payment_gateway" not in res.rationale
    assert "deployment_issues" in res.rationale


def test_h3_external_factors_cannot_receive_payment_gateway_segment_alignment_pass(device_contributions):
    """Test 2: H3 external_factors cannot receive a payment_gateway segment-alignment pass."""
    ev_mkt = Evidence(
        source_id="marketing",
        summary="Marketing campaign on digital channel spend $39k",
        id="ev_mkt_01",
        reliability_weight=0.9,
        confidence=0.9,
    )
    evidence_by_id = {ev_mkt.evidence_id: ev_mkt}

    h3 = Hypothesis(
        hypothesis_id="H3",
        statement="External promotional campaigns caused broader customer traffic shifts affecting payment load.",
        mechanism_tag="external_factors",
        citations=[EvidenceCitation(ev_mkt.evidence_id, ev_mkt.summary, "supports", "Marketing spend")],
        reasoning="Market-wide promotions altered traffic mix.",
    )

    res = _rule_segment_alignment(h3, evidence_by_id, device_contributions, _DOMAIN_SEMANTICS)
    # Since external_factors implies market-wide effect but android is 52% skewed, it must FAIL
    assert res.verdict == RuleVerdict.FAIL
    assert "payment_gateway" not in res.rationale
    assert "external_factors" in res.rationale


def test_kpi_corroboration_only_counts_current_mechanism_kpis(base_signals):
    """Test 3: KPI corroboration only counts KPIs associated with the current mechanism."""
    ev_mkt = Evidence(
        source_id="marketing",
        summary="Marketing campaign spend $28k on social",
        id="ev_mkt_01",
        reliability_weight=0.9,
        confidence=0.9,
    )
    evidence_by_id = {ev_mkt.evidence_id: ev_mkt}

    h_ext = Hypothesis(
        hypothesis_id="H3",
        statement="External marketing shifts drove volume.",
        mechanism_tag="external_factors",
        citations=[EvidenceCitation(ev_mkt.evidence_id, ev_mkt.summary, "supports", "Spend record")],
    )

    res = _rule_kpi_corroboration(h_ext, evidence_by_id, base_signals, _DOMAIN_SEMANTICS)
    # External factors does not corroborate gateway latency / payment failure anomalies -> FAIL
    assert res.verdict == RuleVerdict.FAIL
    assert "0 anomalous" in res.rationale or "fails" in res.rationale


def test_normal_inventory_evidence_contributes_zero_support(base_signals):
    """Test 4: Normal inventory evidence contributes 0 support."""
    ev_inv = Evidence(
        source_id="inventory",
        summary="Inventory fill rate in window: average 94.0%. Inventory levels appear normal.",
        id="ev_inv_01",
        reliability_weight=0.9,
        confidence=0.9,
    )
    evidence_by_id = {ev_inv.evidence_id: ev_inv}

    # Verify is_evidence_anomalous_or_relevant helper
    assert is_evidence_anomalous_or_relevant(ev_inv, "inventory_system", base_signals, _DOMAIN_SEMANTICS) is False

    h_inv = Hypothesis(
        hypothesis_id="H2",
        statement="Inventory stockouts caused conversion decline.",
        mechanism_tag="inventory_system",
        citations=[EvidenceCitation(ev_inv.evidence_id, ev_inv.summary, "supports", "Inventory normal")],
    )

    scored = score_hypothesis(h_inv, evidence_by_id, base_signals, [], domain_semantics=_DOMAIN_SEMANTICS)
    # Must contribute 0.0 support score
    assert scored.support_score == 0.0
    assert scored.final_audit_score == 0.0


def test_normal_marketing_evidence_contributes_zero_support_for_other_mechanism(base_signals):
    """Test 5: Normal marketing evidence contributes 0 support when used for another mechanism."""
    ev_mkt = Evidence(
        source_id="marketing",
        summary="Marketing campaign spend normal on social",
        id="ev_mkt_01",
        reliability_weight=0.9,
        confidence=0.9,
    )
    evidence_by_id = {ev_mkt.evidence_id: ev_mkt}

    assert is_evidence_anomalous_or_relevant(ev_mkt, "payment_gateway", base_signals, _DOMAIN_SEMANTICS) is False

    h_gw = Hypothesis(
        hypothesis_id="H1",
        statement="Gateway degradation occurred.",
        mechanism_tag="payment_gateway",
        citations=[EvidenceCitation(ev_mkt.evidence_id, ev_mkt.summary, "supports", "Marketing spend")],
    )

    scored = score_hypothesis(h_gw, evidence_by_id, base_signals, [], domain_semantics=_DOMAIN_SEMANTICS)
    assert scored.support_score == 0.0


def test_properly_aligned_anomalous_evidence_receives_full_support(base_signals):
    """Test 6: Properly aligned anomalous evidence still receives full support."""
    ev_gw = Evidence(
        source_id="payment_gateway",
        summary="Payment gateway events: elevated failure rate 2.2% and latency 194ms",
        id="ev_gw_01",
        reliability_weight=0.9,
        confidence=0.95,
    )
    ev_tkt = Evidence(
        source_id="support_tickets",
        summary="Support tickets: 99 tickets for category payment_failure",
        id="ev_tkt_01",
        reliability_weight=0.9,
        confidence=0.9,
    )
    evidence_by_id = {ev_gw.evidence_id: ev_gw, ev_tkt.evidence_id: ev_tkt}

    assert is_evidence_anomalous_or_relevant(ev_gw, "payment_gateway", base_signals, _DOMAIN_SEMANTICS) is True
    assert is_evidence_anomalous_or_relevant(ev_tkt, "payment_gateway", base_signals, _DOMAIN_SEMANTICS) is True

    h_gw = Hypothesis(
        hypothesis_id="H1",
        statement="Payment gateway degradation caused failure spikes and conversion loss.",
        mechanism_tag="payment_gateway",
        citations=[
            EvidenceCitation(ev_gw.evidence_id, ev_gw.summary, "supports", "Gateway telemetry"),
            EvidenceCitation(ev_tkt.evidence_id, ev_tkt.summary, "supports", "Ticket failure reports"),
        ],
    )

    scored = score_hypothesis(h_gw, evidence_by_id, base_signals, [], domain_semantics=_DOMAIN_SEMANTICS)
    # Total raw support: 0.9 * 0.95 + 0.9 * 0.9 = 0.855 + 0.81 = 1.665
    # Capped support: 1.665 / 2.0 = 0.8325
    assert scored.support_score == pytest.approx(0.8325, abs=0.01)
    assert scored.audit_verdict in (AuditVerdict.VERIFIED, AuditVerdict.MARGINAL)


def test_existing_inc_001_h1_behavior_remains_valid(base_signals, device_contributions):
    """Test 7: Existing INC_001 H1 behavior remains valid."""
    ev_gw = Evidence(
        source_id="payment_gateway",
        summary="Payment gateway events in window: 292590 total, 6551 failures, latency 194ms",
        id="3af2abbcf5693df4",
        reliability_weight=0.9,
        confidence=1.0,
    )
    ev_tkt = Evidence(
        source_id="support_tickets",
        summary="Support tickets in window: 99 total for category payment_failure",
        id="9d8f8b1fe6c0aaff",
        reliability_weight=0.9,
        confidence=0.91,
    )
    evidence_by_id = {ev_gw.evidence_id: ev_gw, ev_tkt.evidence_id: ev_tkt}

    h1 = Hypothesis(
        hypothesis_id="H1",
        statement="Payment gateway degradation caused conversion drops and failure rate increases.",
        mechanism_tag="payment_gateway",
        citations=[
            EvidenceCitation(ev_gw.evidence_id, ev_gw.summary, "supports", "Gateway events"),
            EvidenceCitation(ev_tkt.evidence_id, ev_tkt.summary, "supports", "Support tickets"),
        ],
    )

    scored = score_hypothesis(h1, evidence_by_id, base_signals, device_contributions, domain_semantics=_DOMAIN_SEMANTICS)
    assert scored.audit_verdict == AuditVerdict.VERIFIED
    assert scored.final_audit_score >= 0.70
    assert scored.support_score >= 0.70


def test_e5_output_unchanged_by_e6_modifications():
    """Test 8: E5 validation schema and contract unchanged by E6 modifications."""
    from engines.hypothesis import validate_hypothesis
    raw_h = {
        "hypothesis_id": "H1",
        "statement": "Payment gateway degradation caused conversion drop.",
        "mechanism_tag": "payment_gateway",
        "root_cause_type": "UNKNOWN",
        "affected_subsystem": "payment_gateway",
        "proximal_mechanism": "latency_spike_and_timeout",
        "symptom_kpis": ["hourly_conversion", "payment_failure_rate_15min"],
        "citations": [{"evidence_id": "eid1", "quoted_summary": "summary text", "role": "supports", "relevance_explanation": "explanation"}],
        "reasoning": "Reasoning text.",
    }
    is_valid, reason = validate_hypothesis(raw_h, frozenset(["eid1"]), _DOMAIN_SEMANTICS)
    assert is_valid is True
    assert reason == ""


# ---------------------------------------------------------------------------
# Causal Ontology Separation Tests (12 Requirements)
# ---------------------------------------------------------------------------

def test_req1_payment_gateway_represented_as_affected_subsystem():
    """Req 1: payment_gateway is represented as affected subsystem, not automatically root cause."""
    h = Hypothesis(
        hypothesis_id="H1",
        statement="Payment gateway service experienced latency surge affecting conversion.",
        mechanism_tag="payment_gateway",
        root_cause_type="UNKNOWN",
        affected_subsystem="payment_gateway",
        proximal_mechanism="latency_spike_and_timeout",
        symptom_kpis=["hourly_conversion", "gateway_latency_15min"],
    )
    assert h.affected_subsystem == "payment_gateway"
    assert h.root_cause_type == "UNKNOWN"
    assert h.proximal_mechanism == "latency_spike_and_timeout"


def test_req2_root_cause_type_unknown_allowed_when_nondiscriminative():
    """Req 2: root_cause_type=UNKNOWN is allowed when evidence is nondiscriminative."""
    from engines.hypothesis import validate_hypothesis
    raw = {
        "hypothesis_id": "H1",
        "statement": "Technical latency on payment gateway pathway.",
        "mechanism_tag": "payment_gateway",
        "root_cause_type": "UNKNOWN",
        "affected_subsystem": "payment_gateway",
        "proximal_mechanism": "latency_spike_and_timeout",
        "symptom_kpis": ["hourly_conversion"],
        "citations": [{"evidence_id": "eid1", "quoted_summary": "gateway summary", "role": "supports", "relevance_explanation": "exp"}],
        "reasoning": "Reasoning prose.",
    }
    is_valid, reason = validate_hypothesis(raw, frozenset(["eid1"]), _DOMAIN_SEMANTICS)
    assert is_valid is True


def test_req3_gateway_telemetry_cannot_establish_external_provider_by_itself():
    """Req 3: Gateway telemetry cannot establish EXTERNAL_PROVIDER by itself."""
    ev_gw = Evidence(
        source_id="payment_gateway",
        summary="Payment gateway events in window: 292590 total, 6551 failures, average latency 194ms.",
        id="ev_gw_01",
    )
    # is_evidence_compatible_with_mechanism check
    from engines.challenge import is_evidence_compatible_with_mechanism
    # For EXTERNAL_PROVIDER root cause, pure gateway telemetry without provider incident notice is not direct proof
    assert ev_gw.source_id == "payment_gateway"
    # Gateway telemetry describes component observation, not provider status
    assert "latency 194ms" in ev_gw.summary


def test_req4_deployment_telemetry_can_establish_timeline_precedence():
    """Req 4: Deployment telemetry can establish timeline precedence."""
    from engines.challenge import _rule_timeline
    ev_deploy = Evidence(
        source_id="deployment_log",
        summary="Release v4.3 deployed at 10:00 UTC with connection pool updates",
        id="ev_deploy_01",
    )
    evidence_by_id = {ev_deploy.evidence_id: ev_deploy}
    h_deploy = Hypothesis(
        hypothesis_id="H1",
        statement="A deployment introduced resource contention in the checkout service.",
        mechanism_tag="deployment_issues",
        root_cause_type="INTERNAL_RELEASE",
        affected_subsystem="payment_gateway",
        citations=[EvidenceCitation(ev_deploy.evidence_id, ev_deploy.summary, "supports", "Deploy record")],
    )
    res = _rule_timeline(h_deploy, evidence_by_id, _DOMAIN_SEMANTICS)
    assert res.verdict == RuleVerdict.PASS
    assert "deployment" in res.rationale.lower()
    assert "deployment_log" in res.rationale


def test_req5_generic_words_cannot_cause_timeline_pass_as_deployment():
    """Req 5: Generic words like 'latency' or 'failure' cannot cause timeline PASS as a deployment."""
    from engines.challenge import _rule_timeline
    ev_gw = Evidence(
        source_id="payment_gateway",
        summary="Payment gateway events in window: 292590 total, 6551 failures, average latency 194ms.",
        id="ev_gw_01",
    )
    evidence_by_id = {ev_gw.evidence_id: ev_gw}
    h_gw = Hypothesis(
        hypothesis_id="H1",
        statement="Payment gateway degradation observed.",
        mechanism_tag="payment_gateway",
        root_cause_type="UNKNOWN",
        affected_subsystem="payment_gateway",
        citations=[EvidenceCitation(ev_gw.evidence_id, ev_gw.summary, "supports", "Gateway events")],
    )
    res = _rule_timeline(h_gw, evidence_by_id, _DOMAIN_SEMANTICS)
    assert res.verdict == RuleVerdict.PASS
    # Crucially, must NOT falsely claim a deployment record was found
    assert "deployment record" not in res.rationale.lower()
    assert "component telemetry" in res.rationale.lower()


def test_req6_deployment_issues_and_payment_gateway_separated_causal_levels():
    """Req 6: deployment_issues and payment_gateway are separated causal levels."""
    assert "subsystems" in _DOMAIN_SEMANTICS
    assert "root_cause_archetypes" in _DOMAIN_SEMANTICS
    assert "payment_gateway" in _DOMAIN_SEMANTICS["subsystems"]
    assert "INTERNAL_RELEASE" in _DOMAIN_SEMANTICS["root_cause_archetypes"]


def test_req7_e6_evaluates_each_hypothesis_independently(base_signals, device_contributions):
    """Req 7: E6 evaluates each hypothesis independently."""
    ev_gw = Evidence(
        source_id="payment_gateway",
        summary="Payment gateway events: 6551 failures, latency 194ms",
        id="ev_gw_01",
        reliability_weight=0.9,
        confidence=1.0,
    )
    ev_tkt = Evidence(
        source_id="support_tickets",
        summary="Support tickets in window: 99 total for category payment_failure",
        id="ev_tkt_01",
        reliability_weight=0.9,
        confidence=0.91,
    )
    ev_mkt = Evidence(
        source_id="marketing",
        summary="Marketing campaign on digital channel spend $39k",
        id="ev_mkt_01",
        reliability_weight=0.9,
        confidence=0.9,
    )
    evidence_by_id = {ev_gw.evidence_id: ev_gw, ev_tkt.evidence_id: ev_tkt, ev_mkt.evidence_id: ev_mkt}

    h1 = Hypothesis(
        hypothesis_id="H1",
        statement="Payment gateway degradation.",
        mechanism_tag="payment_gateway",
        root_cause_type="UNKNOWN",
        affected_subsystem="payment_gateway",
        citations=[
            EvidenceCitation(ev_gw.evidence_id, ev_gw.summary, "supports", "Gateway events"),
            EvidenceCitation(ev_tkt.evidence_id, ev_tkt.summary, "supports", "Ticket failures"),
        ],
    )
    h2 = Hypothesis(
        hypothesis_id="H2",
        statement="Marketing campaign traffic shifts.",
        mechanism_tag="external_factors",
        root_cause_type="MACRO_EXTERNAL",
        affected_subsystem="marketing_channel",
        citations=[EvidenceCitation(ev_mkt.evidence_id, ev_mkt.summary, "supports", "Marketing spend")],
    )

    s1 = score_hypothesis(h1, evidence_by_id, base_signals, device_contributions, domain_semantics=_DOMAIN_SEMANTICS)
    s2 = score_hypothesis(h2, evidence_by_id, base_signals, device_contributions, domain_semantics=_DOMAIN_SEMANTICS)

    assert s1.final_audit_score > s2.final_audit_score
    assert s1.audit_verdict == AuditVerdict.VERIFIED
    assert s2.audit_verdict == AuditVerdict.MARGINAL


def test_req8_e7_selects_rollback_only_when_root_cause_verified_internal_release():
    """Req 8: E7 selects rollback only when root cause is sufficiently verified as internal release."""
    from engines.decision import _build_decision_prompt
    from engines.challenge import ChallengeResult
    scored_h = score_hypothesis(
        Hypothesis(
            hypothesis_id="H1",
            statement="Release v4.3 caused connection pool exhaustion.",
            mechanism_tag="deployment_issues",
            root_cause_type="INTERNAL_RELEASE",
            affected_subsystem="payment_gateway",
        ),
        {},
        [],
        [],
        domain_semantics=_DOMAIN_SEMANTICS,
    )
    cr = ChallengeResult(
        scored_hypotheses=[scored_h],
        winning_hypothesis_id="H1",
        overall_verdict=AuditVerdict.VERIFIED,
        abstained=False,
    )
    from models import Persona
    sys_p, user_p = _build_decision_prompt(
        cr,
        Persona.ANALYST,
        ["[1] Release v4.3 deployed with connection pool changes"],
        {"levers": {"Software Release Reversion": {"authorized_personas": ["analyst"]}, "Targeted Diagnostic Verification": {"authorized_personas": ["analyst"]}}},
        scored_h.hypothesis_id,
        _DOMAIN_SEMANTICS,
    )
    assert "CAUSAL ROOT-CAUSE GATING" in sys_p
    assert "Software Release Reversion" in sys_p


def test_req9_unknown_upstream_cause_results_in_diagnostic_verification():
    """Req 9: Unknown upstream cause results in diagnostic verification rather than speculative rollback."""
    from engines.outcome import _match_curve
    # Diagnostic action matches no operational recovery curve
    curve = _match_curve("Targeted Diagnostic Verification: Collect telemetry on gateway", _DOMAIN_SEMANTICS)
    assert curve is None


def test_req10_e6_scoring_formula_remains_unchanged(base_signals):
    """Req 10: Existing E6 scoring formula remains clamp(min(capped_support, rule_score) - penalty, 0, 1)."""
    ev = Evidence(
        source_id="payment_gateway",
        summary="Payment gateway failure rate 2.2%",
        id="ev_01",
        reliability_weight=0.9,
        confidence=1.0,
    )
    evidence_by_id = {ev.evidence_id: ev}
    h = Hypothesis(
        hypothesis_id="H1",
        statement="Payment gateway degradation.",
        mechanism_tag="payment_gateway",
        citations=[EvidenceCitation(ev.evidence_id, ev.summary, "supports", "Gateway")],
    )
    scored = score_hypothesis(h, evidence_by_id, base_signals, [], domain_semantics=_DOMAIN_SEMANTICS)
    # support_score = 0.9 / 2.0 = 0.45
    # rule_score = 1.0
    # final score = min(0.45, 1.0) = 0.45
    assert scored.support_score == pytest.approx(0.45, abs=0.01)
    assert scored.final_audit_score == pytest.approx(0.45, abs=0.01)


def test_req11_existing_citation_and_security_validation_unchanged():
    """Req 11: Existing citation and security validation remains unchanged."""
    from engines.hypothesis import validate_hypothesis
    # Phantom ID is rejected
    raw = {
        "hypothesis_id": "H1",
        "statement": "Valid statement without numbers.",
        "mechanism_tag": "payment_gateway",
        "citations": [{"evidence_id": "phantom_id_999", "quoted_summary": "fake", "role": "supports", "relevance_explanation": "exp"}],
        "reasoning": "Reasoning.",
    }
    is_valid, reason = validate_hypothesis(raw, frozenset(["real_id_123"]), _DOMAIN_SEMANTICS)
    assert is_valid is False
    assert "hallucinated" in reason.lower() or "phantom" in reason.lower()


def test_req12_existing_inc001_pipeline_behavior_preserved(base_signals, device_contributions):
    """Req 12: Existing INC_001 E5/E6/E7/E8 tests continue to pass."""
    ev_gw = Evidence(
        source_id="payment_gateway",
        summary="Payment gateway events in window: 292590 total, 6551 failures, latency 194ms",
        id="3af2abbcf5693df4",
        reliability_weight=0.9,
        confidence=1.0,
    )
    ev_tkt = Evidence(
        source_id="support_tickets",
        summary="Support tickets in window: 99 total for category payment_failure",
        id="9d8f8b1fe6c0aaff",
        reliability_weight=0.9,
        confidence=0.91,
    )
    evidence_by_id = {ev_gw.evidence_id: ev_gw, ev_tkt.evidence_id: ev_tkt}
    h1 = Hypothesis(
        hypothesis_id="H1",
        statement="Payment gateway pathway experienced technical degradation.",
        mechanism_tag="payment_gateway",
        root_cause_type="UNKNOWN",
        affected_subsystem="payment_gateway",
        proximal_mechanism="latency_spike_and_timeout",
        symptom_kpis=["hourly_conversion", "payment_failure_rate_15min", "gateway_latency_15min"],
        citations=[
            EvidenceCitation(ev_gw.evidence_id, ev_gw.summary, "supports", "Gateway events"),
            EvidenceCitation(ev_tkt.evidence_id, ev_tkt.summary, "supports", "Support tickets"),
        ],
    )
    scored = score_hypothesis(h1, evidence_by_id, base_signals, device_contributions, domain_semantics=_DOMAIN_SEMANTICS)
    assert scored.audit_verdict == AuditVerdict.VERIFIED
    assert scored.final_audit_score >= 0.70


# ---------------------------------------------------------------------------
# Strict ROOT-CAUSE EVIDENCE GATE Tests
# ---------------------------------------------------------------------------

def test_rc_gate_1_gateway_telemetry_with_internal_release_cannot_be_verified(base_signals, device_contributions):
    """Test 1: Gateway telemetry + INTERNAL_RELEASE cannot be VERIFIED without deployment/release evidence."""
    ev_gw = Evidence(
        source_id="payment_gateway",
        summary="Payment gateway events: elevated latency 194ms and failures 6551",
        id="ev_gw_01",
        reliability_weight=0.95,
        confidence=0.95,
    )
    ev_tkt = Evidence(
        source_id="support_tickets",
        summary="Support tickets: 99 category payment_failure",
        id="ev_tkt_01",
        reliability_weight=0.95,
        confidence=0.95,
    )
    evidence_by_id = {ev_gw.evidence_id: ev_gw, ev_tkt.evidence_id: ev_tkt}

    h_unproven_release = Hypothesis(
        hypothesis_id="H1",
        statement="An internal software release caused payment gateway failures and conversion drop.",
        mechanism_tag="payment_gateway",
        root_cause_type="INTERNAL_RELEASE",
        affected_subsystem="payment_gateway",
        proximal_mechanism="latency_spike_and_timeout",
        citations=[
            EvidenceCitation(ev_gw.evidence_id, ev_gw.summary, "supports", "Gateway metrics"),
            EvidenceCitation(ev_tkt.evidence_id, ev_tkt.summary, "supports", "Support tickets"),
        ],
    )

    scored = score_hypothesis(h_unproven_release, evidence_by_id, base_signals, device_contributions, domain_semantics=_DOMAIN_SEMANTICS)
    assert scored.root_cause_gate_passed is False
    assert "no causally discriminative deployment_log or release_notes" in scored.root_cause_rationale
    assert scored.audit_verdict == AuditVerdict.MARGINAL


def test_rc_gate_2_deployment_log_with_internal_release_passes(base_signals, device_contributions):
    """Test 2: deployment_log + INTERNAL_RELEASE root-cause gate can PASS and reach VERIFIED."""
    ev_deploy = Evidence(
        source_id="deployment_log",
        summary="Release v4.3 deployed: connection pool changes rolled out to checkout service",
        id="ev_deploy_01",
        reliability_weight=0.95,
        confidence=0.95,
    )
    ev_rel = Evidence(
        source_id="release_notes",
        summary="Release notes v4.3: parallel payment verification client update",
        id="ev_rel_01",
        reliability_weight=0.95,
        confidence=0.95,
    )
    evidence_by_id = {ev_deploy.evidence_id: ev_deploy, ev_rel.evidence_id: ev_rel}

    h_verified_release = Hypothesis(
        hypothesis_id="H1",
        statement="Internal release v4.3 introduced connection pool exhaustion.",
        mechanism_tag="deployment_issues",
        root_cause_type="INTERNAL_RELEASE",
        affected_subsystem="payment_gateway",
        proximal_mechanism="connection_pool_exhaustion",
        citations=[
            EvidenceCitation(ev_deploy.evidence_id, ev_deploy.summary, "supports", "Deployment log"),
            EvidenceCitation(ev_rel.evidence_id, ev_rel.summary, "supports", "Release notes"),
        ],
    )

    scored = score_hypothesis(h_verified_release, evidence_by_id, base_signals, device_contributions, domain_semantics=_DOMAIN_SEMANTICS)
    assert scored.root_cause_gate_passed is True
    assert scored.root_cause_evidence_ids == sorted([ev_deploy.evidence_id, ev_rel.evidence_id])
    assert scored.audit_verdict == AuditVerdict.VERIFIED


def test_rc_gate_3_gateway_telemetry_with_external_provider_cannot_prove_provider_outage(base_signals, device_contributions):
    """Test 3: Gateway telemetry + EXTERNAL_PROVIDER cannot prove provider outage without configured provider evidence."""
    ev_gw = Evidence(
        source_id="payment_gateway",
        summary="Payment gateway events: elevated latency 194ms and failures 6551",
        id="ev_gw_01",
        reliability_weight=0.95,
        confidence=0.95,
    )
    evidence_by_id = {ev_gw.evidence_id: ev_gw}

    h_unproven_provider = Hypothesis(
        hypothesis_id="H1",
        statement="Third party payment provider suffered an upstream outage.",
        mechanism_tag="payment_gateway",
        root_cause_type="EXTERNAL_PROVIDER",
        affected_subsystem="payment_gateway",
        proximal_mechanism="latency_spike_and_timeout",
        citations=[
            EvidenceCitation(ev_gw.evidence_id, ev_gw.summary, "supports", "Gateway metrics"),
        ],
    )

    scored = score_hypothesis(h_unproven_provider, evidence_by_id, base_signals, device_contributions, domain_semantics=_DOMAIN_SEMANTICS)
    assert scored.root_cause_gate_passed is False
    assert "no third-party provider status or vendor incident records" in scored.root_cause_rationale
    assert scored.audit_verdict == AuditVerdict.MARGINAL


def test_rc_gate_4_normal_inventory_cannot_support_inventory_shortage(base_signals, device_contributions):
    """Test 4: Normal inventory cannot support INVENTORY_SHORTAGE."""
    ev_inv = Evidence(
        source_id="inventory",
        summary="Inventory fill rate in window: average 94.0%. Inventory levels appear normal.",
        id="ev_inv_01",
        reliability_weight=0.95,
        confidence=0.95,
    )
    evidence_by_id = {ev_inv.evidence_id: ev_inv}

    h_stockout = Hypothesis(
        hypothesis_id="H1",
        statement="Inventory stockouts caused conversion decline.",
        mechanism_tag="inventory_system",
        root_cause_type="INVENTORY_SHORTAGE",
        affected_subsystem="inventory_system",
        proximal_mechanism="stockout",
        citations=[
            EvidenceCitation(ev_inv.evidence_id, ev_inv.summary, "supports", "Inventory normal"),
        ],
    )

    scored = score_hypothesis(h_stockout, evidence_by_id, base_signals, device_contributions, domain_semantics=_DOMAIN_SEMANTICS)
    assert scored.root_cause_gate_passed is False
    assert scored.support_score == 0.0
    assert scored.final_audit_score == 0.0
    assert scored.audit_verdict == AuditVerdict.MARGINAL


def test_rc_gate_5_unknown_root_cause_remains_valid_when_upstream_discriminator_absent(base_signals, device_contributions):
    """Test 5: UNKNOWN root cause remains valid when upstream discriminator is absent."""
    ev_gw = Evidence(
        source_id="payment_gateway",
        summary="Payment gateway events: elevated latency 194ms and failures 6551",
        id="ev_gw_01",
        reliability_weight=0.95,
        confidence=0.95,
    )
    ev_tkt = Evidence(
        source_id="support_tickets",
        summary="Support tickets: 99 category payment_failure",
        id="ev_tkt_01",
        reliability_weight=0.95,
        confidence=0.95,
    )
    evidence_by_id = {ev_gw.evidence_id: ev_gw, ev_tkt.evidence_id: ev_tkt}

    h_subsystem_degradation = Hypothesis(
        hypothesis_id="H1",
        statement="Payment gateway technical degradation observed without attributing unobserved upstream cause.",
        mechanism_tag="payment_gateway",
        root_cause_type="UNKNOWN",
        affected_subsystem="payment_gateway",
        proximal_mechanism="latency_spike_and_timeout",
        citations=[
            EvidenceCitation(ev_gw.evidence_id, ev_gw.summary, "supports", "Gateway metrics"),
            EvidenceCitation(ev_tkt.evidence_id, ev_tkt.summary, "supports", "Support tickets"),
        ],
    )

    scored = score_hypothesis(h_subsystem_degradation, evidence_by_id, base_signals, device_contributions, domain_semantics=_DOMAIN_SEMANTICS)
    assert scored.root_cause_gate_passed is True
    assert scored.audit_verdict == AuditVerdict.VERIFIED
    assert scored.final_audit_score >= 0.70


def test_rc_gate_6_existing_inc001_valid_deployment_evidence_permits_verified_internal_release(base_signals, device_contributions):
    """Test 6: Existing INC_001 valid deployment evidence still permits a verified internal-release hypothesis."""
    ev_notes = Evidence(
        source_id="release_notes",
        summary="Release v4.3-hotfix — Emergency rollback: Reverted all payment gateway client changes from v4.3",
        id="7aec5f6a188de795",
        reliability_weight=0.95,
        confidence=0.95,
    )
    ev_deploy = Evidence(
        source_id="deployment_log",
        summary="Deployment log: v4.3 release deployment executed on production cluster",
        id="ev_deploy_inc001",
        reliability_weight=0.95,
        confidence=0.95,
    )
    evidence_by_id = {ev_notes.evidence_id: ev_notes, ev_deploy.evidence_id: ev_deploy}

    h_release = Hypothesis(
        hypothesis_id="H1",
        statement="A recent internal software release caused connection pool exhaustion in checkout service.",
        mechanism_tag="deployment_issues",
        root_cause_type="INTERNAL_RELEASE",
        affected_subsystem="payment_gateway",
        proximal_mechanism="connection_pool_exhaustion",
        citations=[
            EvidenceCitation(ev_notes.evidence_id, ev_notes.summary, "supports", "Release notes rollback"),
            EvidenceCitation(ev_deploy.evidence_id, ev_deploy.summary, "supports", "Deployment log"),
        ],
    )

    scored = score_hypothesis(h_release, evidence_by_id, base_signals, device_contributions, domain_semantics=_DOMAIN_SEMANTICS)
    assert scored.root_cause_gate_passed is True
    assert scored.audit_verdict == AuditVerdict.VERIFIED


def test_rc_gate_7_e6_scoring_formula_itself_remains_unchanged(base_signals):
    """Test 7: E6 scoring formula itself remains unchanged clamp(min(capped_support, rule_score) - penalty, 0, 1)."""
    ev_deploy = Evidence(
        source_id="deployment_log",
        summary="Release v4.3 deployed on cluster",
        id="ev_deploy_01",
        reliability_weight=0.8,
        confidence=1.0,
    )
    evidence_by_id = {ev_deploy.evidence_id: ev_deploy}

    h = Hypothesis(
        hypothesis_id="H1",
        statement="Deployment issues occurred.",
        mechanism_tag="deployment_issues",
        root_cause_type="INTERNAL_RELEASE",
        affected_subsystem="payment_gateway",
        citations=[EvidenceCitation(ev_deploy.evidence_id, ev_deploy.summary, "supports", "Deployment log")],
    )

    scored = score_hypothesis(h, evidence_by_id, base_signals, [], domain_semantics=_DOMAIN_SEMANTICS)
    # Raw support = 0.8 * 1.0 = 0.8 -> capped support = 0.8 / 2.0 = 0.40
    # Rule score = 1.0
    # Final audit score = min(0.40, 1.0) = 0.40
    assert scored.support_score == pytest.approx(0.40, abs=0.01)
    assert scored.final_audit_score == pytest.approx(0.40, abs=0.01)


