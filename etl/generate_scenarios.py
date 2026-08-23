"""
etl/generate_scenarios.py — Generate additional Round 2 test scenarios.

INC_002: Ambiguous scenario — both checkout AND competitor pressure active simultaneously.
         The Challenge Engine should ABSTAIN because the gap between H1 and H2 is too small.

INC_003: Sparse history — new Premium KPI with only 12 days of data.
         The Signal Engine should flag sparse_history=True and NOT generate anomalies.

INC_004: Data-quality false anomaly — an ETL pipeline delay causes apparent revenue drop
         that did not actually occur (all NULL values in the gap window).
         The Signal Engine should set data_quality_suspect=True and NOT generate a business anomaly.

Usage:
    python etl/generate_scenarios.py [--output-dir data/synthetic]
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

RANDOM_SEED = 42

# Generation window: Jan 8 – Jan 16 2024 (mirrors INC_001 window for cross-scenario
# evaluation consistency)
GEN_START = datetime(2024, 1, 8, 0, 0, 0, tzinfo=timezone.utc)
GEN_END   = datetime(2024, 1, 16, 23, 59, 59, tzinfo=timezone.utc)


def _utc_iso(dt: datetime) -> str:
    """Return ISO-8601 string with UTC offset."""
    return dt.isoformat()


# ===========================================================================
# INC_002 — Simultaneous causes: checkout degradation + competitor promotion
# ===========================================================================
#
# Design intent:
#   Both checkout/payment (weak signal: failures 2×) and competitor promotion
#   (stale marketing data with impressions dip) are simultaneously active.
#   Revenue −6%, conversion −5% overall — ambiguous, not clearly dominated by
#   either cause alone.  The Challenge Engine should see a small gap between
#   H1 and H2 (< min_gap=0.15) and ABSTAIN.
#
# INC_002 incident window: 2024-01-15 10:00–14:00 UTC
# ===========================================================================

INC_002_ID            = "INC_002"
INC_002_START         = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
INC_002_END           = datetime(2024, 1, 15, 14, 0, 0, tzinfo=timezone.utc)

# Baseline traffic and KPI parameters (same as INC_001)
INC_002_TXN_PER_HOUR       = 200
INC_002_CONV_BASELINE       = 0.68
INC_002_REVENUE_PER_HR      = 14_000.0
INC_002_DEVICE_SPLIT        = {"android": 0.40, "ios": 0.35, "desktop": 0.25}
INC_002_DEVICE_CONV_BASE    = {"android": 0.70, "ios": 0.66, "desktop": 0.66}

# Incident deltas: mild payment degradation
INC_002_CONV_FACTOR_ANDROID = 1.0 - 0.07   # −7% on Android (weak signal)
INC_002_CONV_FACTOR_IOS     = 1.0 - 0.03   # −3% on iOS
INC_002_FAILURE_RATE_INC    = 0.04          # 2× baseline (2% → 4%)
INC_002_LATENCY_INC_MS      = 280.0         # modest increase (180 → 280ms)

# Competitor promo active across the full window (stale marketing source)
INC_002_COMPETITOR_PROMO_DATES = {datetime(2024, 1, d).date() for d in range(13, 19)}
INC_002_COMPETITOR_IMP_FACTOR  = 0.88       # 12% impression dip (same as INC_001)

# Payment baseline
INC_002_FAILURE_RATE_BASE  = 0.02
INC_002_LATENCY_BASE_MS    = 180.0
INC_002_EVENTS_PER_15MIN   = 400

# Marketing channels / spend (same as INC_001)
_MKT_CHANNELS   = ["digital", "social", "email"]
_MKT_SPEND_BASE = {"digital": 5_000.0, "social": 3_500.0, "email": 1_500.0}
_MKT_IMP_BASE   = {"digital": 120_000, "social": 80_000, "email": 40_000}


def _in_inc002(ts: datetime) -> bool:
    return INC_002_START <= ts <= INC_002_END


def generate_inc002_orders(rng: np.random.Generator) -> pd.DataFrame:
    """
    Hourly orders: mild Android + iOS conversion drop during incident window,
    reflecting a weak checkout signal layered on general promo-driven softness.
    """
    rows = []
    txn_counter = 1
    current = GEN_START

    while current <= GEN_END:
        hour_end = current + timedelta(hours=1)
        in_inc = (current >= INC_002_START) and (hour_end <= INC_002_END + timedelta(seconds=1))
        n_txn = int(rng.poisson(INC_002_TXN_PER_HOUR))

        for _ in range(n_txn):
            dev = rng.choice(
                list(INC_002_DEVICE_SPLIT.keys()),
                p=list(INC_002_DEVICE_SPLIT.values()),
            )
            conv_rate = INC_002_DEVICE_CONV_BASE[dev]
            if in_inc:
                if dev == "android":
                    conv_rate = INC_002_DEVICE_CONV_BASE["android"] * INC_002_CONV_FACTOR_ANDROID
                elif dev == "ios":
                    conv_rate = INC_002_DEVICE_CONV_BASE["ios"] * INC_002_CONV_FACTOR_IOS
                # Competitor promo also slightly reduces overall willingness to purchase
                conv_rate *= 0.97

            converted = bool(rng.random() < conv_rate)
            base_aov = INC_002_REVENUE_PER_HR / (INC_002_TXN_PER_HOUR * INC_002_CONV_BASELINE)
            aov = max(0.01, rng.normal(base_aov, base_aov * 0.15))
            revenue = aov if converted else 0.0

            if dev == "android":
                channel = rng.choice(["app", "web"], p=[0.80, 0.20])
            elif dev == "ios":
                channel = rng.choice(["app", "web"], p=[0.75, 0.25])
            else:
                channel = rng.choice(["web", "in-store"], p=[0.85, 0.15])

            offset_secs = int(rng.integers(0, 3600))
            ts = current + timedelta(seconds=offset_secs)

            rows.append({
                "transaction_id": f"TXN_{txn_counter:07d}",
                "scenario_id":    INC_002_ID,
                "ts":             _utc_iso(ts),
                "device":         dev,
                "channel":        channel,
                "revenue":        round(revenue, 2),
                "conversion":     converted,
                "_in_incident":   in_inc,
            })
            txn_counter += 1

        current += timedelta(hours=1)

    return pd.DataFrame(rows)


def generate_inc002_payment_events(rng: np.random.Generator) -> pd.DataFrame:
    """
    15-min payment gateway events: failure rate doubles (2% → 4%), latency
    increases modestly.  Weak signal — not the clear 4× spike of INC_001.
    """
    rows = []
    evt_counter = 1
    current = GEN_START

    while current <= GEN_END:
        in_inc = _in_inc002(current)
        failure_rate = INC_002_FAILURE_RATE_INC if in_inc else INC_002_FAILURE_RATE_BASE
        n_events = int(rng.poisson(INC_002_EVENTS_PER_15MIN))

        for _ in range(n_events):
            success = bool(rng.random() >= failure_rate)
            if in_inc:
                latency = max(100, int(rng.normal(INC_002_LATENCY_INC_MS, 60)))
            else:
                latency = max(50, int(rng.normal(INC_002_LATENCY_BASE_MS, 30)))

            error_code = None
            if not success:
                error_code = rng.choice(
                    ["TIMEOUT", "DECLINED", "CARD_ERROR"], p=[0.4, 0.4, 0.2]
                )

            offset_secs = int(rng.integers(0, 900))
            ts = current + timedelta(seconds=offset_secs)

            rows.append({
                "event_id":    f"PAY_{evt_counter:07d}",
                "scenario_id": INC_002_ID,
                "ts":          _utc_iso(ts),
                "gateway":     "primary_gateway",
                "success":     success,
                "latency_ms":  latency,
                "error_code":  error_code,
            })
            evt_counter += 1

        current += timedelta(minutes=15)

    return pd.DataFrame(rows)


def generate_inc002_marketing_events(rng: np.random.Generator) -> pd.DataFrame:
    """
    Daily marketing data: competitor promo active Jan 13–18, causing 12%
    impression dip.  source_stale=True to reflect the 5h-delayed feed.
    """
    rows = []
    evt_counter = 1
    current = GEN_START.replace(hour=0, minute=0, second=0)

    while current.date() <= GEN_END.date():
        is_promo = current.date() in INC_002_COMPETITOR_PROMO_DATES

        for channel in _MKT_CHANNELS:
            base_spend = _MKT_SPEND_BASE[channel]
            base_imp   = _MKT_IMP_BASE[channel]

            spend = max(0.0, rng.normal(base_spend, base_spend * 0.05))
            imp_factor = INC_002_COMPETITOR_IMP_FACTOR if is_promo else 1.0
            impressions = max(0, int(rng.normal(base_imp * imp_factor, base_imp * 0.03)))

            rows.append({
                "event_id":    f"MKT_{evt_counter:07d}",
                "scenario_id": INC_002_ID,
                "ts":          _utc_iso(current),
                "channel":     channel,
                "spend":       round(spend, 2),
                "impressions": impressions,
                "source_stale": True,
            })
            evt_counter += 1

        current += timedelta(days=1)

    return pd.DataFrame(rows)


# ===========================================================================
# INC_003 — Sparse history: new Premium KPI with only 12 days of data
# ===========================================================================
#
# Design intent:
#   The "premium_conversion" KPI was introduced 12 days ago.  Baseline sample
#   count = 12 < 30 minimum threshold.  The Signal Engine must set
#   sparse_history=True and suppress anomaly detection entirely.
#   Only 12 rows of history are generated (one per day).
#
# ===========================================================================

INC_003_ID       = "INC_003"
INC_003_KPI_NAME = "premium_conversion"

# Only 12 days of daily KPI snapshots (Jan 3 – Jan 14 2024)
_INC_003_HISTORY_START = datetime(2024, 1, 3, tzinfo=timezone.utc)
_INC_003_HISTORY_END   = datetime(2024, 1, 14, tzinfo=timezone.utc)

# Simulated metric: premium conversion rate with slight day-over-day variation
_INC_003_CONV_MEAN = 0.42
_INC_003_CONV_STD  = 0.015


def generate_inc003_kpi_history(rng: np.random.Generator) -> pd.DataFrame:
    """
    12-row daily KPI snapshot for the premium_conversion metric.

    Row count (12) is deliberately below the 30-sample minimum to trigger
    the sparse-history guard in Signal Engine (Requirement 3.2).

    The evaluator checks:
      - sparse_history_expected = True
      - anomaly_detected = False
    """
    rows = []
    current = _INC_003_HISTORY_START
    day_num = 1

    while current <= _INC_003_HISTORY_END:
        value = float(np.clip(rng.normal(_INC_003_CONV_MEAN, _INC_003_CONV_STD), 0.0, 1.0))

        rows.append({
            "kpi_id":      INC_003_KPI_NAME,
            "scenario_id": INC_003_ID,
            "ts":          _utc_iso(current.replace(hour=9, minute=0)),
            "value":       round(value, 4),
            "sample_count": 1,
            "day_num":     day_num,
            "_note": (
                "Sparse history: only 12 days available. "
                "sample_count < 30 threshold triggers sparse_history guard."
            ),
        })
        current += timedelta(days=1)
        day_num += 1

    df = pd.DataFrame(rows)
    # Metadata row: record total baseline samples for evaluator verification
    assert len(df) == 12, f"Expected exactly 12 rows, got {len(df)}"
    return df


def generate_inc003_metadata() -> pd.DataFrame:
    """
    Single-row metadata record documenting the sparse-history scenario.
    """
    return pd.DataFrame([{
        "scenario_id":      INC_003_ID,
        "kpi_name":         INC_003_KPI_NAME,
        "baseline_samples": 12,
        "min_threshold":    30,
        "sparse_history":   True,
        "evaluation_note":  (
            "Signal Engine must set sparse_history=True and suppress anomaly. "
            "No hypotheses should be generated."
        ),
    }])


# ===========================================================================
# INC_004 — Data-quality false anomaly: ETL pipeline delay
# ===========================================================================
#
# Design intent:
#   An ETL pipeline delay creates a 4-hour gap (NULL values) in the orders
#   table between 11:00–15:00 UTC on Jan 15 2024.  The apparent revenue drop
#   in that window is not a real business anomaly — it is a data artifact.
#   The Signal Engine must set data_quality_suspect=True (quality score < 0.80)
#   and suppress anomaly detection for this window (Requirement 3.3).
#
# ===========================================================================

INC_004_ID         = "INC_004"
INC_004_GAP_START  = datetime(2024, 1, 15, 11, 0, 0, tzinfo=timezone.utc)
INC_004_GAP_END    = datetime(2024, 1, 15, 15, 0, 0, tzinfo=timezone.utc)

# Baseline (same as INC_001 for comparability)
INC_004_TXN_PER_HOUR    = 200
INC_004_CONV_BASELINE   = 0.68
INC_004_REVENUE_PER_HR  = 14_000.0
INC_004_DEVICE_SPLIT    = {"android": 0.40, "ios": 0.35, "desktop": 0.25}
INC_004_DEVICE_CONV_BASE = {"android": 0.70, "ios": 0.66, "desktop": 0.66}


def _in_gap(ts: datetime) -> bool:
    """True when the timestamp falls in the ETL pipeline gap window."""
    return INC_004_GAP_START <= ts < INC_004_GAP_END


def generate_inc004_orders(rng: np.random.Generator) -> pd.DataFrame:
    """
    Hourly orders: normal baseline throughput, with 4 gap hours where all
    revenue/conversion values are NULL (simulating ETL pipeline failure).

    The apparent "revenue drop" in hours 11–15 UTC is entirely due to missing
    data, not a real business anomaly.  data_quality_score for this window
    should be < 0.80 when computed as: non_null_rows / total_expected_rows.
    """
    rows = []
    txn_counter = 1
    current = GEN_START

    while current <= GEN_END:
        hour_end = current + timedelta(hours=1)
        # Check if this entire hour bucket falls in the pipeline gap
        bucket_in_gap = (
            current >= INC_004_GAP_START and hour_end <= INC_004_GAP_END + timedelta(seconds=1)
        )

        n_txn = int(rng.poisson(INC_004_TXN_PER_HOUR))

        for _ in range(n_txn):
            dev = rng.choice(
                list(INC_004_DEVICE_SPLIT.keys()),
                p=list(INC_004_DEVICE_SPLIT.values()),
            )
            conv_rate = INC_004_DEVICE_CONV_BASE[dev]
            converted = bool(rng.random() < conv_rate)
            base_aov = INC_004_REVENUE_PER_HR / (INC_004_TXN_PER_HOUR * INC_004_CONV_BASELINE)
            aov = max(0.01, rng.normal(base_aov, base_aov * 0.15))

            if dev == "android":
                channel = rng.choice(["app", "web"], p=[0.80, 0.20])
            elif dev == "ios":
                channel = rng.choice(["app", "web"], p=[0.75, 0.25])
            else:
                channel = rng.choice(["web", "in-store"], p=[0.85, 0.15])

            offset_secs = int(rng.integers(0, 3600))
            ts = current + timedelta(seconds=offset_secs)

            # In the gap window: revenue and conversion are NULL (pipeline failure)
            if bucket_in_gap:
                revenue    = None   # NULL — ETL pipeline did not deliver data
                conversion = None   # NULL — ETL pipeline did not deliver data
                aov_val    = None
            else:
                revenue    = round(aov if converted else 0.0, 2)
                conversion = converted
                aov_val    = round(aov, 2)

            rows.append({
                "transaction_id": f"TXN_{txn_counter:07d}",
                "scenario_id":    INC_004_ID,
                "ts":             _utc_iso(ts),
                "device":         dev,
                "channel":        channel,
                "revenue":        revenue,
                "conversion":     conversion,
                "aov":            aov_val,
                "_in_gap":        bucket_in_gap,
                "_note": (
                    "ETL gap: revenue/conversion NULL due to pipeline delay, "
                    "not a real business anomaly."
                ) if bucket_in_gap else None,
            })
            txn_counter += 1

        current += timedelta(hours=1)

    return pd.DataFrame(rows)


def generate_inc004_data_quality_log() -> pd.DataFrame:
    """
    Hourly data-quality audit log for INC_004.

    Records the data_quality_score per hour.  For gap hours the score is 0.00
    (no data delivered); for all other hours it is ~0.97–1.00 (normal).

    The evaluator checks data_quality_suspect=True for the gap window, which
    requires that the Signal Engine computes data_quality_score < 0.80.
    """
    rows = []
    current = GEN_START

    while current <= GEN_END:
        hour_end = current + timedelta(hours=1)
        bucket_in_gap = (
            current >= INC_004_GAP_START and hour_end <= INC_004_GAP_END + timedelta(seconds=1)
        )

        # Quality score: 0.00 during the gap, ~0.98 otherwise
        quality_score = 0.00 if bucket_in_gap else round(
            0.95 + (0.05 * (hash(str(current)) % 100) / 100.0), 4
        )

        rows.append({
            "scenario_id":      INC_004_ID,
            "ts":               _utc_iso(current),
            "data_quality_score": quality_score,
            "null_row_count":   200 if bucket_in_gap else 0,
            "total_row_count":  200,
            "in_gap":           bucket_in_gap,
            "_reason": "ETL pipeline delay" if bucket_in_gap else "normal",
        })
        current += timedelta(hours=1)

    return pd.DataFrame(rows)


def generate_inc004_metadata() -> pd.DataFrame:
    """
    Single-row metadata documenting the INC_004 false-anomaly scenario.
    """
    return pd.DataFrame([{
        "scenario_id":        INC_004_ID,
        "gap_start":          _utc_iso(INC_004_GAP_START),
        "gap_end":            _utc_iso(INC_004_GAP_END),
        "gap_duration_hours": 4,
        "data_quality_score_in_gap": 0.00,
        "dq_threshold":       0.80,
        "data_quality_suspect": True,
        "evaluation_note": (
            "Signal Engine must set data_quality_suspect=True for the gap window "
            "and suppress anomaly. No hypotheses should be generated."
        ),
    }])


# ===========================================================================
# Main
# ===========================================================================

def _generate_inc002(output_dir: Path, seeds: dict) -> None:
    """Generate all INC_002 CSV files into output_dir/INC_002/."""
    out = output_dir / INC_002_ID
    out.mkdir(parents=True, exist_ok=True)

    tables = [
        ("orders",           generate_inc002_orders,         np.random.default_rng(seeds["orders"])),
        ("payment_events",   generate_inc002_payment_events, np.random.default_rng(seeds["payments"])),
        ("marketing_events", generate_inc002_marketing_events, np.random.default_rng(seeds["marketing"])),
    ]

    for name, fn, rng in tables:
        df = fn(rng)
        path = out / f"{name}.csv"
        df.to_csv(path, index=False)
        print(f"  ✓ INC_002/{name:22s}  {len(df):>7,} rows  →  {path}")


def _generate_inc003(output_dir: Path, seeds: dict) -> None:
    """Generate all INC_003 CSV files into output_dir/INC_003/."""
    out = output_dir / INC_003_ID
    out.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(seeds["kpi"])

    tables = [
        ("kpi_history", generate_inc003_kpi_history, rng),
    ]
    for name, fn, r in tables:
        df = fn(r)
        path = out / f"{name}.csv"
        df.to_csv(path, index=False)
        print(f"  ✓ INC_003/{name:22s}  {len(df):>7,} rows  →  {path}")

    # Metadata (no rng needed)
    meta = generate_inc003_metadata()
    meta_path = out / "metadata.csv"
    meta.to_csv(meta_path, index=False)
    print(f"  ✓ INC_003/{'metadata':22s}  {len(meta):>7,} rows  →  {meta_path}")


def _generate_inc004(output_dir: Path, seeds: dict) -> None:
    """Generate all INC_004 CSV files into output_dir/INC_004/."""
    out = output_dir / INC_004_ID
    out.mkdir(parents=True, exist_ok=True)

    rng_orders = np.random.default_rng(seeds["orders"])

    # Orders (with NULL gap)
    df_orders = generate_inc004_orders(rng_orders)
    orders_path = out / "orders.csv"
    df_orders.to_csv(orders_path, index=False)
    print(f"  ✓ INC_004/{'orders':22s}  {len(df_orders):>7,} rows  →  {orders_path}")

    # Data quality log (deterministic, no rng)
    df_dq = generate_inc004_data_quality_log()
    dq_path = out / "data_quality_log.csv"
    df_dq.to_csv(dq_path, index=False)
    print(f"  ✓ INC_004/{'data_quality_log':22s}  {len(df_dq):>7,} rows  →  {dq_path}")

    # Metadata
    meta = generate_inc004_metadata()
    meta_path = out / "metadata.csv"
    meta.to_csv(meta_path, index=False)
    print(f"  ✓ INC_004/{'metadata':22s}  {len(meta):>7,} rows  →  {meta_path}")


def main(output_dir: Path) -> None:
    """Generate all three additional scenarios."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Per-scenario, per-table seeds — derived from the master seed for reproducibility
    _BASE = RANDOM_SEED

    inc002_seeds = {
        "orders":    _BASE + 10,
        "payments":  _BASE + 11,
        "marketing": _BASE + 12,
    }
    inc003_seeds = {
        "kpi": _BASE + 20,
    }
    inc004_seeds = {
        "orders": _BASE + 30,
    }

    print("Generating additional Round 2 scenarios …\n")

    print("─── INC_002: Simultaneous causes (abstain) ───")
    _generate_inc002(output_dir, inc002_seeds)

    print("\n─── INC_003: Sparse history ───")
    _generate_inc003(output_dir, inc003_seeds)

    print("\n─── INC_004: Data-quality false anomaly ───")
    _generate_inc004(output_dir, inc004_seeds)

    print("\nDone.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate INC_002/INC_003/INC_004 scenario CSV files"
    )
    parser.add_argument(
        "--output-dir",
        default="data/synthetic",
        help="Directory to write CSV files (default: data/synthetic)",
    )
    args = parser.parse_args()
    main(Path(args.output_dir))
