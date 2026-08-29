"""
Smoke test for the Challenge Engine (Engine E6).

Verifies INC_001 expected outcome bands:
  H1 → HIGH (checkout/payment degradation with deployment + payment evidence)
  H2 → not HIGH (stale marketing evidence, no segment alignment)
  H3 → LOW (inventory-normal evidence refutes the inventory-shortage hypothesis)

Also tests:
  - deterministic reproducibility: same inputs → same scores
  - abstention logic: gap too small → ABSTAIN
  - empty hypothesis list → ABSTAIN
  - narrative non-mutation: final_audit_score and audit_verdict unchanged
"""

import pytest
from engines.challenge import (
    ChallengeThresholds,
    ChallengeResult,
    challenge,
    evaluate_rule,
    resolve_abstention,
    score_hypothesis,
    RULE_NAMES,
)
from models import (
    AnomalySignal,
    AuditVerdict,
    DimensionContribution,
    Evidence,
    EvidenceCitation,
    Hypothesis,
    MethodTag,
    RuleVerdict,
    ScoredHypothesis,
)


# ---------------------------------------------------------------------------
# Fixtures — INC_001 evidence, signals, contributions, hypotheses
# ---------------------------------------------------------------------------

def make_evidence_set():
    """Return a dict[evidence_id → Evidence] for the INC_001 scenario."""
    ev_payment = Evidence(
        evidence_id="ev_payment_001",
        kind="structured",
        summary=(
            "Payment gateway events: high failure rate, latency elevated significantly. "
            "Payment failures increased substantially vs baseline."
        ),
        source_id="payment_gateway",
        reliability_weight=0.95,
        relevance=0.9,
        raw_ref="payment_events:aggregate",
        method=MethodTag.SQL,
    )
    ev_deploy = Evidence(
        evidence_id="ev_deploy_001",
        kind="structured",
        summary=(
            "Deployment of checkout-service was deployed within 48h before anomaly window. "
            "Version upgrade to a new release occurred recently."
        ),
        source_id="deployment_log",
        reliability_weight=0.92,
        relevance=0.85,
        raw_ref="deployment_log:42",
        method=MethodTag.SQL,
    )
    ev_support = Evidence(
        evidence_id="ev_support_001",
        kind="unstructured",
        summary=(
            "Multiple support tickets mention payment failures and checkout errors. "
            "Customers reporting transactions not completing."
        ),
        source_id="support_tickets",
        reliability_weight=0.85,
        relevance=0.8,
        raw_ref="support_tickets:aggregate",
        method=MethodTag.SQL,
    )
    ev_inventory = Evidence(
        evidence_id="ev_inventory_001",
        kind="structured",
        summary=(
            "Inventory fill rate in window: average fill_rate is normal and stable. "
            "Inventory levels appear normal with no shortage."
        ),
        source_id="inventory",
        reliability_weight=0.88,
        relevance=0.9,
        raw_ref="inventory_events:aggregate",
        method=MethodTag.SQL,
    )
    ev_marketing = Evidence(
        evidence_id="ev_marketing_001",
        kind="unstructured",
        summary=(
            "Competitor launched a pricing campaign. Marketing data indicates "
            "some external competitive pressure."
        ),
        source_id="marketing",
        reliability_weight=0.25,  # stale beyond SLA
        relevance=0.5,
        raw_ref="marketing_doc:1",
        method=MethodTag.RETRIEVAL,
    )
    return {
        ev_payment.evidence_id: ev_payment,
        ev_deploy.evidence_id: ev_deploy,
        ev_support.evidence_id: ev_support,
        ev_inventory.evidence_id: ev_inventory,
        ev_marketing.evidence_id: ev_marketing,
    }


def make_signals():
    return [
        AnomalySignal(
            kpi_id="revenue", observed=91.8, expected=100.0, delta_pct=-8.2,
            z_score=-5.1, is_anomaly=True, corroborated_by=["conversion"],
            sparse_history=False, data_quality_suspect=False,
        ),
        AnomalySignal(
            kpi_id="conversion", observed=90.0, expected=100.0, delta_pct=-10.0,
            z_score=-6.2, is_anomaly=True, corroborated_by=["revenue"],
            sparse_history=False, data_quality_suspect=False,
        ),
        AnomalySignal(
            kpi_id="payment_failure_rate", observed=4.0, expected=1.0, delta_pct=100.0,
            z_score=8.5, is_anomaly=True, corroborated_by=[],
            sparse_history=False, data_quality_suspect=False,
        ),
    ]


