"""
etl/load_scenario.py — Load an additional scenario (INC_002 / INC_004) into
Postgres with SCENARIO-SCOPED primary keys so rows never collide with INC_001.

- Prefixes transaction_id / event_id with the scenario id.
- Fills columns absent from the scenario CSVs (store_id, aov) with safe defaults.
- Preserves NULL revenue/conversion (INC_004 ETL gap).
- Loads a per-scenario data_quality_log table (created if absent) so the live
  Signal Engine can apply the data-quality guard (INC_004).

Usage:
    python etl/load_scenario.py --scenario-id INC_002
    python etl/load_scenario.py --scenario-id INC_004
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

_ROOT = Path(__file__).resolve().parent.parent


def _clean(v):
    """Convert pandas NaN / NaT to None; leave everything else intact."""
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def _prefix(scenario_id: str, val) -> str:
    return f"{scenario_id}_{val}"


def _load_orders(conn, sid, df):
    # Fill missing columns
    if "store_id" not in df.columns:
        df["store_id"] = "STORE_001"
    if "aov" not in df.columns:
        df["aov"] = df.get("revenue")
    df = df.where(pd.notna(df), None)
    cols = ["transaction_id", "scenario_id", "ts", "store_id", "device",
            "channel", "revenue", "conversion", "aov"]
    rows = []
    for r in df.itertuples(index=False):
        d = dict(r._asdict())
        rows.append((
            _prefix(sid, d["transaction_id"]), sid, _clean(d["ts"]),
            d.get("store_id") or "STORE_001", d["device"], d["channel"],
            _clean(d.get("revenue")), _clean(d.get("conversion")), _clean(d.get("aov")),
        ))
    with conn.cursor() as cur:
        execute_values(cur,
            f"INSERT INTO orders ({','.join(cols)}) VALUES %s ON CONFLICT DO NOTHING",
            rows, page_size=5000)
    conn.commit()
    return len(rows)


def _load_payment(conn, sid, df):
    df = df.where(pd.notna(df), None)
    cols = ["event_id", "scenario_id", "ts", "gateway", "success", "latency_ms", "error_code"]
    rows = [(_prefix(sid, r.event_id), sid, _clean(r.ts), _clean(r.gateway), _clean(r.success), _clean(r.latency_ms), _clean(r.error_code))
            for r in df.itertuples(index=False)]
    with conn.cursor() as cur:
        execute_values(cur,
            f"INSERT INTO payment_events ({','.join(cols)}) VALUES %s ON CONFLICT DO NOTHING",
            rows, page_size=5000)
    conn.commit()
    return len(rows)


def _load_marketing(conn, sid, df):
    df = df.where(pd.notna(df), None)
    cols = ["event_id", "scenario_id", "ts", "channel", "spend", "impressions", "source_stale"]
    rows = [(_prefix(sid, r.event_id), sid, _clean(r.ts), _clean(r.channel), _clean(r.spend), _clean(r.impressions), _clean(r.source_stale))
            for r in df.itertuples(index=False)]
    with conn.cursor() as cur:
        execute_values(cur,
            f"INSERT INTO marketing_events ({','.join(cols)}) VALUES %s ON CONFLICT DO NOTHING",
            rows, page_size=1000)
    conn.commit()
    return len(rows)


def _load_dq_log(conn, sid, df):
    # Create the data_quality_log table if it does not exist
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS data_quality_log (
                id SERIAL PRIMARY KEY,
                scenario_id VARCHAR(100) NOT NULL,
                ts TIMESTAMPTZ NOT NULL,
                data_quality_score NUMERIC(4,3) NOT NULL,
                null_row_count INTEGER,
                total_row_count INTEGER,
                in_gap BOOLEAN
            );
            CREATE INDEX IF NOT EXISTS idx_dq_scenario ON data_quality_log (scenario_id);
        """)
        conn.commit()
    df = df.where(pd.notna(df), None)
    cols = ["scenario_id", "ts", "data_quality_score", "null_row_count", "total_row_count", "in_gap"]
    rows = [(sid, r.ts, r.data_quality_score, getattr(r, "null_row_count", None),
             getattr(r, "total_row_count", None), getattr(r, "in_gap", None))
            for r in df.itertuples(index=False)]
    with conn.cursor() as cur:
        execute_values(cur,
            f"INSERT INTO data_quality_log ({','.join(cols)}) VALUES %s",
            rows, page_size=1000)
    conn.commit()
    return len(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario-id", required=True)
    ap.add_argument("--db-url", default=os.environ.get("DATABASE_URL", "postgresql://biai:biai@localhost:5432/biai"))
    args = ap.parse_args()

    sid = args.scenario_id
    data_dir = _ROOT / "data" / "synthetic" / sid
    if not data_dir.exists():
        raise SystemExit(f"No data folder for {sid} at {data_dir}")

    conn = psycopg2.connect(args.db_url)
    print(f"Loading {sid} (scenario-scoped IDs) ...")

    handlers = {
        "orders.csv": _load_orders,
        "payment_events.csv": _load_payment,
        "marketing_events.csv": _load_marketing,
        "data_quality_log.csv": _load_dq_log,
    }
    for fname, fn in handlers.items():
        path = data_dir / fname
        if path.exists():
            df = pd.read_csv(path)
            n = fn(conn, sid, df)
            print(f"  OK  {fname:24s} {n:>8,} rows")
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
