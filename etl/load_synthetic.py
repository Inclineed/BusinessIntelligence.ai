"""
etl/load_synthetic.py — Load INC_001 synthetic CSVs into Postgres.

Reads the six CSVs produced by etl/generate_inc001.py and bulk-inserts them
into the corresponding Postgres tables (orders, payment_events, inventory_events,
marketing_events, support_tickets, deployment_log).

After loading, the marketing source's last_refresh is set to utcnow() − 5 h in
the SourceRegistry, making it intentionally stale for the INC_001 scenario.
This causes the marketing evidence reliability_weight to be decayed by the
Evidence_Engine, weakening the competitor-pricing hypothesis H2.

Usage:
    python etl/load_synthetic.py [--scenario-id INC_001] [--db-url postgresql://...]
    DATABASE_URL=postgresql://... python etl/load_synthetic.py

Dependencies: psycopg2, pandas, PyYAML (all in requirements.txt)

Requirements: 1.2, 12.1
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure project root is on sys.path so we can import config modules
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import psycopg2
from psycopg2 import sql as psql

from config.loader import load_sources
from config.registry import SourceRegistry

# ---------------------------------------------------------------------------
# Table → CSV mapping and column definitions
# ---------------------------------------------------------------------------

# Each entry: (table_name, csv_filename, ordered_columns_matching_table)
TABLE_MAP: list[tuple[str, str, list[str]]] = [
    (
        "orders",
        "orders.csv",
        [
            "transaction_id", "scenario_id", "ts", "store_id",
            "device", "channel", "revenue", "conversion", "aov",
        ],
    ),
    (
        "payment_events",
        "payment_events.csv",
        [
            "event_id", "scenario_id", "ts", "gateway",
            "success", "latency_ms", "error_code",
        ],
    ),
    (
        "inventory_events",
        "inventory_events.csv",
        [
            "event_id", "scenario_id", "ts", "sku_id",
            "store_id", "in_stock", "fill_rate",
        ],
    ),
    (
        "marketing_events",
        "marketing_events.csv",
        [
            "event_id", "scenario_id", "ts", "channel",
            "spend", "impressions", "source_stale",
        ],
    ),
    (
        "support_tickets",
        "support_tickets.csv",
        [
            "ticket_id", "scenario_id", "ts", "store_id",
            "device", "message", "category",
        ],
    ),
    (
        "deployment_log",
        "deployment_log.csv",
        [
            "deploy_id", "scenario_id", "ts", "version",
            "component", "notes",
        ],
    ),
]

# Primary key column per table — used for ON CONFLICT DO NOTHING
PK_MAP: dict[str, str] = {
    "orders":            "transaction_id",
    "payment_events":    "event_id",
    "inventory_events":  "event_id",
    "marketing_events":  "event_id",
    "support_tickets":   "ticket_id",
    "deployment_log":    "deploy_id",
}

# Boolean columns that need explicit casting from CSV strings
BOOL_COLUMNS: dict[str, list[str]] = {
    "orders":           ["conversion"],
    "payment_events":   ["success"],
    "inventory_events": ["in_stock"],
    "marketing_events": ["source_stale"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_bool(value: str) -> bool:
    """Convert CSV boolean representations to Python bool."""
    return value.strip().lower() in {"true", "1", "yes", "t"}


def _load_csv_rows(csv_path: Path, columns: list[str], bool_cols: list[str]) -> list[dict]:
    """
    Read a CSV file and return a list of dicts, coercing boolean columns.
    Rows where all non-scenario-id fields are empty are skipped.
    """
    rows = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            for col in bool_cols:
                if col in row:
                    row[col] = _parse_bool(row[col])
            # Replace empty strings with None
            for k, v in row.items():
                if v == "":
                    row[k] = None
            rows.append(row)
    return rows


def _bulk_insert(
    conn: "psycopg2.connection",
    table: str,
    columns: list[str],
    rows: list[dict],
    pk_col: str,
    scenario_id: str,
) -> int:
    """
    Bulk-insert *rows* into *table* using executemany with ON CONFLICT DO NOTHING.

    Rows are first filtered to only those matching *scenario_id* (defensive check
    in case the CSV contains data for multiple scenarios).

    Returns the number of rows actually inserted (approximate — relies on
    rowcount after executemany in psycopg2).
    """
    if not rows:
        return 0

    filtered = [r for r in rows if r.get("scenario_id") == scenario_id]
    if not filtered:
        print(f"    WARNING: no rows matching scenario_id={scenario_id!r} in {table}")
        return 0

    col_idents = [psql.Identifier(c) for c in columns]
    insert_stmt = psql.SQL(
        "INSERT INTO {table} ({cols}) VALUES ({placeholders}) "
        "ON CONFLICT ({pk}) DO NOTHING"
    ).format(
        table=psql.Identifier(table),
        cols=psql.SQL(", ").join(col_idents),
        placeholders=psql.SQL(", ").join(psql.Placeholder() * len(columns)),
        pk=psql.Identifier(pk_col),
    )

    # Build tuple list — preserve column order
    data = [tuple(r.get(c) for c in columns) for r in filtered]

    with conn.cursor() as cur:
        cur.executemany(insert_stmt, data)
        conn.commit()
        # rowcount after executemany = rows processed (not always rows inserted due to conflicts)
        return len(data)


# ---------------------------------------------------------------------------
# Marketing staleness
# ---------------------------------------------------------------------------

def _apply_marketing_staleness(sources_yaml_path: Path) -> None:
    """
    Update the marketing source's last_refresh to utcnow() − 5h in the
    SourceRegistry, making it intentionally stale for INC_001.

    This is an in-memory operation only — it sets the runtime state that the
    Evidence_Engine reads via the registry.  The sources.yaml file is unchanged.
    """
    sources_config = load_sources(sources_yaml_path)
    registry = SourceRegistry(sources_config)

    stale_ts = datetime.utcnow() - timedelta(hours=5)
    registry.update_last_refresh("marketing", stale_ts)

    entry = registry.get("marketing")
    print(
        f"\n  Marketing source freshness updated:"
        f"\n    last_refresh    = {stale_ts.isoformat()} UTC"
        f"\n    sla_minutes     = {entry.sla_minutes}"
        f"\n    staleness_min   = {entry.staleness_minutes:.1f}"
        f"\n    freshness_status= {entry.freshness_status.value}"
    )
    return registry   # caller may inspect


# ---------------------------------------------------------------------------
# Main loader
# ---------------------------------------------------------------------------

def load(
    db_url: str,
    scenario_id: str,
    data_dir: Path,
    sources_yaml: Path,
) -> None:
    """
    Connect to Postgres, load all six tables, then update marketing staleness.
    """
    print(f"\nConnecting to Postgres …")
    try:
        conn = psycopg2.connect(db_url)
    except Exception as exc:
        print(f"ERROR: cannot connect to Postgres: {exc}")
        sys.exit(1)

    print(f"Connected.  Loading scenario {scenario_id!r} from {data_dir} …\n")

    summary_rows = []
    for table, csv_file, columns in TABLE_MAP:
        csv_path = data_dir / csv_file
        if not csv_path.exists():
            print(f"  SKIP  {csv_file} (not found at {csv_path})")
            summary_rows.append({"table": table, "rows_inserted": 0, "status": "missing"})
            continue

        bool_cols = BOOL_COLUMNS.get(table, [])
        rows = _load_csv_rows(csv_path, columns, bool_cols)

        pk_col = PK_MAP[table]
        inserted = _bulk_insert(conn, table, columns, rows, pk_col, scenario_id)
        print(f"  ✓ {table:22s}  {inserted:>7,} rows")
        summary_rows.append({"table": table, "rows_inserted": inserted, "status": "ok"})

    conn.close()

    # --- Summary ---
    print("\n--- Load Summary ---")
    total = 0
    for r in summary_rows:
        print(f"  {r['table']:22s}  {r['rows_inserted']:>7,}  [{r['status']}]")
        total += r["rows_inserted"]
    print(f"  {'TOTAL':22s}  {total:>7,}")

    # --- Marketing staleness ---
    _apply_marketing_staleness(sources_yaml)

    print("\nLoad complete.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load INC_001 synthetic CSVs into Postgres"
    )
    parser.add_argument(
        "--scenario-id",
        default="INC_001",
        help="Scenario identifier to tag loaded rows (default: INC_001)",
    )
    parser.add_argument(
        "--db-url",
        default=os.environ.get("DATABASE_URL", ""),
        help="PostgreSQL connection URL (default: $DATABASE_URL env var)",
    )
    parser.add_argument(
        "--data-dir",
        default="data/synthetic",
        help="Directory containing the CSVs (default: data/synthetic)",
    )
    parser.add_argument(
        "--sources-yaml",
        default="config/sources.yaml",
        help="Path to sources.yaml for SourceRegistry (default: config/sources.yaml)",
    )
    args = parser.parse_args()

    if not args.db_url:
        parser.error(
            "No database URL provided.  Use --db-url or set the DATABASE_URL environment variable."
        )

    load(
        db_url=args.db_url,
        scenario_id=args.scenario_id,
        data_dir=Path(args.data_dir),
        sources_yaml=Path(args.sources_yaml),
    )


if __name__ == "__main__":
    main()
