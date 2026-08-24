"""
benchmarks/run_scale.py — Run scalability benchmarks on BusinessIntelligence.ai.

Usage:
    python benchmarks/run_scale.py --tier 1 --concurrency 1
    python benchmarks/run_scale.py --tier 1 --concurrency 10
"""
import argparse
import sys
import time
import json
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg2
import chromadb

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.loader import load_kpi_contract, load_entitlements, load_sources
from pipeline.investigate import Dependencies, investigate
from llm.provider import OllamaProvider

def run_investigation(scenario_id: str, persona: str, deps: Dependencies):
    start_time = time.monotonic()
    success = False
    error = None
    telemetry = {}
    
    try:
        result = investigate(scenario_id, persona, deps)
        success = True
        telemetry = result.telemetry.model_dump() if hasattr(result.telemetry, "model_dump") else {}
        
        # Security Verification Check (Phase 5)
        auth_sources = deps.entitlements_config.get(persona, {}).get("authorized_sources", [])
        for evidence in result.evidence:
            if evidence.source_id not in auth_sources:
                raise ValueError(f"Security Invariant Failure: Unauthorized evidence from source {evidence.source_id} found in result for persona {persona}.")
                
    except Exception as e:
        error = str(e)
        
    end_time = time.monotonic()
    
    return {
        "success": success,
        "latency_ms": (end_time - start_time) * 1000,
        "error": error,
        "telemetry": telemetry
    }

def main():
    parser = argparse.ArgumentParser(description="Run scale benchmarks")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3, 4], required=True, help="Scale tier (1-4)")
    parser.add_argument("--concurrency", type=int, default=1, help="Number of concurrent requests")
    parser.add_argument("--requests", type=int, default=None, help="Total number of requests to run (default: 10 * concurrency)")
    parser.add_argument("--db-url", type=str, default="postgresql://biai:biai@localhost:5432/biai_benchmark", help="Postgres URL")
    parser.add_argument("--chroma-path", type=str, default="./chroma_benchmark_data", help="Chroma DB path")
    parser.add_argument("--provider", type=str, default="ollama", choices=["ollama", "groq"], help="LLM Provider (ollama or groq)")
    parser.add_argument("--groq-model", type=str, default=None, help="Groq model override")
    
    args = parser.parse_args()
    
    total_requests = args.requests or (args.concurrency * 10)
    
    print(f"=== Starting Benchmark ===")
    print(f"Tier:        {args.tier}")
    print(f"Provider:    {args.provider}")
    print(f"Concurrency: {args.concurrency}")
    print(f"Requests:    {total_requests}")
    
    # Load configs
    kpi_contract = load_kpi_contract(Path("config/kpi_contracts.yaml"))
    entitlements_config = load_entitlements(Path("config/entitlements.yaml"))
    sources_config = load_sources(Path("config/sources.yaml"))
    
    scenario_id = f"BENCH_T{args.tier}"
    
    # Pre-flight check
    try:
        conn = psycopg2.connect(args.db_url)
    except Exception as e:
        print(f"Failed to connect to DB: {e}")
        sys.exit(1)
        
    chroma_client = chromadb.PersistentClient(path=args.chroma_path)
    from llm.provider import get_llm_provider
    if args.provider == "groq":
        from llm.provider import GroqProvider
        llm_provider = GroqProvider(model=args.groq_model)
    else:
        llm_provider = OllamaProvider(base_url=args.ollama_url)
    
    deps = Dependencies(
        db_conn=conn,
        chroma_client=chroma_client,
        llm_provider=llm_provider,
        kpi_contract=kpi_contract,
        entitlements_config=entitlements_config,
        sources_config=sources_config,
        scenario_id=scenario_id,
        window_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        window_end=datetime(2024, 1, 2, tzinfo=timezone.utc),
    )
    
    # Warmup
    print("Running warmup request...")
    warmup = run_investigation(scenario_id, "analyst", deps)
    if not warmup["success"]:
        print(f"Warmup failed! Error: {warmup['error']}")
        sys.exit(1)
        
    print(f"Warmup took {warmup['latency_ms']:.2f} ms")
    
    print("Starting concurrent benchmark...")
    
    results = []
    start_time = time.monotonic()
    
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [
            executor.submit(run_investigation, scenario_id, "analyst", deps)
            for _ in range(total_requests)
        ]
        
        for i, future in enumerate(as_completed(futures), 1):
            res = future.result()
            results.append(res)
            print(f"  [{i}/{total_requests}] Request complete. Latency: {res['latency_ms']:.2f} ms")
            
    end_time = time.monotonic()
    
    # Analysis
    successes = [r for r in results if r["success"]]
    errors = [r for r in results if not r["success"]]
    
    latencies = [r["latency_ms"] for r in successes]
    
    e1_latencies = [r["telemetry"]["engine_timings_ms"].get("kpi_store", 0) for r in successes if "engine_timings_ms" in r["telemetry"]]
    e4_latencies = [r["telemetry"]["engine_timings_ms"].get("evidence", 0) for r in successes if "engine_timings_ms" in r["telemetry"]]
    e9_latencies = [r["telemetry"]["engine_timings_ms"].get("memory", 0) for r in successes if "engine_timings_ms" in r["telemetry"]]
    
    print("\n=== Benchmark Results ===")
    print(f"Total Time:      {(end_time - start_time):.2f} s")
    print(f"Total Requests:  {total_requests}")
    print(f"Success Rate:    {len(successes) / total_requests * 100:.1f}% ({len(successes)}/{total_requests})")
    
    if successes:
        print(f"End-to-End Latency:")
        print(f"  Avg: {sum(latencies)/len(latencies):.2f} ms")
        print(f"  Min: {min(latencies):.2f} ms")
        print(f"  Max: {max(latencies):.2f} ms")
        
        if e1_latencies:
            print(f"E1 (KPI Store) Latency Avg: {sum(e1_latencies)/len(e1_latencies):.2f} ms")
        if e4_latencies:
            print(f"E4 (Evidence) Latency Avg:  {sum(e4_latencies)/len(e4_latencies):.2f} ms")
        if e9_latencies:
            print(f"E9 (Memory) Latency Avg:    {sum(e9_latencies)/len(e9_latencies):.2f} ms")
            
    if errors:
        print("\nErrors encountered:")
        for err in errors:
            print(f"  - {err['error']}")
            
    # Save report
    report = {
        "tier": args.tier,
        "concurrency": args.concurrency,
        "total_requests": total_requests,
        "success_rate": len(successes) / total_requests,
        "avg_latency_ms": sum(latencies)/len(latencies) if latencies else None,
        "avg_e1_ms": sum(e1_latencies)/len(e1_latencies) if e1_latencies else None,
        "avg_e4_ms": sum(e4_latencies)/len(e4_latencies) if e4_latencies else None,
        "avg_e9_ms": sum(e9_latencies)/len(e9_latencies) if e9_latencies else None,
    }
    
    report_file = Path(f"benchmark_report_T{args.tier}_C{args.concurrency}.json")
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nSaved report to {report_file}")

if __name__ == "__main__":
    main()
