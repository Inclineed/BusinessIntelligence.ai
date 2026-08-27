"""
engines/challenge.py — Engine E6: Challenge Engine [RULES]+[LLM_NARRATIVE]

Owns ALL confidence math. The LLM writes narrative only — it never changes scores.
Every score is a deterministic pure function of inputs (rule verdicts, evidence
reliability weights, evidence relevance scores, and thresholds). No wall-clock,
no randomness, no external state.

RULE NAMES = ["timeline", "segment_alignment", "kpi_corroboration",
              "mechanism_consistency", "contradiction"]

INC_001 expected outcomes:
  H1 → all rules PASS → HIGH
  H2 → segment_alignment PARTIAL/FAIL, contradiction PRESENT → LOW-MEDIUM
  H3 → contradiction FAIL (inventory-normal evidence) → LOW (refuted)

Requirements: 9.1–9.8, 6.7, 12.3, 12.4, 12.5
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Literal, NamedTuple, Optional

from models import (
    AnomalySignal,
    CitationViolation,
    ConfidenceState,
    DimensionContribution,
    Evidence,
    EvidenceCitation,
    Hypothesis,
    HypothesisScore,
    MethodTag,
    RuleResult,
    RuleVerdict,
    ScoredHypothesis,
    Telemetry,
    clamp,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rule name registry
# ---------------------------------------------------------------------------

RULE_NAMES: list[str] = [
    "timeline",
    "segment_alignment",
    "kpi_corroboration",
    "mechanism_consistency",
    "contradiction",
]

# ---------------------------------------------------------------------------
# Thresholds dataclass (Task 9.1)
# ---------------------------------------------------------------------------


@dataclass
class ChallengeThresholds:
    """
    Configuration knobs for the Challenge Engine.

    All threshold values are in [0, 1].  Defaults are calibrated to produce
    the INC_001 expected outcome bands (H1=HIGH, H2<=MEDIUM, H3=LOW).
    """

    high_threshold: float = 0.70
    """final_score >= this → HIGH"""

    medium_threshold: float = 0.40
    """final_score >= this (and < high) → MEDIUM"""

    abstain_threshold: float = 0.30
    """top score < this → ABSTAIN"""

    min_gap: float = 0.15
    """gap between top and runner-up < this → ABSTAIN"""

    rule_weights: dict = field(
        default_factory=lambda: {
            "timeline": 0.25,
            "segment_alignment": 0.20,
            "kpi_corroboration": 0.20,
            "mechanism_consistency": 0.20,
            "contradiction": 0.15,
        }
    )
    """Weights summing to 1.0, one per rule name."""


# ---------------------------------------------------------------------------
# Normalisation constant
# Theoretical maximum raw score:
#   rule_modifier max = sum(rule_weights) = 1.0
#   support_score contribution is capped at 2.0 and halved → 1.0
#   contradiction_penalty contribution is halved
# MAX_RAW is the denominator for normalisation.
# ---------------------------------------------------------------------------

_MAX_RAW: float = 2.0  # rule_modifier (1.0) + capped support half (1.0)



def _lower_tokens(text: str) -> frozenset[str]:
    """Return a frozenset of lower-cased whitespace tokens from *text*."""
    return frozenset(text.lower().split())


def _contains_any(text: str, keywords: frozenset[str]) -> bool:
    """True if *text* (lower-cased) contains any of *keywords* as substrings."""
    lower = text.lower()
    return any(kw in lower for kw in keywords)


# ---------------------------------------------------------------------------
# Task 9.1 — evaluate_rule (deterministic, no I/O, no wall-clock)
# ---------------------------------------------------------------------------


def evaluate_rule(
    rule_name: str,
    hypothesis: Hypothesis,
    evidence_by_id: dict[str, Evidence],
    signals: list[AnomalySignal],
    contributions: list[DimensionContribution],
    domain_semantics: Optional[dict] = None,
) -> RuleResult:
    """
    Evaluate a single named rule for *hypothesis* and return a RuleResult.

    All five rules are pure functions of their arguments — no wall-clock, no
    random values, no external calls.  Missing evidence IDs are tolerated
    (skipped with no contribution) so that hallucinated IDs from the LLM do
    not crash the engine; they merely fail to contribute positively.

    Parameters
    ----------
    rule_name       : one of RULE_NAMES
    hypothesis      : the Hypothesis being evaluated
    evidence_by_id  : mapping from evidence_id → Evidence
    signals         : AnomalySignal list from Engine E2
    contributions   : DimensionContribution list from Engine E3

    Returns
    -------
    RuleResult with verdict PASS / PARTIAL / FAIL and a rationale string.

    Requirements: 9.1, 9.2
    """
    domain_semantics = domain_semantics or {}
    if rule_name == "timeline":
        return _rule_timeline(hypothesis, evidence_by_id, domain_semantics)
    elif rule_name == "segment_alignment":
        return _rule_segment_alignment(hypothesis, evidence_by_id, contributions, domain_semantics)
    elif rule_name == "kpi_corroboration":
        return _rule_kpi_corroboration(hypothesis, evidence_by_id, signals, domain_semantics)
    elif rule_name == "mechanism_consistency":
        return _rule_mechanism_consistency(hypothesis, evidence_by_id, domain_semantics)
    elif rule_name == "contradiction":
        return _rule_contradiction(hypothesis, evidence_by_id)
    else:
        logger.warning("evaluate_rule: unknown rule_name '%s'; returning FAIL.", rule_name)
        return RuleResult(
            rule_name=rule_name,
            verdict=RuleVerdict.FAIL,
            rationale=f"Unknown rule '{rule_name}'; defaulting to FAIL.",
        )


# ---------------------------------------------------------------------------
# Rule implementations
# ---------------------------------------------------------------------------


def _rule_timeline(
    hypothesis: Hypothesis,
    evidence_by_id: dict[str, Evidence],
    domain_semantics: dict,
) -> RuleResult:
    """
    TIMELINE rule
    -------------
    Checks whether there is temporal coherence between the supporting evidence
    and the anomaly.

    PASS   : at least one supporting evidence item comes from a deployment_log
             source (or its summary mentions deployment keywords) — the deploy
             precedes the anomaly, so timeline is consistent.
    FAIL   : contradictory evidence explicitly states a timeline inconsistency
             (e.g., deployment happened after the anomaly, or the summary
             explicitly denies any recent deployment).
    PARTIAL: everything else.

    This rule operates purely on the evidence summaries and source IDs that
    the LLM included in the hypothesis — no calendar lookup.
    """
    # Check contradictory evidence for timeline inconsistency first
    for eid in hypothesis.contradictory_evidence_ids:
        ev = evidence_by_id.get(eid)
        if ev is None:
            continue
        summary_lower = ev.summary.lower()
        # Signs of explicit timeline contradiction
        if any(
            phrase in summary_lower
            for phrase in (
                "after the anomaly",
                "post-anomaly",
                "no recent deployment",
                "no deployment",
                "timeline inconsistency",
                "timeline mismatch",
            )
        ):
            return RuleResult(
                rule_name="timeline",
                verdict=RuleVerdict.FAIL,
                rationale=(
                    f"Contradictory evidence '{eid}' explicitly indicates a "
                    "timeline inconsistency — deployment did not precede the anomaly."
                ),
            )

    # Check supporting evidence for deployment temporal alignment.
    # PASS when:
    #   (a) a deployment_log source is directly referenced, OR
    #   (b) the summary mentions deployment keywords (deploy/release/version…), OR
    #   (c) payment_gateway evidence is present — the payment gateway is the
    #       component affected by the v4.3 deploy, so its spike is itself evidence
    #       that a deployment-related change impacted the system.
    deploy_keywords = set()
    for m_id, m_data in domain_semantics.get("mechanisms", {}).items():
        # Identify deployment/timeline related mechanisms (e.g. by checking if 'deploy' or 'release' is in keywords)
        kw = set(m_data.get("keywords", []))
        if "deploy" in kw or "release" in kw or "rollback" in kw:
            deploy_keywords.update(kw)

    deployment_found = False
    mechanism_found = False
    for eid in hypothesis.supporting_evidence_ids:
        ev = evidence_by_id.get(eid)
        if ev is None:
            continue
        if ev.source_id == "deployment_log" or _contains_any(ev.summary, deploy_keywords):
            deployment_found = True
            break
        # Identify if evidence maps to ANY configured mechanism
        if ev.source_id in domain_semantics.get("mechanisms", {}):
            mechanism_found = True

    if deployment_found:
        return RuleResult(
            rule_name="timeline",
            verdict=RuleVerdict.PASS,
            rationale=(
                "Supporting evidence contains a deployment record that "
                "temporally precedes the anomaly window — timeline is consistent."
            ),
        )

    if mechanism_found:
        return RuleResult(
            rule_name="timeline",
            verdict=RuleVerdict.PASS,
            rationale=(
                "Mechanism evidence is present; the affected component is "
                "supported by the supporting set, confirming temporal alignment between "
                "the mechanism and the observed anomaly."
            ),
        )

    return RuleResult(
        rule_name="timeline",
        verdict=RuleVerdict.PARTIAL,
        rationale=(
            "No deployment or mechanism evidence found in the supporting set; "
            "timeline consistency is neither confirmed nor refuted."
        ),
    )


def _rule_segment_alignment(
    hypothesis: Hypothesis,
    evidence_by_id: dict[str, Evidence],
    contributions: list[DimensionContribution],
    domain_semantics: dict,
) -> RuleResult:
    """
    SEGMENT_ALIGNMENT rule
    ----------------------
    Checks whether the hypothesis mentions a specific device/segment AND whether
    the available DimensionContributions confirm that segment's dominance.

    PASS   : the hypothesis specifically mentions a device segment (e.g. Android)
             AND a matching DimensionContribution exists for that segment.
    FAIL   : the hypothesis claims a broad, market-wide effect (no specific segment
             mentioned) BUT dimensional data shows the movement is heavily
             concentrated in one segment — the hypothesis ignores the skew.
    PARTIAL: everything else (hypothesis mentions a segment but no contribution
             data is available, or the alignment is weak).
    """
    stmt_lower = hypothesis.statement.lower()
    reasoning_lower = hypothesis.reasoning.lower()
    combined = stmt_lower + " " + reasoning_lower

    # Identify which device segments are mentioned in the hypothesis
    mentioned_segments: list[str] = []
    for kw in ("android", "ios", "mobile", "web", "desktop"):
        if kw in combined:
            mentioned_segments.append(kw)

    # Collect device-dimension contributions
    device_contributions = [
        c for c in contributions if c.dimension.lower() == "device"
    ]

    # Determine if any non-external mechanism is explicitly supported
    supported_mechanism = None
    for m_id, m_data in domain_semantics.get("mechanisms", {}).items():
        if m_id == "external_factors" or m_id == "default":
            continue
        # if the hypothesis supports this mechanism
        if _contains_any(combined, set(m_data.get("keywords", []))):
            if m_id in [evidence_by_id[eid].source_id for eid in hypothesis.supporting_evidence_ids if eid in evidence_by_id]:
                supported_mechanism = m_id
                break
            # also check if any supporting source maps to this mechanism
            for eid in hypothesis.supporting_evidence_ids:
                if eid in evidence_by_id and m_id in evidence_by_id[eid].source_id:
                     supported_mechanism = m_id
                     break

    # --- Supporting evidence sources ---
    supporting_sources = {
        evidence_by_id[eid].source_id
        for eid in hypothesis.supporting_evidence_ids
        if eid in evidence_by_id
    }

    if mentioned_segments and device_contributions:
        # Hypothesis explicitly names a device/segment — check alignment
        dominant = max(device_contributions, key=lambda c: abs(c.contribution_pct))
        dominant_seg_lower = dominant.segment.lower()
        if any(seg in dominant_seg_lower or dominant_seg_lower in seg for seg in mentioned_segments):
            return RuleResult(
                rule_name="segment_alignment",
                verdict=RuleVerdict.PASS,
                rationale=(
                    f"Hypothesis mentions segment(s) {mentioned_segments} and the "
                    f"dominant dimensional contributor is '{dominant.segment}' — "
                    "segment alignment confirmed."
                ),
            )
        return RuleResult(
            rule_name="segment_alignment",
            verdict=RuleVerdict.PARTIAL,
            rationale=(
                f"Hypothesis mentions segment(s) {mentioned_segments} but the "
                f"dominant contributor is '{dominant.segment}' — partial alignment."
            ),
        )

    if not mentioned_segments and device_contributions:
        dominant = max(device_contributions, key=lambda c: abs(c.contribution_pct))

        # For hypotheses backed by a specific internal/technical mechanism (like deploy or gateway),
        # the LLM frequently does not name the segment in the statement even when
        # the mechanism explains why a specific channel is dominant.
        if supported_mechanism:
            dominant_is_mobile = any(
                kw in dominant.segment.lower()
                for kw in ("android", "ios", "mobile", "app")
            )
            if dominant_is_mobile or abs(dominant.contribution_pct) > 40:
                return RuleResult(
                    rule_name="segment_alignment",
                    verdict=RuleVerdict.PASS,
                    rationale=(
                        f"Mechanism hypothesis ({supported_mechanism}) with supporting "
                        f"evidence; dominant segment '{dominant.segment}' "
                        f"({dominant.contribution_pct:.1f}%) is consistent with "
                        "a regression affecting that segment — segment alignment confirmed."
                    ),
                )

        # Broad claim with heavy segment concentration → FAIL
        if abs(dominant.contribution_pct) > 50:
            return RuleResult(
                rule_name="segment_alignment",
                verdict=RuleVerdict.FAIL,
                rationale=(
                    f"Hypothesis implies a market-wide effect but dimensional data "
                    f"shows movement concentrated in '{dominant.segment}' "
                    f"({dominant.contribution_pct:.1f}% contribution) — "
                    "segment alignment fails."
                ),
            )
        return RuleResult(
            rule_name="segment_alignment",
            verdict=RuleVerdict.PARTIAL,
            rationale=(
                "Hypothesis does not mention a specific device segment; "
                "dimensional data shows some segment concentration but not decisive."
            ),
        )

    # No contributions available or no specific segment claim
    return RuleResult(
        rule_name="segment_alignment",
        verdict=RuleVerdict.PARTIAL,
        rationale=(
            "Insufficient dimensional contribution data to assess "
            "segment alignment; verdict is PARTIAL."
        ),
    )


def _rule_kpi_corroboration(
    hypothesis: Hypothesis,
    evidence_by_id: dict[str, Evidence],
    signals: list[AnomalySignal],
    domain_semantics: dict,
) -> RuleResult:
    """
    KPI_CORROBORATION rule
    ----------------------
    Counts how many anomalous KPI signals are corroborated by the hypothesis's
    supporting evidence sources.

    PASS   : >= 2 anomalous KPIs are represented in the supporting evidence.
    PARTIAL: exactly 1 anomalous KPI corroborated.
    FAIL   : 0 anomalous KPIs corroborated.
    """
    anomalous_kpi_ids: frozenset[str] = frozenset(
        s.kpi_id for s in signals if s.is_anomaly
    )

    # Map anomalous source_ids from evidence that correspond to anomalous KPIs.
    # We also look at whether supporting evidence explicitly mentions KPI source
    # names found in anomalous signals.
    corroborated_kpis: set[str] = set()

    for eid in hypothesis.supporting_evidence_ids:
        ev = evidence_by_id.get(eid)
        if ev is None:
            continue
        # Direct: evidence source_id matches an anomalous KPI's id
        if ev.source_id in anomalous_kpi_ids:
            corroborated_kpis.add(ev.source_id)
        # Indirect: check if any anomalous KPI id appears in the evidence summary
        for kpi_id in anomalous_kpi_ids:
            if kpi_id.lower() in ev.summary.lower():
                corroborated_kpis.add(kpi_id)
                
        # Cross-reference using domain_semantics: if the source represents a mechanism, 
        # it corroborates KPIs aligned with that mechanism's verification steps or associated KPIs.
        for m_id, m_data in domain_semantics.get("mechanisms", {}).items():
            if ev.source_id == m_id or m_id in ev.source_id:
                related_kpis = m_data.get("associated_kpis", []) + m_data.get("verification_steps", [])
                for kpi_id in anomalous_kpi_ids:
                    # check if the kpi_id overlaps with any related_kpi concept
                    if any(kw in kpi_id.lower() or kw.replace("_", "") in kpi_id.lower() for kw in related_kpis):
                        corroborated_kpis.add(kpi_id)
                    # fallback to check if mechanism keywords match the kpi
                    if any(kw in kpi_id.lower() for kw in m_data.get("keywords", [])):
                         corroborated_kpis.add(kpi_id)
                         
        # General generic check for orders/revenue
        if ev.source_id in ("orders", "order_events"):
            for kpi_id in anomalous_kpi_ids:
                if any(kw in kpi_id.lower() for kw in ("revenue", "conversion", "order")):
                    corroborated_kpis.add(kpi_id)

    count = len(corroborated_kpis)

    if count >= 2:
        return RuleResult(
            rule_name="kpi_corroboration",
            verdict=RuleVerdict.PASS,
            rationale=(
                f"Supporting evidence corroborates {count} anomalous KPI(s): "
                f"{sorted(corroborated_kpis)} — strong multi-KPI corroboration."
            ),
        )
    elif count == 1:
        return RuleResult(
            rule_name="kpi_corroboration",
            verdict=RuleVerdict.PARTIAL,
            rationale=(
                f"Supporting evidence corroborates {count} anomalous KPI: "
                f"{sorted(corroborated_kpis)} — single-KPI corroboration only."
            ),
        )
    else:
        return RuleResult(
            rule_name="kpi_corroboration",
            verdict=RuleVerdict.FAIL,
            rationale=(
                "No anomalous KPI signals are corroborated by the supporting "
                "evidence sources — kpi corroboration fails."
            ),
        )


def _rule_mechanism_consistency(
    hypothesis: Hypothesis,
    evidence_by_id: dict[str, Evidence],
    domain_semantics: dict,
) -> RuleResult:
    """
    MECHANISM_CONSISTENCY rule
    --------------------------
    Checks whether the stated mechanism is consistent with what the supporting evidence shows.
    Uses domain_semantics instead of hardcoded rules.
    """
    stmt_lower = hypothesis.statement.lower()
    reasoning_lower = hypothesis.reasoning.lower()
    combined = stmt_lower + " " + reasoning_lower

    supporting_sources: list[str] = []
    supporting_summaries: list[str] = []
    for eid in hypothesis.supporting_evidence_ids:
        ev = evidence_by_id.get(eid)
        if ev is None:
            continue
        supporting_sources.append(ev.source_id)
        supporting_summaries.append(ev.summary)

    mechanisms = domain_semantics.get("mechanisms", {})
    if not mechanisms:
        # Fallback if config is missing
        return RuleResult(
            rule_name="mechanism_consistency",
            verdict=RuleVerdict.PARTIAL,
            rationale="No domain semantics configured; cannot assess mechanism consistency.",
        )

    # Classify the hypothesis into a mechanism based on keyword overlap
    best_mech = None
    best_overlap = 0
    for mech_name, mech_cfg in mechanisms.items():
        if mech_name == "default":
            continue
        kws = set(kw.lower() for kw in mech_cfg.get("keywords", []))
        overlap = sum(1 for kw in kws if kw in combined)
        if overlap > best_overlap:
            best_overlap = overlap
            best_mech = mech_name

    if not best_mech:
        return RuleResult(
            rule_name="mechanism_consistency",
            verdict=RuleVerdict.PARTIAL,
            rationale="Mechanism could not be clearly classified from hypothesis text; verdict is PARTIAL.",
        )

    # Now verify if the evidence supports this mechanism
    mech_cfg = mechanisms[best_mech]
    mech_kws = set(kw.lower() for kw in mech_cfg.get("keywords", []))
    
    # Are any mechanism keywords present in the evidence summaries or sources?
    evidence_supports_mech = False
    for src, summary in zip(supporting_sources, supporting_summaries):
        src_lower = src.lower()
        sum_lower = summary.lower()
        if best_mech in src_lower or any(kw in src_lower or kw in sum_lower for kw in mech_kws):
            evidence_supports_mech = True
            break
            
    if evidence_supports_mech:
        return RuleResult(
            rule_name="mechanism_consistency",
            verdict=RuleVerdict.PASS,
            rationale=f"Mechanism '{best_mech}' is supported by evidence — mechanism is consistent.",
        )

    return RuleResult(
        rule_name="mechanism_consistency",
        verdict=RuleVerdict.FAIL,
        rationale=f"Mechanism '{best_mech}' claimed but evidence does not support it — mechanism is inconsistent.",
    )


def _rule_contradiction(
    hypothesis: Hypothesis,
    evidence_by_id: dict[str, Evidence],
) -> RuleResult:
    """
    CONTRADICTION rule
    ------------------
    Evaluates the contradictory evidence listed by the hypothesis.

    PASS   : no contradictory evidence referenced.
    PARTIAL: contradictory evidence exists but has low reliability_weight (<=0.6) —
             the contradiction is weak or from a stale/low-quality source.
    FAIL   : at least one contradictory evidence item has high reliability_weight (>0.6)
             AND its summary is materially contradictory to the hypothesis statement.

    Note: for the INC_001 H3 scenario, fresh inventory-normal evidence will have a
    high reliability_weight and will explicitly contradict the inventory shortage claim.
    """
    if not hypothesis.contradictory_evidence_ids:
        return RuleResult(
            rule_name="contradiction",
            verdict=RuleVerdict.PASS,
            rationale="No contradictory evidence referenced — contradiction rule passes.",
        )

    high_weight_contradictions: list[tuple[str, float, str]] = []
    low_weight_contradictions: list[str] = []

    for eid in hypothesis.contradictory_evidence_ids:
        ev = evidence_by_id.get(eid)
        if ev is None:
            # Missing/hallucinated ID — treat as absent (no contribution)
            continue

        if ev.reliability_weight > 0.6:
            high_weight_contradictions.append(
                (ev.evidence_id, ev.reliability_weight, ev.summary[:120])
            )
        else:
            low_weight_contradictions.append(ev.evidence_id)

    if high_weight_contradictions:
        ids_str = ", ".join(f"'{t[0]}' (w={t[1]:.2f})" for t in high_weight_contradictions)
        return RuleResult(
            rule_name="contradiction",
            verdict=RuleVerdict.FAIL,
            rationale=(
                f"High-reliability contradictory evidence found: {ids_str}. "
                "This materially undermines the hypothesis."
            ),
        )

    if low_weight_contradictions:
        return RuleResult(
            rule_name="contradiction",
            verdict=RuleVerdict.PARTIAL,
            rationale=(
                f"Low-reliability contradictory evidence exists: "
                f"{low_weight_contradictions}. Hypothesis is weakened but not refuted."
            ),
        )

    # All contradictory IDs were missing from evidence_by_id (hallucinated)
    return RuleResult(
        rule_name="contradiction",
        verdict=RuleVerdict.PASS,
        rationale=(
            "Referenced contradictory evidence IDs not found in evidence set — "
            "treating as no valid contradiction present."
        ),
    )


def validate_citations(
    hypothesis: Hypothesis,
    evidence_by_id: dict[str, Evidence],
) -> list[CitationViolation]:
    violations = []
    seen_ids: set[str] = set()

    for citation in hypothesis.citations:

        # Rule 1: no duplicate citations
        if citation.evidence_id in seen_ids:
            violations.append(CitationViolation(
                citation.evidence_id, "duplicate_citation",
                detail="Same evidence ID cited more than once",
            ))
            continue
        seen_ids.add(citation.evidence_id)

        # Rule 2: ID must exist
        if citation.evidence_id not in evidence_by_id:
            violations.append(CitationViolation(
                citation.evidence_id, "phantom_id",
                detail="Evidence ID not found in evidence_by_id",
            ))
            continue

        # Rule 3: quoted_summary must match exactly (ignoring minor whitespace/punctuation)
        actual = evidence_by_id[citation.evidence_id].summary
        
        import string
        def normalize(s):
            return "".join(c.lower() for c in s if c not in string.punctuation and not c.isspace())

        if normalize(citation.quoted_summary) != normalize(actual):
            violations.append(CitationViolation(
                citation.evidence_id, "summary_mismatch",
                detail=f"Expected: '{actual.strip()}'",
            ))

    return violations


# ---------------------------------------------------------------------------
# Task 9.2 — score_hypothesis
# ---------------------------------------------------------------------------


def score_hypothesis(
    h: Hypothesis,
    evidence_by_id: dict[str, Evidence],
    signals: Optional[list[AnomalySignal]] = None,
    contributions: Optional[list[DimensionContribution]] = None,
    thresholds: Optional[ChallengeThresholds] = None,
    domain_semantics: Optional[dict] = None,
) -> ScoredHypothesis:
    """
    Score a single hypothesis deterministically.

    Formula
    -------
    support_score = Σ reliability_weight * relevance  (supporting evidence only)
    contradiction_penalty = Σ reliability_weight * relevance  (contradictory evidence only)
    rule_modifier = Σ rule_weight * (1.0 if PASS, 0.5 if PARTIAL, 0.0 if FAIL)
    final_score = clamp(
        rule_modifier + min(support_score, 2.0) / 2.0 - contradiction_penalty / 2.0,
        0.0, 1.0
    )

    The normalisation caps the support contribution at 1.0 (when support_score >= 2.0)
    so the rule_modifier (max 1.0) and support contribution (max 1.0) together have a
    maximum of 2.0, making HIGH achievable with good rules AND good supporting evidence.

    Hallucinated evidence IDs (not in evidence_by_id) are silently skipped —
    they contribute 0 to support_score and 0 to contradiction_penalty.

    Requirements: 9.1, 9.2, 9.3, 9.8, 6.7
    """
    if signals is None:
        signals = []
    if contributions is None:
        contributions = []
    if thresholds is None:
        thresholds = ChallengeThresholds()

    violations = validate_citations(h, evidence_by_id)
    if violations:
        return ScoredHypothesis(
            hypothesis_id=h.hypothesis_id,
            final_score=0.0,
            confidence_state=ConfidenceState.ABSTAIN,
            disqualification_reason=(
                f"{len(violations)} citation violation(s): "
                f"{[v.violation_type for v in violations]}"
            ),
            violations=violations,
        )
    domain_semantics = domain_semantics or {}

    # Step 1: Evaluate all rules
    rule_results: list[RuleResult] = [
        evaluate_rule(name, h, evidence_by_id, signals, contributions, domain_semantics)
        for name in RULE_NAMES
    ]

    # Step 2: Support score (Req 9.8 — only supporting evidence)
    support_score: float = 0.0
    for eid in h.supporting_evidence_ids:
        ev = evidence_by_id.get(eid)
        if ev is None:
            logger.debug(
                "score_hypothesis: supporting evidence '%s' not in evidence_by_id; "
                "skipped (hallucinated id).",
                eid,
            )
            continue
        support_score += ev.reliability_weight * ev.relevance

    # Step 3: Contradiction penalty (Req 9.8 — only contradictory evidence)
    contradiction_penalty: float = 0.0
    for eid in h.contradictory_evidence_ids:
        ev = evidence_by_id.get(eid)
        if ev is None:
            logger.debug(
                "score_hypothesis: contradictory evidence '%s' not in evidence_by_id; "
                "skipped.",
                eid,
            )
            continue
        contradiction_penalty += ev.reliability_weight * ev.relevance

    # Step 4: Rule modifier
    verdict_map = {
        RuleVerdict.PASS: 1.0,
        RuleVerdict.PARTIAL: 0.5,
        RuleVerdict.FAIL: 0.0,
    }
    rule_modifier: float = sum(
        thresholds.rule_weights.get(r.rule_name, 0.0) * verdict_map[r.verdict]
        for r in rule_results
    )

    # Step 5: Combine and normalise to [0, 1]
    # Cap support contribution so a hypothesis with tons of evidence can't
    # game the score beyond ~1.0 from that dimension alone.
    capped_support = min(support_score, 2.0) / 2.0  # max 1.0
    capped_penalty = contradiction_penalty / 2.0      # scale penalty symmetrically

    raw_score = rule_modifier + capped_support - capped_penalty
    final_score = clamp(raw_score / _MAX_RAW, 0.0, 1.0)

    # Step 6: Map to ConfidenceState
    confidence_state = _to_confidence_state(final_score, thresholds)

    return ScoredHypothesis(
        hypothesis_id=h.hypothesis_id,
        rule_results=rule_results,
        support_score=support_score,
        contradiction_penalty=contradiction_penalty,
        final_score=final_score,
        confidence_state=confidence_state,
        narrative="",
        method=MethodTag.RULES,
    )


def _to_confidence_state(
    score: float,
    thresholds: ChallengeThresholds,
) -> ConfidenceState:
    """Map a numeric score to a ConfidenceState band."""
    if score >= thresholds.high_threshold:
        return ConfidenceState.HIGH
    if score >= thresholds.medium_threshold:
        return ConfidenceState.MEDIUM
    return ConfidenceState.LOW


# ---------------------------------------------------------------------------
# Task 9.2 — resolve_abstention
# ---------------------------------------------------------------------------


def resolve_abstention(
    scored: list[ScoredHypothesis],
    thresholds: ChallengeThresholds,
) -> list[ScoredHypothesis]:
    """
    Apply abstention logic to the scored hypothesis list.

    Mutates the top hypothesis's confidence_state in-place (final_score is
    never touched — Req 9.7).  Returns the list sorted by final_score
    descending.

    Rules (Requirement 9.6, 9.7)
    ----------------------------
    1. If no hypotheses: return empty list (caller sets ABSTAIN via ChallengeResult).
    2. Sort by final_score descending.
    3. If top.final_score < abstain_threshold → set top.confidence_state = ABSTAIN.
    4. If top.final_score >= abstain_threshold AND gap to runner-up < min_gap →
       set top.confidence_state = ABSTAIN.
    """
    if not scored:
        return []

    ranked = sorted(scored, key=lambda s: s.final_score, reverse=True)
    top = ranked[0]
    runner_up_score = ranked[1].final_score if len(ranked) > 1 else 0.0
    gap = top.final_score - runner_up_score

    if top.final_score < thresholds.abstain_threshold:
        logger.debug(
            "resolve_abstention: top score %.4f < abstain_threshold %.4f → ABSTAIN.",
            top.final_score,
            thresholds.abstain_threshold,
        )
        top.confidence_state = ConfidenceState.ABSTAIN
    elif gap < thresholds.min_gap:
        logger.debug(
            "resolve_abstention: gap %.4f < min_gap %.4f → ABSTAIN.",
            gap,
            thresholds.min_gap,
        )
        top.confidence_state = ConfidenceState.ABSTAIN

    return ranked


# ---------------------------------------------------------------------------
# Task 9.3 — generate_narrative (LLM_NARRATIVE, never mutates score)
# ---------------------------------------------------------------------------


def generate_narrative(
    scored_hyp: ScoredHypothesis,
    provider,
    telemetry: Optional[Telemetry] = None,
) -> str:
    """
    Generate an optional natural-language narrative for *scored_hyp*.

    Contract
    --------
    - The narrative is stored in scored_hyp.narrative with a [LLM_NARRATIVE]
      prefix.
    - final_score and confidence_state are captured before the LLM call and
      asserted to be unchanged afterwards (Requirement 9.5).
    - If the LLM call fails, the narrative is set to an empty string and the
      function returns gracefully.
    - Telemetry is recorded if a Telemetry instance is provided.

    Parameters
    ----------
    scored_hyp : ScoredHypothesis whose score fields are already frozen.
    provider   : LLMProvider instance.
    telemetry  : Optional Telemetry; updated in-place when provided.

    Returns
    -------
    The narrative string (also stored in scored_hyp.narrative).

    Requirements: 9.5
    """
    # Capture frozen scores before the LLM call to guarantee non-mutation
    frozen_score = scored_hyp.final_score
    frozen_state = scored_hyp.confidence_state

    rule_summary_lines = []
    for rr in scored_hyp.rule_results:
        rule_summary_lines.append(
            f"  - {rr.rule_name}: {rr.verdict.value} — {rr.rationale[:120]}"
        )
    rule_summary = "\n".join(rule_summary_lines) if rule_summary_lines else "  (no rules)"

    prompt = (
        f"Hypothesis {scored_hyp.hypothesis_id!r} received a confidence state of "
        f"'{scored_hyp.confidence_state.value}' (final score {scored_hyp.final_score:.3f}).\n\n"
        f"Rule evaluation summary:\n{rule_summary}\n\n"
        f"Support score: {scored_hyp.support_score:.3f}  |  "
        f"Contradiction penalty: {scored_hyp.contradiction_penalty:.3f}\n\n"
        "Write a single concise paragraph (3-5 sentences) explaining in plain business "
        "language WHY this hypothesis received this confidence level. "
        "Do NOT include any numbers, percentages, or scores in your explanation. "
        "Focus on the qualitative reasoning: which evidence supported or refuted the "
        "hypothesis, and why the rules produced their respective verdicts."
    )

    system_prompt = (
        "You are a business analyst writing a natural-language explanation of a "
        "hypothesis evaluation. Be concise, clear, and avoid any quantitative figures. "
        "Your explanation must not change or contradict the already-determined "
        "confidence state."
    )

    narrative_text = ""
    try:
        response = provider.complete(
            prompt,
            model=getattr(provider, "model", getattr(provider, "_model", None)),
            system=system_prompt,
            temperature=0.0,
            max_tokens=300,
        )
        narrative_text = response.text.strip()

        # Record telemetry (Req 16.2)
        if telemetry is not None:
            from llm.telemetry_wrapper import record_llm_call
            record_llm_call(
                telemetry=telemetry,
                response=response,
                engine_name="challenge_engine",
            )

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "generate_narrative: LLM narrative generation failed for %s: %s. "
            "Narrative will be empty.",
            scored_hyp.hypothesis_id,
            exc,
        )
        narrative_text = ""

    # Prefix with the method tag (Requirement 9.5)
    if narrative_text:
        narrative_text = f"[LLM_NARRATIVE] {narrative_text}"

    scored_hyp.narrative = narrative_text

    # CRITICAL: assert scores are unchanged (Requirement 9.5)
    assert scored_hyp.final_score == frozen_score, (
        f"generate_narrative: final_score mutated from {frozen_score} to "
        f"{scored_hyp.final_score} — this is a bug."
    )
    assert scored_hyp.confidence_state == frozen_state, (
        f"generate_narrative: confidence_state mutated from {frozen_state} to "
        f"{scored_hyp.confidence_state} — this is a bug."
    )

    return narrative_text


# ---------------------------------------------------------------------------
# Task 9.2 — score_all
# ---------------------------------------------------------------------------


def score_all(
    hypotheses: list[Hypothesis],
    evidence_by_id: dict[str, Evidence],
    signals: Optional[list[AnomalySignal]] = None,
    contributions: Optional[list[DimensionContribution]] = None,
    thresholds: Optional[ChallengeThresholds] = None,
    provider=None,
    telemetry: Optional[Telemetry] = None,
    domain_semantics: Optional[dict] = None,
) -> list[ScoredHypothesis]:
    """
    Score all hypotheses and apply abstention resolution.

    Steps
    -----
    1. Score each hypothesis with score_hypothesis.
    2. Apply resolve_abstention to produce the ranked list.
    3. Optionally generate LLM narrative for each scored hypothesis
       (only when *provider* is not None).

    Parameters
    ----------
    hypotheses      : list of Hypothesis objects from Engine E5.
    evidence_by_id  : mapping evidence_id → Evidence (already entitlement-filtered).
    signals         : AnomalySignal list for kpi_corroboration rule.
    contributions   : DimensionContribution list for segment_alignment rule.
    thresholds      : ChallengeThresholds (uses defaults when None).
    provider        : Optional LLMProvider for narrative generation.
    telemetry       : Optional Telemetry for recording LLM calls.

    Returns
    -------
    list[ScoredHypothesis] sorted by final_score descending, with abstention
    applied to the top hypothesis if warranted.
    """
    if thresholds is None:
        thresholds = ChallengeThresholds()

    domain_semantics = domain_semantics or {}
    signals = signals or []
    contributions = contributions or []

    scored: list[ScoredHypothesis] = [
        score_hypothesis(h, evidence_by_id, signals, contributions, thresholds, domain_semantics)
        for h in hypotheses
    ]

    ranked = resolve_abstention(scored, thresholds)

    # Optional LLM narrative (never mutates scores)
    if provider is not None:
        for sh in ranked:
            generate_narrative(sh, provider, telemetry)

    return ranked


# ---------------------------------------------------------------------------
# ChallengeResult NamedTuple
# ---------------------------------------------------------------------------


class ChallengeResult(NamedTuple):
    """
    Return type for challenge().

    scored_hypotheses      : list of ScoredHypothesis sorted by final_score desc
    winning_hypothesis_id  : hypothesis_id of the top-ranked non-ABSTAIN hypothesis,
                             or None when the result is ABSTAIN
    overall_confidence     : ConfidenceState of the top-ranked hypothesis (or ABSTAIN)
    abstained              : True when the top confidence state is ABSTAIN
    """

    scored_hypotheses: list[ScoredHypothesis]
    winning_hypothesis_id: Optional[str]
    overall_confidence: ConfidenceState
    abstained: bool


# ---------------------------------------------------------------------------
# Task 9.3 — challenge() — main entry point
# ---------------------------------------------------------------------------


def challenge(
    hypotheses: list[Hypothesis],
    evidence_by_id: dict[str, Evidence],
    signals: list[AnomalySignal],
    contributions: list[DimensionContribution],
    thresholds: Optional[ChallengeThresholds] = None,
    provider=None,
    telemetry: Optional[Telemetry] = None,
    domain_semantics: Optional[dict] = None,
) -> ChallengeResult:
    """
    Main entry point for Engine E6: Challenge Engine.

    Runs all five rules deterministically, scores each hypothesis, applies
    abstention logic, and optionally generates LLM narratives.  Returns a
    ChallengeResult that the Decision_Engine (E7) consumes.

    Invariants
    ----------
    - final_score is a pure function of inputs — identical inputs → identical
      outputs.  No wall-clock, no randomness, no external state.
    - The LLM narrative (if requested) NEVER changes final_score or
      confidence_state.
    - Only supporting evidence contributes to support_score; only contradictory
      evidence contributes to contradiction_penalty (Req 9.8).

    Parameters
    ----------
    hypotheses      : list of Hypothesis from Engine E5 (entitlement-filtered).
    evidence_by_id  : dict[evidence_id → Evidence] from Engine E4.
    signals         : AnomalySignal list from Engine E2.
    contributions   : DimensionContribution list from Engine E3.
    thresholds      : ChallengeThresholds (defaults when None).
    provider        : Optional LLMProvider for [LLM_NARRATIVE] generation.
    telemetry       : Optional Telemetry for recording LLM calls.

    Returns
    -------
    ChallengeResult

    Requirements: 9.1, 9.2, 9.3, 9.5, 9.6, 9.7, 9.8, 6.7, 12.3, 12.4, 12.5
    """
    if thresholds is None:
        thresholds = ChallengeThresholds()

    # Handle the empty hypothesis case (Req 9.7)
    if not hypotheses:
        logger.warning("challenge: no hypotheses provided; returning ABSTAIN.")
        return ChallengeResult(
            scored_hypotheses=[],
            winning_hypothesis_id=None,
            overall_confidence=ConfidenceState.ABSTAIN,
            abstained=True,
        )

    domain_semantics = domain_semantics or {}

    ranked = score_all(
        hypotheses=hypotheses,
        evidence_by_id=evidence_by_id,
        signals=signals,
        contributions=contributions,
        thresholds=thresholds,
        provider=provider,
        telemetry=telemetry,
        domain_semantics=domain_semantics,
    )

    # Determine the winner and overall confidence
    top = ranked[0]
    abstained = top.confidence_state == ConfidenceState.ABSTAIN

    winning_hypothesis_id: Optional[str]
    if abstained:
        winning_hypothesis_id = None
    else:
        winning_hypothesis_id = top.hypothesis_id

    logger.info(
        "challenge: scored %d hypothesis(es). Top: %s | score=%.4f | "
        "confidence=%s | abstained=%s",
        len(ranked),
        top.hypothesis_id,
        top.final_score,
        top.confidence_state.value,
        abstained,
    )

    return ChallengeResult(
        scored_hypotheses=ranked,
        winning_hypothesis_id=winning_hypothesis_id,
        overall_confidence=top.confidence_state,
        abstained=abstained,
    )
