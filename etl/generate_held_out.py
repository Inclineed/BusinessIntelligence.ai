"""
etl/generate_held_out.py — Generate and load complete synthetic datasets for held-out
scenarios INC_005, INC_006, and INC_007 into PostgreSQL and ChromaDB.

INC_005: Normal seasonal / periodic demand pattern (no anomaly).
INC_006: Multi-root-cause incident (Network latency packet loss + deployment bug v4.3.1).
INC_007: Gradual degradation (Memory leak drift over 48 hours).
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import chromadb
from chromadb.config import Settings

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from llm.provider import OllamaProvider

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://biai:biai@localhost:5432/biai")
CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))

GEN_START = datetime(2024, 1, 8, 0, 0, 0, tzinfo=timezone.utc)
GEN_END   = datetime(2024, 1, 16, 23, 59, 59, tzinfo=timezone.utc)

def _utc_iso(dt: datetime) -> str:
    return dt.isoformat()

def _clean(v):
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v

# ===========================================================================
# 1. INC_005 — Normal Seasonality (No Anomaly)
# ===========================================================================
def generate_inc005_data(rng: np.random.Generator):
    orders = []
    payments = []
    current = GEN_START
    txn_id = 1
    event_id = 1

    devices = ["android", "ios", "desktop"]
    dev_weights = [0.40, 0.35, 0.25]
    channels = ["app", "web"]

    while current <= GEN_END:
        # Periodic diurnal curve (peaks at 14:00, troughs at 03:00)
        hour = current.hour
        hour_factor = 0.7 + 0.6 * np.sin(np.pi * (hour - 6) / 12) ** 2
        
        for _ in range(120):
            dev = rng.choice(devices, p=dev_weights)
            chan = "app" if dev in ("android", "ios") and rng.random() < 0.85 else "web"
            
            # Normal conversion: ~68%
            is_conv = bool(rng.random() < 0.68)
            rev = round(float(rng.normal(70.0, 15.0)), 2) if is_conv else 0.0
            
            orders.append({
                "transaction_id": f"INC_005_TXN_{txn_id:07d}",
                "scenario_id": "INC_005",
                "ts": _utc_iso(current + timedelta(minutes=int(rng.integers(0, 60)))),
                "store_id": "STORE_001",
                "device": dev,
                "channel": chan,
                "revenue": rev,
                "conversion": is_conv,
                "aov": rev if is_conv else 70.0,
            })
            txn_id += 1

        # Payment events: normal 2% failure, 180ms latency
        for _ in range(40):
            is_succ = bool(rng.random() > 0.02)
            lat = int(rng.normal(180, 25))
            payments.append({
                "event_id": f"INC_005_PAY_{event_id:07d}",
                "scenario_id": "INC_005",
                "ts": _utc_iso(current + timedelta(minutes=int(rng.integers(0, 60)))),
                "gateway": "stripe_v2",
                "success": is_succ,
                "latency_ms": max(50, lat),
                "error_code": None if is_succ else "GENERIC_DECLINE",
            })
            event_id += 1

        current += timedelta(hours=1)

    return pd.DataFrame(orders), pd.DataFrame(payments)


# ===========================================================================
# 2. INC_006 — Multi-Root-Cause (Network Packet Loss + Deployment Bug v4.3.1)
# ===========================================================================
INC_006_INC_START = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
INC_006_INC_END   = datetime(2024, 1, 15, 15, 0, 0, tzinfo=timezone.utc)

def generate_inc006_data(rng: np.random.Generator):
    orders = []
    payments = []
    current = GEN_START
    txn_id = 1
    event_id = 1

    devices = ["android", "ios", "desktop"]
    dev_weights = [0.40, 0.35, 0.25]

    while current <= GEN_END:
        in_incident = (INC_006_INC_START <= current <= INC_006_INC_END)

        for _ in range(120):
            dev = rng.choice(devices, p=dev_weights)
            chan = "app" if dev in ("android", "ios") and rng.random() < 0.85 else "web"

            # Baseline conv 68%. During incident: Android drops to 52% (-16%), iOS drops to 58% (-10%)
            if in_incident:
                if dev == "android":
                    conv_prob = 0.52
                elif dev == "ios":
                    conv_prob = 0.58
                else:
                    conv_prob = 0.65
            else:
                conv_prob = 0.68

            is_conv = bool(rng.random() < conv_prob)
            rev = round(float(rng.normal(70.0, 15.0)), 2) if is_conv else 0.0

            orders.append({
                "transaction_id": f"INC_006_TXN_{txn_id:07d}",
                "scenario_id": "INC_006",
                "ts": _utc_iso(current + timedelta(minutes=int(rng.integers(0, 60)))),
                "store_id": "STORE_001",
                "device": dev,
                "channel": chan,
                "revenue": rev,
                "conversion": is_conv,
                "aov": rev if is_conv else 70.0,
            })
            txn_id += 1

        # Payment events: failure spikes to 6.5%, latency spikes to 460ms during incident
        for _ in range(40):
            if in_incident:
                is_succ = bool(rng.random() > 0.065)
                lat = int(rng.normal(460, 80))
                err = None if is_succ else "GATEWAY_TIMEOUT"
            else:
                is_succ = bool(rng.random() > 0.02)
                lat = int(rng.normal(180, 25))
                err = None if is_succ else "GENERIC_DECLINE"

            payments.append({
                "event_id": f"INC_006_PAY_{event_id:07d}",
                "scenario_id": "INC_006",
                "ts": _utc_iso(current + timedelta(minutes=int(rng.integers(0, 60)))),
                "gateway": "stripe_v2",
                "success": is_succ,
                "latency_ms": max(50, lat),
                "error_code": err,
            })
            event_id += 1

        current += timedelta(hours=1)

    deployment = pd.DataFrame([{
        "deploy_id": "INC_006_DEP_001",
        "scenario_id": "INC_006",
        "ts": "2024-01-15T08:45:00+00:00",
        "version": "v4.3.1",
        "component": "checkout-service",
        "notes": "Refactored payment gateway client connection pooling and timeout handling.",
    }])

    return pd.DataFrame(orders), pd.DataFrame(payments), deployment


# ===========================================================================
# 3. INC_007 — Gradual Degradation (Memory Leak Drift over 48h)
# ===========================================================================
INC_007_DRIFT_START = datetime(2024, 1, 14, 12, 0, 0, tzinfo=timezone.utc)
INC_007_DRIFT_END   = datetime(2024, 1, 16, 12, 0, 0, tzinfo=timezone.utc)

def generate_inc007_data(rng: np.random.Generator):
    orders = []
    payments = []
    current = GEN_START
    txn_id = 1
    event_id = 1

    devices = ["android", "ios", "desktop"]
    dev_weights = [0.40, 0.35, 0.25]

    total_drift_hours = (INC_007_DRIFT_END - INC_007_DRIFT_START).total_seconds() / 3600.0

    while current <= GEN_END:
        if current < INC_007_DRIFT_START:
            drift_factor = 0.0
        elif current <= INC_007_DRIFT_END:
            elapsed = (current - INC_007_DRIFT_START).total_seconds() / 3600.0
            drift_factor = elapsed / total_drift_hours
        else:
            drift_factor = 1.0

        for _ in range(120):
            dev = rng.choice(devices, p=dev_weights)
            chan = "app" if dev in ("android", "ios") and rng.random() < 0.85 else "web"

            # Conversion drifts from 0.68 down to 0.54
            conv_prob = 0.68 - (0.14 * drift_factor)
            is_conv = bool(rng.random() < conv_prob)
            rev = round(float(rng.normal(70.0, 15.0)), 2) if is_conv else 0.0

            orders.append({
                "transaction_id": f"INC_007_TXN_{txn_id:07d}",
                "scenario_id": "INC_007",
                "ts": _utc_iso(current + timedelta(minutes=int(rng.integers(0, 60)))),
                "store_id": "STORE_001",
                "device": dev,
                "channel": chan,
                "revenue": rev,
                "conversion": is_conv,
                "aov": rev if is_conv else 70.0,
            })
            txn_id += 1

        # Payment events: latency drifts from 180ms to 520ms, failure rate drifts from 2% to 6%
        for _ in range(40):
            fail_prob = 0.02 + (0.04 * drift_factor)
            mean_lat = 180.0 + (340.0 * drift_factor)

            is_succ = bool(rng.random() > fail_prob)
            lat = int(rng.normal(mean_lat, 35))
            err = None if is_succ else "CONNECTION_RESET"

            payments.append({
                "event_id": f"INC_007_PAY_{event_id:07d}",
                "scenario_id": "INC_007",
                "ts": _utc_iso(current + timedelta(minutes=int(rng.integers(0, 60)))),
                "gateway": "stripe_v2",
                "success": is_succ,
                "latency_ms": max(50, lat),
                "error_code": err,
            })
            event_id += 1

        current += timedelta(hours=1)

    deployment = pd.DataFrame([{
        "deploy_id": "INC_007_DEP_001",
        "scenario_id": "INC_007",
        "ts": "2024-01-14T11:30:00+00:00",
        "version": "v4.3.0-worker",
        "component": "checkout-service",
        "notes": "Deployed worker process update for checkout transaction processing.",
    }])

    return pd.DataFrame(orders), pd.DataFrame(payments), deployment


# ===========================================================================
# 4. INC_008 — B2B SaaS Churn / SSO Integration Failure
# ===========================================================================
INC_008_START = datetime(2024, 2, 2, 0, 0, 0, tzinfo=timezone.utc)
INC_008_END   = datetime(2024, 2, 10, 23, 59, 59, tzinfo=timezone.utc)
INC_008_ANOMALY_START = datetime(2024, 2, 10, 14, 0, 0, tzinfo=timezone.utc)
INC_008_ANOMALY_END   = datetime(2024, 2, 10, 18, 0, 0, tzinfo=timezone.utc)

def generate_inc008_data(rng: np.random.Generator):
    orders = []
    payments = []
    current = INC_008_START
    txn_id = 1
    event_id = 1

    devices = ["android", "ios", "desktop"]
    dev_weights = [0.40, 0.35, 0.25]

    while current <= INC_008_END:
        in_anomaly = (INC_008_ANOMALY_START <= current <= INC_008_ANOMALY_END)

        for _ in range(100):
            dev = rng.choice(devices, p=dev_weights)
            chan = "app" if dev in ("android", "ios") and rng.random() < 0.85 else "web"

            conv_prob = 0.55 if in_anomaly else 0.70
            is_conv = bool(rng.random() < conv_prob)
            rev = round(float(rng.normal(85.0, 20.0)), 2) if is_conv else 0.0

            orders.append({
                "transaction_id": f"INC_008_TXN_{txn_id:07d}",
                "scenario_id": "INC_008",
                "ts": _utc_iso(current + timedelta(minutes=int(rng.integers(0, 60)))),
                "store_id": "STORE_001",
                "device": dev,
                "channel": chan,
                "revenue": rev,
                "conversion": is_conv,
                "aov": rev if is_conv else 85.0,
            })
            txn_id += 1

        for _ in range(40):
            fail_prob = 0.35 if in_anomaly else 0.01
            is_succ = bool(rng.random() > fail_prob)
            lat = int(rng.normal(480, 50)) if in_anomaly else int(rng.normal(120, 15))
            err = "SSO_OKTA_AUTH_FAILURE" if (in_anomaly and not is_succ) else (None if is_succ else "PAYMENT_FAILED")

            payments.append({
                "event_id": f"INC_008_PAY_{event_id:07d}",
                "scenario_id": "INC_008",
                "ts": _utc_iso(current + timedelta(minutes=int(rng.integers(0, 60)))),
                "gateway": "okta_sso",
                "success": is_succ,
                "latency_ms": max(50, lat),
                "error_code": err,
            })
            event_id += 1

        current += timedelta(hours=1)

    deployment = pd.DataFrame([{
        "deploy_id": "INC_008_DEP_001",
        "scenario_id": "INC_008",
        "ts": "2024-02-10T13:30:00+00:00",
        "version": "v2.4.0",
        "component": "sso-auth-service",
        "notes": "Deployed v2.4.0 auth update introducing SAML SSO integration changes for Okta.",
    }])

    return pd.DataFrame(orders), pd.DataFrame(payments), deployment


# ===========================================================================
# 5. ChromaDB Evidence Seeding
# ===========================================================================
HELD_OUT_EVIDENCE = {
    "INC_005": [
        ("orders", "ORD_seas_1", "Hourly revenue and conversion followed standard weekend and diurnal seasonality patterns with no structural deviation from baseline."),
        ("payment_gateway", "PAY_seas_1", "Payment gateway transaction volume and latency metrics remained within normal expected SLA boundaries throughout the observation window."),
    ],
    "INC_006": [
        ("deployment_log", "DEP_v431_1", "Checkout-service v4.3.1 deployed at 08:45 UTC introduced a connection pool starvation regression in the payment gateway client under high concurrency."),
        ("payment_gateway", "PAY_net_1", "Upstream network packet loss of 4.5% observed on primary payment routing links during 09:00-15:00 UTC, causing elevated retry latency and socket drops."),
        ("orders", "ORD_dev_1", "Order conversion dropped significantly across mobile channels with Android experiencing a 15% decline and iOS a 10% decline during the incident window."),
        ("support_tickets", "SUP_tick_1", "Support tickets surged with customer reports of payment timeouts and gateway error screens during checkout completion."),
    ],
    "INC_007": [
        ("deployment_log", "DEP_mem_1", "Worker process memory leak: heap allocation increased monotonically from 450MB to 3.8GB over 48 hours following the Jan 14 11:30 deployment."),
        ("payment_gateway", "PAY_lat_1", "Gateway latency exhibited steady gradual drift over 48 hours with average response time rising from 180ms to over 500ms and GC pause frequency spiking."),
        ("orders", "ORD_drift_1", "Conversion rate showed progressive multi-day downward drift across all checkout channels as transaction timeout rates crept upward."),
    ],
    "INC_008": [
        ("deployment_log", "DEP_sso_1", "SSO auth service v2.4.0 deployed at 13:30 UTC introduced an authentication token parsing bug breaking Okta SAML SSO login for Enterprise tier users."),
        ("payment_gateway", "PAY_sso_1", "SSO failure rate spiked to 94% on Okta auth provider links following v2.4.0 deployment, causing Enterprise subscription cancellations."),
        ("support_tickets", "SUP_sso_1", "Zendesk support tickets surged with Enterprise admins complaining about being unable to log in via Okta SSO."),
    ],
}


class _Embed:
    def __init__(self, provider, model="bge-m3"):
        self._p = provider
        self._m = model
    def __call__(self, input):
        return self._p.embed(input, model=self._m)
    def name(self):
        return f"ollama-{self._m}"


def load_postgres(conn, df_orders, df_payments, df_deploy=None):
    with conn.cursor() as cur:
        # Load orders
        if not df_orders.empty:
            cols = ["transaction_id", "scenario_id", "ts", "store_id", "device", "channel", "revenue", "conversion", "aov"]
            rows = [
                (r["transaction_id"], r["scenario_id"], _clean(r["ts"]), r["store_id"], r["device"], r["channel"], _clean(r["revenue"]), _clean(r["conversion"]), _clean(r["aov"]))
                for _, r in df_orders.iterrows()
            ]
            execute_values(cur, f"INSERT INTO orders ({','.join(cols)}) VALUES %s ON CONFLICT (transaction_id) DO UPDATE SET revenue=EXCLUDED.revenue", rows, page_size=5000)
            print(f"  -> Inserted {len(rows)} rows into orders")

        # Load payment_events
        if not df_payments.empty:
            cols = ["event_id", "scenario_id", "ts", "gateway", "success", "latency_ms", "error_code"]
            rows = [
                (r["event_id"], r["scenario_id"], _clean(r["ts"]), r["gateway"], _clean(r["success"]), _clean(r["latency_ms"]), _clean(r["error_code"]))
                for _, r in df_payments.iterrows()
            ]
            execute_values(cur, f"INSERT INTO payment_events ({','.join(cols)}) VALUES %s ON CONFLICT (event_id) DO NOTHING", rows, page_size=5000)
            print(f"  -> Inserted {len(rows)} rows into payment_events")

        # Load deployment_log
        if df_deploy is not None and not df_deploy.empty:
            cols = ["deploy_id", "scenario_id", "ts", "version", "component", "notes"]
            rows = [
                (r["deploy_id"], r["scenario_id"], _clean(r["ts"]), r["version"], r["component"], _clean(r["notes"]))
                for _, r in df_deploy.iterrows()
            ]
            execute_values(cur, f"INSERT INTO deployment_log ({','.join(cols)}) VALUES %s ON CONFLICT (deploy_id) DO NOTHING", rows, page_size=100)
            print(f"  -> Inserted {len(rows)} rows into deployment_log")

    conn.commit()


def main():
    print("=" * 60)
    print("Generating & Loading Held-Out Datasets (INC_005, INC_006, INC_007)")
    print("=" * 60)

    rng = np.random.default_rng(42)
    conn = psycopg2.connect(DATABASE_URL)

    # 1. INC_005
    print("\n--- Generating INC_005 (Seasonality) ---")
    df_ord5, df_pay5 = generate_inc005_data(rng)
    load_postgres(conn, df_ord5, df_pay5)

    # 2. INC_006
    print("\n--- Generating INC_006 (Multi-Root-Cause) ---")
    df_ord6, df_pay6, df_dep6 = generate_inc006_data(rng)
    load_postgres(conn, df_ord6, df_pay6, df_dep6)

    # 3. INC_007
    print("\n--- Generating INC_007 (Gradual Degradation) ---")
    df_ord7, df_pay7, df_dep7 = generate_inc007_data(rng)
    load_postgres(conn, df_ord7, df_pay7, df_dep7)

    # 4. INC_008
    print("\n--- Generating INC_008 (B2B SaaS Churn / SSO Failure) ---")
    df_ord8, df_pay8, df_dep8 = generate_inc008_data(rng)
    load_postgres(conn, df_ord8, df_pay8, df_dep8)

    # 4. ChromaDB Seeding
    print("\n--- Seeding ChromaDB Evidence Collections ---")
    provider = OllamaProvider()
    ef = _Embed(provider)
    chroma_client = chromadb.HttpClient(
        host=CHROMA_HOST,
        port=CHROMA_PORT,
        settings=Settings(anonymized_telemetry=False),
    )

    for sid, docs in HELD_OUT_EVIDENCE.items():
        col_name = f"evidence_{sid}"
        col = chroma_client.get_or_create_collection(
            name=col_name,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
        ids = [f"{sid}_{d[1]}" for d in docs]
        documents = [d[2] for d in docs]
        metadatas = [{"source": d[0], "scenario_id": sid, "evidence_type": "unstructured"} for d in docs]
        col.upsert(ids=ids, documents=documents, metadatas=metadatas)
        print(f"  -> Seeded {col_name}: {len(docs)} documents")

    print("\nGeneration and ingestion completed successfully!")


if __name__ == "__main__":
    main()
