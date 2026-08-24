"""
benchmarks/test_e9_filter.py
"""
import argparse
import sys
import time
import json
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import chromadb

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from engines.memory import MemoryEngine

class MockLLMProvider:
    def embed(self, texts, model="bge-m3"):
        return [[0.1] * 1024 for _ in texts]

def bench_pipeline_a(chroma_client, mock_llm, scenario_id, auth_sources):
    me = MemoryEngine(chroma_client=chroma_client, llm_provider=mock_llm)
    start = time.monotonic()
    res = me.retrieve_precedents(
        scenario_id=scenario_id, 
        authorized_sources=frozenset(auth_sources),
        include_simulated=False
    )
    return (time.monotonic() - start) * 1000, res

def bench_pipeline_b(chroma_client, mock_llm, scenario_id, auth_sources, multiplier):
    me = MemoryEngine(chroma_client=chroma_client, llm_provider=mock_llm)
    col = me._get_or_create_collection()
    
    class CollectionProxy:
        def __init__(self, col):
            self._col = col
        def query(self, *args, **kwargs):
            # Do NOT mutate kwargs directly in a way that affects caller state if passed by ref,
            # though kwargs is local here.
            new_kwargs = dict(kwargs)
            if "where" in new_kwargs:
                del new_kwargs["where"]
            if "n_results" in new_kwargs:
                new_kwargs["n_results"] = new_kwargs["n_results"] * multiplier
            return self._col.query(*args, **new_kwargs)
        def __getattr__(self, name):
            return getattr(self._col, name)
            
    proxy = CollectionProxy(col)
    me._get_or_create_collection = lambda: proxy
    
    start = time.monotonic()
    res = me.retrieve_precedents(
        scenario_id=scenario_id, 
        authorized_sources=frozenset(auth_sources),
        include_simulated=False
    )
    return (time.monotonic() - start) * 1000, res

def benchmark_concurrent(func, concurrency, requests, *args):
    start_time = time.monotonic()
    latencies = []
    errors = 0
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(func, *args) for _ in range(requests)]
        for f in as_completed(futures):
            try:
                lat, _ = f.result()
                latencies.append(lat)
            except Exception:
                errors += 1
    
    if not latencies:
        return {"p50": 0, "p95": 0, "max": 0, "errors": errors}
        
    latencies.sort()
    return {
        "p50": round(latencies[int(len(latencies) * 0.5)], 2),
        "p95": round(latencies[int(len(latencies) * 0.95)], 2),
        "max": round(latencies[-1], 2),
        "errors": errors
    }

def verify_invariants(results, auth_sources):
    for r in results:
        if r["outcome_type"] != "observed":
            return False, f"Leaked outcome_type: {r['outcome_type']}"
        sources = set(r["source_ids"])
        if not sources:
            return False, "Leaked unknown provenance (no sources)"
        if not sources.issubset(set(auth_sources)):
            return False, f"Leaked unauthorized sources: {sources}"
    return True, "OK"

