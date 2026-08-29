"""
etl/seed_scenario_evidence.py — Seed ChromaDB evidence collections for the
additional live scenarios (INC_002, INC_004).

Docs are tagged with sources in the analyst authorization scope
(orders / payment_gateway / inventory / marketing) so they survive the
entitlement filter and are usable by the Evidence Engine.
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import chromadb
from llm.provider import OllamaProvider


class _Embed:
    def __init__(self, provider, model="bge-m3"):
        self._p = provider; self._m = model
    def __call__(self, input):
        return self._p.embed(input, model=self._m)
    def name(self):
        return f"ollama-{self._m}"


SEED_DOCS = {
    "INC_002": [
        ("payment_gateway", "PAY_note_1", "Payment gateway failure rate roughly doubled during the mid-day window; a minority of checkout attempts returned intermittent timeouts."),
        ("marketing", "MKT_note_1", "A competitor launched a promotional price campaign during the same week; marketing impressions dipped, suggesting some demand was diverted externally."),
        ("orders", "ORD_note_1", "Conversion softened modestly across app sessions, with Android showing a slightly larger dip than iOS or desktop."),
        ("payment_gateway", "PAY_note_2", "Gateway latency rose moderately but remained far below the levels seen in a full payment outage."),
    ],
    "INC_004": [
        ("orders", "ORD_gap_1", "An upstream ETL pipeline delay created a multi-hour gap in order records between late morning and mid-afternoon; revenue rows for that window are missing rather than zero."),
        ("orders", "ORD_gap_2", "Order ingestion resumed normally after the pipeline backlog cleared; pre-gap and post-gap volumes are consistent with a normal day."),
        ("payment_gateway", "PAY_ok_1", "Payment gateway metrics were healthy throughout the day with no elevation in failures or latency, indicating the apparent revenue drop is a data artifact, not a checkout problem."),
    ],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chroma-host", default="localhost")
    ap.add_argument("--chroma-port", type=int, default=8000)
    ap.add_argument("--ollama-host", default="http://localhost:11434")
    args = ap.parse_args()

    provider = OllamaProvider(base_url=args.ollama_host)
    ef = _Embed(provider)
    client = chromadb.HttpClient(host=args.chroma_host, port=args.chroma_port)

    for sid, docs in SEED_DOCS.items():
        name = f"evidence_{sid}"
        col = client.get_or_create_collection(
            name=name,
            embedding_function=ef,
            metadata={
                "hnsw:space": "cosine",
                "hnsw:search_ef": 64,
                "hnsw:M": 32,
            },
        )
        ids = [f"{sid}_{d[1]}" for d in docs]
        documents = [d[2] for d in docs]
        metadatas = [{"source": d[0], "scenario_id": sid, "evidence_type": "unstructured"} for d in docs]
        col.upsert(ids=ids, documents=documents, metadatas=metadatas)
        print(f"  seeded {name}: {len(docs)} docs")

    print("Done.")


if __name__ == "__main__":
    main()