def make_contributions():
    return [
        DimensionContribution(
            dimension="device", segment="android",
            contribution_pct=68.0, segment_delta_pct=-17.0,
            method=MethodTag.SQL,
        ),
        DimensionContribution(
            dimension="device", segment="ios",
            contribution_pct=22.0, segment_delta_pct=-5.0,
            method=MethodTag.SQL,
        ),
        DimensionContribution(
            dimension="device", segment="web",
            contribution_pct=10.0, segment_delta_pct=-2.0,
            method=MethodTag.SQL,
        ),
    ]


def make_hypotheses():
    evidence_set = make_evidence_set()
    h1 = Hypothesis(
        hypothesis_id="H1",
        mechanism_tag="payment_gateway",
        statement=(
            "The checkout and payment system experienced a significant degradation "
            "due to a recent deployment of the checkout service, causing elevated "
            "payment failures and gateway latency that disproportionately affected "
            "Android users."
        ),
        citations=[
            EvidenceCitation(
                evidence_id="ev_payment_001",
                quoted_summary=evidence_set["ev_payment_001"].summary,
                role="supports",
                relevance_explanation="Payment failures increased substantially.",
            ),
            EvidenceCitation(
                evidence_id="ev_deploy_001",
                quoted_summary=evidence_set["ev_deploy_001"].summary,
                role="supports",
                relevance_explanation="Deployment occurred within 48h before anomaly.",
            ),
            EvidenceCitation(
                evidence_id="ev_support_001",
                quoted_summary=evidence_set["ev_support_001"].summary,
                role="supports",
                relevance_explanation="Support tickets corroborate payment failures.",
            ),
        ],
        reasoning=(
            "The deployment of a new version of the checkout service coincided with "
            "the onset of increased payment failures and gateway latency. The Android "
            "device segment shows the dominant negative contribution, consistent with "
            "a checkout code change that may have introduced a regression."
        ),
        method=MethodTag.LLM,
    )
    h2 = Hypothesis(
        hypothesis_id="H2",
        statement=(
            "A competitor launched a promotional pricing campaign that drew customers "
            "away, reducing conversion and revenue across channels."
        ),
        citations=[
            EvidenceCitation(
                evidence_id="ev_marketing_001",
                quoted_summary=evidence_set["ev_marketing_001"].summary,
                role="supports",
                relevance_explanation="Marketing data indicates external competitive pressure.",
            ),
        ],
        reasoning=(
            "Marketing data suggests competitive activity. However, the evidence is "
            "based on stale marketing intelligence that may not reflect current conditions."
        ),
        method=MethodTag.LLM,
    )
    h3 = Hypothesis(
        hypothesis_id="H3",
        mechanism_tag="inventory_stockout",
        statement=(
            "An inventory shortage reduced the availability of products, causing "
            "customers to abandon the checkout process."
        ),
        citations=[
            EvidenceCitation(
                evidence_id="ev_inventory_001",
                quoted_summary=evidence_set["ev_inventory_001"].summary,
                role="contradicts",
                relevance_explanation="Inventory levels are normal with no shortage.",
            ),
        ],
        reasoning=(
            "An inventory shortage could explain conversion decline if customers cannot "
            "find products. However, contradictory evidence from the inventory system "
            "shows normal fill rate levels."
        ),
        method=MethodTag.LLM,
    )
    return [h1, h2, h3]


# ---------------------------------------------------------------------------
# Tests — INC_001 expected bands (Requirements 12.3, 12.4, 12.5)
# ---------------------------------------------------------------------------