def main():
    print("Initializing E9 Filter Comparison Benchmark...")
    chroma_client = chromadb.PersistentClient(path="./chroma_benchmark_data")
    mock_llm = MockLLMProvider()
    memory_engine = MemoryEngine(chroma_client=chroma_client, llm_provider=mock_llm)
    
    # 1. Inject Top-K test data
    print("Injecting Top-K test data to measure recall push-out...")
    col = memory_engine._get_or_create_collection()
    test_scenario = "BENCH_TOPK"
    auth_sources = ["inventory", "orders"]
    
    # Insert 15 simulated/unauthorized records with high similarity to dummy vector
    # and 5 authorized 'observed' records.
    # The raw dummy vector is [0.1]*1024, so they will all be retrieved if they share the vector.
    topk_ids = []
    topk_embs = []
    topk_docs = []
    topk_metas = []
    
    # 15 Unauthorized or simulated (Noise)
    for i in range(15):
        topk_ids.append(f"PREC_NOISE_{i}")
        topk_embs.append([0.1]*1024)
        topk_docs.append("Noise")
        topk_metas.append({
            "scenario_id": f"PREC_NOISE_{i}",
            "persona": "analyst",
            "source_ids": "support_tickets", # unauthorized for auth_sources
            "confidence_state": "high",
            "outcome_type": "simulated" if i < 7 else "observed",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "human_validated": False
        })
        
    # 5 Authorized and observed (Valid)
    valid_expected_ids = []
    for i in range(5):
        vid = f"PREC_VALID_{i}"
        valid_expected_ids.append(vid)
        topk_ids.append(vid)
        topk_embs.append([0.1]*1024)
        topk_docs.append("Valid")
        topk_metas.append({
            "scenario_id": vid,
            "persona": "analyst",
            "source_ids": "inventory", 
            "confidence_state": "high",
            "outcome_type": "observed",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "human_validated": False
        })
        
    col.upsert(ids=topk_ids, embeddings=topk_embs, documents=topk_docs, metadatas=topk_metas)
    
    # Top-K test
    _, res_a = bench_pipeline_a(chroma_client, mock_llm, test_scenario, auth_sources)
    res_a_ids = {r["scenario_id"] for r in res_a}
    print(f"\nPipeline A (Current) retrieved {len(res_a_ids)} valid records.")
    
    for mult in [1, 2, 5, 10]:
        _, res_b = bench_pipeline_b(chroma_client, mock_llm, test_scenario, auth_sources, multiplier=mult)
        res_b_ids = {r["scenario_id"] for r in res_b}
        overlap = len(res_a_ids.intersection(res_b_ids))
        print(f"Pipeline B (Multiplier x{mult}) retrieved {len(res_b_ids)} valid records. Overlap with A: {overlap}/{len(res_a_ids)}")
        if res_b_ids == res_a_ids:
            print(f"  -> Multiplier x{mult} achieves 100% recall.")
            
    # Remove test data
    col.delete(ids=topk_ids)
    
    # 2. Benchmark Tiers
    tiers = [1, 2, 3, 4]
    
    results = []
    
    for tier in tiers:
        scenario_id = f"BENCH_T{tier}"
        print(f"\n{'='*50}\nRunning Tier {tier}\n{'='*50}")
        
        # Verify invariants using Pipeline B x5
        print("Verifying Security Invariants (Pipeline B x5)...")
        _, res_b_check = bench_pipeline_b(chroma_client, mock_llm, scenario_id, auth_sources, multiplier=5)
        ok, msg = verify_invariants(res_b_check, auth_sources)
        print(f"  Invariants passed: {ok} ({msg})")
        
        concurrencies = [1, 5, 10, 25]
        for c in concurrencies:
            reqs = c * 2
            print(f"\n  Concurrency: {c} (Requests: {reqs})")
            
            # Skip C>1 for Pipeline A to save time (we already know it's extremely slow).
            if c == 1:
                res_a = benchmark_concurrent(bench_pipeline_a, c, reqs, chroma_client, mock_llm, scenario_id, auth_sources)
                print(f"    [Pipeline A - Current]  p95: {res_a['p95']}ms")
            else:
                res_a = {"p95": -1, "max": -1} # Skipped
                print(f"    [Pipeline A - Current]  SKIPPED (Too slow)")
                
            res_b = benchmark_concurrent(bench_pipeline_b, c, reqs, chroma_client, mock_llm, scenario_id, auth_sources, 5) # using x5 mult
            print(f"    [Pipeline B - No Where] p95: {res_b['p95']}ms")
            
            results.append({
                "tier": tier,
                "concurrency": c,
                "pipeline_a": res_a,
                "pipeline_b": res_b
            })
            
    with open("benchmarks/results/e9_filter_comparison.json", "w") as f:
        json.dump(results, f, indent=2)
        
    print("\nBenchmark complete. Saved to benchmarks/results/e9_filter_comparison.json")

if __name__ == "__main__":
    main()
