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

from models import Decision, MethodTag, OutcomeProjection, OutcomeType

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

RECOVERY_CURVES: dict[str, dict] = {
    "rollback": {
        "projected_metric": "payment_success_rate + conversion_rate",
        "projected_recovery_pct": 85.0,
        "recovery_window_hours": 2,
        "narrative": (
            "Following a rollback of the problematic release, payment success rate "
            "and conversion are expected to recover toward baseline levels within "
            "the defined window."
        ),
    },
    "reorder": {
        "projected_metric": "inventory_fill_rate",
        "projected_recovery_pct": 90.0,
        "recovery_window_hours": 6,
    },
    "default": {
        "projected_metric": "kpi_primary_metric",
        "projected_recovery_pct": 75.0,
        "recovery_window_hours": 4,
    },
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _match_curve(recommended_action: str) -> dict:
    """
    Determine the best-matching recovery curve from the recommended action text.

    Looks for intervention keywords in order of specificity.  Falls back to
    the 'default' curve when no keyword matches.

    Parameters
    ----------
    recommended_action : The recommended-action string from the Decision Engine.

    Returns
    -------
    The matching curve dict from RECOVERY_CURVES.
    """
    lower = recommended_action.lower()

    if any(kw in lower for kw in ("rollback", "roll back", "revert", "downgrade")):
        return RECOVERY_CURVES["rollback"]

    if any(kw in lower for kw in ("reorder", "re-order", "replenish", "restock",
                                   "inventory", "supply")):
        return RECOVERY_CURVES["reorder"]

    return RECOVERY_CURVES["default"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def project_outcome(decision: Decision) -> Optional[OutcomeProjection]:
    """
    Engine E8: produce a SIMULATED outcome projection from a Decision.

    Returns None (no projection) when:
    - The decision is abstained (no recommended action to project on).
    - The guard assertion detects a non-SIMULATED tag (should never happen
      under normal operation — exists to satisfy Req 14.5).

    Parameters
    ----------
    decision : Decision produced by Engine E7.

    Returns
    -------
    OutcomeProjection stamped with OutcomeType.SIMULATED and
    MethodTag.SIMULATED, or None.

    Requirements: 14.1, 14.2, 14.3, 14.5
    """
    # Guard: abstained decisions carry no recommended action — nothing to project.
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

    # Select the matching pre-scripted recovery curve.
    curve = _match_curve(decision.recommended_action)

    # Build the projection — always SIMULATED (Req 14.1, 14.2).
    projection = OutcomeProjection(
        outcome_type=OutcomeType.SIMULATED,
        projected_metric=curve["projected_metric"],
        projected_recovery_pct=curve["projected_recovery_pct"],
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
