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
# Unit labels for each KPI
# ---------------------------------------------------------------------------

_KPI_UNITS: dict[str, str] = {
    "hourly_revenue": "USD",
    "hourly_conversion": "ratio",
    "payment_failure_rate_15min": "ratio",
    "gateway_latency_15min": "ms",
    "inventory_fill_rate_daily": "ratio",
}

# ---------------------------------------------------------------------------
# SQL queries per KPI id
# ---------------------------------------------------------------------------
# Each query accepts (scenario_id, window_start, window_end) as positional
# %s parameters (psycopg2 style).

_QUERIES: dict[str, str] = {
    "hourly_revenue": """
        SELECT
            date_trunc('hour', ts) AS period,
            SUM(revenue) AS value
        FROM orders
        WHERE scenario_id = %s
          AND conversion = true
          AND ts >= %s
          AND ts <= %s
        GROUP BY period
        ORDER BY period
    """,

    "hourly_conversion": """
        SELECT
            date_trunc('hour', ts) AS period,
            device,
            COUNT(CASE WHEN conversion = true THEN 1 END)::float
                / NULLIF(COUNT(*), 0) AS value
        FROM orders
        WHERE scenario_id = %s
          AND ts >= %s
          AND ts <= %s
        GROUP BY period, device
        ORDER BY period, device
    """,

    # Aggregate (device-agnostic) version for hourly_conversion summary row
    "_hourly_conversion_agg": """
        SELECT
            date_trunc('hour', ts) AS period,
            COUNT(CASE WHEN conversion = true THEN 1 END)::float
                / NULLIF(COUNT(*), 0) AS value
        FROM orders
        WHERE scenario_id = %s
          AND ts >= %s
          AND ts <= %s
        GROUP BY period
        ORDER BY period
    """,

    "payment_failure_rate_15min": """
        SELECT
            date_trunc('minute', ts
                - (EXTRACT(minute FROM ts)::int %% 15) * interval '1 minute'
            ) AS period,
            COUNT(CASE WHEN success = false THEN 1 END)::float
                / NULLIF(COUNT(*), 0) AS value
        FROM payment_events
        WHERE scenario_id = %s
          AND ts >= %s
          AND ts <= %s
        GROUP BY period
        ORDER BY period
    """,

    "gateway_latency_15min": """
        SELECT
            date_trunc('minute', ts
                - (EXTRACT(minute FROM ts)::int %% 15) * interval '1 minute'
            ) AS period,
            PERCENTILE_CONT(0.95)
                WITHIN GROUP (ORDER BY latency_ms) AS value
        FROM payment_events
        WHERE scenario_id = %s
          AND ts >= %s
          AND ts <= %s
        GROUP BY period
        ORDER BY period
    """,

    "inventory_fill_rate_daily": """
        SELECT
            date_trunc('day', ts) AS period,
            store_id,
            COUNT(CASE WHEN in_stock = true THEN 1 END)::float
                / NULLIF(COUNT(*), 0) AS value
        FROM inventory_events
        WHERE scenario_id = %s
          AND ts >= %s
          AND ts <= %s
        GROUP BY period, store_id
        ORDER BY period, store_id
    """,
}


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
        unit: str = _KPI_UNITS.get(kpi_id, "")

        # -----------------------------------------------------------------
        # Resolve freshness from the registry (Requirement 1.4)
        # -----------------------------------------------------------------
        freshness = _resolve_freshness(source_id, registry, errors)

        # -----------------------------------------------------------------
        # Execute the appropriate SQL query (Requirement 2.4)
        # -----------------------------------------------------------------
        try:
            rows = _execute_kpi_query(kpi_id, scenario_id, window_start, window_end, db_conn)
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
    scenario_id: str,
    window_start: datetime,
    window_end: datetime,
    db_conn,
) -> list[tuple]:
    """
    Run the SQL query for *kpi_id*.  For hourly_conversion the device-segmented
    query is used; an aggregate query is also run and tagged with dimension
    ``_agg`` so callers can distinguish it.

    Raises psycopg2.Error (or any other DB exception) on failure — the caller
    wraps this in a try/except.
    """
    from datetime import timedelta

    if kpi_id not in _QUERIES:
        raise ValueError(f"No SQL query defined for kpi_id '{kpi_id}'")

    sql = _QUERIES[kpi_id]
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
            if "hourly" in kpi_id:
                if p_dt + timedelta(hours=1) > w_end:
                    continue
            elif "15min" in kpi_id:
                if p_dt + timedelta(minutes=15) > w_end:
                    continue
            elif "daily" in kpi_id:
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
) -> list[KPIValue]:
    """
    Convert raw DB rows into KPIValue objects.

    Row shapes per query
    --------------------
    hourly_revenue             : (period, value)
    hourly_conversion          : (period, device, value)  — segmented
    payment_failure_rate_15min : (period, value)
    gateway_latency_15min      : (period, value)
    inventory_fill_rate_daily  : (period, store_id, value) — segmented
    """
    result: list[KPIValue] = []

    if not rows:
        return result

    # Determine column layout from kpi_id
    if kpi_id == "hourly_conversion":
        # Segmented by device: (period, device, value)
        # Build one KPIValue per (period, device) combination, plus one
        # aggregated KPIValue per period (average across devices in that hour).
        period_device_map: dict[str, dict[str, float]] = {}
        for row in rows:
            period_dt, device, value = row[0], row[1], row[2]
            period_str = _period_to_str(period_dt)
            val = float(value) if value is not None else float("nan")
            # Per-device KPIValue
            result.append(
                KPIValue(
                    kpi_id=kpi_id,
                    name=kpi_name,
                    value=val,
                    unit=unit,
                    period=period_str,
                    dimension_filters={"device": str(device)},
                    source_id=source_id,
                    freshness=freshness,
                    method=MethodTag.SQL,
                )
            )
            period_device_map.setdefault(period_str, {})[str(device)] = val

        # Aggregate row per period (mean of finite device values)
        for period_str, device_vals in sorted(period_device_map.items()):
            finite_vals = [v for v in device_vals.values() if _is_finite(v)]
            agg_val = sum(finite_vals) / len(finite_vals) if finite_vals else float("nan")
            result.append(
                KPIValue(
                    kpi_id=kpi_id,
                    name=kpi_name,
                    value=agg_val,
                    unit=unit,
                    period=period_str,
                    dimension_filters={},  # aggregate — no dimension filter
                    source_id=source_id,
                    freshness=freshness,
                    method=MethodTag.SQL,
                )
            )

    elif kpi_id == "inventory_fill_rate_daily":
        # Segmented by store_id: (period, store_id, value)
        period_store_map: dict[str, dict[str, float]] = {}
        for row in rows:
            period_dt, store_id, value = row[0], row[1], row[2]
            period_str = _period_to_str(period_dt)
            val = float(value) if value is not None else float("nan")
            result.append(
                KPIValue(
                    kpi_id=kpi_id,
                    name=kpi_name,
                    value=val,
                    unit=unit,
                    period=period_str,
                    dimension_filters={"store_id": str(store_id)},
                    source_id=source_id,
                    freshness=freshness,
                    method=MethodTag.SQL,
                )
            )
            period_store_map.setdefault(period_str, {})[str(store_id)] = val

        # Aggregate row per day (mean across stores)
        for period_str, store_vals in sorted(period_store_map.items()):
            finite_vals = [v for v in store_vals.values() if _is_finite(v)]
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
