"""
scripts/validate_held_out.py — Run held-out scenarios INC_005, INC_006, INC_007 through investigate()
and report actual vs expected outputs.
"""

from __future__ import annotations

import os
import sys
import json
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import psycopg2
import chromadb
from chromadb.config import Settings

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.loader import load_entitlements, load_kpi_contract, load_sources
from pipeline.investigate import Dependencies, investigate
from llm.provider import OllamaProvider
from evaluation.evaluator import Evaluator

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://biai:biai@localhost:5432/biai")
CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
CONFIG_DIR = ROOT / "config"

def main():
    print("=" * 60)
    print("Validating Held-Out Scenarios (INC_005, INC_006, INC_007)")
    print("=" * 60)

    db_conn = psycopg2.connect(DATABASE_URL)
    chroma_client = chromadb.HttpClient(
        host=CHROMA_HOST,
        port=CHROMA_PORT,
        settings=Settings(anonymized_telemetry=False),
    )

    kpi_contract = load_kpi_contract(CONFIG_DIR / "kpi_contracts.yaml")
    entitlements_config = load_entitlements(CONFIG_DIR / "entitlements.yaml")
    sources_config = load_sources(CONFIG_DIR / "sources.yaml")
    llm_provider = OllamaProvider()
    evaluator = Evaluator()

    scenarios = ["INC_005", "INC_006", "INC_007", "INC_008"]

    for sc_id in scenarios:
        print(f"\n" + "=" * 50)
        print(f"Running pipeline for held-out scenario: {sc_id}")
        print("=" * 50)
        deps = Dependencies(
            db_conn=db_conn,
            chroma_client=chroma_client,
            kpi_contract=kpi_contract,
            entitlements_config=entitlements_config,
            sources_config=sources_config,
            llm_provider=llm_provider,
        )

        try:
            result = investigate(
                scenario_id=sc_id,
                persona_str="analyst",
                deps=deps,
            )

            actual_anomaly = any(s.is_anomaly for s in result.signals)
            actual_abstained = result.decision.abstained if result.decision else True
            winning_h = result.decision.winning_hypothesis_id if result.decision else None
            rec_action = result.decision.recommended_action if result.decision else None
            top_conf = (
                result.scored[0].confidence_state.value
                if result.scored
                else ("abstain" if actual_abstained else "none")
            )

            print(f"ACTUAL RESULTS for {sc_id}:")
            print(f"  - anomaly_detected: {actual_anomaly}")
            print(f"  - signals count: {len(result.signals)}")
            print(f"  - evidence count: {len(result.evidence)}")
            print(f"  - hypotheses count: {len(result.hypotheses)}")
            print(f"  - scored count: {len(result.scored)}")
            print(f"  - abstained: {actual_abstained}")
            print(f"  - confidence state: {top_conf}")
            print(f"  - winning hypothesis: {winning_h}")
            print(f"  - recommended action: {rec_action}")

            eval_res = evaluator.evaluate(result)
            print(f"\nEVALUATION SCORECARD for {sc_id}:")
            print(eval_res.scorecard_text)
            print(f"Overall Pass: {eval_res.overall_pass}")

        except Exception as e:
            print(f"ERROR executing {sc_id}: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
