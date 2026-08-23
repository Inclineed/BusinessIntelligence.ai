"""
scripts/rebuild_memory.py — ISSUE-002 Memory Reset and Precedent Rebuild.

Wipes ONLY the 'investigation_precedents' ChromaDB collection and runs
investigations for INC_001, INC_002, INC_003, INC_004 to cleanly rebuild
all precedents with complete provenance metadata.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
import psycopg2
import chromadb

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("rebuild_memory")

from config.loader import load_entitlements, load_kpi_contract, load_sources
from llm.provider import OllamaProvider
from pipeline.investigate import Dependencies, investigate
from engines.memory import MemoryEngine
from models import ConfidenceState, OutcomeType

CHROMA_HOST = "127.0.0.1"
CHROMA_PORT = 8000
DATABASE_URL = "postgresql://biai:biai@127.0.0.1:5432/biai"
CONFIG_DIR = PROJECT_ROOT / "config"


def main() -> None:
    print("=" * 60)
    print("ISSUE-002: Memory Reset and Clean Rebuild")
    print("=" * 60)

    # 1. Connect to ChromaDB
    chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    
    # Check baseline evidence collections (verify they exist and are not touched)
    evidence_counts = {}
    for col_name in ["evidence_INC_001", "evidence_INC_002", "evidence_INC_004"]:
        try:
            col = chroma_client.get_collection(col_name)
            evidence_counts[col_name] = col.count()
        except Exception:
            evidence_counts[col_name] = "not found"
    print(f"[1] Evidence collections baseline: {evidence_counts}")

    # Check precedent collection before wipe
    try:
        prec_col = chroma_client.get_collection("investigation_precedents")
        count_before = prec_col.count()
    except Exception:
        count_before = 0
    print(f"[1] 'investigation_precedents' count before wipe: {count_before}")

    # Safely delete and reinitialize 'investigation_precedents' ONLY
    try:
        chroma_client.delete_collection("investigation_precedents")
        print("[2] Deleted 'investigation_precedents' collection.")
    except Exception as e:
        print(f"[2] Collection delete notice: {e}")

    prec_col = chroma_client.get_or_create_collection(
        name="investigation_precedents",
        metadata={"hnsw:space": "cosine"},
    )
    count_after_init = prec_col.count()
    print(f"[3] Reinitialized 'investigation_precedents' count: {count_after_init}")
    assert count_after_init == 0, "Precedent collection should be empty after reset!"

    # Verify evidence collections were untouched
    for col_name, initial_count in evidence_counts.items():
        if isinstance(initial_count, int):
            current_count = chroma_client.get_collection(col_name).count()
            assert current_count == initial_count, f"Evidence collection {col_name} was modified!"
    print("[3] Confirmed all evidence collections are untouched and intact.")

    # 2. Connect to Postgres & Load Configs
    db_conn = psycopg2.connect(DATABASE_URL)
    kpi_contract = load_kpi_contract(CONFIG_DIR / "kpi_contracts.yaml")
    entitlements_config = load_entitlements(CONFIG_DIR / "entitlements.yaml")
    sources_config = load_sources(CONFIG_DIR / "sources.yaml")
    llm_provider = OllamaProvider()

    scenarios = ["INC_001", "INC_002", "INC_003", "INC_004"]
    results = {}

    print("\n[4] Running investigations through pipeline and rebuilding precedents...")
    for sc_id in scenarios:
        print(f"--- Running {sc_id} (persona=analyst) ---")
        deps = Dependencies(
            db_conn=db_conn,
            chroma_client=chroma_client,
            llm_provider=llm_provider,
            kpi_contract=kpi_contract,
            entitlements_config=entitlements_config,
            sources_config=sources_config,
            scenario_id=sc_id,
        )
        res = investigate(
            scenario_id=sc_id,
            persona_str="analyst",
            deps=deps,
        )
        results[sc_id] = res
        abstained = res.decision.abstained if res.decision else True
        winning = res.decision.winning_hypothesis_id if res.decision else None
        top_conf = res.scored[0].confidence_state.value if res.scored else "none"
        print(f"    Result for {sc_id}: abstained={abstained}, winning={winning}, top_confidence={top_conf}")

    db_conn.close()

    # 3. Verify rebuilt precedents in ChromaDB
    print("\n[5] Verifying rebuilt precedents in ChromaDB...")
    prec_col = chroma_client.get_collection("investigation_precedents")
    final_count = prec_col.count()
    print(f"    Total precedents in collection: {final_count}")

    # Fetch all items
    all_data = prec_col.get(include=["metadatas", "documents"])
    ids = all_data.get("ids", [])
    metadatas = all_data.get("metadatas", [])

    print(f"    Stored precedent IDs: {ids}")
    for doc_id, meta in zip(ids, metadatas):
        print(f"\n    Precedent ID: {doc_id}")
        for key in [
            "scenario_id",
            "confidence_state",
            "original_confidence_state",
            "outcome_type",
            "created_at",
            "evidence_ids",
            "winning_hypothesis",
            "recommendation",
        ]:
            val = meta.get(key)
            print(f"      - {key}: {val}")
            assert val is not None, f"Precedent {doc_id} missing metadata key {key}!"
            if key == "outcome_type":
                assert val == OutcomeType.OBSERVED.value, f"Precedent {doc_id} outcome_type is {val}, expected observed!"
            if key == "confidence_state":
                assert val in [s.value for s in ConfidenceState], f"Invalid confidence_state {val}!"

    # 4. Verify retrieval behavior
    print("\n[6] Verifying retrieval behavior via MemoryEngine...")
    engine = MemoryEngine(chroma_client=chroma_client, llm_provider=llm_provider)
    retrieved = engine.retrieve_precedents("INC_001", "payment checkout degradation")
    print(f"    Retrieved {len(retrieved)} precedent(s) for INC_001 query:")
    for p in retrieved:
        print(
            f"      * {p['scenario_id']}: conf={p['confidence_state']} "
            f"weight={p['retrieval_weight']} score={p['retrieval_score']} "
            f"outcome={p['outcome_type']}"
        )
        assert p["outcome_type"] == OutcomeType.OBSERVED.value
        assert p["confidence_state"] in [s.value for s in ConfidenceState]

    print("\n[7] Memory reset and clean rebuild completed successfully!")


if __name__ == "__main__":
    main()