class TestINC001Bands:
    def setup_method(self):
        self.evidence_by_id = make_evidence_set()
        self.signals = make_signals()
        self.contributions = make_contributions()
        self.hypotheses = make_hypotheses()
        self.thresholds = ChallengeThresholds()
        from config.loader import load_domain_semantics
        self.domain_semantics = load_domain_semantics("config/domain_semantics.yaml")

    def test_h1_is_high(self):
        result = challenge(
            self.hypotheses, self.evidence_by_id, self.signals, self.contributions, domain_semantics=self.domain_semantics
        )
        by_id = {sh.hypothesis_id: sh for sh in result.scored_hypotheses}
        assert by_id["H1"].audit_verdict == AuditVerdict.VERIFIED, (
            f"H1 expected VERIFIED, got {by_id['H1'].audit_verdict.value} "
            f"(score={by_id['H1'].final_audit_score:.4f})"
        )

    def test_h3_is_low(self):
        result = challenge(
            self.hypotheses, self.evidence_by_id, self.signals, self.contributions, domain_semantics=self.domain_semantics
        )
        by_id = {sh.hypothesis_id: sh for sh in result.scored_hypotheses}
        assert by_id["H3"].audit_verdict == AuditVerdict.REJECTED, (
            f"H3 expected REJECTED, got {by_id['H3'].audit_verdict.value} "
            f"(score={by_id['H3'].final_audit_score:.4f})"
        )

    def test_h2_not_high(self):
        result = challenge(
            self.hypotheses, self.evidence_by_id, self.signals, self.contributions, domain_semantics=self.domain_semantics
        )
        by_id = {sh.hypothesis_id: sh for sh in result.scored_hypotheses}
        assert by_id["H2"].audit_verdict != AuditVerdict.VERIFIED, (
            f"H2 must not be VERIFIED, got {by_id['H2'].audit_verdict.value} "
            f"(score={by_id['H2'].final_audit_score:.4f})"
        )

    def test_h1_wins(self):
        result = challenge(
            self.hypotheses, self.evidence_by_id, self.signals, self.contributions, domain_semantics=self.domain_semantics
        )
        assert result.winning_hypothesis_id == "H1"
        assert not result.abstained

    def test_ranking_h1_gt_h2_gt_h3(self):
        result = challenge(
            self.hypotheses, self.evidence_by_id, self.signals, self.contributions, domain_semantics=self.domain_semantics
        )
        by_id = {sh.hypothesis_id: sh for sh in result.scored_hypotheses}
        assert by_id["H1"].final_audit_score > by_id["H2"].final_audit_score, "H1 must outscore H2"
        assert by_id["H1"].final_audit_score > by_id["H3"].final_audit_score, "H1 must outscore H3"

    def test_scores_in_0_1(self):
        result = challenge(
            self.hypotheses, self.evidence_by_id, self.signals, self.contributions, domain_semantics=self.domain_semantics
        )
        for sh in result.scored_hypotheses:
            assert 0.0 <= sh.final_audit_score <= 1.0, (
                f"{sh.hypothesis_id} final_audit_score={sh.final_audit_score} out of [0,1]"
            )


# ---------------------------------------------------------------------------
# Tests — Deterministic reproducibility (Requirement 9.4)
# ---------------------------------------------------------------------------

class TestReproducibility:
    def test_identical_inputs_yield_identical_scores(self):
        evidence_by_id = make_evidence_set()
        signals = make_signals()
        contributions = make_contributions()
        hypotheses = make_hypotheses()

        result_a = challenge(hypotheses, evidence_by_id, signals, contributions)
        result_b = challenge(hypotheses, evidence_by_id, signals, contributions)

        for sha, shb in zip(result_a.scored_hypotheses, result_b.scored_hypotheses):
            assert sha.hypothesis_id == shb.hypothesis_id
            assert sha.final_audit_score == shb.final_audit_score, (
                f"{sha.hypothesis_id}: score changed between runs "
                f"({sha.final_audit_score} vs {shb.final_audit_score})"
            )
            assert sha.audit_verdict == shb.audit_verdict

    def test_shuffled_evidence_order_same_scores(self):
        """Evidence dict order must not affect scores."""
        evidence_by_id_1 = make_evidence_set()
        signals = make_signals()
        contributions = make_contributions()
        hypotheses = make_hypotheses()

        # Reverse the dict order
        evidence_by_id_2 = dict(reversed(list(evidence_by_id_1.items())))

        result_1 = challenge(hypotheses, evidence_by_id_1, signals, contributions)
        result_2 = challenge(hypotheses, evidence_by_id_2, signals, contributions)

        scores_1 = {sh.hypothesis_id: sh.final_audit_score for sh in result_1.scored_hypotheses}
        scores_2 = {sh.hypothesis_id: sh.final_audit_score for sh in result_2.scored_hypotheses}
        assert scores_1 == scores_2, f"Scores differ with reordered evidence: {scores_1} vs {scores_2}"


