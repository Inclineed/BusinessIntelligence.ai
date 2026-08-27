"""
engines/kpi_store.py — Engine E1: KPI Store [SQL]

Loads connected KPI values from Postgres per the KPI Semantic Contract.
Each KPIValue is stamped with source_id, freshness, and MethodTag.SQL.
LLMs never compute KPI values.

Requirements: 1.1, 1.2, 1.4, 1.7, 2.4, 2.5, 2.6
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import NamedTuple, Optional

import psycopg2

from models import FreshnessStatus, KPIValue, MethodTag
from config.registry import SourceRegistry

# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


class KPILoadResult(NamedTuple):
    """
    Outcome of a load_kpis() call.

    kpi_values   : successfully loaded KPIValue objects
    errors       : error strings for DB failures or unavailable sources
    access_denied: kpi_ids denied because the persona lacked access
    """
    kpi_values: list[KPIValue]
    errors: list[str]
    access_denied: list[str]





# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_kpis(
    scenario_id: str,
    contract: dict,
    registry: SourceRegistry,
    persona: str,
    db_conn,
    authorized_kpi_ids: Optional[list[str]] = None,
    window_start: Optional[datetime] = None,
    window_end: Optional[datetime] = None,
) -> KPILoadResult:
    """
    Load connected KPIs from Postgres per the KPI Semantic Contract.

    Parameters
    ----------
    scenario_id       : identifies the scenario slice in each DB table
    contract          : validated dict from load_kpi_contract() — must contain
                        ``contract["kpis"]`` as a list of KPI definition dicts
    registry          : SourceRegistry instance; freshness is resolved per-KPI
    persona           : requesting persona string (e.g. "analyst", "cfo")
    db_conn           : live psycopg2 connection
    authorized_kpi_ids: optional allow-list; when provided, only KPIs whose id
                        appears in this list are returned (post-access check)
    window_start      : inclusive start of the query window; defaults to 7 days ago
    window_end        : inclusive end of the query window; defaults to utcnow()

    Returns
    -------
    KPILoadResult with three lists:
      kpi_values   — KPIValue objects stamped with source_id, freshness, MethodTag.SQL
      errors       — error strings for DB failures or unavailable sources
      access_denied— kpi_ids denied because the persona lacked access
    """
    now = datetime.utcnow()
    if window_end is None:
        window_end = now
    if window_start is None:
        window_start = now - timedelta(days=7)

    kpi_values: list[KPIValue] = []
    errors: list[str] = []
    access_denied: list[str] = []

    for kpi_def in contract.get("kpis", []):
        kpi_id: str = kpi_def["id"]

        # -----------------------------------------------------------------
        # Optional allow-list filter (applied before access check so callers
        # that pass authorized_kpi_ids can skip irrelevant KPIs cheaply)
        # -----------------------------------------------------------------
        if authorized_kpi_ids is not None and kpi_id not in authorized_kpi_ids:
            continue

        # -----------------------------------------------------------------
        # Persona access check (Requirement 2.2, 2.6)
        # -----------------------------------------------------------------
        access_map: dict = kpi_def.get("access", {})
        if persona not in access_map:
            access_denied.append(kpi_id)
            continue

        kpi_name: str = kpi_def.get("label", kpi_id)
        source_id: str = kpi_def.get("source", "")
        unit: str = kpi_def.get("unit", "")
        query: str = kpi_def.get("query", "")
        grain: str = kpi_def.get("grain", "")
        dimensions: list[str] = kpi_def.get("dimensions", [])

        # -----------------------------------------------------------------
        # Resolve freshness from the registry (Requirement 1.4)
        # -----------------------------------------------------------------
        freshness = _resolve_freshness(source_id, registry, errors)

        # -----------------------------------------------------------------
        # Execute the appropriate SQL query (Requirement 2.4)
        # -----------------------------------------------------------------
        try:
            if not query:
                raise ValueError(f"No SQL query defined in contract for kpi '{kpi_id}'")
            rows = _execute_kpi_query(kpi_id, grain, query, scenario_id, window_start, window_end, db_conn)
        except Exception as exc:  # noqa: BLE001 — never raise; pipeline handles gracefully
            # Requirement 1.7: return KPI with freshness=UNKNOWN and error indication
            errors.append(
                f"[E1] source='{source_id}' kpi='{kpi_id}': DB query failed: {exc}"
            )
            kpi_values.append(
                KPIValue(
                    kpi_id=kpi_id,
                    name=kpi_name,
                    value=float("nan"),
                    unit=unit,
                    period="",
                    dimension_filters={},
                    source_id=source_id,
                    freshness=FreshnessStatus.UNKNOWN,
                    method=MethodTag.SQL,
                )
            )
            continue

        # -----------------------------------------------------------------
        # Build KPIValue objects from result rows
        # -----------------------------------------------------------------
        built = _build_kpi_values(
            kpi_id=kpi_id,
            kpi_name=kpi_name,
            unit=unit,
            source_id=source_id,
            freshness=freshness,
            rows=rows,
            dimensions=dimensions,
        )
        kpi_values.extend(built)

    return KPILoadResult(
        kpi_values=kpi_values,
        errors=errors,
        access_denied=access_denied,
    )


def get_kpi_summary(kpi_values: list[KPIValue]) -> dict:
    """
    Build a quick summary dict keyed by kpi_id for anomaly seeding.

    For each kpi_id, aggregates values into::

        {
            "current":    <most-recent non-NaN value, or None>,
            "baseline":   <oldest non-NaN value, or None>,
            "delta_pct":  <(current - baseline) / baseline * 100, or None>,
            "freshness":  <FreshnessStatus of the most-recent entry, or None>,
        }

    When a kpi has dimension-segmented values (e.g. hourly_conversion by
    device), only the aggregate (empty dimension_filters) entries are used for
    the current/baseline calculation.  If no aggregate row exists, all entries
    are used.

    Parameters
    ----------
    kpi_values : list of KPIValue objects from load_kpis()

    Returns
    -------
    dict mapping kpi_id -> summary sub-dict
    """
    # Group by kpi_id
    grouped: dict[str, list[KPIValue]] = {}
    for kv in kpi_values:
        grouped.setdefault(kv.kpi_id, []).append(kv)

    summary: dict = {}
    for kpi_id, entries in grouped.items():
        # Prefer aggregate (non-segmented) rows for the current/baseline calc
        agg_entries = [e for e in entries if not e.dimension_filters]
        working = agg_entries if agg_entries else entries

        # Filter to finite values only
        finite = [e for e in working if e.value is not None and _is_finite(e.value)]

        # Sort by period string (ISO format sorts lexicographically)
        finite_sorted = sorted(finite, key=lambda e: e.period)

        current_val: Optional[float] = finite_sorted[-1].value if finite_sorted else None
        baseline_val: Optional[float] = finite_sorted[0].value if finite_sorted else None
        freshness_val = entries[-1].freshness if entries else None

        delta_pct: Optional[float] = None
        if (
            current_val is not None
            and baseline_val is not None
            and baseline_val != 0.0
        ):
            delta_pct = (current_val - baseline_val) / abs(baseline_val) * 100.0

        summary[kpi_id] = {
            "current": current_val,
            "baseline": baseline_val,
            "delta_pct": delta_pct,
            "freshness": freshness_val,
        }

    return summary


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_freshness(
    source_id: str,
    registry: SourceRegistry,
    errors: list[str],
) -> FreshnessStatus:
    """
    Look up freshness from the registry.  Returns UNKNOWN and appends an error
    string if the source_id is not registered.
    """
    try:
        entry = registry.get(source_id)
        return registry.compute_freshness(entry)
    except KeyError:
        errors.append(
            f"[E1] source_id '{source_id}' not found in SourceRegistry; "
            "freshness set to UNKNOWN."
        )
        return FreshnessStatus.UNKNOWN


def _execute_kpi_query(
    kpi_id: str,
    grain: str,
    query: str,
    scenario_id: str,
    window_start: datetime,
    window_end: datetime,
    db_conn,
) -> list[tuple]:
    """
    Run the SQL query for *kpi_id*.

    Raises psycopg2.Error (or any other DB exception) on failure — the caller
    wraps this in a try/except.
    """
    from datetime import timedelta

    sql = query
    params = (scenario_id, window_start, window_end)

    with db_conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    valid_rows = []
    for row in rows:
        period_dt = row[0]
        if isinstance(period_dt, datetime):
            # Align naive vs aware for comparison
            w_end = window_end
            p_dt = period_dt
            if w_end.tzinfo is None and p_dt.tzinfo is not None:
                p_dt = p_dt.replace(tzinfo=None)
            elif w_end.tzinfo is not None and p_dt.tzinfo is None:
                p_dt = p_dt.replace(tzinfo=w_end.tzinfo)
            
            # Filter incomplete trailing periods
            grain = grain.lower()
            if "hour" in grain:
                if p_dt + timedelta(hours=1) > w_end:
                    continue
            elif "15-min" in grain or "15min" in grain:
                if p_dt + timedelta(minutes=15) > w_end:
                    continue
            elif "day" in grain or "daily" in grain:
                if p_dt + timedelta(days=1) > w_end:
                    continue
        valid_rows.append(row)

    return valid_rows


def _build_kpi_values(
    kpi_id: str,
    kpi_name: str,
    unit: str,
    source_id: str,
    freshness: FreshnessStatus,
    rows: list[tuple],
    dimensions: list[str],
) -> list[KPIValue]:
    """
    Convert raw DB rows into KPIValue objects.

    If dimensions is present, expects (period, dimension_val, value).
    Otherwise, expects (period, value).
    """
    result: list[KPIValue] = []

    if not rows:
        return result

    if dimensions:
        dim_name = dimensions[0]
        # Segmented by dimension: (period, dim_val, value)
        # Build one KPIValue per (period, dim_val) combination, plus one
        # aggregated KPIValue per period (average across dims in that period).
        period_dim_map: dict[str, dict[str, float]] = {}
        for row in rows:
            period_dt, dim_val, value = row[0], row[1], row[2]
            period_str = _period_to_str(period_dt)
            val = float(value) if value is not None else float("nan")
            result.append(
                KPIValue(
                    kpi_id=kpi_id,
                    name=kpi_name,
                    value=val,
                    unit=unit,
                    period=period_str,
                    dimension_filters={dim_name: str(dim_val)},
                    source_id=source_id,
                    freshness=freshness,
                    method=MethodTag.SQL,
                )
            )
            period_dim_map.setdefault(period_str, {})[str(dim_val)] = val

        # Aggregate row per period (mean of finite dim values)
        for period_str, dim_vals in sorted(period_dim_map.items()):
            finite_vals = [v for v in dim_vals.values() if _is_finite(v)]
            agg_val = sum(finite_vals) / len(finite_vals) if finite_vals else float("nan")
            result.append(
                KPIValue(
                    kpi_id=kpi_id,
                    name=kpi_name,
                    value=agg_val,
                    unit=unit,
                    period=period_str,
                    dimension_filters={},
                    source_id=source_id,
                    freshness=freshness,
                    method=MethodTag.SQL,
                )
            )

    else:
        # Simple (period, value) shape
        for row in rows:
            period_dt, value = row[0], row[1]
            period_str = _period_to_str(period_dt)
            val = float(value) if value is not None else float("nan")
            result.append(
                KPIValue(
                    kpi_id=kpi_id,
                    name=kpi_name,
                    value=val,
                    unit=unit,
                    period=period_str,
                    dimension_filters={},
                    source_id=source_id,
                    freshness=freshness,
                    method=MethodTag.SQL,
                )
            )

    return result


def _period_to_str(period) -> str:
    """Convert a DB timestamp/date to an ISO-8601 string."""
    if period is None:
        return ""
    if isinstance(period, str):
        return period
    # datetime, date, or similar
    try:
        return period.isoformat()
    except AttributeError:
        return str(period)


def _is_finite(v: float) -> bool:
    """Return True if v is a real, finite number (not NaN, not Inf)."""
    import math
    return not (math.isnan(v) or math.isinf(v))
