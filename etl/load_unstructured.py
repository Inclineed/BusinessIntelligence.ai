"""
etl/load_unstructured.py â€” Embed and load unstructured evidence into ChromaDB.

Documents: support tickets (support_tickets.csv), deployment events
(deployment_log.csv), and release notes (data/release_notes/*.txt).

Embedding model: bge-m3 (via Ollama, through OllamaProvider).

Usage:
    python -m etl.load_unstructured \\
        --scenario-id INC_001 \\
        --chroma-host localhost \\
        --chroma-port 8000 \\
        --ollama-host http://localhost:11434

Requirements: 12.1
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path
from typing import Any

import chromadb
from chromadb import Collection

# Make the project root importable when this module is run directly.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from llm.provider import OllamaProvider  # noqa: E402


# ---------------------------------------------------------------------------
# ChromaDB custom embedding function
# ---------------------------------------------------------------------------

class OllamaEmbeddingFunction:
    """
    ChromaDB-compatible embedding function backed by OllamaProvider.embed().

    ChromaDB's EmbeddingFunction interface requires a single __call__ method
    that accepts a list[str] and returns list[list[float]].
    """

    def __init__(self, provider: OllamaProvider, model: str = "bge-m3") -> None:
        self._provider = provider
        self._model = model

    def __call__(self, input: list[str]) -> list[list[float]]:  # noqa: A002
        """Embed a batch of texts and return the corresponding float vectors."""
        return self._provider.embed(input, model=self._model)

    def name(self) -> str:
        """Required by newer ChromaDB versions."""
        return f"ollama-{self._model}"


# ---------------------------------------------------------------------------
# Helper: get-or-create a named collection with our embedding function
# ---------------------------------------------------------------------------

def _get_collection(
    chroma_client: chromadb.HttpClient,
    scenario_id: str,
    embedding_fn: OllamaEmbeddingFunction,
) -> Collection:
    collection_name = f"evidence_{scenario_id}"
    return chroma_client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding_fn,
        metadata={
            "hnsw:space": "cosine",
            "hnsw:search_ef": 64,
            "hnsw:M": 32,
        },
    )


# ---------------------------------------------------------------------------
# Loader 1 â€” Support tickets
# ---------------------------------------------------------------------------

def load_support_tickets(
    chroma_client: chromadb.HttpClient,
    scenario_id: str,
    tickets_csv_path: str | os.PathLike,
    embedding_fn: OllamaEmbeddingFunction,
) -> int:
    """
    Read support_tickets.csv, embed each ticket message, and upsert into
    collection "evidence_{scenario_id}".

    CSV expected columns (from schema.sql):
        ticket_id, scenario_id, ts, store_id, device, message, category

    Metadata attached per document:
        source, scenario_id, ts, device, category, evidence_type

    Returns the count of documents loaded.
    """
    documents: list[str] = []
    ids: list[str] = []
    metadatas: list[dict[str, Any]] = []

    with open(tickets_csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ticket_id = row["ticket_id"]
            message = row["message"].strip()
            if not message:
                continue  # skip blank messages

            documents.append(message)
            ids.append(f"ticket_{ticket_id}")
            metadatas.append(
                {
                    "source": "support_tickets",
                    "scenario_id": row.get("scenario_id", scenario_id),
                    "ts": row.get("ts", ""),
                    "device": row.get("device", ""),
                    "category": row.get("category", ""),
                    "evidence_type": "unstructured",
                }
            )

    if not documents:
        print("[load_support_tickets] No documents found â€” skipping upsert.")
        return 0

    collection = _get_collection(chroma_client, scenario_id, embedding_fn)
    _batch_upsert(collection, ids, documents, metadatas)

    print(f"[load_support_tickets] Loaded {len(documents)} document(s) "
          f"from {tickets_csv_path}.")
    return len(documents)


# ---------------------------------------------------------------------------
# Loader 2 â€” Deployment log
# ---------------------------------------------------------------------------

def load_deployment_log(
    chroma_client: chromadb.HttpClient,
    scenario_id: str,
    deploy_csv_path: str | os.PathLike,
    embedding_fn: OllamaEmbeddingFunction,
) -> int:
    """
    Read deployment_log.csv, embed each row's notes (or a combined description),
    and upsert into collection "evidence_{scenario_id}".

    CSV expected columns (from schema.sql):
        deploy_id, scenario_id, ts, version, component, notes

    Metadata attached per document:
        source, scenario_id, version, component, evidence_type

    The document text is: "Version {version} deployed to {component}: {notes}"

    Returns the count of documents loaded.
    """
    documents: list[str] = []
    ids: list[str] = []
    metadatas: list[dict[str, Any]] = []

    with open(deploy_csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            deploy_id = row["deploy_id"]
            version = row.get("version", "")
            component = row.get("component", "")
            notes = row.get("notes", "").strip()

            # Build a descriptive document text so embeddings are meaningful.
            text = f"Version {version} deployed to {component}."
            if notes:
                text = f"{text} {notes}"

            documents.append(text)
            ids.append(f"deploy_{deploy_id}")
            metadatas.append(
                {
                    "source": "deployment_log",
                    "scenario_id": row.get("scenario_id", scenario_id),
                    "version": version,
                    "component": component,
                    "evidence_type": "unstructured",
                }
            )

    if not documents:
        print("[load_deployment_log] No documents found â€” skipping upsert.")
        return 0

    collection = _get_collection(chroma_client, scenario_id, embedding_fn)
    _batch_upsert(collection, ids, documents, metadatas)

    print(f"[load_deployment_log] Loaded {len(documents)} document(s) "
          f"from {deploy_csv_path}.")
    return len(documents)


# ---------------------------------------------------------------------------
# Loader 3 â€” Release notes
# ---------------------------------------------------------------------------

def load_release_notes(
    chroma_client: chromadb.HttpClient,
    scenario_id: str,
    release_notes_dir: str | os.PathLike,
    embedding_fn: OllamaEmbeddingFunction,
) -> int:
    """
    Read every .txt file from release_notes_dir, embed the full file content,
    and upsert into collection "evidence_{scenario_id}".

    The filename stem (without .txt) is used as the version identifier.

    Metadata attached per document:
        source, scenario_id, version, evidence_type

    Returns the count of documents loaded.
    """
    notes_dir = Path(release_notes_dir)
    txt_files = sorted(notes_dir.glob("*.txt"))

    if not txt_files:
        print(f"[load_release_notes] No .txt files found in {notes_dir}.")
        return 0

    documents: list[str] = []
    ids: list[str] = []
    metadatas: list[dict[str, Any]] = []

    for txt_path in txt_files:
        version = txt_path.stem  # e.g. "v4.3-hotfix"
        content = txt_path.read_text(encoding="utf-8").strip()
        if not content:
            continue

        documents.append(content)
        ids.append(f"release_note_{version}")
        metadatas.append(
            {
                "source": "release_notes",
                "scenario_id": scenario_id,
                "version": version,
                "evidence_type": "unstructured",
            }
        )

    if not documents:
        print("[load_release_notes] All files were empty â€” skipping upsert.")
        return 0

    collection = _get_collection(chroma_client, scenario_id, embedding_fn)
    _batch_upsert(collection, ids, documents, metadatas)

    print(f"[load_release_notes] Loaded {len(documents)} document(s) "
          f"from {notes_dir}.")
    return len(documents)


# ---------------------------------------------------------------------------
# Internal helper â€” chunked upsert to avoid overloading the embed endpoint
# ---------------------------------------------------------------------------

_BATCH_SIZE = 32  # embed and upsert in batches to stay within memory/timeout


def _batch_upsert(
    collection: Collection,
    ids: list[str],
    documents: list[str],
    metadatas: list[dict[str, Any]],
) -> None:
    """Upsert documents in batches of _BATCH_SIZE."""
    for start in range(0, len(documents), _BATCH_SIZE):
        end = start + _BATCH_SIZE
        collection.upsert(
            ids=ids[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
        )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Embed and load unstructured evidence into ChromaDB."
    )
    parser.add_argument(
        "--scenario-id",
        default="INC_001",
        help="Scenario identifier (default: INC_001)",
    )
    parser.add_argument(
        "--chroma-host",
        default="localhost",
        help="ChromaDB host (default: localhost)",
    )
    parser.add_argument(
        "--chroma-port",
        type=int,
        default=8000,
        help="ChromaDB port (default: 8000)",
    )
    parser.add_argument(
        "--ollama-host",
        default="http://localhost:11434",
        help="Ollama base URL (default: http://localhost:11434)",
    )
    # Optional explicit paths â€” default to standard project-layout paths.
    parser.add_argument(
        "--tickets-csv",
        default=None,
        help="Path to support_tickets.csv (default: data/synthetic/support_tickets.csv)",
    )
    parser.add_argument(
        "--deploy-csv",
        default=None,
        help="Path to deployment_log.csv (default: data/synthetic/deployment_log.csv)",
    )
    parser.add_argument(
        "--release-notes-dir",
        default=None,
        help="Directory of release note .txt files (default: data/release_notes/)",
    )

    args = parser.parse_args(argv)

    # Resolve default paths relative to the project root.
    project_root = Path(__file__).resolve().parent.parent
    tickets_csv = Path(args.tickets_csv) if args.tickets_csv else (
        project_root / "data" / "synthetic" / "support_tickets.csv"
    )
    deploy_csv = Path(args.deploy_csv) if args.deploy_csv else (
        project_root / "data" / "synthetic" / "deployment_log.csv"
    )
    release_notes_dir = Path(args.release_notes_dir) if args.release_notes_dir else (
        project_root / "data" / "release_notes"
    )

    # Build shared clients.
    ollama_provider = OllamaProvider(base_url=args.ollama_host)
    embedding_fn = OllamaEmbeddingFunction(provider=ollama_provider, model="bge-m3")

    chroma_client = chromadb.HttpClient(
        host=args.chroma_host,
        port=args.chroma_port,
    )

    scenario_id = args.scenario_id
    print(f"Loading unstructured evidence for scenario '{scenario_id}' "
          f"into ChromaDB at {args.chroma_host}:{args.chroma_port} â€¦")

    totals: dict[str, int] = {}

    # --- Support tickets ---
    if tickets_csv.exists():
        count = load_support_tickets(
            chroma_client, scenario_id, tickets_csv, embedding_fn
        )
        totals["support_tickets"] = count
    else:
        print(f"[main] support_tickets CSV not found at {tickets_csv} â€” skipping.")
        totals["support_tickets"] = 0

    # --- Deployment log ---
    if deploy_csv.exists():
        count = load_deployment_log(
            chroma_client, scenario_id, deploy_csv, embedding_fn
        )
        totals["deployment_log"] = count
    else:
        print(f"[main] deployment_log CSV not found at {deploy_csv} â€” skipping.")
        totals["deployment_log"] = 0

    # --- Release notes ---
    if release_notes_dir.exists():
        count = load_release_notes(
            chroma_client, scenario_id, release_notes_dir, embedding_fn
        )
        totals["release_notes"] = count
    else:
        print(f"[main] release_notes directory not found at {release_notes_dir} â€” skipping.")
        totals["release_notes"] = 0

    # Summary
    print("\n--- Load summary ---")
    for source, n in totals.items():
        print(f"  {source:<20} {n:>4} document(s)")
    print(f"  {'TOTAL':<20} {sum(totals.values()):>4} document(s)")
    print(f"Collection name: evidence_{scenario_id}")


if __name__ == "__main__":
    main()