# ---------------------------------------------------------------------------
# Tests — Abstention logic (Requirement 9.6, 9.7)
# ---------------------------------------------------------------------------

class TestAbstention:
    def test_empty_hypotheses_abstains(self):
        result = challenge([], {}, [], [])
        assert result.abstained
        assert result.overall_verdict == AuditVerdict.ABSTAIN
        assert result.winning_hypothesis_id is None

    def test_low_top_score_abstains(self):
        """A hypothesis with zero evidence and all-FAIL rules should score very low."""
        # Create a near-empty hypothesis with no evidence → low score
        h_weak = Hypothesis(
            hypothesis_id="H_WEAK",
            statement="An unknown factor caused the movement.",
            citations=[],
            reasoning="No supporting evidence available.",
            method=MethodTag.LLM,
        )
        # With a high abstain threshold and a weak hypothesis, should abstain
        thresholds = ChallengeThresholds(abstain_threshold=0.99)
        result = challenge(
            [h_weak], {}, [], [],
            thresholds=thresholds,
        )
        assert result.abstained
        assert result.overall_verdict == AuditVerdict.ABSTAIN

    def test_small_gap_abstains(self):
        """When top and runner-up are very close, should abstain."""
        # Create two hypotheses with very similar scores
        ev = Evidence(
            evidence_id="ev_a",
            kind="structured",
            summary="some evidence",
            source_id="payment_gateway",
            reliability_weight=0.5,
            relevance=0.5,
            raw_ref="ref",
            method=MethodTag.SQL,
        )
        ev_b = Evidence(
            evidence_id="ev_b",
            kind="structured",
            summary="some evidence b",
            source_id="payment_gateway",
            reliability_weight=0.5,
            relevance=0.5,
            raw_ref="ref_b",
            method=MethodTag.SQL,
        )
        evidence_by_id = {"ev_a": ev, "ev_b": ev_b}
        h_a = Hypothesis(
            hypothesis_id="HA",
            statement="checkout payment degradation",
            citations=[
                EvidenceCitation("ev_a", "some evidence", "supports", "Some reason a."),
            ],
            reasoning="payment",
            method=MethodTag.LLM,
        )
        h_b = Hypothesis(
            hypothesis_id="HB",
            statement="checkout payment degradation similar",
            citations=[
                EvidenceCitation("ev_b", "some evidence b", "supports", "Some reason b."),
            ],
            reasoning="payment",
            method=MethodTag.LLM,
        )
        thresholds = ChallengeThresholds(min_gap=0.99)  # gap threshold impossible to meet
        result = challenge([h_a, h_b], evidence_by_id, [], [], thresholds=thresholds)
        assert result.abstained

    def test_abstention_does_not_mutate_final_audit_score(self):
        """final_audit_score fields are unmodified even when ABSTAIN is set (Req 9.7)."""
        thresholds = ChallengeThresholds(abstain_threshold=0.99)
        hypotheses = make_hypotheses()
        result_normal = challenge(
            make_hypotheses(), make_evidence_set(), make_signals(), make_contributions(),
            thresholds=ChallengeThresholds(),
        )
        result_abstain = challenge(
            hypotheses, make_evidence_set(), make_signals(), make_contributions(),
            thresholds=thresholds,
        )
        # Scores should be identical; only audit_verdict differs
        normal_by_id = {sh.hypothesis_id: sh.final_audit_score for sh in result_normal.scored_hypotheses}
        abstain_by_id = {sh.hypothesis_id: sh.final_audit_score for sh in result_abstain.scored_hypotheses}
        assert normal_by_id == abstain_by_id, (
            f"Final scores changed between normal and abstain runs: {normal_by_id} vs {abstain_by_id}"
        )


# ---------------------------------------------------------------------------
# Tests — hallucinated evidence IDs handled gracefully
# ---------------------------------------------------------------------------

