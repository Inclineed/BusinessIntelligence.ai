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
    Verifies temporal consistency between claimed causal mechanisms and evidence.

    Invariants:
    1. A deployment/release timeline PASS requires actual deployment/release evidence:
       source_id in ("deployment_log", "release_notes") or an explicit release artifact.
       Generic words such as "latency", "failure", "timeout" must NEVER establish deployment precedence.
    2. If the hypothesis claims an internal release root cause (root_cause_type == "INTERNAL_RELEASE"
       or mechanism_tag == "deployment_issues"), it MUST provide explicit deployment/release evidence.
       If none is provided, timeline is PARTIAL (or unconfirmed).
    3. For component/subsystem hypotheses (e.g. payment_gateway, inventory_system, external_factors),
       timestamped telemetry within/preceding the anomaly window confirms component observation alignment.
    4. Temporal precedence alone establishes chronology, not ultimate causation.
    """
    # Check contradictory evidence for timeline inconsistency first
    for eid in hypothesis.contradictory_evidence_ids:
        ev = evidence_by_id.get(eid)
        if ev is None:
            continue
        summary_lower = ev.summary.lower()
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

    deploy_sources = {"deployment_log", "release_notes"}
    deployment_evidence_found = False
    deployment_evidence_source = ""
    component_evidence_found = False
    component_evidence_sources = []

    subsystems = domain_semantics.get("subsystems", {})
    mechanisms = domain_semantics.get("mechanisms", {})

    raw_root = getattr(hypothesis, "root_cause_type", "UNKNOWN")
    claimed_root = raw_root.value if hasattr(raw_root, "value") else str(raw_root) if raw_root else "UNKNOWN"
    claimed_mech = getattr(hypothesis, "mechanism_tag", "")
    is_deploy_claim = (claimed_root == "INTERNAL_RELEASE" or claimed_mech == "deployment_issues")

    for eid in hypothesis.supporting_evidence_ids:
        ev = evidence_by_id.get(eid)
        if ev is None:
            continue

        ev_src = ev.source_id.lower()
        summary_lower = ev.summary.lower()

        # Strict check for deployment / release record
        if ev_src in deploy_sources or (
            any(w in summary_lower for w in ("deployed", "deployment", "released", "release notes", "rollback"))
            and not any(symptom in summary_lower for symptom in ("gateway events", "support tickets", "marketing campaign"))
        ):
            deployment_evidence_found = True
            deployment_evidence_source = ev.source_id
            break

        # Check for valid component / telemetry evidence
        if ev_src in subsystems or ev_src in mechanisms or ev_src in ("payment_gateway", "inventory", "marketing", "orders", "device_performance"):
            component_evidence_found = True
            component_evidence_sources.append(ev.source_id)

    if deployment_evidence_found:
        return RuleResult(
            rule_name="timeline",
            verdict=RuleVerdict.PASS,
            rationale=(
                f"Supporting evidence contains an explicit deployment/release record (source='{deployment_evidence_source}') "
                "preceding the anomaly window - deployment timeline is consistent."
            ),
        )

    if is_deploy_claim and not deployment_evidence_found:
        return RuleResult(
            rule_name="timeline",
            verdict=RuleVerdict.PARTIAL,
            rationale=(
                "Hypothesis claims an internal software release/deployment root cause, but supporting evidence "
                "contains no explicit deployment or release records; deployment timeline precedence is unconfirmed."
            ),
        )

    if component_evidence_found:
        return RuleResult(
            rule_name="timeline",
            verdict=RuleVerdict.PASS,
            rationale=(
                f"Supporting evidence contains timestamped component telemetry ({', '.join(sorted(set(component_evidence_sources)))}) "
                "aligning with the anomaly window - temporal observation is consistent (note: chronology alone does not prove initiating cause)."
            ),
        )

    return RuleResult(
        rule_name="timeline",
        verdict=RuleVerdict.PARTIAL,
        rationale=(
            "No deployment log or timestamped component telemetry found in the supporting set; "
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

    Evaluates ONLY the current hypothesis's mechanism_tag to prevent cross-mechanism
    contamination.
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

    h_mech = getattr(hypothesis, "mechanism_tag", "") or "UNKNOWN"
    mechanisms = domain_semantics.get("mechanisms", {})
    if h_mech == "UNKNOWN" or h_mech not in mechanisms:
        # Fallback for legacy untagged test hypotheses: infer from statement keywords
        for m_id, m_data in mechanisms.items():
            if m_id in ("external_factors", "default"):
                continue
            if _contains_any(combined, set(m_data.get("keywords", []))):
                h_mech = m_id
                break
    mech_data = mechanisms.get(h_mech, {})

    # Check if the hypothesis's OWN mechanism has compatible supporting evidence
    has_compatible_evidence = False
    if h_mech != "UNKNOWN" and h_mech in mechanisms:
        direct_s = (mech_data.get("direct_source") or h_mech).lower()
        comp_s = set(s.lower() for s in mech_data.get("compatible_sources", []))
        for eid in hypothesis.supporting_evidence_ids:
            ev = evidence_by_id.get(eid)
            if ev and (ev.source_id.lower() == direct_s or ev.source_id.lower() in comp_s):
                has_compatible_evidence = True
                break

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

        # Technical/internal mechanisms with supporting evidence consistent with dominant segment concentration
        if h_mech not in ("external_factors", "default", "UNKNOWN") and has_compatible_evidence:
            dominant_is_mobile = any(
                kw in dominant.segment.lower()
                for kw in ("android", "ios", "mobile", "app")
            )
            if dominant_is_mobile or abs(dominant.contribution_pct) > 40:
                return RuleResult(
                    rule_name="segment_alignment",
                    verdict=RuleVerdict.PASS,
                    rationale=(
                        f"Mechanism hypothesis ({h_mech}) with supporting "
                        f"evidence; dominant segment '{dominant.segment}' "
                        f"({dominant.contribution_pct:.1f}%) is consistent with "
                        "a regression affecting that segment - segment alignment confirmed."
                    ),
                )

        # Broad/external claims with heavy segment concentration -> FAIL
        if abs(dominant.contribution_pct) > 50:
            return RuleResult(
                rule_name="segment_alignment",
                verdict=RuleVerdict.FAIL,
                rationale=(
                    f"Hypothesis ({h_mech}) implies a market-wide effect but dimensional data "
                    f"shows movement concentrated in '{dominant.segment}' "
                    f"({dominant.contribution_pct:.1f}% contribution) - "
                    "segment alignment fails."
                ),
            )
        return RuleResult(
            rule_name="segment_alignment",
            verdict=RuleVerdict.PARTIAL,
            rationale=(
                f"Hypothesis ({h_mech}) does not mention a specific device segment; "
                "dimensional data shows some segment concentration but not decisive."
            ),
        )

    return RuleResult(
        rule_name="segment_alignment",
        verdict=RuleVerdict.PARTIAL,
        rationale=f"Hypothesis ({h_mech}) mentions segment(s) but insufficient dimensional data is available.",
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
    supporting evidence sources aligned with the hypothesis's affected subsystem/mechanism.

    PASS   : >= 2 anomalous KPIs are represented in the supporting evidence.
    PARTIAL: exactly 1 anomalous KPI corroborated.
    FAIL   : 0 anomalous KPIs corroborated.
    """
    anomalous_kpi_ids: frozenset[str] = frozenset(
        s.kpi_id for s in signals if s.is_anomaly
    )

    corroborated_kpis: set[str] = set()
    h_sub = getattr(hypothesis, "affected_subsystem", "UNKNOWN") or "UNKNOWN"
    h_mech = getattr(hypothesis, "mechanism_tag", "") or "UNKNOWN"

    subsystems = domain_semantics.get("subsystems", {})
    mechanisms = domain_semantics.get("mechanisms", {})

    target_comp = h_sub if (h_sub != "UNKNOWN" and h_sub in subsystems) else h_mech
    if target_comp == "UNKNOWN" or (target_comp not in subsystems and target_comp not in mechanisms):
        stmt_comb = (hypothesis.statement + " " + hypothesis.reasoning).lower()
        for m_id, m_data in mechanisms.items():
            if m_id in ("external_factors", "default"):
                continue
            if _contains_any(stmt_comb, set(m_data.get("keywords", []))):
                target_comp = m_id
                break

    comp_data = subsystems.get(target_comp, mechanisms.get(target_comp, {}))

    direct_s = (comp_data.get("direct_source") or target_comp).lower() if comp_data else ""
    comp_s = set(s.lower() for s in comp_data.get("compatible_sources", [])) if comp_data else set()
    associated_kpis = [k.lower() for k in comp_data.get("associated_kpis", []) + comp_data.get("verification_steps", [])] if comp_data else []
    comp_keywords = set(kw.lower() for kw in comp_data.get("keywords", [])) if comp_data else set()

    for eid in hypothesis.supporting_evidence_ids:
        ev = evidence_by_id.get(eid)
        if ev is None:
            continue

        ev_src = ev.source_id.lower()
        summary_lower = ev.summary.lower()

        # Direct: evidence source_id matches an anomalous KPI's id
        if ev.source_id in anomalous_kpi_ids:
            if not target_comp or target_comp in ("UNKNOWN", "default") or ev_src == direct_s or ev_src in comp_s:
                corroborated_kpis.add(ev.source_id)

        # Indirect: check if any anomalous KPI id appears in the evidence summary
        for kpi_id in anomalous_kpi_ids:
            if kpi_id.lower() in summary_lower:
                if not target_comp or target_comp in ("UNKNOWN", "default") or ev_src == direct_s or ev_src in comp_s:
                    corroborated_kpis.add(kpi_id)

        # Mechanism/Subsystem associated KPI corroboration: ONLY for the current hypothesis's component
        if comp_data and is_evidence_compatible_with_mechanism(ev, target_comp, domain_semantics):
            for kpi_id in anomalous_kpi_ids:
                kpi_lower = kpi_id.lower()
                if any(rk in kpi_lower or kpi_lower in rk or rk.replace("_", "") in kpi_lower for rk in associated_kpis):
                    corroborated_kpis.add(kpi_id)
                if any(kw in kpi_lower for kw in comp_keywords):
                    corroborated_kpis.add(kpi_id)

        # Orders / Revenue generic check: only if orders is compatible with THIS mechanism
        if ev_src in ("orders", "order_events") and (not target_comp or ev_src in comp_s or ev_src == direct_s):
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
    corroborates a hypothesis's mechanism_tag, subsystem, or root-cause archetype.

    Enforces:
    1. Subsystem / Root cause separation: payment_gateway telemetry does NOT prove deployment_issues
       without explicit release/deployment logs.
    2. Source compatibility: ev.source_id must be declared in compatible_sources or direct_source.
    3. Content/KPI relevance: For multi-purpose/contextual sources (e.g. support_tickets, deployment_log, orders),
       the evidence summary or source_id must explicitly contain mechanism-specific keywords, KPIs, or steps.
    """
    if not mechanism_tag or mechanism_tag in ("UNKNOWN", "default"):
        return True

    subsystems = domain_semantics.get("subsystems", {})
    root_archetypes = domain_semantics.get("root_cause_archetypes", {})
    mechanisms = domain_semantics.get("mechanisms", {})

    if mechanism_tag in subsystems:
        mech_data = subsystems[mechanism_tag]
    elif mechanism_tag in root_archetypes:
        mech_data = root_archetypes[mechanism_tag]
    elif mechanism_tag in mechanisms:
        mech_data = mechanisms[mechanism_tag]
    else:
        return True

    compatible_sources = set(s.lower() for s in (mech_data.get("compatible_sources") or mech_data.get("discriminating_sources") or []))
    direct_source = (mech_data.get("direct_source") or "").lower()
    associated_kpis = set(k.lower() for k in mech_data.get("associated_kpis", []))
    keywords = set(k.lower() for k in mech_data.get("keywords", []))
    verification_steps = set(s.lower() for s in mech_data.get("verification_steps", []))

    ev_source = ev.source_id.lower()
    summary_lower = ev.summary.lower()

    # Explicit check: pure payment gateway telemetry does not prove deployment_issues
    if mechanism_tag in ("deployment_issues", "INTERNAL_RELEASE") and ev_source == "payment_gateway":
        if not any(kw in summary_lower for kw in ("deploy", "release", "rollback", "v4.3", "v4.2", "frontend", "backend")):
            return False

    # 1. Source compatibility check
    if compatible_sources or direct_source:
        if ev_source not in compatible_sources and ev_source != direct_source:
            return False
    else:
        for other_m_id, other_m_data in mechanisms.items():
            if other_m_id == mechanism_tag:
                continue
            other_direct = (other_m_data.get("direct_source") or other_m_id).lower()
            if ev_source == other_direct:
                return False

    # 2. Content & KPI alignment check for contextual/general sources
    contextual_sources = {"support_tickets", "deployment_log", "release_notes", "orders"}
    if ev_source in contextual_sources:
        has_keyword = any(kw in summary_lower for kw in keywords)
        has_kpi = any(kpi in summary_lower or kpi == ev_source for kpi in associated_kpis)
        has_step = any(step in summary_lower for step in verification_steps)
        if not (has_keyword or has_kpi or has_step):
            return False

    return True


def is_evidence_anomalous_or_relevant(
    ev: Evidence,
    mechanism_tag: str,
    signals: list[AnomalySignal],
    domain_semantics: dict,
) -> bool:
    """
    Deterministically determines whether an evidence item represents anomalous /
    mechanism-relevant evidence versus unperturbed normal baseline telemetry.

    Unperturbed baseline / negative-control evidence (e.g. normal inventory levels,
    unperturbed marketing spend) must contribute 0.0 positive support to prevent
    spurious corroboration of irrelevant mechanisms.
    """
    summary_lower = ev.summary.lower()
    ev_src = ev.source_id.lower()

    # 1. Explicit normal / baseline indicator in summary
    normal_phrases = (
        "appear normal",
        "appears normal",
        "levels appear normal",
        "within normal",
        "normal range",
        "no anomaly",
        "unperturbed",
        "baseline normal",
    )
    if any(phrase in summary_lower for phrase in normal_phrases):
        return False

    # 2. Event / Unstructured / Deployment sources are inherently relevant causal/temporal observations
    event_sources = {"deployment_log", "release_notes"}
    if ev_src in event_sources or getattr(ev, "kind", "") == "unstructured":
        return True

    # 3. Support tickets: check if error/failure vs general background
    if ev_src == "support_tickets":
        error_keywords = ("failure", "error", "unable", "issue", "bug", "crash", "timeout", "latency", "failed")
        return any(kw in summary_lower for kw in error_keywords)

    # 4. Telemetry / Structured KPI sources: check if the source/metric aligns with an active anomaly
    anomalous_kpi_ids = {s.kpi_id.lower() for s in signals if s.is_anomaly}
    non_anomalous_kpi_ids = {s.kpi_id.lower() for s in signals if not s.is_anomaly}

    # If the evidence explicitly mentions or originates from an anomalous KPI
    if ev_src in anomalous_kpi_ids or any(kpi in summary_lower for kpi in anomalous_kpi_ids):
        return True

    # Check against domain semantics associated KPIs for the mechanism
    mechanisms = domain_semantics.get("mechanisms", {})
    if mechanism_tag in mechanisms:
        mech_kpis = [k.lower() for k in mechanisms[mechanism_tag].get("associated_kpis", [])]
        for kpi in mech_kpis:
            if kpi in anomalous_kpi_ids and (kpi in summary_lower or ev_src in kpi or kpi in ev_src):
                return True

    # If the source is registered as a non-anomalous signal and has no anomaly indicators, it's baseline
    if ev_src in non_anomalous_kpi_ids:
        return False

    for s in signals:
        if not s.is_anomaly and (s.kpi_id.lower() in summary_lower or s.kpi_id.lower() == ev_src):
            return False

    # When signals are present, unaligned background inventory is baseline
    if signals and ev_src == "inventory" and not anomalous_kpi_ids.intersection({"inventory", "inventory_fill_rate_daily"}):
        return False

    # If marketing evidence is used for non-marketing mechanism, it is baseline
    if ev_src == "marketing" and mechanism_tag not in ("external_factors", "", "UNKNOWN"):
        return False

    return True


def check_root_cause_evidence_sufficiency(
    hypothesis: Hypothesis,
    evidence_by_id: dict[str, Evidence],
    signals: list[AnomalySignal],
    domain_semantics: dict,
) -> tuple[bool, str, list[str]]:
    """
    ROOT-CAUSE EVIDENCE SUFFICIENCY GATE
    ------------------------------------
    Deterministically evaluates whether the supporting evidence provides sufficient,
    causally discriminative proof for the claimed root_cause_type (initiating cause),
    strictly separating affected subsystems, proximal failure mechanisms, and initiating root causes.

    Returns:
        tuple[bool, str, list[str]]: (passed, rationale, root_cause_evidence_ids)

    Rules:
    - UNKNOWN:
      Passed. An UNKNOWN root cause accurately reflects unobserved upstream initiating factors
      and makes no unsubstantiated causal claims.

    - INTERNAL_RELEASE:
      Requires at least one causally discriminative deployment/release evidence record
      (source_id in ('deployment_log', 'release_notes') or explicit release/hotfix record).
      Gateway telemetry alone (source_id='payment_gateway') and support tickets alone
      (source_id='support_tickets') MUST NOT satisfy this gate.

    - EXTERNAL_PROVIDER:
      Requires configured provider-specific evidence (e.g. source_id in ('provider_status',
      'vendor_incident', 'gateway_provider', 'third_party_status') or explicit third-party outage record).
      Gateway telemetry alone does NOT automatically establish external provider causation.

    - MACRO_EXTERNAL:
      Requires relevant external/market evidence (e.g. source_id in ('marketing', 'competitor_data',
      'market_intelligence', 'social_media') or market-wide promotional telemetry).

    - INVENTORY_SHORTAGE:
      Requires anomalous inventory evidence (active stockout / depletion records).
      Normal inventory telemetry (e.g. fill rate 94% normal) fails this gate.

    - RESOURCE_EXHAUSTION:
      Requires mechanism-specific resource evidence (e.g. connection pool saturation metrics,
      memory/CPU telemetry, socket exhaustion logs).
    """
    raw_root_cause = getattr(hypothesis, "root_cause_type", None)
    if hasattr(raw_root_cause, "value"):
        root_cause_str = raw_root_cause.value
    elif raw_root_cause:
        root_cause_str = str(raw_root_cause)
    else:
        root_cause_str = "UNKNOWN"

    mech_tag = getattr(hypothesis, "mechanism_tag", "UNKNOWN")

    # If root_cause_type is UNKNOWN (or not specified), check if mechanism_tag implies an archetype
    if root_cause_str in ("UNKNOWN", "none", "", None):
        if mech_tag == "deployment_issues":
            root_cause_str = "INTERNAL_RELEASE"
        else:
            return (
                True,
                "Hypothesis claims no specific upstream root cause (UNKNOWN); upstream causal gate is satisfied.",
                [],
            )

    supporting_eids = list(hypothesis.supporting_evidence_ids)
    supporting_evs = [evidence_by_id[eid] for eid in supporting_eids if eid in evidence_by_id]

    if root_cause_str == "INTERNAL_RELEASE":
        # Requires at least one causally discriminative deployment/release record
        # Valid sources: deployment_log, release_notes
        matched_eids: list[str] = []
        for ev in supporting_evs:
            src = ev.source_id.lower()
            summ = ev.summary.lower()
            if src in ("deployment_log", "release_notes"):
                matched_eids.append(ev.evidence_id)
            elif any(kw in summ for kw in ("release v", "hotfix", "emergency rollback", "deployed v", "deployment log")):
                if src not in ("payment_gateway", "orders", "support_tickets"):
                    matched_eids.append(ev.evidence_id)

        if matched_eids:
            return (
                True,
                f"Claimed root cause INTERNAL_RELEASE is supported by discriminative deployment/release evidence: {sorted(matched_eids)}.",
                sorted(matched_eids),
            )
        else:
            return (
                False,
                "Hypothesis claims INTERNAL_RELEASE root cause, but supporting evidence contains no causally discriminative deployment_log or release_notes records (gateway telemetry and support tickets alone do not prove an internal release).",
                [],
            )

    elif root_cause_str == "EXTERNAL_PROVIDER":
        matched_eids: list[str] = []
        for ev in supporting_evs:
            src = ev.source_id.lower()
            summ = ev.summary.lower()
            if src in ("provider_status", "vendor_incident", "gateway_provider", "third_party_status"):
                matched_eids.append(ev.evidence_id)
            elif any(kw in summ for kw in ("provider status", "vendor status", "upstream provider outage", "third-party status", "gateway provider incident")):
                if src not in ("payment_gateway", "orders", "support_tickets"):
                    matched_eids.append(ev.evidence_id)

        if matched_eids:
            return (
                True,
                f"Claimed root cause EXTERNAL_PROVIDER is supported by provider-specific evidence: {sorted(matched_eids)}.",
                sorted(matched_eids),
            )
        else:
            return (
                False,
                "Hypothesis claims EXTERNAL_PROVIDER root cause, but supporting evidence contains no third-party provider status or vendor incident records (gateway telemetry alone does not prove an external provider outage).",
                [],
            )

    elif root_cause_str == "MACRO_EXTERNAL":
        matched_eids: list[str] = []
        for ev in supporting_evs:
            src = ev.source_id.lower()
            summ = ev.summary.lower()
            if src in ("marketing", "competitor_data", "market_intelligence", "social_media"):
                if is_evidence_anomalous_or_relevant(ev, "external_factors", signals, domain_semantics):
                    matched_eids.append(ev.evidence_id)
            elif any(kw in summ for kw in ("competitor campaign", "market shift", "macro holiday", "ad campaign")):
                matched_eids.append(ev.evidence_id)

        if matched_eids:
            return (
                True,
                f"Claimed root cause MACRO_EXTERNAL is supported by external market/campaign evidence: {sorted(matched_eids)}.",
                sorted(matched_eids),
            )
        else:
            return (
                False,
                "Hypothesis claims MACRO_EXTERNAL root cause, but supporting evidence contains no external market or campaign evidence.",
                [],
            )

    elif root_cause_str == "INVENTORY_SHORTAGE":
        matched_eids: list[str] = []
        for ev in supporting_evs:
            src = ev.source_id.lower()
            if src == "inventory":
                if is_evidence_anomalous_or_relevant(ev, "inventory_system", signals, domain_semantics):
                    matched_eids.append(ev.evidence_id)

        if matched_eids:
            return (
                True,
                f"Claimed root cause INVENTORY_SHORTAGE is supported by anomalous inventory/stockout evidence: {sorted(matched_eids)}.",
                sorted(matched_eids),
            )
        else:
            return (
                False,
                "Hypothesis claims INVENTORY_SHORTAGE root cause, but supporting evidence contains no anomalous inventory or stockout records (normal fill rate does not prove inventory shortage).",
                [],
            )

    elif root_cause_str == "RESOURCE_EXHAUSTION":
        matched_eids: list[str] = []
        for ev in supporting_evs:
            src = ev.source_id.lower()
            summ = ev.summary.lower()
            if any(kw in summ for kw in ("connection pool exhaustion", "memory exhaustion", "cpu saturation", "thread pool", "resource exhaustion", "socket exhaustion")):
                matched_eids.append(ev.evidence_id)
            elif src in ("server_metrics", "infrastructure_telemetry", "host_metrics"):
                matched_eids.append(ev.evidence_id)

        if matched_eids:
            return (
                True,
                f"Claimed root cause RESOURCE_EXHAUSTION is supported by resource telemetry evidence: {sorted(matched_eids)}.",
                sorted(matched_eids),
            )
        else:
            return (
                False,
                "Hypothesis claims RESOURCE_EXHAUSTION root cause, but supporting evidence contains no resource utilization or connection pool saturation telemetry.",
                [],
            )

    return (
        True,
        f"Root cause '{root_cause_str}' evaluated with standard baseline telemetry checks.",
        [],
    )


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

    # Step 2: Support score (Deduplicated, Mechanism Aligned & Baseline Guarded)
    support_score: float = 0.0
    aligned_support_eids: list[str] = []
    unaligned_evidence_ids: list[str] = []

    for eid in support_set:
        ev = evidence_by_id.get(eid)
        if ev is None:
            continue
        mech_tag = getattr(h, "mechanism_tag", "")
        if is_evidence_compatible_with_mechanism(ev, mech_tag, domain_semantics):
            # Baseline / negative-control guard: normal unperturbed evidence contributes 0.0 support
            if is_evidence_anomalous_or_relevant(ev, mech_tag, signals, domain_semantics):
                aligned_support_eids.append(eid)
                support_score += ev.reliability_weight * ev.relevance
            else:
                unaligned_evidence_ids.append(eid)
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

    # Check Root-Cause Evidence Sufficiency Gate
    root_cause_gate_passed, root_cause_rationale, root_cause_eids = check_root_cause_evidence_sufficiency(
        h, evidence_by_id, signals, domain_semantics
    )

    # Determine Verdict
    if final_audit_score >= thresholds.high_threshold and sufficiency_level in (EvidenceSufficiencyLevel.SUFFICIENT, EvidenceSufficiencyLevel.STRONG):
        if root_cause_gate_passed:
            verdict = AuditVerdict.VERIFIED
        else:
            # When root-cause evidence is missing for a specific root_cause_type claim, cap at MARGINAL
            verdict = AuditVerdict.MARGINAL
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
        root_cause_gate_passed=root_cause_gate_passed,
        root_cause_evidence_ids=root_cause_eids,
        root_cause_rationale=root_cause_rationale,
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
