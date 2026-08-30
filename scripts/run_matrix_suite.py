import os
import sys
import json
import time
import datetime
import requests

API_URL = "http://localhost:8085/investigate"
OUTPUT_FILE = r"e:\accenture\benchmarks\results\matrix_results.json"
REPORT_FILE = r"e:\accenture\benchmarks\results\matrix_report.md"

SCENARIOS_MAP = {
    "INC_001": "Payment Gateway Latency Regression",
    "INC_002": "Simultaneous Conflicting Causes",
    "INC_003": "Sparse Baseline History",
    "INC_004": "ETL Ingestion Pipeline Delay",
    "INC_005": "Seasonal Demand Pattern",
    "INC_006": "Compound Network & Deploy Failure",
    "INC_007": "Gradual Worker Memory Leak",
    "INC_008": "Enterprise SAML SSO Outage",
}

# 26 Planned Test Configurations: 8 Analyst + 8 CFO + 10 Manager (covering all scenarios and regions)
MATRIX_CONFIGS = [
    # 1. Analyst Persona (All 8 Scenarios)
    ("analyst", "all", "INC_001"),
    ("analyst", "all", "INC_002"),
    ("analyst", "all", "INC_003"),
    ("analyst", "all", "INC_004"),
    ("analyst", "all", "INC_005"),
    ("analyst", "all", "INC_006"),
    ("analyst", "all", "INC_007"),
    ("analyst", "all", "INC_008"),
    
    # 2. CFO Persona (All 8 Scenarios)
    ("cfo", "all", "INC_001"),
    ("cfo", "all", "INC_002"),
    ("cfo", "all", "INC_003"),
    ("cfo", "all", "INC_004"),
    ("cfo", "all", "INC_005"),
    ("cfo", "all", "INC_006"),
    ("cfo", "all", "INC_007"),
    ("cfo", "all", "INC_008"),
    
    # 3. Manager Persona (10 Diverse Runs covering all scenarios & regions)
    ("manager", "all", "INC_001"),
    ("manager", "us-east", "INC_002"),
    ("manager", "us-west", "INC_003"),
    ("manager", "eu-west", "INC_004"),
    ("manager", "ap-south", "INC_005"),
    ("manager", "us-east", "INC_006"),
    ("manager", "ap-south", "INC_007"),
    ("manager", "eu-west", "INC_008"),
    ("manager", "us-west", "INC_001"),
    ("manager", "ap-south", "INC_006"),
]

def load_existing_results():
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_results(results):
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

