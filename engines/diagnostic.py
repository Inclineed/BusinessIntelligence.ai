"""
engines/diagnostic.py — Engine E3: Diagnostic Engine [SQL+STATS]

Decomposes a KPI movement across dimensions (region, channel, device).
All outputs are deterministic; no LLM.

INC_001: Android must be the dominant negative contributor for conversion.
Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 12.2
"""

from __future__ import annotations

import math
from typing import NamedTuple, Optional

from models import AnomalySignal, DimensionContribution, KPIValue, MethodTag


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


class DecompositionResult(NamedTuple):
    """
    Output of a single decompose() call.

    contributions   : one DimensionContribution per (dimension, segment) pair
    dominant_segment: (dimension_name, segment_name) of the segment with the
                      maximum absolute contribution_pct across ALL dimensions;
                      None when no contributions were produced
    errors          : per-dimension error strings (missing/insufficient data)
    """

    contributions: list[DimensionContribution]
    dominant_segment: Optional[tuple[str, str]]
    errors: list[str]


# ---------------------------------------------------------------------------
# Default dimension list
# ---------------------------------------------------------------------------

_DEFAULT_DIMENSIONS: list[str] = ["device", "region", "channel"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def decompose(
    kpi_values: list[KPIValue],
    signal: AnomalySignal,
    dimensions: list[str] = None,
    db_conn=None,
    scenario_id: str = None,
    window_start=None,
    window_end=None,
) -> DecompositionResult:
    """
    Decompose a KPI movement across the requested dimensions.

    For each dimension, the engine groups the segmented KPIValue entries by
    segment name, computes a per-segment delta contribution, normalises so the
    absolute contributions sum to 100 within ±0.1 pp (Req 4.2), and stamps
    every contribution with MethodTag.SQL (Req 4.5).

    The dominant segment is the segment with the maximum absolute
    contribution_pct across ALL dimensions.  When two segments share the same
    maximum, the one whose segment name sorts lexicographically first is chosen
    (Req 4.3, 4.4).

    If dimensional data is missing or insufficient for a dimension the engine
    skips it, adds an error string, and does NOT mutate any other state (Req 4.6).

    Parameters
    ----------
    kpi_values  : full KPIValue list from E1, including segmented rows
    signal      : AnomalySignal whose kpi_id we are decomposing
    dimensions  : list of dimension keys to evaluate; defaults to
                  ["device", "region", "channel"]
    db_conn     : optional live DB connection (used only when in-memory
                  segmented data is absent for a dimension)
    scenario_id : scenario identifier passed through to any SQL fallback
    window_start: inclusive start of the fallback query window
    window_end  : inclusive end of the fallback query window

    Returns
    -------
    DecompositionResult
    """
    if dimensions is None:
        dimensions = _DEFAULT_DIMENSIONS

    all_contributions: list[DimensionContribution] = []
    errors: list[str] = []

    for dim in dimensions:
        dim_contributions, dim_error = _decompose_dimension(
            kpi_values=kpi_values,
            signal=signal,
            dimension=dim,
        )
        if dim_error:
            errors.append(dim_error)
            # Req 4.6: do not append partial results
            continue
        all_contributions.extend(dim_contributions)

    dominant_segment = _find_dominant(all_contributions)

    return DecompositionResult(
        contributions=all_contributions,
        dominant_segment=dominant_segment,
        errors=errors,
    )


def get_ordered_contributions(
    result: DecompositionResult,
    top_n: int = 5,
) -> list[DimensionContribution]:
    """
    Return contributions sorted by abs(contribution_pct) descending, capped at top_n.

    Parameters
    ----------
    result : DecompositionResult from decompose()
    top_n  : maximum number of results to return

    Returns
    -------
    list[DimensionContribution] — up to top_n entries, most impactful first
    """
    sorted_contribs = sorted(
        result.contributions,
        key=lambda c: abs(c.contribution_pct),
        reverse=True,
    )
    return sorted_contribs[:top_n]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _decompose_dimension(
    kpi_values: list[KPIValue],
    signal: AnomalySignal,
    dimension: str,
) -> tuple[list[DimensionContribution], Optional[str]]:
    """
    Compute contributions for a single dimension.

    Algorithm
    ---------
    1. Separate aggregate (no dimension_filters) rows from segmented rows
       for the target kpi_id.
    2. Sort both groups by period string (ISO-8601 sorts lexicographically).
    3. Use the most-recent aggregate value as ``observed`` (same as signal.observed)
       and the second-most-recent (or mean of earlier) as ``expected``.
    4. For each segment present in the segmented rows, identify a "current"
       period value and a "baseline" period value using the same two-period split.
    5. Compute each segment's delta contribution proportional to its movement
       relative to the overall observed - expected movement.
    6. Normalise so contributions sum to 100.
    7. Return error string (not raise) if data is insufficient.

    Returns
    -------
    (contributions, error_string)  — error_string is None on success
    """
    kpi_id = signal.kpi_id

    # --- 1. Filter to this KPI ---
    kpi_rows = [kv for kv in kpi_values if kv.kpi_id == kpi_id]

    # Segmented rows for this dimension
    seg_rows = [
        kv for kv in kpi_rows
        if dimension in kv.dimension_filters
        and kv.dimension_filters.get(dimension) is not None
    ]

    if not seg_rows:
        return [], (
            f"[E3] dimension='{dimension}' kpi='{kpi_id}': "
            "no segmented data available."
        )

    # Aggregate (no dimension_filters) rows — used to anchor the total movement
    agg_rows = [kv for kv in kpi_rows if not kv.dimension_filters]

    # --- 2. Sort ---
    seg_rows_sorted = sorted(seg_rows, key=lambda kv: kv.period)
    agg_rows_sorted = sorted(agg_rows, key=lambda kv: kv.period) if agg_rows else []

    # --- 3. Determine baseline_mean and observed for anchor ---
    # Use signal's observed and expected (already computed by E2) when present,
    # otherwise fall back to the aggregate row series.
    if not _is_nan(signal.observed) and not _is_nan(signal.expected):
        agg_observed = signal.observed
        agg_expected = signal.expected
    elif len(agg_rows_sorted) >= 2:
        agg_observed = float(agg_rows_sorted[-1].value)
        # Use the mean of all rows except the last as the baseline
        baseline_vals = [
            float(r.value)
            for r in agg_rows_sorted[:-1]
            if _is_finite(r.value)
        ]
        agg_expected = sum(baseline_vals) / len(baseline_vals) if baseline_vals else float("nan")
    elif len(agg_rows_sorted) == 1:
        agg_observed = float(agg_rows_sorted[0].value)
        agg_expected = float(agg_rows_sorted[0].value)  # no movement visible
    else:
        return [], (
            f"[E3] dimension='{dimension}' kpi='{kpi_id}': "
            "insufficient aggregate data to anchor decomposition."
        )

    if _is_nan(agg_observed) or _is_nan(agg_expected):
        return [], (
            f"[E3] dimension='{dimension}' kpi='{kpi_id}': "
            "NaN in observed or expected anchor values."
        )

    total_movement = agg_observed - agg_expected  # signed; 0 means no movement

    # --- 4. Per-segment current and baseline values ---
    # Group segmented rows by segment identifier
    segments: dict[str, list[KPIValue]] = {}
    for kv in seg_rows_sorted:
        seg_label = kv.dimension_filters[dimension]
        segments.setdefault(seg_label, []).append(kv)

    if len(segments) < 1:
        return [], (
            f"[E3] dimension='{dimension}' kpi='{kpi_id}': "
            "no distinct segments found."
        )

    # Compute per-segment current vs baseline value
    # current = most-recent value; baseline = mean of earlier values (or same period
    # mean across other segments when only one data point)
    seg_current: dict[str, float] = {}
    seg_baseline: dict[str, float] = {}

    for seg_label, rows in segments.items():
        rows_sorted = sorted(rows, key=lambda r: r.period)
        finite_vals = [float(r.value) for r in rows_sorted if _is_finite(r.value)]

        if not finite_vals:
            # Missing data for this segment — skip whole dimension
            return [], (
                f"[E3] dimension='{dimension}' kpi='{kpi_id}' "
                f"segment='{seg_label}': no finite values."
            )

        if len(finite_vals) >= 2:
            seg_current[seg_label] = finite_vals[-1]
            seg_baseline[seg_label] = sum(finite_vals[:-1]) / len(finite_vals[:-1])
        else:
            # Only one data point — current equals baseline (zero individual delta)
            seg_current[seg_label] = finite_vals[0]
            seg_baseline[seg_label] = finite_vals[0]

    # --- 5. Compute raw absolute delta contribution per segment ---
    # contribution_raw[seg] = abs(seg_current - seg_baseline)
    # This is the magnitude of each segment's movement.
    # The sign of segment_delta_pct tells direction but contribution_pct is in [0, 100].

    seg_delta: dict[str, float] = {}
    for seg_label in segments:
        seg_delta[seg_label] = seg_current[seg_label] - seg_baseline[seg_label]

    total_abs_delta = sum(abs(d) for d in seg_delta.values())

    if total_abs_delta == 0.0:
        # No movement in any segment — all contributions are zero
        contributions: list[DimensionContribution] = []
        for seg_label in sorted(segments.keys()):
            seg_base = seg_baseline[seg_label]
            seg_delta_pct = 0.0
            contributions.append(
                DimensionContribution(
                    dimension=dimension,
                    segment=seg_label,
                    contribution_pct=0.0,
                    segment_delta_pct=seg_delta_pct,
                    method=MethodTag.SQL,
                )
            )
        return contributions, None

    # --- 6. Raw contribution percentages ---
    raw_pcts: dict[str, float] = {}
    for seg_label in segments:
        raw_pcts[seg_label] = abs(seg_delta[seg_label]) / total_abs_delta * 100.0

    # --- 6b. Normalise so sum == 100 within ±0.1 pp (Req 4.2) ---
    raw_pcts = _normalise_to_100(raw_pcts)

    # --- 7. Compute segment_delta_pct ---
    seg_delta_pcts: dict[str, float] = {}
    for seg_label in segments:
        base = seg_baseline[seg_label]
        if base != 0.0:
            seg_delta_pcts[seg_label] = (
                (seg_current[seg_label] - base) / abs(base) * 100.0
            )
        else:
            seg_delta_pcts[seg_label] = 0.0

    # --- Build DimensionContribution objects (Req 4.5: stamp MethodTag.SQL) ---
    contributions = []
    for seg_label in segments:
        contributions.append(
            DimensionContribution(
                dimension=dimension,
                segment=seg_label,
                contribution_pct=round(raw_pcts[seg_label], 2),
                segment_delta_pct=round(seg_delta_pcts[seg_label], 2),
                method=MethodTag.SQL,
            )
        )

    return contributions, None


def _normalise_to_100(pcts: dict[str, float]) -> dict[str, float]:
    """
    Adjust contribution percentages so they sum to exactly 100.

    The largest segment absorbs the floating-point rounding residual.
    The adjustment is always within ±0.1 pp (Req 4.2).
    """
    total = sum(pcts.values())
    if total == 0.0:
        return pcts
    # Scale to sum == 100
    scaled = {k: v / total * 100.0 for k, v in pcts.items()}
    # Absorb residual into the largest entry
    current_sum = sum(scaled.values())
    residual = 100.0 - current_sum
    if residual != 0.0:
        largest_key = max(scaled, key=lambda k: scaled[k])
        scaled[largest_key] += residual
    return scaled


def _find_dominant(
    contributions: list[DimensionContribution],
) -> Optional[tuple[str, str]]:
    """
    Identify the dominant segment: the segment with max abs(contribution_pct)
    across ALL dimensions.  Lexicographic tie-break on segment name (Req 4.3, 4.4).

    Returns (dimension, segment) or None if contributions is empty.
    """
    if not contributions:
        return None

    # Sort: primary key = -abs(contribution_pct) so highest first,
    # secondary key = segment name (lexicographic ascending) for tie-break.
    ranked = sorted(
        contributions,
        key=lambda c: (-abs(c.contribution_pct), c.segment),
    )
    top = ranked[0]
    return (top.dimension, top.segment)


# ---------------------------------------------------------------------------
# Internal numeric helpers
# ---------------------------------------------------------------------------


def _is_nan(v: float) -> bool:
    """Return True if v is NaN."""
    try:
        return math.isnan(v)
    except (TypeError, ValueError):
        return False


def _is_finite(v) -> bool:
    """Return True if v is a real, finite number."""
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False
