"""
engines/evidence.py — Engine E4: Evidence Engine [SQL]+[RETRIEVAL]

Assembles authorized, freshness-weighted evidence records using the Canonical
Data & Evidence Layer:
  1. Structured facts extracted and normalized via IngestionAdapter / SQL mappings
  2. Unstructured semantic chunks retrieved from ChromaDB (or MockUnstructuredExtractor in test mode)

Evidence is ALWAYS assembled AFTER the entitlement boundary.
reliability_weight = calculate_reliability_decay(data_quality, staleness, sla)

Requirements: 6.1–6.7, 7.3–7.5
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime
from typing import NamedTuple, Optional

from models import (
    AnomalySignal,
    CanonicalEvidenceRecord,
    Evidence,
    FreshnessStatus,
    MethodTag,
    SourceRegistryEntry,
    calculate_reliability_decay,
    clamp,
)
from config.registry import SourceRegistry
from etl.ingestion_adapter import (
    BatchSQLIngestionAdapter,
    IngestionAdapter,
    MockUnstructuredExtractor,
)
from security.entitlements import AuthorizationScope

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public helper: reliability_weight
# ---------------------------------------------------------------------------

def reliability_weight(entry: SourceRegistryEntry) -> float:
    """
    Compute freshness-decayed reliability weight for a SourceRegistryEntry.
    Delegates to the pinned continuous linear decay function.
    """
    if entry.sla_minutes == 0:
        logger.debug(
            "reliability_weight: source '%s' has sla_minutes=0; returning 0.0 "
            "(missing SLA metadata).",
            entry.source_id,
        )
        return 0.0

    if entry.freshness_status == FreshnessStatus.UNKNOWN:
        logger.debug(
            "reliability_weight: source '%s' freshness is UNKNOWN; returning 0.0.",
            entry.source_id,
        )
        return 0.0

    return calculate_reliability_decay(
        base_quality=entry.data_quality,
        staleness_minutes=entry.staleness_minutes,
        sla_minutes=float(entry.sla_minutes),
    )


def _reliability_weight_with_note(
    entry: SourceRegistryEntry,
    notes: list[str],
) -> float:
    """
    Wrapper around reliability_weight that appends a note to *notes* when the
    weight is zero due to missing metadata.
    """
    if entry.sla_minutes == 0:
        notes.append(
            f"source '{entry.source_id}': reliability_weight=0.0 "
            "(sla_minutes=0 — SLA undefined)"
        )
        return 0.0

    if entry.freshness_status == FreshnessStatus.UNKNOWN:
        notes.append(
            f"source '{entry.source_id}': reliability_weight=0.0 "
            "(freshness_status=UNKNOWN)"
        )
        return 0.0

    return reliability_weight(entry)


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

class EvidenceAssemblyResult(NamedTuple):
    """
    Return type for assemble_evidence().

    evidence          : assembled, authorized, freshness-weighted items sorted
                        by (reliability_weight * relevance) descending
    dropped_count     : items dropped due to unresolvable source_id (Req 7.5)
    reliability_notes : notes about zero-weight or missing metadata (Req 6.6)
    """

    evidence: list[CanonicalEvidenceRecord]
    dropped_count: int
    reliability_notes: list[str]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_evidence_id(prefix: str, scenario_id: str, suffix: str) -> str:
    """
    Build a deterministic evidence_id from the given components.
    Uses a short SHA-256 hex digest for stable, unique identifiers.
    """
    raw = f"{prefix}:{scenario_id}:{suffix}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _word_count(text: str) -> int:
    return len(text.split())


def _maybe_summarize(
    summary: str,
    provider,
    max_words: int = 200,
) -> str:
    """
    If *provider* is supplied and *summary* exceeds *max_words* words, call the
    LLM once to reduce it to one sentence.  Returns the original string on any
    error or when provider is None (Req 7.3).
    """
    if provider is None or _word_count(summary) <= max_words:
        return summary

    try:
        from llm.provider import LLMUnavailableError

        response = provider.complete(
            f"Summarize the following evidence in exactly one concise sentence:\n\n{summary}",
            model=getattr(provider, "DEFAULT_MODEL", "qwen3:8b"),
            system=(
                "You are a data analyst. Summarize evidence in one sentence. "
                "Do not include numbers or quantitative claims."
            ),
            temperature=0.0,
            max_tokens=80,
        )
        return response.text.strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "_maybe_summarize: LLM summarization failed (%s); using original summary.",
            exc,
        )
        return summary


# ---------------------------------------------------------------------------
# Structured evidence assembly (Step A) — IngestionAdapter
# ---------------------------------------------------------------------------

def _assemble_structured(
    authorized_sources: frozenset[str],
    scenario_id: str,
    anomaly_window_start: datetime,
    anomaly_window_end: datetime,
    registry: SourceRegistry,
    db_conn,
    notes: list[str],
    provider,
    adapter: Optional[IngestionAdapter] = None,
) -> tuple[list[CanonicalEvidenceRecord], int]:
    """
    Query structured sources via IngestionAdapter and build CanonicalEvidenceRecord items tagged [SQL].
    """
    items: list[CanonicalEvidenceRecord] = []
    dropped = 0

    if not authorized_sources or db_conn is None:
        return items, dropped

    if adapter is None:
        adapter = BatchSQLIngestionAdapter(db_conn=db_conn)

    for source_id in sorted(list(authorized_sources)):
        try:
            entry = registry.get(source_id)
        except KeyError:
            notes.append(
                f"structured evidence: source '{source_id}' not found in registry; "
                "item dropped (Req 7.5)"
            )
            dropped += 1
            continue

        try:
            for extracted in adapter.extract(
                source_id=source_id,
                window_start=anomaly_window_start,
                window_end=anomaly_window_end,
                scenario_id=scenario_id,
            ):
                norm_record = adapter.normalize(
                    extracted=extracted,
                    source_entry=entry,
                    scenario_id=scenario_id,
                )
                if norm_record is not None:
                    norm_record.observation = _maybe_summarize(norm_record.observation, provider)
                    items.append(norm_record)
        except Exception as exc:
            logger.warning("_assemble_structured: extraction failed for '%s': %s", source_id, exc)

    return items, dropped


# ---------------------------------------------------------------------------
# Forbidden collections for evidence retrieval (ISSUE-002 Phase 2)
# Precedent and memory collections must NEVER enter E4 evidence retrieval.
# ---------------------------------------------------------------------------
_FORBIDDEN_EVIDENCE_COLLECTIONS: frozenset[str] = frozenset({
    "investigation_precedents",
    "precedents",
    "precedent_memory",
})


# ---------------------------------------------------------------------------
# Unstructured evidence assembly (Step B) — Dual-Retrieval
# ---------------------------------------------------------------------------

def _assemble_unstructured(
    authorized_sources: frozenset[str],
    signals: list[AnomalySignal],
    scenario_id: str,
    registry: SourceRegistry,
    chroma_client,
    notes: list[str],
    provider,
    allowed_collections: Optional[frozenset[str]] = None,
    mock_extractor: Optional[MockUnstructuredExtractor] = None,
) -> tuple[list[CanonicalEvidenceRecord], int]:
    """
    Query ChromaDB (or MockUnstructuredExtractor in test mode) for unstructured
    evidence tagged [RETRIEVAL].
    """
    items: list[CanonicalEvidenceRecord] = []
    dropped = 0

    if not authorized_sources:
        return items, dropped

    # Test / Demo mode swap using cached extraction fixtures
    env_mode = os.getenv("ENV_MODE", "").lower()
    if env_mode == "test" or mock_extractor is not None:
        extractor = mock_extractor or MockUnstructuredExtractor()
        for extracted in extractor.extract("anomaly investigation"):
            payload = extracted.raw_payload
            src_id = payload.get("source", "release_notes")
            if src_id in authorized_sources:
                try:
                    entry = registry.get(src_id)
                except KeyError:
                    dropped += 1
                    continue
                weight = _reliability_weight_with_note(entry, notes)
                items.append(
                    CanonicalEvidenceRecord(
                        source_id=src_id,
                        source_name=entry.name,
                        entity=payload.get("entity", src_id),
                        observation=payload.get("observation", ""),
                        timestamp=payload.get("timestamp", datetime.utcnow()),
                        source_reliability=weight,
                        confidence=0.95,
                        method=MethodTag.RETRIEVAL,
                        raw_ref=extracted.raw_identifier,
                        kind="unstructured",
                    )
                )
        return items, dropped

    if chroma_client is None:
        return items, dropped

    collection_name = f"evidence_{scenario_id}"

    # Structural Collection Boundary Guard (ISSUE-002 Phase 2)
    if collection_name in _FORBIDDEN_EVIDENCE_COLLECTIONS:
        logger.error(
            "_assemble_unstructured: collection '%s' is a forbidden precedent collection; "
            "cannot be queried as raw evidence.",
            collection_name,
        )
        return items, dropped

    if allowed_collections is not None and collection_name not in allowed_collections:
        logger.warning(
            "_assemble_unstructured: collection '%s' is not in allowed_collections %s; skipping.",
            collection_name,
            allowed_collections,
        )
        return items, dropped

    # Build generic retrieval query from signals
    kpi_ids = " ".join(s.kpi_id for s in signals if s.is_anomaly)
    query_text = (
        f"incident anomaly failure telemetry logs deployment {kpi_ids}".strip()
    )

    try:
        collection = chroma_client.get_collection(collection_name)
    except Exception:  # noqa: BLE001
        logger.info(
            "_assemble_unstructured: no ChromaDB collection '%s' (scenario has no "
            "unstructured evidence loaded); continuing with structured evidence only.",
            collection_name,
        )
        return items, dropped

    # Build ChromaDB metadata where filter for query-level authorization
    auth_list = sorted(list(authorized_sources))
    if len(auth_list) == 1:
        where_filter = {"source": auth_list[0]}
    else:
        where_filter = {"source": {"$in": auth_list}}

    # Embed query
    query_embedding = None
    try:
        if hasattr(provider, "embed"):
            query_embedding = provider.embed([query_text], model="bge-m3")[0]
        else:
            from llm.provider import OllamaProvider
            _embedder = OllamaProvider(base_url="http://localhost:11434")
            query_embedding = _embedder.embed([query_text], model="bge-m3")[0]
    except Exception as exc:  # noqa: BLE001
        logger.warning("_assemble_unstructured: query embedding failed (%s) — falling back to metadata get.", exc)
        query_embedding = None

    results = None
    try:
        col_count = 5
        try:
            raw_count = collection.count()
            if isinstance(raw_count, int):
                col_count = raw_count
        except Exception:
            col_count = 5
        n_res = min(5, max(1, col_count))
        if query_embedding is not None:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=n_res,
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )
        else:
            try:
                results = collection.query(
                    query_texts=[query_text],
                    n_results=n_res,
                    where=where_filter,
                    include=["documents", "metadatas", "distances"],
                )
            except Exception:
                results = collection.query(
                    where=where_filter,
                    n_results=n_res,
                    include=["documents", "metadatas", "distances"],
                )
    except Exception as exc:
        logger.warning("_assemble_unstructured: vector query failed: %s", exc)

    if results is None or not isinstance(results, dict) or not results.get("ids") or not results["ids"][0]:
        try:
            get_res = collection.get(where=where_filter, limit=5, include=["documents", "metadatas"])
            if get_res and isinstance(get_res, dict) and get_res.get("ids"):
                results = {
                    "ids": [get_res["ids"]],
                    "documents": [get_res.get("documents", [])],
                    "metadatas": [get_res.get("metadatas", [])],
                    "distances": [[0.1] * len(get_res["ids"])],
                }
        except Exception as exc:  # noqa: BLE001
            logger.warning("_assemble_unstructured: ChromaDB query fallback failed: %s", exc)


    if not results or not results.get("ids") or not results["ids"][0]:
        return items, dropped

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    doc_ids = results.get("ids", [[]])[0]

    for idx, (doc, meta, distance, doc_id) in enumerate(
        zip(documents, metadatas, distances, doc_ids)
    ):
        source_id = (meta or {}).get("source", "")

        # Only include authorized sources (secondary defense-in-depth check)
        if source_id not in authorized_sources:
            logger.debug(
                "_assemble_unstructured: secondary check skipped doc '%s' from unauthorized source '%s'.",
                doc_id,
                source_id,
            )
            continue

        # Resolve registry entry
        try:
            entry = registry.get(source_id)
        except KeyError:
            notes.append(
                f"unstructured evidence: source '{source_id}' (doc '{doc_id}') "
                "not found in registry; item dropped (Req 7.5)"
            )
            dropped += 1
            continue

        weight = _reliability_weight_with_note(entry, notes)
        relevance = clamp(1.0 - float(distance), 0.0, 1.0)
        summary = doc or f"Document chunk from {source_id}."
        summary = _maybe_summarize(summary, provider)

        items.append(
            CanonicalEvidenceRecord(
                source_id=source_id,
                source_name=entry.name,
                entity=str((meta or {}).get("entity", source_id)),
                observation=summary,
                freshness_minutes=entry.staleness_minutes,
                source_reliability=weight,
                confidence=relevance,
                raw_ref=doc_id,
                method=MethodTag.RETRIEVAL,
                kind="unstructured",
            )
        )

    return items, dropped


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def assemble_evidence(
    authorized_sources: frozenset[str],
    signals: list[AnomalySignal],
    registry: SourceRegistry,
    db_conn,
    chroma_client,
    scenario_id: str,
    anomaly_window_start: datetime,
    anomaly_window_end: datetime,
    provider=None,
    scope: Optional[AuthorizationScope] = None,
    allowed_collections: Optional[frozenset[str]] = None,
    adapter: Optional[IngestionAdapter] = None,
    mock_extractor: Optional[MockUnstructuredExtractor] = None,
) -> EvidenceAssemblyResult:
    """
    Assemble authorized, freshness-weighted canonical evidence (Engine E4).

    Dual-retrieval pipeline:
      - Structured facts via IngestionAdapter
      - Unstructured semantic chunks via ChromaDB / Vector Extractor
    """
    if isinstance(authorized_sources, AuthorizationScope):
        scope = authorized_sources
        authorized_sources = scope.authorized_sources
    elif scope is not None and (authorized_sources is None or not isinstance(authorized_sources, (set, frozenset))):
        authorized_sources = scope.authorized_sources

    if not isinstance(authorized_sources, (set, frozenset)):
        raise TypeError(
            f"assemble_evidence requires authorized_sources as a frozenset[str]; "
            f"got {type(authorized_sources).__name__!r}. "
            f"Authorization must be explicitly passed at evidence assembly layer."
        )

    auth_sources = frozenset(authorized_sources)

    # Fail-closed: empty frozenset means no sources authorized -> zero evidence returned
    if not auth_sources:
        logger.info("assemble_evidence: authorized_sources is empty; returning zero evidence (fail-closed).")
        return EvidenceAssemblyResult(evidence=[], dropped_count=0, reliability_notes=[])

    # Filter out forbidden precedent collections from allowed_collections if supplied
    if allowed_collections is not None:
        allowed_collections = frozenset(
            c for c in allowed_collections if c not in _FORBIDDEN_EVIDENCE_COLLECTIONS
        )

    notes: list[str] = []
    total_dropped = 0

    # Step A — structured facts via IngestionAdapter
    structured, dropped_a = _assemble_structured(
        authorized_sources=auth_sources,
        scenario_id=scenario_id,
        anomaly_window_start=anomaly_window_start,
        anomaly_window_end=anomaly_window_end,
        registry=registry,
        db_conn=db_conn,
        notes=notes,
        provider=provider,
        adapter=adapter,
    )
    total_dropped += dropped_a

    # Step B — unstructured semantic retrieval
    unstructured, dropped_b = _assemble_unstructured(
        authorized_sources=auth_sources,
        signals=signals,
        scenario_id=scenario_id,
        registry=registry,
        chroma_client=chroma_client,
        notes=notes,
        provider=provider,
        allowed_collections=allowed_collections,
        mock_extractor=mock_extractor,
    )
    total_dropped += dropped_b

    all_items = structured + unstructured

    # Step C — verify source_ids in registry
    verified: list[CanonicalEvidenceRecord] = []
    for item in all_items:
        try:
            registry.get(item.source_id)
            verified.append(item)
        except KeyError:
            notes.append(
                f"final pass: evidence '{item.id}' source "
                f"'{item.source_id}' not in registry; dropped (Req 7.5)"
            )
            total_dropped += 1

    # Sort by (source_reliability * confidence) descending
    verified.sort(
        key=lambda e: e.source_reliability * e.confidence,
        reverse=True,
    )

    return EvidenceAssemblyResult(
        evidence=verified,
        dropped_count=total_dropped,
        reliability_notes=notes,
    )
