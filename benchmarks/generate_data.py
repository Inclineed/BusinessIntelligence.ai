"""
benchmarks/generate_data.py — Generate synthetic data for scalability benchmarks.

Generates PostgreSQL event rows and ChromaDB precedents based on the target Tier.

Usage:
    python benchmarks/generate_data.py --tier 1
"""
import argparse
import os
import sys
import time
import uuid
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import psycopg2
from psycopg2.extras import execute_values
import chromadb

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Tier definitions
# (events_per_scenario, precedents_count)
TIERS = {
    1: (1_000, 100),
    2: (10_000, 1_000),
    3: (100_000, 10_000),
    4: (1_000_000, 100_000),
}

SCENARIO_PREFIX = "BENCH_"
GEN_START = datetime(2024, 1, 1, tzinfo=timezone.utc)
EMBEDDING_DIM = 1024

def get_db_conn(db_url: str):
    return psycopg2.connect(db_url)

def generate_postgres_data(conn, tier: int):
    events_target, _ = TIERS[tier]
    scenario_id = f"{SCENARIO_PREFIX}T{tier}"
    
    print(f"Generating {events_target} PostgreSQL rows for scenario {scenario_id}...")
    
    # We will generate orders and payment_events to hit the target.
    # Split 50/50
    orders_target = events_target // 2
    payments_target = events_target - orders_target
    
    start_time = time.monotonic()
    
    with conn.cursor() as cur:
        # Generate Orders
        orders_data = []
        for i in range(orders_target):
            ts = GEN_START + timedelta(minutes=i)
            device = random.choice(["android", "ios", "desktop"])
            channel = random.choice(["app", "web"])
            orders_data.append((
                f"TXN_{uuid.uuid4().hex[:8]}",
                scenario_id,
                ts.isoformat(),
                "store_1",
                device,
                channel,
                round(random.uniform(10.0, 150.0), 2),
                random.random() > 0.3,
                round(random.uniform(10.0, 150.0), 2)
            ))
            
            if len(orders_data) >= 10000:
                execute_values(cur,
                    "INSERT INTO orders (transaction_id, scenario_id, ts, store_id, device, channel, revenue, conversion, aov) VALUES %s ON CONFLICT DO NOTHING",
                    orders_data
                )
                orders_data = []
                
        if orders_data:
            execute_values(cur,
                "INSERT INTO orders (transaction_id, scenario_id, ts, store_id, device, channel, revenue, conversion, aov) VALUES %s ON CONFLICT DO NOTHING",
                orders_data
            )
            
        # Generate Payments
        payments_data = []
        for i in range(payments_target):
            ts = GEN_START + timedelta(minutes=i)
            success = random.random() > 0.05
            payments_data.append((
                f"PAY_{uuid.uuid4().hex[:8]}",
                scenario_id,
                ts.isoformat(),
                "gateway_1",
                success,
                int(random.uniform(50, 500)),
                None if success else "DECLINED"
            ))
            
            if len(payments_data) >= 10000:
                execute_values(cur,
                    "INSERT INTO payment_events (event_id, scenario_id, ts, gateway, success, latency_ms, error_code) VALUES %s ON CONFLICT DO NOTHING",
                    payments_data
                )
                payments_data = []
                
        if payments_data:
            execute_values(cur,
                "INSERT INTO payment_events (event_id, scenario_id, ts, gateway, success, latency_ms, error_code) VALUES %s ON CONFLICT DO NOTHING",
                payments_data
            )
            
        conn.commit()
        
    print(f"PostgreSQL generation completed in {time.monotonic() - start_time:.2f}s")


def generate_chroma_data(chroma_path: str, tier: int):
    _, precedents_target = TIERS[tier]
    
    print(f"Generating {precedents_target} ChromaDB precedents in path {chroma_path}...")
    
    client = chromadb.PersistentClient(path=chroma_path)
    collection = client.get_or_create_collection(
        name="investigation_precedents",
        metadata={"hnsw:space": "cosine"}
    )
    
    start_time = time.monotonic()
    
    batch_size = 5000
    ids = []
    embeddings = []
    documents = []
    metadatas = []
    
    confidences = ["high", "medium", "low", "abstain"]
    sources = ["inventory", "orders", "payment_gateway", "support_tickets", "deployment_log"]
    
    for i in range(precedents_target):
        p_id = f"PREC_{tier}_{uuid.uuid4().hex[:8]}"
        ids.append(p_id)
        
        # Synthetic 1024-d embedding (bge-m3 size)
        embeddings.append(np.random.normal(0, 1, EMBEDDING_DIM).tolist())
        documents.append(f"Synthetic benchmark precedent for tier {tier}. Incident {p_id}.")
        
        # Random subset of sources
        sampled_sources = random.sample(sources, random.randint(1, 3))
        
        metadatas.append({
            "scenario_id": p_id,
            "persona": random.choice(["analyst", "cfo", "manager"]),
            "source_ids": ",".join(sorted(sampled_sources)),
            "confidence_state": random.choice(confidences),
            "outcome_type": "observed",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "human_validated": random.random() > 0.8
        })
        
        if len(ids) >= batch_size:
            collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
            ids, embeddings, documents, metadatas = [], [], [], []
            print(f"  Inserted batch... ({i+1}/{precedents_target})")
            
    if ids:
        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        
    print(f"ChromaDB generation completed in {time.monotonic() - start_time:.2f}s")


def main():
    parser = argparse.ArgumentParser(description="Generate benchmark data")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3, 4], required=True, help="Scale tier (1-4)")
    parser.add_argument("--db-url", type=str, default="postgresql://biai:biai@localhost:5432/biai_benchmark", help="Postgres URL")
    parser.add_argument("--chroma-path", type=str, default="./chroma_benchmark_data", help="Chroma DB path")
    args = parser.parse_args()

    # Create chroma dir if not exists
    os.makedirs(args.chroma_path, exist_ok=True)
    
    print(f"=== Starting Data Generation for TIER {args.tier} ===")
    
    try:
        conn = get_db_conn(args.db_url)
        generate_postgres_data(conn, args.tier)
        conn.close()
    except Exception as e:
        print(f"Failed to generate Postgres data: {e}. Is the biai_benchmark DB created?")
        
    generate_chroma_data(args.chroma_path, args.tier)
    print("=== Done ===")

if __name__ == "__main__":
    main()
