"""
evaluation/feedback_metrics.py — Feedback Quality Metrics Evaluator.

Computes institutional feedback statistics from the PostgreSQL feedback table.
These metrics measure the degree to which human analysts have reviewed,
confirmed, corrected, or rejected autonomous pipeline decisions.

This module does NOT compute "model accuracy" — it computes human agreement
and coverage metrics that serve as institutional learning signals.

Requirements: Round 2 — Human Feedback → Validation → Learning Loop
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class FeedbackMetrics:
    """Aggregate feedback quality metrics."""

    feedback_count: int = 0
    feedback_coverage: float = 0.0
    scenarios_with_feedback: int = 0
    total_scenarios: int = 0
    human_confirmed_count: int = 0
    human_rejected_count: int = 0
    partial_correction_count: int = 0
    unsure_count: int = 0
    validated_precedent_count: int = 0
    human_agreement_rate: Optional[float] = None
    per_scenario: dict[str, dict] = field(default_factory=dict)


def compute_feedback_metrics(db_conn) -> FeedbackMetrics:
    """
    Compute aggregate feedback quality metrics from PostgreSQL.

    Returns a FeedbackMetrics dataclass with all computed values.
    Raises RuntimeError if db_conn is None or query fails.
    """
    if db_conn is None:
        raise RuntimeError("compute_feedback_metrics: no database connection")

    metrics = FeedbackMetrics()

    try:
        with db_conn.cursor() as cur:
            # Aggregate counts
            cur.execute("""
                SELECT
                    COUNT(*) AS feedback_count,
                    COUNT(DISTINCT scenario_id) AS scenarios_with_feedback,
                    COUNT(*) FILTER (WHERE verdict = 'CORRECT') AS human_confirmed,
                    COUNT(*) FILTER (WHERE verdict = 'INCORRECT') AS human_rejected,
                    COUNT(*) FILTER (WHERE verdict = 'PARTIALLY_CORRECT') AS partial_corrections,
                    COUNT(*) FILTER (WHERE verdict = 'UNSURE') AS unsure_count,
                    COUNT(*) FILTER (WHERE validated_precedent = TRUE) AS validated_precedents
                FROM feedback
            """)
            row = cur.fetchone()

            metrics.feedback_count = row[0] or 0
            metrics.scenarios_with_feedback = row[1] or 0
            metrics.human_confirmed_count = row[2] or 0
            metrics.human_rejected_count = row[3] or 0
            metrics.partial_correction_count = row[4] or 0
            metrics.unsure_count = row[5] or 0
            metrics.validated_precedent_count = row[6] or 0

            # Human agreement rate: CORRECT / (CORRECT + INCORRECT)
            decisive = metrics.human_confirmed_count + metrics.human_rejected_count
            if decisive > 0:
                metrics.human_agreement_rate = round(
                    metrics.human_confirmed_count / decisive, 4
                )

            # Total scenarios for coverage
            cur.execute("SELECT COUNT(DISTINCT scenario_id) FROM investigations")
            metrics.total_scenarios = cur.fetchone()[0] or 0

            if metrics.total_scenarios > 0:
                metrics.feedback_coverage = round(
                    metrics.scenarios_with_feedback / metrics.total_scenarios, 4
                )

            # Per-scenario breakdown
            cur.execute("""
                SELECT
                    scenario_id,
                    COUNT(*) AS count,
                    COUNT(*) FILTER (WHERE verdict = 'CORRECT') AS confirmed,
                    COUNT(*) FILTER (WHERE verdict = 'INCORRECT') AS rejected,
                    COUNT(*) FILTER (WHERE verdict = 'PARTIALLY_CORRECT') AS partial,
                    COUNT(*) FILTER (WHERE verdict = 'UNSURE') AS unsure,
                    bool_or(validated_precedent) AS has_validated_precedent
                FROM feedback
                WHERE scenario_id IS NOT NULL
                GROUP BY scenario_id
                ORDER BY scenario_id
            """)
            for r in cur.fetchall():
                sc_decisive = (r[2] or 0) + (r[3] or 0)
                metrics.per_scenario[r[0]] = {
                    "feedback_count": r[1] or 0,
                    "human_confirmed": r[2] or 0,
                    "human_rejected": r[3] or 0,
                    "partial_corrections": r[4] or 0,
                    "unsure": r[5] or 0,
                    "has_validated_precedent": bool(r[6]),
                    "agreement_rate": round((r[2] or 0) / sc_decisive, 4) if sc_decisive > 0 else None,
                }

    except Exception as exc:
        logger.error("compute_feedback_metrics: DB error: %s", exc)
        try:
            db_conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(f"Failed to compute feedback metrics: {exc}") from exc

    return metrics