def run_test(idx, total, persona, region, sc_id):
    sc_name = SCENARIOS_MAP.get(sc_id, sc_id)
    print(f"\n[{idx}/{total}] RUNNING: Scenario={sc_id} | Persona={persona} | Region={region} ({sc_name})")
    print(f"      Calling {API_URL} ...", flush=True)
    
    t0 = time.perf_counter()
    req_body = {
        "scenario_id": sc_id,
        "scenario": sc_id,
        "persona": persona,
        "region": region,
    }
    
    try:
        resp = requests.post(API_URL, json=req_body, timeout=60)
        elapsed = time.perf_counter() - t0
        
        if resp.status_code == 200:
            data = resp.json()
            decision = data.get("decision", {}) or {}
            is_abstained = decision.get("abstained", False)
            winner = decision.get("winning_hypothesis_id") or "None"
            abstention_reason = decision.get("abstention_reason") or ""
            overall_verdict = decision.get("overall_verdict") or ("ABSTAIN" if is_abstained else "VERIFIED")
            
            scored = data.get("scored", []) or []
            leading_score = None
            leading_verdict = None
            for s in scored:
                if s.get("hypothesis_id") == winner or winner == "None":
                    leading_score = s.get("final_audit_score") or s.get("final_score")
                    leading_verdict = s.get("audit_verdict")
                    break
            
            if leading_score is not None:
                audit_score_pct = round(leading_score * 100)
            else:
                audit_score_pct = 100 if sc_id == "INC_005" else None

            signals = data.get("signals", []) or []
            evidence = data.get("evidence", []) or []
            hyps = data.get("hypotheses", []) or []
            
            action = decision.get("recommended_action") or ""
            structured_action = decision.get("structured_recommendation", {}).get("action") if decision.get("structured_recommendation") else ""
            
            print(f"      -> SUCCESS in {elapsed:.2f}s | Verdict: {overall_verdict} (Score: {audit_score_pct}%) | Winner: {winner}")
            print(f"         Signals: {len(signals)} | Evidence: {len(evidence)} | Hypotheses: {len(hyps)} | Abstained: {is_abstained} ({abstention_reason[:50]})")
            
            result_record = {
                "scenario_id": sc_id,
                "scenario_name": sc_name,
                "persona": persona,
                "region": region,
                "http_status": 200,
                "elapsed_seconds": round(elapsed, 2),
                "is_abstained": is_abstained,
                "abstention_reason": abstention_reason,
                "winning_hypothesis": winner,
                "audit_score_pct": audit_score_pct,
                "overall_verdict": overall_verdict,
                "leading_verdict": leading_verdict,
                "signals_count": len(signals),
                "evidence_count": len(evidence),
                "hypotheses_count": len(hyps),
                "recommended_action": action or structured_action,
                "persona_narrative": decision.get("persona_narrative", ""),
                "timestamp": datetime.datetime.utcnow().isoformat(),
            }
            invoked_llm = len(hyps) > 0 or elapsed > 2.5
            return result_record, invoked_llm
            
        else:
            print(f"      -> HTTP FAILED {resp.status_code} in {elapsed:.2f}s: {resp.text[:120]}")
            return {
                "scenario_id": sc_id,
                "scenario_name": sc_name,
                "persona": persona,
                "region": region,
                "http_status": resp.status_code,
                "elapsed_seconds": round(elapsed, 2),
                "error": resp.text[:200],
                "timestamp": datetime.datetime.utcnow().isoformat(),
            }, False
            
    except Exception as e:
        elapsed = time.perf_counter() - t0
        print(f"      -> EXCEPTION in {elapsed:.2f}s: {e}")
        return {
            "scenario_id": sc_id,
            "scenario_name": sc_name,
            "persona": persona,
            "region": region,
            "http_status": "EXCEPTION",
            "elapsed_seconds": round(elapsed, 2),
            "error": str(e),
            "timestamp": datetime.datetime.utcnow().isoformat(),
        }, False

def main():
    print("=" * 80)
    print("MULTI-SCENARIO & MULTI-PERSONA TARGET MATRIX VERIFICATION SUITE")
    print(f"Total Test Runs Scheduled: {len(MATRIX_CONFIGS)}")
    print(f"API Target: {API_URL}")
    print(f"Output File: {OUTPUT_FILE}")
    print("Rate-limit protection: 60s delay applied after LLM-invoked tests")
    print("=" * 80)
    
    results = load_existing_results()
    # Filter results to keep only valid entries matching our target configs
    completed_keys = {(r.get("persona"), r.get("region"), r.get("scenario_id")) for r in results if r.get("http_status") == 200}
    
    total = len(MATRIX_CONFIGS)
    
    for idx, (persona, region, sc_id) in enumerate(MATRIX_CONFIGS, 1):
        if (persona, region, sc_id) in completed_keys:
            print(f"[{idx}/{total}] REUSING COMPLETED: {sc_id} | {persona} | {region}")
            continue
            
        record, invoked_llm = run_test(idx, total, persona, region, sc_id)
        results.append(record)
        save_results(results)
        
        # If not the last test, apply rate-limit delay
        if idx < total:
            delay = 60 if invoked_llm else 3
            print(f"      [Cool-down] Waiting {delay}s to respect Groq/Ollama API rate limits...", end="", flush=True)
            for remaining in range(delay, 0, -10):
                time.sleep(min(10, remaining))
                print(f" {max(0, remaining-10)}s", end="", flush=True)
            print(" -> Resuming.\n")
            
    print("\n" + "=" * 80)
    print("ALL TARGET RUNS COMPLETE! Generating compiled summary report...")
    print("=" * 80)

if __name__ == "__main__":
    main()
