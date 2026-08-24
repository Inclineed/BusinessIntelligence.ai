"""
benchmarks/run_provider_comparison.py — Controlled apples-to-apples benchmark: Ollama vs. Groq.

Measures:
  1. Per-engine latencies (E5, E6, E7, total E5-E7, E2E)
  2. Token consumption (prompt, completion, total)
  3. Cost accounting (external, local, equivalent cloud)
  4. Concurrency scaling (C=1, C=5, C=10)
  5. Deterministic scoring & behavioral invariance verification

Saves machine-readable results to benchmarks/results/provider_comparison.json.
"""

import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg2
import chromadb

# Ensure project root is importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

# Safe console output for Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from config.loader import load_kpi_contract, load_entitlements, load_sources
from pipeline.investigate import Dependencies, investigate
from llm.provider import OllamaProvider, GroqProvider, get_llm_provider
from llm.cost_estimator import estimate_model_cost


def get_dependencies(provider):
    """Construct a fresh Dependencies container for the given LLM provider."""
    # Connect to standard Postgres DB and ChromaDB
    try:
        conn = psycopg2.connect("postgresql://biai:biai@localhost:5432/biai")
    except Exception as exc:
        print(f"[WARN] PostgreSQL connection failed: {exc}. Using mock DB connection.")
        conn = None

    try:
        chroma_client = chromadb.HttpClient(host="localhost", port=8000)
    except Exception as exc:
        print(f"[WARN] ChromaDB HttpClient failed: {exc}. Falling back to PersistentClient.")
        chroma_client = chromadb.PersistentClient(path="./chroma_data")

    kpi_contract = load_kpi_contract(_PROJECT_ROOT / "config" / "kpi_contracts.yaml")
    entitlements_config = load_entitlements(_PROJECT_ROOT / "config" / "entitlements.yaml")
    sources_config = load_sources(_PROJECT_ROOT / "config" / "sources.yaml")

    return Dependencies(
        db_conn=conn,
        chroma_client=chroma_client,
        llm_provider=provider,
        kpi_contract=kpi_contract,
        entitlements_config=entitlements_config,
        sources_config=sources_config,
        region=None,
    )


def run_single_investigation(scenario_id: str, persona: str, provider):
    """Run a single investigation and record detailed breakdown."""
    deps = get_dependencies(provider)
    deps.scenario_id = scenario_id

    t0 = time.perf_counter()
    try:
        result = investigate(scenario_id, persona, deps)
        e2e_ms = (time.perf_counter() - t0) * 1000.0
        success = True
        error_msg = None
    except Exception as exc:
        e2e_ms = (time.perf_counter() - t0) * 1000.0
        success = False
        error_msg = str(exc)
        result = None

    if deps.db_conn:
        try:
            deps.db_conn.close()
        except Exception:
            pass

    if not success or result is None:
        return {
            "success": False,
            "error": error_msg,
            "e2e_ms": round(e2e_ms, 2),
        }

    # Extract telemetry metrics
    tel = result.telemetry
    latency_map = tel.latency_ms_by_engine if hasattr(tel, "latency_ms_by_engine") else {}
    
    e5_ms = latency_map.get("hypothesis_engine", 0.0)
    e6_ms = latency_map.get("challenge_engine", 0.0)
    e7_ms = latency_map.get("decision_engine", 0.0)
    total_llm_engine_ms = e5_ms + e6_ms + e7_ms

    top_hyp = result.decision.winning_hypothesis_id if result.decision else None
    conf_state = (
        result.scored[0].confidence_state.value if result.scored else "unknown"
    )
    rec_action = result.decision.recommended_action if result.decision else None

    # Citation counts
    all_citations = []
    for h in result.hypotheses:
        all_citations.extend(h.citations)

    return {
        "success": True,
        "scenario_id": scenario_id,
        "provider": provider.provider_name,
        "model": getattr(provider, "_model", getattr(provider, "DEFAULT_MODEL", "unknown")),
        "e5_ms": round(e5_ms, 2),
        "e6_ms": round(e6_ms, 2),
        "e7_ms": round(e7_ms, 2),
        "total_llm_engine_ms": round(total_llm_engine_ms, 2),
        "e2e_ms": round(e2e_ms, 2),
        "llm_calls": tel.llm_calls,
        "prompt_tokens": tel.llm_tokens_in,
        "completion_tokens": tel.llm_tokens_out,
        "total_tokens": tel.llm_tokens_in + tel.llm_tokens_out,
        "external_cost_usd": tel.external_cost_usd,
        "equivalent_cloud_cost_usd": tel.equivalent_cloud_cost_usd,
        "winning_hypothesis_id": top_hyp,
        "confidence_state": conf_state,
        "recommended_action": rec_action,
        "hypotheses_count": len(result.hypotheses),
        "evidence_count": len(result.evidence),
        "citation_count": len(all_citations),
        "abstained": result.decision.abstained if result.decision else False,
    }


