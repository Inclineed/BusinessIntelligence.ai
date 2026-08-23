"""
etl/load_fast.py — Fast bulk loader for INC_001 synthetic CSVs into Postgres.

Uses psycopg2.extras.execute_values (batched multi-row INSERT) which is far
faster than executemany for the 345k-row payment_events table.

Usage:
    python etl/load_fast.py
    python etl/load_fast.py --db-url postgresql://biai:biai@localhost:5432/biai
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

_ROOT = Path(__file__).resolve().parent.parent
_DATA = _ROOT / "data" / "synthetic"

# table -> (csv file, ordered columns, boolean columns)
_SPEC = [
    ("orders", "orders.csv",
     ["transaction_id", "scenario_id", "ts", "store_id", "device", "channel",
      "revenue", "conversion", "aov"],
     ["conversion"]),
    ("payment_events", "payment_events.csv",
     ["event_id", "scenario_id", "ts", "gateway", "success", "latency_ms", "error_code"],
     ["success"]),
    ("inventory_events", "inventory_events.csv",
     ["event_id", "scenario_id", "ts", "sku_id", "store_id", "in_stock", "fill_rate"],
     ["in_stock"]),
    ("marketing_events", "marketing_events.csv",
     ["event_id", "scenario_id", "ts", "channel", "spend", "impressions", "source_stale"],
     ["source_stale"]),
    ("support_tickets", "support_tickets.csv",
     ["ticket_id", "scenario_id", "ts", "store_id", "device", "message", "category"],
     []),
    ("deployment_log", "deployment_log.csv",
     ["deploy_id", "scenario_id", "ts", "version", "component", "notes"],
     []),
]

_BOOL_MAP = {"True": True, "False": False, True: True, False: False, "true": True, "false": False}


def _load_table(conn, table, csv_file, cols, bool_cols):
    path = _DATA / csv_file
    if not path.exists():
        print(f"  SKIP  {table}: {path} not found")
        return 0

    df = pd.read_csv(path)
    # keep only the schema columns (drops helper cols like _in_incident)
    df = df[[c for c in cols if c in df.columns]]
    for bc in bool_cols:
        if bc in df.columns:
            df[bc] = df[bc].map(_BOOL_MAP)
    # normalise NaN -> None for nullable columns (e.g. error_code)
    df = df.where(pd.notna(df), None)

    rows = [tuple(r) for r in df.itertuples(index=False)]
    if not rows:
        print(f"  {table}: 0 rows")
        return 0

    collist = ", ".join(cols[:len(df.columns)])
    sql = f"INSERT INTO {table} ({collist}) VALUES %s ON CONFLICT DO NOTHING"
    with conn.cursor() as cur:
        execute_values(cur, sql, rows, page_size=5000)
    conn.commit()
    print(f"  OK  {table:20s} {len(rows):>8,} rows")
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fast-load INC_001 CSVs into Postgres")
    parser.add_argument(
        "--db-url",
        default=os.environ.get("DATABASE_URL", "postgresql://biai:biai@localhost:5432/biai"),
    )
    args = parser.parse_args()

    print(f"Connecting to {args.db_url} ...")
    conn = psycopg2.connect(args.db_url)
    print("Loading tables (execute_values, batched):")
    total = 0
    for table, csv_file, cols, bool_cols in _SPEC:
        total += _load_table(conn, table, csv_file, cols, bool_cols)
    conn.close()
    print(f"Done. {total:,} rows loaded.")


if __name__ == "__main__":
    main()
