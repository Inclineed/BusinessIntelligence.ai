"""
engines/signal.py — Engine E2: Signal Engine [STATS]

Anomaly detection over connected KPI values.
All outputs are deterministic; no LLM involvement.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from models import (
    AnomalySignal,
    BusinessMateriality,
    FreshnessStatus,
    KPIValue,
    MaterialityAssessment,
    MethodTag,
)


# ---------------------------------------------------------------------------
# History window container
# ---------------------------------------------------------------------------


@dataclass
class HistoryWindow:
    """
    Baseline window for a single KPI.

    values              : ordered oldest-to-newest baseline values
    periods             : corresponding ISO-8601 period strings
    data_quality_score  : [0, 1] quality score for this window
    """

    kpi_id: str
    values: list[float]
    periods: list[str]
    data_quality_score: float = 1.0


# ---------------------------------------------------------------------------
# Default thresholds
# ---------------------------------------------------------------------------

_DEFAULT_THRESHOLDS: dict = {
    "zscore": 3.0,
    "delta_pct": 10.0,
    "sparse_history_min_samples": 30,
    "data_quality_min": 0.80,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_signals(
    kpi_values: list[KPIValue],
    history: dict[str, HistoryWindow],
    thresholds: dict = None,
) -> list[AnomalySignal]:
    """
    Detect anomalies in *kpi_values* against the provided baseline *history*.

    Only aggregate rows (those with empty dimension_filters) are evaluated.
    The most-recent aggregate value is used as the "observed" (current) value.

    Parameters
    ----------
    kpi_values  : KPIValue objects from Engine E1
    history     : mapping kpi_id → HistoryWindow (baseline samples)
    thresholds  : override dict; falls back to _DEFAULT_THRESHOLDS for missing keys

    Returns
    -------
    list[AnomalySignal] — one signal per kpi_id found in kpi_values (aggregate
    rows).  Each signal is stamped with MethodTag.STATS.

    Requirements: 3.1, 3.2, 3.3, 3.5, 3.6
    """
    if thresholds is None:
        thresholds = {}

    # Merge provided thresholds over defaults
    t = {**_DEFAULT_THRESHOLDS, **thresholds}

    zscore_thresh: float = float(t["zscore"])
    delta_pct_thresh: float = float(t["delta_pct"])
    min_samples: int = int(t["sparse_history_min_samples"])
    dq_min: float = float(t["data_quality_min"])

    # Group aggregate KPI values by kpi_id (empty dimension_filters)
    agg_by_kpi: dict[str, list[KPIValue]] = {}
    for kv in kpi_values:
        if kv.dimension_filters:
            continue  # skip segmented rows
        agg_by_kpi.setdefault(kv.kpi_id, []).append(kv)

    signals: list[AnomalySignal] = []

    for kpi_id, entries in agg_by_kpi.items():
        # Sort by period string (ISO-8601 sorts lexicographically)
        entries_sorted = sorted(entries, key=lambda e: e.period)
        latest = entries_sorted[-1]
        observed = latest.value if not _is_nan(latest.value) else float("nan")

        # ---------------------------------------------------------------
        # Look up history window
        # ---------------------------------------------------------------
        window = history.get(kpi_id)

        if window is None:
            # Req 3.6: no baseline data → not evaluable
            signals.append(
                AnomalySignal(
                    kpi_id=kpi_id,
                    observed=observed,
                    expected=float("nan"),
                    delta_pct=0.0,
                    z_score=0.0,
                    is_anomaly=False,
                    corroborated_by=[],
                    sparse_history=False,
                    data_quality_suspect=False,
                    method=MethodTag.STATS,
                )
            )
            continue

        baseline_values = [v for v in window.values if not _is_nan(v) and math.isfinite(v)]

        if not baseline_values:
            # Req 3.6: absent baseline data → not evaluable
            signals.append(
                AnomalySignal(
                    kpi_id=kpi_id,
                    observed=observed,
                    expected=float("nan"),
                    delta_pct=0.0,
                    z_score=0.0,
                    is_anomaly=False,
                    corroborated_by=[],
                    sparse_history=False,
                    data_quality_suspect=False,
                    method=MethodTag.STATS,
                )
            )
            continue

        # ---------------------------------------------------------------
        # Req 3.2: Sparse-history guard
        # ---------------------------------------------------------------
        if len(baseline_values) < min_samples:
            signals.append(
                AnomalySignal(
                    kpi_id=kpi_id,
                    observed=observed,
                    expected=float(np.mean(baseline_values)),
                    delta_pct=0.0,
                    z_score=0.0,
                    is_anomaly=False,
                    corroborated_by=[],
                    sparse_history=True,
                    data_quality_suspect=False,
                    method=MethodTag.STATS,
                )
            )
            continue

        # ---------------------------------------------------------------
        # Req 3.1: Compute z-score and delta_pct
        # ---------------------------------------------------------------
        baseline_mean = float(np.mean(baseline_values))
        baseline_std = float(np.std(baseline_values, ddof=1))

        if baseline_std == 0.0:
            z_score_raw = 0.0
        else:
            z_score_raw = (observed - baseline_mean) / baseline_std

        # Clamp to [-1000, 1000], round to 2 dp
        z_score = round(max(-1000.0, min(1000.0, z_score_raw)), 2)

        if baseline_mean != 0.0:
            delta_pct_raw = (observed - baseline_mean) / abs(baseline_mean) * 100.0
        else:
            delta_pct_raw = 0.0

        # Clamp to [-100, 100], round to 2 dp
        delta_pct = round(max(-100.0, min(100.0, delta_pct_raw)), 2)

        # ---------------------------------------------------------------
        # Req 3.3: Data-quality guard
        # ---------------------------------------------------------------
        data_quality_suspect = window.data_quality_score < dq_min

        if data_quality_suspect:
            signals.append(
                AnomalySignal(
                    kpi_id=kpi_id,
                    observed=observed,
                    expected=baseline_mean,
                    delta_pct=delta_pct,
                    z_score=z_score,
                    is_anomaly=False,
                    corroborated_by=[],
                    sparse_history=False,
                    data_quality_suspect=True,
                    method=MethodTag.STATS,
                )
            )
            continue

        # ---------------------------------------------------------------
        # Req 3.5: Anomaly threshold — both guards must be False
        # ---------------------------------------------------------------
        is_anomaly = abs(z_score) >= zscore_thresh and abs(delta_pct) >= delta_pct_thresh

        signals.append(
            AnomalySignal(
                kpi_id=kpi_id,
                observed=observed,
                expected=baseline_mean,
                delta_pct=delta_pct,
                z_score=z_score,
                is_anomaly=is_anomaly,
                corroborated_by=[],
                sparse_history=False,
                data_quality_suspect=False,
                method=MethodTag.STATS,
            )
        )

    return signals


def assert_corroboration(
    signals: list[AnomalySignal],
    kpi_periods: dict[str, list[str]],
) -> list[AnomalySignal]:
    """
    For each pair of anomalous signals whose observation periods overlap by
    >= 80% of the shorter period's duration, add each kpi_id to the other
    signal's corroborated_by list.

    Parameters
    ----------
    signals     : list[AnomalySignal] from detect_signals()
    kpi_periods : mapping kpi_id → list[ISO-8601 period strings] of the
                  observed (current) window for that KPI

    Returns
    -------
    The same list with corroborated_by fields populated in-place.

    Requirements: 3.4
    """
    # Only consider anomalous signals
    anomalous = [s for s in signals if s.is_anomaly]

    for i, sig_a in enumerate(anomalous):
        for sig_b in anomalous[i + 1 :]:
            periods_a = set(kpi_periods.get(sig_a.kpi_id, []))
            periods_b = set(kpi_periods.get(sig_b.kpi_id, []))

            if not periods_a or not periods_b:
                continue

            overlap = len(periods_a & periods_b)
            shorter = min(len(periods_a), len(periods_b))

            if shorter == 0:
                continue

            overlap_ratio = overlap / shorter
            if overlap_ratio >= 0.80:
                if sig_b.kpi_id not in sig_a.corroborated_by:
                    sig_a.corroborated_by.append(sig_b.kpi_id)
                if sig_a.kpi_id not in sig_b.corroborated_by:
                    sig_b.corroborated_by.append(sig_a.kpi_id)

    return signals


def build_history_from_kpis(
    all_kpi_values: list[KPIValue],
    baseline_kpi_ids: list[str] = None,
) -> dict[str, HistoryWindow]:
    """
    Build HistoryWindow objects from a KPIValue series.

    Uses aggregate rows only (empty dimension_filters), sorted by period.
    All values except the last are used as the baseline window; the last
    value is the "current" observation that detect_signals() will score.

    Parameters
    ----------
    all_kpi_values  : full time series including the current value
    baseline_kpi_ids: optional allow-list; when provided only these kpi_ids
                      are built into history windows

    Returns
    -------
    dict mapping kpi_id → HistoryWindow
    """
    grouped: dict[str, list[KPIValue]] = {}
    for kv in all_kpi_values:
        if kv.dimension_filters:
            continue  # aggregate rows only
        if baseline_kpi_ids is not None and kv.kpi_id not in baseline_kpi_ids:
            continue
        grouped.setdefault(kv.kpi_id, []).append(kv)

    history: dict[str, HistoryWindow] = {}
    for kpi_id, entries in grouped.items():
        sorted_entries = sorted(entries, key=lambda e: e.period)
        # All but the last → baseline; last → current (handled by detect_signals)
        baseline_entries = sorted_entries[:-1]
        values = [
            float(e.value) if not _is_nan(e.value) else float("nan")
            for e in baseline_entries
        ]
        periods = [e.period for e in baseline_entries]
        history[kpi_id] = HistoryWindow(
            kpi_id=kpi_id,
            values=values,
            periods=periods,
        )

    return history


# ---------------------------------------------------------------------------
# Business Materiality & Priority Ranking
# ---------------------------------------------------------------------------

_MATERIALITY_SEVERITY_ORDER: dict[BusinessMateriality, int] = {
    BusinessMateriality.CRITICAL: 1,
    BusinessMateriality.HIGH: 2,
    BusinessMateriality.MEDIUM: 3,
    BusinessMateriality.LOW: 4,
    BusinessMateriality.NEGLIGIBLE: 5,
}


def assess_materiality(
    signals: list[AnomalySignal],
    kpi_contract: dict | None = None,
    segmentable_kpi_ids: Optional[set[str]] = None,
) -> list[MaterialityAssessment]:
    """
    Assess business materiality for each AnomalySignal.

    Distinguishes statistical significance from business impact and assigns
    deterministic priority ranking:
      1. Materiality severity (CRITICAL -> HIGH -> MEDIUM -> LOW -> NEGLIGIBLE)
      2. Absolute business impact (financial or volume magnitude)
      3. Segmentability tie-breaker (segmentable before non-segmentable)
      4. Deterministic KPI ID tie-breaker

    Non-anomalies default to NEGLIGIBLE and are excluded from investigation ranking (priority_rank=0).
    """
    if segmentable_kpi_ids is None:
        segmentable_kpi_ids = set()

    # Map KPI id to contract definition if provided
    contract_by_id: dict[str, dict] = {}
    if kpi_contract and isinstance(kpi_contract, dict):
        for kpi_def in kpi_contract.get("kpis", []):
            if isinstance(kpi_def, dict) and "id" in kpi_def:
                contract_by_id[kpi_def["id"]] = kpi_def

    assessments: list[MaterialityAssessment] = []
    anomalous_assessments: list[tuple[MaterialityAssessment, float, bool]] = []

    for sig in signals:
        kpi_def = contract_by_id.get(sig.kpi_id, {})
        mat_cfg = kpi_def.get("materiality", {})

        observed_val = sig.observed
        expected_val = sig.expected
        baseline_mean = expected_val if not _is_nan(expected_val) else 0.0

        if not sig.is_anomaly or _is_nan(observed_val) or _is_nan(expected_val):
            # Non-anomalies or un-evaluable signals default to NEGLIGIBLE (excluded from rank)
            assessments.append(
                MaterialityAssessment(
                    kpi_id=sig.kpi_id,
                    observed_value=observed_val,
                    baseline_mean=baseline_mean,
                    z_score=sig.z_score,
                    delta_pct=sig.delta_pct,
                    is_statistical_anomaly=sig.is_anomaly,
                    financial_impact=None,
                    volume_impact=None,
                    business_materiality=BusinessMateriality.NEGLIGIBLE,
                    priority_rank=0,
                )
            )
            continue

        # Anomaly confirmed: compute absolute delta and business impact
        abs_delta = abs(observed_val - baseline_mean)
        impact_metric = mat_cfg.get("impact_metric", "financial")
        multiplier = float(mat_cfg.get("multiplier", 1.0))
        calculated_impact = round(abs_delta * multiplier, 2)

        crit_thresh = float(mat_cfg.get("critical_threshold", 50000.0))
        high_thresh = float(mat_cfg.get("high_threshold", 10000.0))
        med_thresh = float(mat_cfg.get("medium_threshold", 5000.0))
        low_thresh = float(mat_cfg.get("low_threshold", 1000.0))

        if calculated_impact >= crit_thresh:
            tier = BusinessMateriality.CRITICAL
        elif calculated_impact >= high_thresh:
            tier = BusinessMateriality.HIGH
        elif calculated_impact >= med_thresh:
            tier = BusinessMateriality.MEDIUM
        elif calculated_impact >= low_thresh:
            tier = BusinessMateriality.LOW
        else:
            tier = BusinessMateriality.NEGLIGIBLE

        fin_impact: Optional[float] = calculated_impact if impact_metric == "financial" else None
        vol_impact: Optional[float] = calculated_impact if impact_metric == "volume" else None

        assessment = MaterialityAssessment(
            kpi_id=sig.kpi_id,
            observed_value=observed_val,
            baseline_mean=baseline_mean,
            z_score=sig.z_score,
            delta_pct=sig.delta_pct,
            is_statistical_anomaly=True,
            financial_impact=fin_impact,
            volume_impact=vol_impact,
            business_materiality=tier,
            priority_rank=0,  # ranked below
        )
        is_seg = sig.kpi_id in segmentable_kpi_ids
        anomalous_assessments.append((assessment, calculated_impact, is_seg))
        assessments.append(assessment)

    # Sort anomalous assessments deterministically:
    # 1. Materiality severity (1=CRITICAL, 2=HIGH, 3=MEDIUM, 4=LOW, 5=NEGLIGIBLE)
    # 2. -calculated_impact (descending impact magnitude)
    # 3. not is_seg (segmentable True comes before False)
    # 4. kpi_id (alphabetical)
    anomalous_assessments.sort(
        key=lambda item: (
            _MATERIALITY_SEVERITY_ORDER[item[0].business_materiality],
            -item[1],
            not item[2],
            item[0].kpi_id,
        )
    )

    for rank, (assessment, _, _) in enumerate(anomalous_assessments, start=1):
        assessment.priority_rank = rank

    return assessments


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_nan(v: float) -> bool:
    """Return True if v is NaN."""
    try:
        return math.isnan(v)
    except (TypeError, ValueError):
        return False
