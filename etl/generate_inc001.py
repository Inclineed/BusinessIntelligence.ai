"""
etl/generate_inc001.py — Scenario-driven synthetic data generator for INC_001.

INC_001: Checkout/Payment Degradation caused by release v4.3.
  Incident window : 2024-01-15 09:00 UTC → 2024-01-15 15:00 UTC
  Baseline period : 2024-01-08 → 2024-01-14 (7 days)

Key observable patterns embedded in the data:
  - Revenue −8.2% during incident window
  - Overall conversion −10% (0.68 → 0.612), Android −17% (0.70 → 0.581)
  - iOS / desktop conversion unchanged
  - AOV +2% (partial compensation)
  - Payment failures ~4× baseline (2% → 8%), gateway latency +240% (180ms → 612ms)
  - TIMEOUT error on failed payments during incident
  - Inventory fill_rate UNCHANGED (~0.94) — contradicts H3
  - Marketing source intentionally stale; slight impression dip Jan 13-18 (competitor promo)
  - Support tickets ~3× during incident, skewed to android, category=payment_failure
  - v4.3 deploy at Jan 15 08:45 — 15 min before onset

Usage:
    python etl/generate_inc001.py [--output-dir data/synthetic]
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCENARIO_ID = "INC_001"
RANDOM_SEED = 42

# Per-table seeds derived from the base seed — ensures each table's generation
# is independent of the others so RNG state from one table doesn't affect another.
_SEED_ORDERS     = RANDOM_SEED + 1
_SEED_PAYMENTS   = RANDOM_SEED + 2
_SEED_INVENTORY  = RANDOM_SEED + 3
_SEED_MARKETING  = RANDOM_SEED + 4
_SEED_TICKETS    = RANDOM_SEED + 5

# Incident / baseline window boundaries (all UTC)
BASELINE_START = datetime(2024, 1, 8, 0, 0, 0, tzinfo=timezone.utc)
BASELINE_END   = datetime(2024, 1, 14, 23, 59, 59, tzinfo=timezone.utc)
INCIDENT_START = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
INCIDENT_END   = datetime(2024, 1, 15, 15, 0, 0, tzinfo=timezone.utc)

# Day boundaries for the full generation window (Jan 8 – Jan 16 inclusive)
GEN_START = datetime(2024, 1, 8, 0, 0, 0, tzinfo=timezone.utc)
GEN_END   = datetime(2024, 1, 16, 23, 59, 59, tzinfo=timezone.utc)

# ------- Orders / KPI parameters -------
# Baseline
BASELINE_TXN_PER_HOUR    = 200
BASELINE_CONVERSION_RATE = 0.68
BASELINE_REVENUE_PER_HR  = 14_000.0   # GBP
BASELINE_AOV             = BASELINE_REVENUE_PER_HR / (BASELINE_TXN_PER_HOUR * BASELINE_CONVERSION_RATE)

# Device split (baseline)
DEVICE_SPLIT = {"android": 0.40, "ios": 0.35, "desktop": 0.25}
# Per-device conversion rate at baseline (weighted average ≈ 0.68)
DEVICE_CONV_BASELINE = {"android": 0.70, "ios": 0.66, "desktop": 0.66}

# Incident deltas
INCIDENT_REVENUE_FACTOR      = 1.0 - 0.082    # −8.2%
INCIDENT_CONV_ANDROID_FACTOR = 1.0 - 0.17     # −17%
# iOS also affected (app payment issues extend to iOS app, though less severe than Android)
# A small drop on iOS closes the gap to the −10% overall target:
#   0.40×(0.70×0.83) + 0.35×(0.66×0.945) + 0.25×0.66 ≈ 0.612
INCIDENT_CONV_IOS_FACTOR     = 1.0 - 0.055    # −5.5% on iOS (minor)
INCIDENT_AOV_FACTOR          = 1.0 + 0.02     # +2%

# ------- Payment parameters -------
PAYMENT_EVENTS_PER_15MIN = 400
BASELINE_FAILURE_RATE    = 0.02
BASELINE_LATENCY_MS      = 180.0

INCIDENT_FAILURE_RATE    = 0.08            # 4× baseline
INCIDENT_LATENCY_MS      = 612.0           # +240%
INCIDENT_LATENCY_CREEP_START = datetime(2024, 1, 15, 8, 45, 0, tzinfo=timezone.utc)  # deploy v4.3

# ------- Inventory parameters -------
SKU_IDS   = [f"SKU_{i:04d}" for i in range(1, 51)]   # 50 SKUs
STORE_IDS = [f"STORE_{i:03d}" for i in range(1, 6)]   # 5 stores
FILL_RATE_MEAN = 0.94
FILL_RATE_STD  = 0.02

# ------- Marketing parameters -------
MARKETING_CHANNELS   = ["digital", "social", "email"]
MARKETING_SPEND_BASE = {"digital": 5_000.0, "social": 3_500.0, "email": 1_500.0}
MARKETING_IMP_BASE   = {"digital": 120_000, "social": 80_000, "email": 40_000}
COMPETITOR_PROMO_DATES = {datetime(2024, 1, d).date() for d in range(13, 19)}  # Jan 13–18
COMPETITOR_IMP_FACTOR  = 0.88   # 12% dip in impressions during competitor promo

# ------- Support tickets -------
BASELINE_TICKETS_PER_HOUR = 5
INCIDENT_TICKETS_PER_HOUR = 15
BASELINE_CATEGORIES = ["general", "returns", "stock"]
INCIDENT_CATEGORY   = "payment_failure"
INCIDENT_MESSAGES   = [
    "Payment failed on checkout",
    "Card declined repeatedly",
    "App crashed during payment",
    "Transaction timed out at checkout",
    "Payment processing error on mobile app",
    "Unable to complete purchase — payment gateway error",
    "Checkout button unresponsive after entering card details",
    "Payment declined but money held in account",
]
# Device skew during incident: android more heavily represented
INCIDENT_DEVICE_PROBS = {"android": 0.65, "ios": 0.25, "desktop": 0.10}
BASELINE_DEVICE_PROBS = {"android": 0.40, "ios": 0.35, "desktop": 0.25}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_iso(dt: datetime) -> str:
    """Return ISO-8601 string with UTC offset for a timezone-aware datetime."""
    return dt.isoformat()


def _in_incident(ts: datetime) -> bool:
    """True when *ts* falls within the incident window."""
    return INCIDENT_START <= ts <= INCIDENT_END


def _is_pre_incident_creep(ts: datetime) -> bool:
    """True for the single 15-min bucket just before the incident (deploy v4.3)."""
    return INCIDENT_CREEP_START <= ts < INCIDENT_START


INCIDENT_CREEP_START = INCIDENT_CREEP_END = INCIDENT_CREEP_START = datetime(
    2024, 1, 15, 8, 45, tzinfo=timezone.utc
)
INCIDENT_CREEP_END   = datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc)


def _is_latency_creep(ts: datetime) -> bool:
    return INCIDENT_CREEP_START <= ts < INCIDENT_CREEP_END


# ---------------------------------------------------------------------------
# 1. Orders (hourly)
# ---------------------------------------------------------------------------

def generate_orders(rng: np.random.Generator) -> pd.DataFrame:
    """
    Generate hourly orders for baseline + Jan 15 incident day.

    The incident lowers Android conversion from 0.70 → 0.581 (−17%).
    iOS and desktop conversion stay at baseline.  AOV inflates +2%.
    """
    rows = []
    txn_counter = 1

    # Iterate hour by hour across the full generation window
    current = GEN_START
    while current <= GEN_END:
        hour_end = current + timedelta(hours=1)
        # A bucket is "in incident" only when it is fully inside the incident window.
        # Partial overlap hours get baseline behaviour to keep the boundary clean.
        in_inc = (current >= INCIDENT_START) and (hour_end <= INCIDENT_END + timedelta(seconds=1))

        # Volume is stable — traffic not affected by incident
        n_txn = int(rng.poisson(BASELINE_TXN_PER_HOUR))

        for _ in range(n_txn):
            # Assign device
            dev = rng.choice(
                list(DEVICE_SPLIT.keys()),
                p=list(DEVICE_SPLIT.values()),
            )

            # Per-device conversion rate
            conv_rate = DEVICE_CONV_BASELINE[dev]
            if in_inc:
                if dev == "android":
                    conv_rate = DEVICE_CONV_BASELINE["android"] * INCIDENT_CONV_ANDROID_FACTOR
                elif dev == "ios":
                    conv_rate = DEVICE_CONV_BASELINE["ios"] * INCIDENT_CONV_IOS_FACTOR

            converted = bool(rng.random() < conv_rate)

            # AOV
            base_aov = BASELINE_AOV * (INCIDENT_AOV_FACTOR if in_inc else 1.0)
            aov = max(0.01, rng.normal(base_aov, base_aov * 0.15))

            revenue = aov if converted else 0.0

            # Channel: app (android+ios), web (desktop+some mobile), in-store (small %)
            if dev == "android":
                channel = rng.choice(["app", "web"], p=[0.80, 0.20])
            elif dev == "ios":
                channel = rng.choice(["app", "web"], p=[0.75, 0.25])
            else:
                channel = rng.choice(["web", "in-store"], p=[0.85, 0.15])

            # Timestamp: offset randomly within the hour, clamped to the bucket window
            offset_secs = int(rng.integers(0, 3600))
            ts = current + timedelta(seconds=offset_secs)

            rows.append({
                "transaction_id": f"TXN_{txn_counter:07d}",
                "scenario_id":    SCENARIO_ID,
                "ts":             _utc_iso(ts),
                "store_id":       f"STORE_{rng.integers(1, 6):03d}",
                "device":         dev,
                "channel":        channel,
                "revenue":        round(revenue, 2),
                "conversion":     converted,
                "aov":            round(aov, 2),
                # _bucket_hour is the generating hour bucket — kept for ETL validation only,
                # not loaded into Postgres (schema does not have this column).
                "_bucket_hour":   _utc_iso(current),
                "_in_incident":   in_inc,
            })
            txn_counter += 1

        current += timedelta(hours=1)

    df = pd.DataFrame(rows)
    return df


# ---------------------------------------------------------------------------
# 2. Payment events (15-minute buckets)
# ---------------------------------------------------------------------------

def generate_payment_events(rng: np.random.Generator) -> pd.DataFrame:
    """
    Generate 15-min gateway events.

    Failure rate spikes from 2% → 8% during incident.
    Latency creeps at the v4.3 deploy window (08:45) before full onset.
    """
    rows = []
    evt_counter = 1

    current = GEN_START
    while current <= GEN_END:
        in_inc       = _in_incident(current)
        is_creep     = _is_latency_creep(current)

        failure_rate = INCIDENT_FAILURE_RATE if in_inc else BASELINE_FAILURE_RATE
        if is_creep:
            # Partial creep: failure rate starts climbing
            failure_rate = BASELINE_FAILURE_RATE + 0.02   # 4% — noticeable but not peak

        n_events = int(rng.poisson(PAYMENT_EVENTS_PER_15MIN))

        for _ in range(n_events):
            success = bool(rng.random() >= failure_rate)

            # Latency
            if in_inc:
                latency = max(100, int(rng.normal(INCIDENT_LATENCY_MS, 150)))
            elif is_creep:
                # Creep latency: midway between baseline and incident
                midpoint = (BASELINE_LATENCY_MS + INCIDENT_LATENCY_MS) / 2
                latency = max(100, int(rng.normal(midpoint, 80)))
            else:
                latency = max(50, int(rng.normal(BASELINE_LATENCY_MS, 30)))

            error_code = None
            if not success:
                error_code = "TIMEOUT" if (in_inc or is_creep) else rng.choice(
                    ["DECLINED", "INSUFFICIENT_FUNDS", "CARD_ERROR"], p=[0.5, 0.3, 0.2]
                )

            offset_secs = int(rng.integers(0, 900))
            ts = current + timedelta(seconds=offset_secs)

            rows.append({
                "event_id":   f"PAY_{evt_counter:07d}",
                "scenario_id": SCENARIO_ID,
                "ts":         _utc_iso(ts),
                "gateway":    "primary_gateway",
                "success":    success,
                "latency_ms": latency,
                "error_code": error_code,
            })
            evt_counter += 1

        current += timedelta(minutes=15)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 3. Inventory events (daily)
# ---------------------------------------------------------------------------

def generate_inventory_events(rng: np.random.Generator) -> pd.DataFrame:
    """
    Daily SKU × store snapshots.

    Critically: fill_rate remains ~0.94 throughout — even during the incident.
    This is the contradictory evidence that refutes H3 (inventory shortage).
    """
    rows = []
    evt_counter = 1

    current = GEN_START.replace(hour=6, minute=0, second=0)   # daily snapshot at 06:00
    while current.date() <= GEN_END.date():
        for sku in SKU_IDS:
            for store in STORE_IDS:
                fill_rate = float(np.clip(rng.normal(FILL_RATE_MEAN, FILL_RATE_STD), 0.0, 1.0))
                in_stock  = bool(rng.random() < fill_rate)

                rows.append({
                    "event_id":   f"INV_{evt_counter:07d}",
                    "scenario_id": SCENARIO_ID,
                    "ts":         _utc_iso(current),
                    "sku_id":     sku,
                    "store_id":   store,
                    "in_stock":   in_stock,
                    "fill_rate":  round(fill_rate, 4),
                })
                evt_counter += 1

        current += timedelta(days=1)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 4. Marketing events (daily)
# ---------------------------------------------------------------------------

def generate_marketing_events(rng: np.random.Generator) -> pd.DataFrame:
    """
    Daily campaign data per channel.

    Impressions dip ~12% on Jan 13–18 due to competitor promotion.
    All rows source_stale=True (simulating the 5h-delayed feed).
    """
    rows = []
    evt_counter = 1

    current = GEN_START.replace(hour=0, minute=0, second=0)
    while current.date() <= GEN_END.date():
        is_promo = current.date() in COMPETITOR_PROMO_DATES

        for channel in MARKETING_CHANNELS:
            base_spend = MARKETING_SPEND_BASE[channel]
            base_imp   = MARKETING_IMP_BASE[channel]

            spend       = max(0.0, rng.normal(base_spend, base_spend * 0.05))
            imp_factor  = COMPETITOR_IMP_FACTOR if is_promo else 1.0
            impressions = max(0, int(rng.normal(base_imp * imp_factor, base_imp * 0.03)))

            rows.append({
                "event_id":   f"MKT_{evt_counter:07d}",
                "scenario_id": SCENARIO_ID,
                "ts":         _utc_iso(current),
                "channel":    channel,
                "spend":      round(spend, 2),
                "impressions": impressions,
                "source_stale": True,
            })
            evt_counter += 1

        current += timedelta(days=1)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 5. Support tickets
# ---------------------------------------------------------------------------

def generate_support_tickets(rng: np.random.Generator) -> pd.DataFrame:
    """
    Hourly support tickets.

    Incident window: ~15/hr (3× baseline), category=payment_failure,
    with device skewed heavily toward android.
    """
    rows = []
    ticket_counter = 1

    current = GEN_START
    while current <= GEN_END:
        in_inc = _in_incident(current)
        rate   = INCIDENT_TICKETS_PER_HOUR if in_inc else BASELINE_TICKETS_PER_HOUR

        n_tickets = int(rng.poisson(rate))

        for _ in range(n_tickets):
            if in_inc:
                dev      = rng.choice(
                    list(INCIDENT_DEVICE_PROBS.keys()),
                    p=list(INCIDENT_DEVICE_PROBS.values()),
                )
                category = INCIDENT_CATEGORY
                message  = rng.choice(INCIDENT_MESSAGES)
            else:
                dev      = rng.choice(
                    list(BASELINE_DEVICE_PROBS.keys()),
                    p=list(BASELINE_DEVICE_PROBS.values()),
                )
                category = rng.choice(BASELINE_CATEGORIES)
                message  = f"Customer enquiry — {category}"

            offset_secs = int(rng.integers(0, 3600))
            ts = current + timedelta(seconds=offset_secs)

            rows.append({
                "ticket_id":   f"TKT_{ticket_counter:07d}",
                "scenario_id": SCENARIO_ID,
                "ts":          _utc_iso(ts),
                "store_id":    f"STORE_{rng.integers(1, 6):03d}",
                "device":      dev,
                "message":     message,
                "category":    category,
            })
            ticket_counter += 1

        current += timedelta(hours=1)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 6. Deployment log
# ---------------------------------------------------------------------------

def generate_deployment_log() -> pd.DataFrame:
    """
    Three software releases bracketing the incident.

    v4.3 at 08:45 Jan 15 — 15 min before incident onset — is the root cause.
    """
    rows = [
        {
            "deploy_id":   "DEPLOY_001",
            "scenario_id": SCENARIO_ID,
            "ts":          _utc_iso(datetime(2024, 1, 14, 22, 0, 0, tzinfo=timezone.utc)),
            "version":     "v4.2",
            "component":   "checkout-service",
            "notes":       "Routine maintenance: checkout UI improvements and dependency updates",
        },
        {
            "deploy_id":   "DEPLOY_002",
            "scenario_id": SCENARIO_ID,
            "ts":          _utc_iso(datetime(2024, 1, 15, 8, 45, 0, tzinfo=timezone.utc)),
            "version":     "v4.3",
            "component":   "checkout-service",
            "notes":       "Checkout performance optimisation and payment gateway refactor",
        },
        {
            "deploy_id":   "DEPLOY_003",
            "scenario_id": SCENARIO_ID,
            "ts":          _utc_iso(datetime(2024, 1, 16, 10, 0, 0, tzinfo=timezone.utc)),
            "version":     "v4.3-hotfix",
            "component":   "checkout-service",
            "notes":       "Emergency rollback of payment gateway changes introduced in v4.3",
        },
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(RANDOM_SEED)

    print("Generating INC_001 synthetic data …")

    generators = [
        ("orders",            generate_orders,           (np.random.default_rng(_SEED_ORDERS),)),
        ("payment_events",    generate_payment_events,   (np.random.default_rng(_SEED_PAYMENTS),)),
        ("inventory_events",  generate_inventory_events, (np.random.default_rng(_SEED_INVENTORY),)),
        ("marketing_events",  generate_marketing_events, (np.random.default_rng(_SEED_MARKETING),)),
        ("support_tickets",   generate_support_tickets,  (np.random.default_rng(_SEED_TICKETS),)),
        ("deployment_log",    generate_deployment_log,   ()),
    ]

    summary_rows = []
    for name, fn, args in generators:
        df = fn(*args)
        out_path = output_dir / f"{name}.csv"
        df.to_csv(out_path, index=False)
        summary_rows.append({"file": f"{name}.csv", "rows": len(df)})
        print(f"  ✓ {name:22s}  {len(df):>7,} rows  →  {out_path}")

    # Write summary
    summary_df = pd.DataFrame(summary_rows)
    summary_path = output_dir / "summary.csv"
    summary_df.to_csv(summary_path, index=False)
    print(f"\nSummary written to {summary_path}")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate INC_001 scenario-driven synthetic data CSVs"
    )
    parser.add_argument(
        "--output-dir",
        default="data/synthetic",
        help="Directory to write CSV files (default: data/synthetic)",
    )
    args = parser.parse_args()
    main(Path(args.output_dir))
