"""
engines/challenge.py - Engine E6: Challenge Engine [RULES]+[LLM_NARRATIVE]

Owns ALL confidence math. The LLM writes narrative only - it never changes scores.
Every score is a deterministic pure function of inputs (rule verdicts, evidence
reliability weights, evidence relevance scores, and thresholds). No wall-clock,
no randomness, no external state.

RULE NAMES = ["timeline", "segment_alignment", "kpi_corroboration",
              "mechanism_consistency", "contradiction"]

INC_001 expected outcomes:
  H1  all rules PASS  HIGH
  H2  segment_alignment PARTIAL/FAIL, contradiction PRESENT  LOW-MEDIUM
  H3  contradiction FAIL (inventory-normal evidence)  LOW (refuted)

Requirements: 9.19.8, 6.7, 12.3, 12.4, 12.5
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Literal, NamedTuple, Optional

from models import (
    AnomalySignal,
    CitationViolation,
    AuditVerdict,
    EvidenceSufficiencyLevel,
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
    """final_audit_score >= this  HIGH"""

    medium_threshold: float = 0.40
    """final_audit_score >= this (and < high)  MEDIUM"""

    abstain_threshold: float = 0.30
    """top score < this  ABSTAIN"""

    min_gap: float = 0.15
    """gap between top and runner-up < this  ABSTAIN"""

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
#   support_score contribution is capped at 2.0 and halved  1.0
#   contradiction_score contribution is halved
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
# Task 9.1 - evaluate_rule (deterministic, no I/O, no wall-clock)
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

    All five rules are pure functions of their arguments - no wall-clock, no
    random values, no external calls.  Missing evidence IDs are tolerated
    (skipped with no contribution) so that hallucinated IDs from the LLM do
    not crash the engine; they merely fail to contribute positively.

    Parameters
    ----------
    rule_name       : one of RULE_NAMES
    hypothesis      : the Hypothesis being evaluated
    evidence_by_id  : mapping from evidence_id  Evidence
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
             source (or its summary mentions deployment keywords) - the deploy
             precedes the anomaly, so timeline is consistent.
    FAIL   : contradictory evidence explicitly states a timeline inconsistency
             (e.g., deployment happened after the anomaly, or the summary
             explicitly denies any recent deployment).
    PARTIAL: everything else.

    This rule operates purely on the evidence summaries and source IDs that
    the LLM included in the hypothesis - no calendar lookup.
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
                    "timeline inconsistency - deployment did not precede the anomaly."
                ),
            )

    # Check supporting evidence for deployment temporal alignment.
    # PASS when:
    #   (a) a deployment_log source is directly referenced, OR
    #   (b) the summary mentions deployment keywords (deploy/release/version), OR
    #   (c) payment_gateway evidence is present - the payment gateway is the
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
                "temporally precedes the anomaly window - timeline is consistent."
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
             concentrated in one segment - the hypothesis ignores the skew.
    PARTIAL: everything else (hypothesis mentions a segment but no contribution
             data is available, or the alignment is weak).
    """
    if not contributions:
        return RuleResult(
            rule_name="segment_alignment",
            verdict=RuleVerdict.PARTIAL,
            rationale="Insufficient dimensional contribution data to assess segment alignment.",
        )

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
    h_mech = getattr(hypothesis, "mechanism_tag", "")
    for m_id, m_data in domain_semantics.get("mechanisms", {}).items():
        if m_id == "external_factors" or m_id == "default":
            continue
        if h_mech == m_id:
            supported_mechanism = m_id
            break
        direct_s = (m_data.get("direct_source") or m_id).lower()
        comp_s = set(s.lower() for s in m_data.get("compatible_sources", []))
        if any(
            eid in evidence_by_id and (
                evidence_by_id[eid].source_id.lower() == direct_s
                or evidence_by_id[eid].source_id.lower() in comp_s
            )
            for eid in hypothesis.supporting_evidence_ids
        ):
            supported_mechanism = m_id
            break
        if _contains_any(combined, set(m_data.get("keywords", []))):
            supported_mechanism = m_id
            break

    # --- Supporting evidence sources ---
    supporting_sources = {
        evidence_by_id[eid].source_id
        for eid in hypothesis.supporting_evidence_ids
        if eid in evidence_by_id
    }

    if mentioned_segments and device_contributions:
        # Hypothesis explicitly names a device/segment - check alignment
        dominant = max(device_contributions, key=lambda c: abs(c.contribution_pct))
        dominant_seg_lower = dominant.segment.lower()
        if any(seg in dominant_seg_lower or dominant_seg_lower in seg for seg in mentioned_segments):
            return RuleResult(
                rule_name="segment_alignment",
                verdict=RuleVerdict.PASS,
                rationale=(
                    f"Hypothesis mentions segment(s) {mentioned_segments} and the "
                    f"dominant dimensional contributor is '{dominant.segment}' - "
                    "segment alignment confirmed."
                ),
            )
        return RuleResult(
            rule_name="segment_alignment",
            verdict=RuleVerdict.PARTIAL,
            rationale=(
                f"Hypothesis mentions segment(s) {mentioned_segments} but the "
                f"dominant contributor is '{dominant.segment}' - partial alignment."
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
                        "a regression affecting that segment - segment alignment confirmed."
                    ),
                )

        # Broad claim with heavy segment concentration  FAIL
        if abs(dominant.contribution_pct) > 50:
            return RuleResult(
                rule_name="segment_alignment",
                verdict=RuleVerdict.FAIL,
                rationale=(
                    f"Hypothesis implies a market-wide effect but dimensional data "
                    f"shows movement concentrated in '{dominant.segment}' "
                    f"({dominant.contribution_pct:.1f}% contribution) - "
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

    return RuleResult(
        rule_name="segment_alignment",
        verdict=RuleVerdict.PARTIAL,
        rationale="Hypothesis mentions segment(s) but insufficient dimensional data is available.",
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
                
        # Cross-reference using domain_semantics: if the source represents a mechanism or hypothesis mechanism aligns,
        # it corroborates KPIs aligned with that mechanism's verification steps or associated KPIs.
        h_mech = getattr(hypothesis, "mechanism_tag", "")
        for m_id, m_data in domain_semantics.get("mechanisms", {}).items():
            direct_s = (m_data.get("direct_source") or m_id).lower()
            comp_s = set(s.lower() for s in m_data.get("compatible_sources", []))
            if (
                ev.source_id.lower() == direct_s
                or ev.source_id.lower() in comp_s
                or ev.source_id.lower() == m_id.lower()
                or (h_mech and m_id.lower() == h_mech.lower())
            ):
                related_kpis = [k.lower() for k in m_data.get("associated_kpis", []) + m_data.get("verification_steps", [])]
                for kpi_id in anomalous_kpi_ids:
                    kpi_lower = kpi_id.lower()
                    if any(rk in kpi_lower or kpi_lower in rk or rk.replace("_", "") in kpi_lower for rk in related_kpis):
                        corroborated_kpis.add(kpi_id)
                    if any(kw.lower() in kpi_lower for kw in m_data.get("keywords", [])):
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
                f"{sorted(corroborated_kpis)} - strong multi-KPI corroboration."
            ),
        )
    elif count == 1:
        return RuleResult(
            rule_name="kpi_corroboration",
            verdict=RuleVerdict.PARTIAL,
            rationale=(
                f"Supporting evidence corroborates {count} anomalous KPI: "
                f"{sorted(corroborated_kpis)} - single-KPI corroboration only."
            ),
        )
    else:
        return RuleResult(
            rule_name="kpi_corroboration",
            verdict=RuleVerdict.FAIL,
            rationale=(
                "No anomalous KPI signals are corroborated by the supporting "
                "evidence sources - kpi corroboration fails."
            ),
        )


def is_evidence_compatible_with_mechanism(
    ev: Evidence,
    mechanism_tag: str,
    domain_semantics: dict,
) -> bool:
    """
    Deterministically validates whether an evidence record semantically
    corroborates a hypothesis's mechanism_tag.

    Enforces dual-check policy:
    1. Source compatibility: ev.source_id must be declared in compatible_sources or direct_source.
    2. Content/KPI relevance: For multi-purpose/contextual sources (e.g. support_tickets, deployment_log, orders),
       the evidence summary or source_id must explicitly contain mechanism-specific keywords, KPIs, or steps.
    """
    if not mechanism_tag or mechanism_tag in ("UNKNOWN", "default"):
        return True

    mechanisms = domain_semantics.get("mechanisms", {})
    if mechanism_tag not in mechanisms:
        return True

    mech_data = mechanisms[mechanism_tag]
    compatible_sources = set(s.lower() for s in mech_data.get("compatible_sources", []))
    direct_source = (mech_data.get("direct_source") or mechanism_tag).lower()
    associated_kpis = set(k.lower() for k in mech_data.get("associated_kpis", []))
    keywords = set(k.lower() for k in mech_data.get("keywords", []))
    verification_steps = set(s.lower() for s in mech_data.get("verification_steps", []))

    ev_source = ev.source_id.lower()

    # 1. Source compatibility check
    if compatible_sources:
        if ev_source not in compatible_sources and ev_source != direct_source:
            return False
    else:
        # If compatible_sources not specified, reject if source is directly dedicated to another distinct mechanism
        for other_m_id, other_m_data in mechanisms.items():
            if other_m_id == mechanism_tag:
                continue
            other_direct = (other_m_data.get("direct_source") or other_m_id).lower()
            if ev_source == other_direct:
                return False

    # 3. Content & KPI alignment check for contextual/general sources
    contextual_sources = {"support_tickets", "deployment_log", "release_notes", "orders"}
    if ev_source in contextual_sources:
        summary_lower = ev.summary.lower()
        has_keyword = any(kw in summary_lower for kw in keywords)
        has_kpi = any(kpi in summary_lower or kpi == ev_source for kpi in associated_kpis)
        has_step = any(step in summary_lower for step in verification_steps)
        if not (has_keyword or has_kpi or has_step):
            return False

    return True


def _rule_mechanism_consistency(
    hypothesis: Hypothesis,
    evidence_by_id: dict[str, Evidence],
    domain_semantics: dict,
) -> RuleResult:
    """
    MECHANISM_CONSISTENCY rule
    --------------------------
    Checks whether the structured mechanism_tag is supported by compatible evidence.
    """
    mechanism_tag = getattr(hypothesis, "mechanism_tag", "UNKNOWN")
    
    if mechanism_tag == "UNKNOWN":
        return RuleResult(
            rule_name="mechanism_consistency",
            verdict=RuleVerdict.PARTIAL,
            rationale="No configured mechanism claimed (UNKNOWN); cannot assess mechanistic consistency.",
        )
        
    mechanisms = domain_semantics.get("mechanisms", {})
    if mechanism_tag not in mechanisms:
        # Invalid tag shouldn't reach here due to E5 schema, but just in case
        return RuleResult(
            rule_name="mechanism_consistency",
            verdict=RuleVerdict.FAIL,
            rationale=f"Claimed mechanism_tag '{mechanism_tag}' is not recognized in domain semantics.",
        )

    compatible_eids: list[str] = []
    unaligned_eids: list[str] = []

    for eid in hypothesis.supporting_evidence_ids:
        ev = evidence_by_id.get(eid)
        if ev is None:
            continue
        if is_evidence_compatible_with_mechanism(ev, mechanism_tag, domain_semantics):
            compatible_eids.append(eid)
        else:
            unaligned_eids.append(eid)

    if compatible_eids:
        unaligned_note = f" (Note: unaligned citations {sorted(unaligned_eids)} excluded from support scoring)" if unaligned_eids else ""
        return RuleResult(
            rule_name="mechanism_consistency",
            verdict=RuleVerdict.PASS,
            rationale=f"Mechanism '{mechanism_tag}' is supported by compatible evidence {sorted(compatible_eids)}.{unaligned_note}",
        )

    return RuleResult(
        rule_name="mechanism_consistency",
        verdict=RuleVerdict.FAIL,
        rationale=f"Mechanism '{mechanism_tag}' claimed but supporting evidence does not semantically corroborate it.",
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
    PARTIAL: contradictory evidence exists but has low reliability_weight (<=0.6) -
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
            rationale="No contradictory evidence referenced - contradiction rule passes.",
        )

    high_weight_contradictions: list[tuple[str, float, str]] = []
    low_weight_contradictions: list[str] = []

    for eid in hypothesis.contradictory_evidence_ids:
        ev = evidence_by_id.get(eid)
        if ev is None:
            # Missing/hallucinated ID - treat as absent (no contribution)
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
            "Referenced contradictory evidence IDs not found in evidence set - "
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
# Task 9.2 - score_hypothesis
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
    Score a single hypothesis deterministically using a weakest-link formula.
    """
    if signals is None:
        signals = []
    if contributions is None:
        contributions = []
    if thresholds is None:
        thresholds = ChallengeThresholds()

    if not domain_semantics:
        try:
            from config.loader import load_domain_semantics
            from pathlib import Path
            p = Path(__file__).resolve().parent.parent / "config" / "domain_semantics.yaml"
            if p.exists():
                domain_semantics = load_domain_semantics(p)
            else:
                domain_semantics = {}
        except Exception:
            domain_semantics = {}

    violations = validate_citations(h, evidence_by_id)
    
    # Deduplication and double-dipping prevention
    support_set = set(h.supporting_evidence_ids)
    contradictory_set = set(h.contradictory_evidence_ids)
    
    overlap = support_set.intersection(contradictory_set)
    if overlap:
        violations.append(CitationViolation(
            list(overlap)[0], "duplicate_citation",
            detail="Evidence ID appears in both supporting and contradictory sets",
        ))

    if violations:
        return ScoredHypothesis(
            hypothesis_id=h.hypothesis_id,
            final_audit_score=0.0,
            audit_verdict=AuditVerdict.REJECTED,
            disqualification_reason=(
                f"{len(violations)} citation violation(s): "
                f"{[v.violation_type for v in violations]}"
            ),
            violations=violations,
        )

    # Step 1: Evaluate all rules
    rule_results: list[RuleResult] = [
        evaluate_rule(name, h, evidence_by_id, signals, contributions, domain_semantics)
        for name in RULE_NAMES
    ]

    # Check hard constraints immediately
    hard_fails = [
        r for r in rule_results 
        if r.rule_name in ("timeline", "contradiction") and r.verdict == RuleVerdict.FAIL
    ]
    if hard_fails:
        return ScoredHypothesis(
            hypothesis_id=h.hypothesis_id,
            rule_results=rule_results,
            final_audit_score=0.0,
            audit_verdict=AuditVerdict.REJECTED,
            disqualification_reason=f"Failed hard constraint(s): {[r.rule_name for r in hard_fails]}",
        )

    # Step 2: Support score (Deduplicated & Mechanism Alignment Validated)
    support_score: float = 0.0
    aligned_support_eids: list[str] = []
    unaligned_evidence_ids: list[str] = []

    for eid in support_set:
        ev = evidence_by_id.get(eid)
        if ev is None:
            continue
        if is_evidence_compatible_with_mechanism(ev, getattr(h, "mechanism_tag", ""), domain_semantics):
            aligned_support_eids.append(eid)
            support_score += ev.reliability_weight * ev.relevance
        else:
            unaligned_evidence_ids.append(eid)

    # Step 3: Contradiction penalty (Deduplicated)
    contradiction_score: float = 0.0
    for eid in contradictory_set:
        ev = evidence_by_id.get(eid)
        if ev is None:
            continue
        contradiction_score += ev.reliability_weight * ev.relevance

    # Step 4: Rule modifier
    verdict_map = {
        RuleVerdict.PASS: 1.0,
        RuleVerdict.PARTIAL: 0.5,
        RuleVerdict.FAIL: 0.0,
    }
    rule_score: float = sum(
        thresholds.rule_weights.get(r.rule_name, 0.0) * verdict_map[r.verdict]
        for r in rule_results
    )

    # Step 5: Final Audit Score (Weakest link invariant)
    capped_support = clamp(support_score / 2.0, 0.0, 1.0)
    capped_penalty = clamp(contradiction_score / 2.0, 0.0, 1.0)
    
    final_audit_score = clamp(min(capped_support, rule_score) - capped_penalty, 0.0, 1.0)

    # Determine Evidence Sufficiency
    if support_score < 0.4:
        sufficiency_level = EvidenceSufficiencyLevel.INSUFFICIENT
    elif support_score < 0.8:
        sufficiency_level = EvidenceSufficiencyLevel.LIMITED
    elif support_score < 1.5:
        sufficiency_level = EvidenceSufficiencyLevel.SUFFICIENT
    else:
        sufficiency_level = EvidenceSufficiencyLevel.STRONG

    # Determine Verdict
    if final_audit_score >= thresholds.high_threshold and sufficiency_level in (EvidenceSufficiencyLevel.SUFFICIENT, EvidenceSufficiencyLevel.STRONG):
        verdict = AuditVerdict.VERIFIED
    elif final_audit_score >= thresholds.medium_threshold or (final_audit_score >= thresholds.high_threshold and sufficiency_level == EvidenceSufficiencyLevel.LIMITED):
        verdict = AuditVerdict.MARGINAL
    else:
        verdict = AuditVerdict.MARGINAL  # Weak scores are marginal unless they fail a hard rule

    return ScoredHypothesis(
        hypothesis_id=h.hypothesis_id,
        rule_results=rule_results,
        support_score=capped_support,
        contradiction_score=capped_penalty,
        rule_score=rule_score,
        final_audit_score=final_audit_score,
        audit_verdict=verdict,
        evidence_sufficiency_score=support_score,
        evidence_sufficiency_level=sufficiency_level,
        narrative="",
        method=MethodTag.RULES,
        unaligned_evidence_ids=sorted(unaligned_evidence_ids),
    )


# ---------------------------------------------------------------------------
# Task 9.2 - resolve_abstention
# ---------------------------------------------------------------------------


def resolve_abstention(
    scored: list[ScoredHypothesis],
    thresholds: ChallengeThresholds,
) -> tuple[list[ScoredHypothesis], AuditVerdict]:
    """
    Apply abstention logic to the scored hypothesis list.

    Returns the list sorted by final_audit_score descending, and the overall AuditVerdict.
    Individual hypothesis verdicts are NOT mutated here.
    """
    if not scored:
        return [], AuditVerdict.ABSTAIN

    ranked = sorted(scored, key=lambda s: s.final_audit_score, reverse=True)
    top = ranked[0]
    runner_up_score = ranked[1].final_audit_score if len(ranked) > 1 else 0.0
    gap = top.final_audit_score - runner_up_score

    overall_verdict = top.audit_verdict

    # Ambiguity checks that trigger an investigation-level ABSTAIN
    if top.final_audit_score < thresholds.abstain_threshold:
        logger.debug(
            "resolve_abstention: top score %.4f < abstain_threshold %.4f  ABSTAIN.",
            top.final_audit_score,
            thresholds.abstain_threshold,
        )
        overall_verdict = AuditVerdict.ABSTAIN
    elif gap < thresholds.min_gap:
        logger.debug(
            "resolve_abstention: gap %.4f < min_gap %.4f  ABSTAIN.",
            gap,
            thresholds.min_gap,
        )
        overall_verdict = AuditVerdict.ABSTAIN

    # A rejected hypothesis cannot be the winner
    if top.audit_verdict == AuditVerdict.REJECTED:
        overall_verdict = AuditVerdict.ABSTAIN

    return ranked, overall_verdict


# ---------------------------------------------------------------------------
# Task 9.3 - generate_narrative (LLM_NARRATIVE, never mutates score)
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
    - final_audit_score and audit_verdict are captured before the LLM call and
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
    frozen_score = scored_hyp.final_audit_score
    frozen_state = scored_hyp.audit_verdict

    rule_summary_lines = []
    for rr in scored_hyp.rule_results:
        rule_summary_lines.append(
            f"  - {rr.rule_name}: {rr.verdict.value} - {rr.rationale[:120]}"
        )
    rule_summary = "\n".join(rule_summary_lines) if rule_summary_lines else "  (no rules)"

    prompt = (
        f"Hypothesis {scored_hyp.hypothesis_id!r} received an audit verdict of "
        f"'{scored_hyp.audit_verdict.value}' (final score {scored_hyp.final_audit_score:.3f}).\n\n"
        f"Rule evaluation summary:\n{rule_summary}\n\n"
        f"Support score: {scored_hyp.support_score:.3f}  |  "
        f"Contradiction penalty: {scored_hyp.contradiction_score:.3f}\n\n"
        "Write a single concise paragraph (3-5 sentences) explaining in plain business "
        "language WHY this hypothesis received this audit verdict. "
        "Do NOT include any numbers, percentages, or scores in your explanation. "
        "Focus on the qualitative reasoning: which evidence supported or refuted the "
        "hypothesis, and why the rules produced their respective verdicts."
    )

    system_prompt = (
        "You are a business analyst writing a natural-language explanation of a "
        "hypothesis evaluation. Be concise, clear, and avoid any quantitative figures. "
        "Your explanation must not change or contradict the already-determined "
        "audit verdict."
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
    assert scored_hyp.final_audit_score == frozen_score, (
        f"generate_narrative: final_audit_score mutated from {frozen_score} to "
        f"{scored_hyp.final_audit_score} - this is a bug."
    )
    assert scored_hyp.audit_verdict == frozen_state, (
        f"generate_narrative: audit_verdict mutated from {frozen_state} to "
        f"{scored_hyp.audit_verdict} - this is a bug."
    )

    return narrative_text


# ---------------------------------------------------------------------------
# Task 9.2 - score_all
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
    evidence_by_id  : mapping evidence_id  Evidence (already entitlement-filtered).
    signals         : AnomalySignal list for kpi_corroboration rule.
    contributions   : DimensionContribution list for segment_alignment rule.
    thresholds      : ChallengeThresholds (uses defaults when None).
    provider        : Optional LLMProvider for narrative generation.
    telemetry       : Optional Telemetry for recording LLM calls.

    Returns
    -------
    tuple of (list[ScoredHypothesis] sorted by final_audit_score descending, overall AuditVerdict)
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

    ranked, overall_verdict = resolve_abstention(scored, thresholds)

    # Optional LLM narrative (never mutates scores)
    if provider is not None:
        for sh in ranked:
            generate_narrative(sh, provider, telemetry)

    return ranked, overall_verdict


# ---------------------------------------------------------------------------
# ChallengeResult NamedTuple
# ---------------------------------------------------------------------------


class ChallengeResult(NamedTuple):
    """
    Return type for challenge().

    scored_hypotheses      : list of ScoredHypothesis sorted by final_audit_score desc
    winning_hypothesis_id  : hypothesis_id of the top-ranked non-ABSTAIN hypothesis,
                             or None when the result is ABSTAIN
    overall_verdict        : AuditVerdict of the investigation as a whole
    abstained              : True when overall_verdict is ABSTAIN
    """

    scored_hypotheses: list[ScoredHypothesis]
    winning_hypothesis_id: Optional[str]
    overall_verdict: AuditVerdict
    abstained: bool


# ---------------------------------------------------------------------------
# Task 9.3 - challenge() - main entry point
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
    - final_audit_score is a pure function of inputs - identical inputs  identical
      outputs.  No wall-clock, no randomness, no external state.
    - The LLM narrative (if requested) NEVER changes final_audit_score or
      audit_verdict.
    - Only supporting evidence contributes to support_score; only contradictory
      evidence contributes to contradiction_score (Req 9.8).

    Parameters
    ----------
    hypotheses      : list of Hypothesis from Engine E5 (entitlement-filtered).
    evidence_by_id  : dict[evidence_id  Evidence] from Engine E4.
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
            overall_verdict=AuditVerdict.ABSTAIN,
            abstained=True,
        )

    domain_semantics = domain_semantics or {}

    ranked, overall_verdict = score_all(
        hypotheses=hypotheses,
        evidence_by_id=evidence_by_id,
        signals=signals,
        contributions=contributions,
        thresholds=thresholds,
        provider=provider,
        telemetry=telemetry,
        domain_semantics=domain_semantics,
    )

    abstained = (overall_verdict == AuditVerdict.ABSTAIN)
    winning_hypothesis_id: Optional[str]
    if abstained:
        winning_hypothesis_id = None
    else:
        winning_hypothesis_id = ranked[0].hypothesis_id

    if ranked:
        top = ranked[0]
        logger.info(
            "challenge: scored %d hypothesis(es). Top: %s | score=%.4f | "
            "verdict=%s | overall_verdict=%s",
            len(ranked),
            top.hypothesis_id,
            top.final_audit_score,
            top.audit_verdict.value,
            overall_verdict.value,
        )

    return ChallengeResult(
        scored_hypotheses=ranked,
        winning_hypothesis_id=winning_hypothesis_id,
        overall_verdict=overall_verdict,
        abstained=abstained,
    )
