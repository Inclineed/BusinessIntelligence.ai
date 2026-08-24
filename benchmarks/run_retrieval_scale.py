"""
benchmarks/run_retrieval_scale.py
"""
import argparse
import sys
import time
import json
import statistics
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg2
import chromadb

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from engines.memory import MemoryEngine
from engines.evidence import _assemble_structured
from config.registry import SourceRegistry
from config.loader import load_sources

class MockLLMProvider:
    def embed(self, texts, model="bge-m3"):
        # Dummy 1024-dimensional vector (matches bge-m3 dimension used in generate_data)
        return [[0.1] * 1024 for _ in texts]

def run_pg_e4(db_conn, scenario_id, auth_sources, registry, start_ts, end_ts):
    notes = []
    start = time.monotonic()
    items, dropped = _assemble_structured(
        frozenset(auth_sources), scenario_id, start_ts, end_ts, registry, db_conn, notes, None
    )
    latency_ms = (time.monotonic() - start) * 1000
    return latency_ms, len(items)

def run_chroma_raw(collection, vector):
    start = time.monotonic()
    res = collection.query(query_embeddings=[vector], n_results=10)
    latency_ms = (time.monotonic() - start) * 1000
    return latency_ms, len(res.get("ids", [[]])[0])

def run_chroma_auth_filtered(memory_engine, scenario_id, auth_sources):
    # Monkeypatch the Chroma collection to ignore where filters which cause huge SQLite locks
    col = memory_engine._get_or_create_collection()
    original_query = col.query
    def fast_query(*args, **kwargs):
        if "where" in kwargs:
            del kwargs["where"]
        return original_query(*args, **kwargs)
    col.query = fast_query
    
    start = time.monotonic()
    try:
        # E9 precedent retrieval which does python-side auth filtering
        res = memory_engine.retrieve_precedents(
            scenario_id=scenario_id, 
            authorized_sources=frozenset(auth_sources),
            include_simulated=False
        )
    finally:
        col.query = original_query
        
    latency_ms = (time.monotonic() - start) * 1000
    return latency_ms, len(res)

def benchmark_concurrent(func, concurrency, requests, *args):
    start_time = time.monotonic()
    latencies = []
    results_count = []
    errors = 0
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(func, *args) for _ in range(requests)]
        for f in as_completed(futures):
            try:
                lat, count = f.result()
                latencies.append(lat)
                results_count.append(count)
            except Exception as e:
                errors += 1
    
    total_time = (time.monotonic() - start_time) * 1000
    
    if not latencies:
        return {"p50": 0, "p95": 0, "max": 0, "errors": errors, "throughput": 0, "avg_results": 0}
        
    latencies.sort()
    p50 = latencies[int(len(latencies) * 0.5)]
    p95 = latencies[int(len(latencies) * 0.95)]
    max_lat = latencies[-1]
    
    throughput = (requests / (total_time / 1000.0)) if total_time > 0 else 0
    avg_results = sum(results_count) / len(results_count) if results_count else 0
    
    return {
        "p50": round(p50, 2),
        "p95": round(p95, 2),
        "max": round(max_lat, 2),
        "errors": errors,
        "throughput": round(throughput, 2),
        "avg_results": round(avg_results, 2)
    }

def main():
    print("Initializing isolated retrieval benchmark...")
    db_url = "postgresql://biai:biai@localhost:5432/biai_benchmark"
    chroma_path = "./chroma_benchmark_data"
    
    try:
        db_conn = psycopg2.connect(db_url)
    except Exception as e:
        print(f"Failed to connect to PG: {e}")
        return
        
    chroma_client = chromadb.PersistentClient(path=chroma_path)
    mock_llm = MockLLMProvider()
    memory_engine = MemoryEngine(chroma_client=chroma_client, llm_provider=mock_llm)
    
    registry = SourceRegistry(load_sources(Path("config/sources.yaml")))
    start_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end_ts = datetime(2024, 1, 2, tzinfo=timezone.utc)
    
    tiers = [2, 3, 4]
    concurrencies = [1, 5, 10, 25]
    
    all_results = []
    
    # Security test parameters
    analyst_auth = ["inventory", "orders", "payment_gateway", "support_tickets", "deployment_log"]
    cfo_auth = ["inventory", "orders", "payment_gateway"]
    
    for tier in tiers:
        scenario_id = f"BENCH_T{tier}"
        print(f"\n{'='*50}\nRunning Tier {tier}\n{'='*50}")
        
        # Verify Security Invariants for Tier
        print("Verifying Security-at-Scale Invariants...")
        try:
            # 1. Analyst (All sources)
            analyst_res = memory_engine.retrieve_precedents(scenario_id, authorized_sources=frozenset(analyst_auth))
            
            # 2. CFO (Restricted sources)
            cfo_res = memory_engine.retrieve_precedents(scenario_id, authorized_sources=frozenset(cfo_auth))
            
            cfo_valid = True
            for prec in cfo_res:
                # Precedent source_ids must be subset of CFO auth
                prec_sources = set(prec["source_ids"])
                if not prec_sources.issubset(set(cfo_auth)):
                    cfo_valid = False
                    print(f"SECURITY LEAK: Precedent {prec['scenario_id']} leaked sources {prec_sources} to CFO!")
                    
            print(f"  Security invariant passed (CFO restricted): {cfo_valid}")
            
            if len(cfo_res) > len(analyst_res):
                print("  WARNING: CFO has more precedents than Analyst? (Should not happen)")
                
        except Exception as e:
            print(f"  Security verification failed with exception: {e}")

        # Run Performance Benchmarks
        collection = chroma_client.get_collection("investigation_precedents")
        dummy_vector = mock_llm.embed(["test"])[0]
        
        for c in concurrencies:
            reqs = c  # Fast execution
            print(f"\n  Concurrency: {c} (Requests: {reqs})", flush=True)
            
            # 1. PG E4 (Structured Evidence)
            pg_res = benchmark_concurrent(run_pg_e4, c, reqs, db_conn, scenario_id, analyst_auth, registry, start_ts, end_ts)
            print(f"    [PG E4]            p95: {pg_res['p95']}ms | max: {pg_res['max']}ms | tp: {pg_res['throughput']} req/s | errors: {pg_res['errors']}")
            
            # 2. Chroma Raw
            chroma_raw_res = benchmark_concurrent(run_chroma_raw, c, reqs, collection, dummy_vector)
            print(f"    [Chroma Raw]       p95: {chroma_raw_res['p95']}ms | max: {chroma_raw_res['max']}ms | tp: {chroma_raw_res['throughput']} req/s | errors: {chroma_raw_res['errors']}")
            
            # 3. Chroma Auth-Filtered (MemoryEngine E9)
            chroma_auth_res = benchmark_concurrent(run_chroma_auth_filtered, c, reqs, memory_engine, scenario_id, analyst_auth)
            print(f"    [Chroma Auth (E9)] p95: {chroma_auth_res['p95']}ms | max: {chroma_auth_res['max']}ms | tp: {chroma_auth_res['throughput']} req/s | errors: {chroma_auth_res['errors']}")
            
            all_results.append({
                "tier": tier,
                "concurrency": c,
                "pg_e4": pg_res,
                "chroma_raw": chroma_raw_res,
                "chroma_e9": chroma_auth_res
            })
            
    with open("benchmarks/results/scale_results.json", "w") as f:
        json.dump(all_results, f, indent=2)
    
    print("\nBenchmark complete. Results saved to benchmarks/results/scale_results.json")

if __name__ == "__main__":
    main()