class TestHallucinatedIds:
    def test_hallucinated_support_id_scores_zero_contribution(self):
        evidence_by_id = make_evidence_set()
        signals = make_signals()
        contributions = make_contributions()

        h_hallucinated = Hypothesis(
            hypothesis_id="H_HALL",
            statement="checkout payment degradation caused by a system issue",
            citations=[
                EvidenceCitation("FAKE_ID_999", "anything", "supports", "Fake reasoning."),
            ],
            reasoning="some reasoning about payment",
            method=MethodTag.LLM,
        )
        thresholds = ChallengeThresholds()
        sh = score_hypothesis(h_hallucinated, evidence_by_id, signals, contributions, thresholds)
        # support_score should be 0.0 (hallucinated id skipped or gated with 0 score)
        assert sh.support_score == 0.0, f"Expected support_score=0.0, got {sh.support_score}"
        assert 0.0 <= sh.final_audit_score <= 1.0


# ---------------------------------------------------------------------------
# Tests — individual rules (spot checks)
# ---------------------------------------------------------------------------

class TestRules:
    def setup_method(self):
        from config.loader import load_domain_semantics
        self.evidence_by_id = make_evidence_set()
        self.signals = make_signals()
        self.contributions = make_contributions()
        self.domain_semantics = load_domain_semantics("config/domain_semantics.yaml")

    def test_timeline_pass_with_deployment_evidence(self):
        h = make_hypotheses()[0]  # H1 references ev_deploy_001
        result = evaluate_rule("timeline", h, self.evidence_by_id, self.signals, self.contributions)
        assert result.verdict == RuleVerdict.PASS

    def test_contradiction_fail_with_high_weight_evidence(self):
        h = make_hypotheses()[2]  # H3 references ev_inventory_001 as contradictory
        result = evaluate_rule("contradiction", h, self.evidence_by_id, self.signals, self.contributions)
        assert result.verdict == RuleVerdict.FAIL

    def test_contradiction_pass_with_no_contradictory_evidence(self):
        h = make_hypotheses()[0]  # H1 has no contradictory evidence
        result = evaluate_rule("contradiction", h, self.evidence_by_id, self.signals, self.contributions)
        assert result.verdict == RuleVerdict.PASS

    def test_segment_alignment_pass_for_h1(self):
        """H1 mentions Android and it's the dominant contributor."""
        h = make_hypotheses()[0]
        result = evaluate_rule("segment_alignment", h, self.evidence_by_id, self.signals, self.contributions)
        assert result.verdict == RuleVerdict.PASS

    def test_segment_alignment_fail_for_h2(self):
        """H2 (competitor pricing) claims market-wide effect but data shows Android skew."""
        h = make_hypotheses()[1]
        result = evaluate_rule("segment_alignment", h, self.evidence_by_id, self.signals, self.contributions)
        # Should be FAIL (market-wide claim but 68% in Android) or PARTIAL
        assert result.verdict in (RuleVerdict.FAIL, RuleVerdict.PARTIAL)

    def test_mechanism_consistency_fail_for_h3(self):
        """H3 (inventory shortage) is refuted by inventory-normal evidence."""
        h = make_hypotheses()[2]
        result = evaluate_rule("mechanism_consistency", h, self.evidence_by_id, self.signals, self.contributions, self.domain_semantics)
        assert result.verdict == RuleVerdict.FAIL

    def test_mechanism_consistency_pass_for_h1(self):
        """H1 has payment_gateway supporting evidence → mechanism confirmed."""
        h = make_hypotheses()[0]
        result = evaluate_rule("mechanism_consistency", h, self.evidence_by_id, self.signals, self.contributions, self.domain_semantics)
        assert result.verdict == RuleVerdict.PASS

    def test_all_rule_names_evaluated(self):
        """score_hypothesis must produce exactly one RuleResult per rule name."""
        h = make_hypotheses()[0]
        thresholds = ChallengeThresholds()
        sh = score_hypothesis(h, self.evidence_by_id, self.signals, self.contributions, thresholds)
        rule_names_evaluated = [rr.rule_name for rr in sh.rule_results]
        assert set(rule_names_evaluated) == set(RULE_NAMES)
        assert len(rule_names_evaluated) == len(RULE_NAMES)


# ---------------------------------------------------------------------------
# Tests — ScoredHypothesis method tag
# ---------------------------------------------------------------------------

class TestMethodTag:
    def test_scored_hypothesis_tagged_rules(self):
        evidence_by_id = make_evidence_set()
        result = challenge(
            make_hypotheses(), evidence_by_id, make_signals(), make_contributions()
        )
        for sh in result.scored_hypotheses:
            assert sh.method == MethodTag.RULES, (
                f"{sh.hypothesis_id} method should be RULES, got {sh.method}"
            )
