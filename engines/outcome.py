"""
engines/outcome.py — Engine E8: Outcome Engine [SIMULATED]

Projects a simulated outcome based on the recommended decision.
NEVER presents projections as causal proof.
Every projection carries outcome_type=SIMULATED and a disclaimer.

Requirements: 14.1–14.6
"""

from __future__ import annotations

import logging
from typing import Optional

from models import AuditVerdict, Decision, MethodTag, OutcomeProjection, OutcomeType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

SIMULATED_DISCLAIMER: str = (
    "This projection is a simulated estimate based on scripted recovery patterns. "
    "It is not causal proof. Causal effect has not been independently established."
)

# ---------------------------------------------------------------------------
# Pre-scripted recovery projections keyed by intervention type.
# All projections are SIMULATED — never observed.  The Engine reads these
# curves to populate OutcomeProjection fields deterministically (no LLM,
# no random state, no wall-clock reads).
#
# Keys
# ----
#   projected_metric        : The KPI(s) expected to recover.
#   projected_recovery_pct  : Scripted % recovery toward baseline within the window.
#   recovery_window_hours   : Expected time to see the projected recovery.
#   narrative               : Optional plain-text context (display only).
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _match_curve(recommended_action: str, domain_semantics: dict) -> Optional[dict]:
    """
    Determine the best-matching recovery curve from the recommended action text.

    Looks for intervention keywords in order of specificity from domain_semantics.
    Returns the matched curve data, or the 'default' curve if it represents an operational action.
    Returns None if the action is diagnostic or non-remedial.
    """
    lower = recommended_action.lower()

    # Defense-in-depth: diagnostic directives never match operational recovery curves
    if (
        "targeted diagnostic investigation" in lower
        or "targeted diagnostic" in lower
        or "diagnostic verification" in lower
        or "collect telemetry and verify" in lower
        or "diagnostic investigation" in lower
    ):
        return None

    recovery_curves = domain_semantics.get("recovery_curves", {})

    for curve_id, curve_data in recovery_curves.items():
        if curve_id == "default":
             continue
        if any(kw in lower for kw in curve_data.get("keywords", [])):
            return curve_data

    return recovery_curves.get("default", {
        "projected_metric": "kpi_primary_metric",
        "projected_recovery_pct": 75.0,
        "recovery_window_hours": 4,
        "mean_time_to_normalcy": "15 min",
        "assumptions": ["Remediation directly addresses identified primary anomaly driver."],
    })


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def project_outcome(
    decision: Decision,
    domain_semantics: Optional[dict] = None,
    overall_verdict: Optional[AuditVerdict] = None,
) -> Optional[OutcomeProjection]:
    """
    Engine E8: produce a SIMULATED outcome projection from a Decision.

    Returns None (no projection) when:
    - The decision is abstained (no recommended action to project on).
    - The decision has no recommended action.
    - The overall_verdict is not VERIFIED (e.g. MARGINAL, ABSTAIN, REJECTED).
    - The recommended action or lever is diagnostic/telemetry verification rather than operational remediation.
    - The guard assertion detects a non-SIMULATED tag or missing disclaimer.

    Parameters
    ----------
    decision        : Decision produced by Engine E7.
    domain_semantics: Optional domain semantics dictionary containing recovery curves.
    overall_verdict : Optional AuditVerdict from Engine E6 / E7 governance state.

    Returns
    -------
    OutcomeProjection stamped with OutcomeType.SIMULATED and
    MethodTag.SIMULATED, or None.

    Requirements: 14.1, 14.2, 14.3, 14.5
    """
    # Guard 1: Abstained decisions carry no recommended action — nothing to project (Req 14.3)
    if decision.abstained:
        logger.info(
            "project_outcome: decision is abstained; no projection produced."
        )
        return None

    if decision.recommended_action is None:
        logger.warning(
            "project_outcome: recommended_action is None on a non-abstained decision; "
            "no projection produced."
        )
        return None

    # Guard 2: Structured verdict check (Governance State Gating)
    # Only VERIFIED hypotheses with operational remediation are eligible for recovery simulation.
    # MARGINAL, ABSTAIN, and REJECTED states MUST return None.
    if overall_verdict is not None and overall_verdict != AuditVerdict.VERIFIED:
        logger.info(
            "project_outcome: overall_verdict is %s (not VERIFIED); suppressing recovery projection.",
            overall_verdict.value if hasattr(overall_verdict, "value") else str(overall_verdict),
        )
        return None

    # Guard 3: Structured lever check (Diagnostic levers produce no operational recovery)
    if decision.structured_recommendation:
        lever = (decision.structured_recommendation.controllable_lever or "").strip().lower()
        if "diagnostic" in lever or "telemetry" in lever:
            logger.info(
                "project_outcome: controllable_lever is diagnostic (%r); suppressing recovery projection.",
                decision.structured_recommendation.controllable_lever,
            )
            return None

    # Guard 4: Prose-level diagnostic keyword check (defense-in-depth)
    lower_action = decision.recommended_action.lower()
    if (
        lower_action.startswith("targeted diagnostic investigation")
        or "collect telemetry and verify" in lower_action
        or "diagnostic telemetry before committing" in lower_action
    ):
        logger.info(
            "project_outcome: recommended_action is a diagnostic directive; suppressing recovery projection."
        )
        return None

    domain_semantics = domain_semantics or {}
    curve = _match_curve(decision.recommended_action, domain_semantics)

    if not curve:
        logger.info(
            "project_outcome: action %r did not match an operational recovery curve; no projection produced.",
            decision.recommended_action,
        )
        return None

    # Build the projection — always SIMULATED (Req 14.1, 14.2).
    projection = OutcomeProjection(
        outcome_type=OutcomeType.SIMULATED,
        projected_metric=curve["projected_metric"],
        projected_recovery_pct=curve["projected_recovery_pct"],
        recovery_window_hours=curve.get("recovery_window_hours"),
        mean_time_to_normalcy=curve.get("mean_time_to_normalcy", "5 min"),
        assumptions=list(curve.get("assumptions", [])),
        disclaimer=SIMULATED_DISCLAIMER,
        method=MethodTag.SIMULATED,
    )

    # Guard assertion: withhold if the tag is somehow not SIMULATED (Req 14.5).
    # Under normal code paths this never fires, but it provides a hard
    # safety net if the dataclass default is changed inadvertently.
    if not validate_outcome_projection(projection):
        logger.error(
            "project_outcome: guard assertion failed — projection lacks "
            "SIMULATED tag or disclaimer; withheld from output (Req 14.5)."
        )
        return None

    logger.info(
        "project_outcome: projection produced — metric=%r, recovery_pct=%.1f%%.",
        projection.projected_metric,
        projection.projected_recovery_pct,
    )
    return projection


def validate_outcome_projection(projection: OutcomeProjection) -> bool:
    """
    Validate that an OutcomeProjection meets the minimum honesty requirements.

    A projection that fails validation MUST be withheld from display (Req 14.5).

    Checks
    ------
    1. outcome_type == OutcomeType.SIMULATED  (Req 14.1)
    2. method == MethodTag.SIMULATED          (Req 14.1)
    3. disclaimer is a non-empty string       (Req 14.2)

    Parameters
    ----------
    projection : The OutcomeProjection to validate.

    Returns
    -------
    True if all checks pass, False otherwise.
    """
    if projection.outcome_type != OutcomeType.SIMULATED:
        logger.warning(
            "validate_outcome_projection: outcome_type is %r, expected SIMULATED.",
            projection.outcome_type,
        )
        return False

    if projection.method != MethodTag.SIMULATED:
        logger.warning(
            "validate_outcome_projection: method tag is %r, expected SIMULATED.",
            projection.method,
        )
        return False

    if not projection.disclaimer or not projection.disclaimer.strip():
        logger.warning(
            "validate_outcome_projection: disclaimer is empty or whitespace-only."
        )
        return False

    return True