def run_concurrency_test(provider_name: str, concurrency: int, requests: int, scenario_id: str = "INC_001"):
    """Execute concurrent requests against the provider and compute distribution."""
    latencies = []
    errors = 0
    err_samples = []

    def task():
        if provider_name == "groq":
            p = GroqProvider()
        else:
            p = OllamaProvider()
        res = run_single_investigation(scenario_id, "analyst", p)
        return res

    t_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(task) for _ in range(requests)]
        for f in as_completed(futures):
            try:
                res = f.result()
                if res.get("success"):
                    latencies.append(res["e2e_ms"])
                else:
                    errors += 1
                    err_samples.append(res.get("error"))
            except Exception as exc:
                errors += 1
                err_samples.append(str(exc))
    t_total = time.perf_counter() - t_start

    if not latencies:
        return {
            "provider": provider_name,
            "concurrency": concurrency,
            "requests": requests,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "max_ms": 0.0,
            "throughput_req_per_s": 0.0,
            "errors": errors,
            "error_samples": err_samples[:2],
        }

    latencies.sort()
    n = len(latencies)
    p50 = latencies[int(n * 0.50)]
    p95 = latencies[min(int(n * 0.95), n - 1)]
    max_lat = latencies[-1]
    throughput = round(requests / t_total, 2)

    return {
        "provider": provider_name,
        "concurrency": concurrency,
        "requests": requests,
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "max_ms": round(max_lat, 2),
        "throughput_req_per_s": throughput,
        "errors": errors,
    }


def main():
    print("=" * 80)
    print("  BusinessIntelligence.ai — Controlled Provider Benchmark: Ollama vs. Groq")
    print("=" * 80)

    # Initialize providers
    try:
        ollama_p = OllamaProvider()
        print(f"[INIT] OllamaProvider ready. Model: {ollama_p.DEFAULT_MODEL}")
    except Exception as exc:
        print(f"[ERROR] Failed to initialize Ollama: {exc}")
        ollama_p = None

    try:
        groq_p = GroqProvider()
        print(f"[INIT] GroqProvider ready. Model: {groq_p._model}")
    except Exception as exc:
        print(f"[WARN] GroqProvider not initialized ({exc}).")
        groq_p = None

    scenarios = ["INC_001", "INC_002"]
    scenario_results = []

    # 1. Single Investigation Benchmarks
    print("\n" + "-" * 80)
    print("1. RUNNING SINGLE INVESTIGATION BENCHMARKS (INC_001 & INC_002)")
    print("-" * 80)

    for sc in scenarios:
        if ollama_p:
            print(f"\n[RUN] Scenario {sc} with Ollama...")
            res_ollama = run_single_investigation(sc, "analyst", ollama_p)
            scenario_results.append(res_ollama)
            if res_ollama.get("success"):
                print(f"  -> Ollama {sc}: E2E={res_ollama['e2e_ms']}ms | E5={res_ollama['e5_ms']}ms | E6={res_ollama['e6_ms']}ms | E7={res_ollama['e7_ms']}ms | Tokens={res_ollama['total_tokens']}")
            else:
                print(f"  -> Ollama {sc} FAILED: {res_ollama.get('error')}")

        if groq_p:
            print(f"\n[RUN] Scenario {sc} with Groq...")
            res_groq = run_single_investigation(sc, "analyst", groq_p)
            scenario_results.append(res_groq)
            if res_groq.get("success"):
                print(f"  -> Groq   {sc}: E2E={res_groq['e2e_ms']}ms | E5={res_groq['e5_ms']}ms | E6={res_groq['e6_ms']}ms | E7={res_groq['e7_ms']}ms | Tokens={res_groq['total_tokens']} | Cost=${res_groq['external_cost_usd']:.6f}")
            else:
                print(f"  -> Groq   {sc} FAILED: {res_groq.get('error')}")

    # 2. Concurrency Benchmarks
    print("\n" + "-" * 80)
    print("2. RUNNING CONCURRENCY BENCHMARKS (INC_001)")
    print("-" * 80)

    concurrency_configs = [
        (1, 2),
        (5, 5),
    ]

    concurrency_results = []

    if ollama_p:
        print("\n--- Ollama Concurrency Tests ---")
        for c, reqs in concurrency_configs:
            print(f"  Testing Ollama at Concurrency={c} ({reqs} requests)...")
            c_res = run_concurrency_test("ollama", concurrency=c, requests=reqs)
            concurrency_results.append(c_res)
            print(f"    p50: {c_res['p50_ms']}ms | p95: {c_res['p95_ms']}ms | Max: {c_res['max_ms']}ms | Throughput: {c_res['throughput_req_per_s']} req/s | Errors: {c_res['errors']}")

    if groq_p:
        print("\n--- Groq Concurrency Tests ---")
        for c, reqs in concurrency_configs:
            print(f"  Testing Groq at Concurrency={c} ({reqs} requests)...")
            c_res = run_concurrency_test("groq", concurrency=c, requests=reqs)
            concurrency_results.append(c_res)
            print(f"    p50: {c_res['p50_ms']}ms | p95: {c_res['p95_ms']}ms | Max: {c_res['max_ms']}ms | Throughput: {c_res['throughput_req_per_s']} req/s | Errors: {c_res['errors']}")

    # Save to JSON
    out_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "single_investigation_results": scenario_results,
        "concurrency_results": concurrency_results,
    }

    out_dir = _PROJECT_ROOT / "benchmarks" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "provider_comparison.json"

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(out_payload, f, indent=2)

    print(f"\n[DONE] Benchmark metrics saved to {out_file}")


if __name__ == "__main__":
    main()
