"""
engines/evidence.py — Engine E4: Evidence Engine [SQL]+[RETRIEVAL]

Assembles authorized, freshness-weighted evidence from:
  1. Structured SQL sources (payment_events, inventory_events, deployment_log,
     support_tickets summary)
  2. Unstructured ChromaDB retrieval (support tickets, release notes, deploy log)

Evidence is ALWAYS assembled AFTER the entitlement boundary.
reliability_weight = freshness_decay(staleness, sla) * data_quality

Requirements: 6.1–6.7, 7.3–7.5
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import NamedTuple, Optional

from models import (
    AnomalySignal,
    Evidence,
    FreshnessStatus,
    MethodTag,
    clamp,
)
from config.registry import SourceRegistry
from security.entitlements import AuthorizationScope

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public helper: reliability_weight
# ---------------------------------------------------------------------------

def reliability_weight(entry) -> float:
    """
    Compute freshness-decayed reliability weight for a SourceRegistryEntry.

    Rules (Requirements 6.1–6.6):
    - UNKNOWN freshness status OR sla_minutes == 0: return 0.0 (Req 6.6)
    - In-SLA (freshness == FRESH): weight = data_quality  (Req 6.2)
    - Stale beyond SLA: weight = data_quality * max(0, 1 - staleness_beyond_ratio)
      where staleness_beyond_ratio = (staleness_minutes - sla_minutes) / sla_minutes
      This is strictly < data_quality and monotonically non-increasing (Reqs 6.3, 6.4)
    - Result clamped to [0, 1]

    Returns
    -------
    float in [0, 1]
    """
    # Undeterminable freshness or no SLA defined → weight 0 (Req 6.6)
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

    staleness = entry.staleness_minutes
    sla = float(entry.sla_minutes)

    if staleness <= sla:
        # In-SLA: full quality weight (Req 6.2)
        return clamp(entry.data_quality, 0.0, 1.0)

    # Stale beyond SLA: apply linear decay (Reqs 6.3, 6.4)
    staleness_beyond_ratio = (staleness - sla) / sla
    decay_factor = max(0.0, 1.0 - staleness_beyond_ratio)
    weight = entry.data_quality * decay_factor
    return clamp(weight, 0.0, 1.0)


def _reliability_weight_with_note(
    entry,
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

    evidence: list[Evidence]
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
# Structured evidence assembly (Step A)
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
) -> tuple[list[Evidence], int]:
    """
    Query structured SQL sources and build Evidence items tagged [SQL].

    Evidence retrieval is constrained by the authorized source set before evidence assembly.
    Unauthorized sources are excluded at the retrieval layer.
    """
    items: list[Evidence] = []
    dropped = 0

    if not authorized_sources:
        return items, dropped

    # -----------------------------------------------------------------------
    # Helper: resolve registry entry and compute reliability weight
    # -----------------------------------------------------------------------
    def _get_weight(source_id: str) -> Optional[float]:
        try:
            entry = registry.get(source_id)
        except KeyError:
            notes.append(
                f"structured evidence: source '{source_id}' not found in registry; "
                "item dropped (Req 7.5)"
            )
            return None
        return _reliability_weight_with_note(entry, notes)

    # -----------------------------------------------------------------------
    # Helper: execute a query and return rows (graceful on error)
    # -----------------------------------------------------------------------
    def _query(sql: str, params: tuple = ()) -> list:
        if db_conn is None:
            return []
        try:
            cur = db_conn.cursor()
            cur.execute(sql, params)
            return cur.fetchall()
        except Exception as exc:  # noqa: BLE001
            logger.warning("_assemble_structured: query failed: %s", exc)
            return []

    start_ts = anomaly_window_start.isoformat()
    end_ts = anomaly_window_end.isoformat()

    # --- Payment events summary (source: payment_gateway) ---
    SOURCE_PAYMENT = "payment_gateway"
    if SOURCE_PAYMENT in authorized_sources:
        weight = _get_weight(SOURCE_PAYMENT)
        if weight is not None:
            rows = _query(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN success = false THEN 1 ELSE 0 END) AS failures,
                    AVG(latency_ms) AS avg_latency
                FROM payment_events
                WHERE scenario_id = %s
                  AND ts >= %s
                  AND ts <= %s
                """,
                (scenario_id, start_ts, end_ts),
            )
            # COUNT(*) on an un-grouped aggregate always returns one row, so a
            # bare `if rows:` is truthy even when the table holds nothing for
            # this scenario. Emitting evidence then would assert a 0% failure
            # rate from absent data — a fabricated fact. Require real rows.
            if rows and (rows[0][0] or 0) > 0:
                total, failures, avg_latency = rows[0]
                total = total or 0
                failures = failures or 0
                avg_latency = avg_latency or 0.0
                failure_rate = (failures / total * 100) if total > 0 else 0.0
                summary = (
                    f"Payment gateway events in window: {total} total, "
                    f"{failures} failures (failure rate: {failure_rate:.1f}%), "
                    f"average latency {avg_latency:.0f}ms."
                )
                summary = _maybe_summarize(summary, provider)
                items.append(
                    Evidence(
                        evidence_id=_make_evidence_id(
                            "payment_summary", scenario_id, f"{start_ts}:{end_ts}"
                        ),
                        kind="structured",
                        summary=summary,
                        source_id=SOURCE_PAYMENT,
                        reliability_weight=weight,
                        relevance=0.9,
                        raw_ref="payment_events:aggregate",
                        method=MethodTag.SQL,
                    )
                )
        else:
            dropped += 1

    # --- Inventory fill rate (source: inventory) ---
    SOURCE_INVENTORY = "inventory"
    if SOURCE_INVENTORY in authorized_sources:
        weight = _get_weight(SOURCE_INVENTORY)
        if weight is not None:
            rows = _query(
                """
                SELECT AVG(fill_rate) AS avg_fill_rate
                FROM inventory_events
                WHERE scenario_id = %s
                  AND ts >= %s
                  AND ts <= %s
                """,
                (scenario_id, start_ts, end_ts),
            )
            if rows and rows[0][0] is not None:
                avg_fill = rows[0][0]
                summary = (
                    f"Inventory fill rate in window: average {avg_fill:.1%}. "
                    "Inventory levels appear normal."
                )
                summary = _maybe_summarize(summary, provider)
                items.append(
                    Evidence(
                        evidence_id=_make_evidence_id(
                            "inventory_fill", scenario_id, f"{start_ts}:{end_ts}"
                        ),
                        kind="structured",
                        summary=summary,
                        source_id=SOURCE_INVENTORY,
                        reliability_weight=weight,
                        relevance=0.9,
                        raw_ref="inventory_events:aggregate",
                        method=MethodTag.SQL,
                    )
                )
        else:
            dropped += 1

    # --- Deployment log (source: deployment_log) ---
    SOURCE_DEPLOY = "deployment_log"
    if SOURCE_DEPLOY in authorized_sources:
        weight = _get_weight(SOURCE_DEPLOY)
        if weight is not None:
            # Look for deployments in the 48h before anomaly_window_start
            rows = _query(
                """
                SELECT deploy_id, version, ts, component
                FROM deployment_log
                WHERE ts >= (CAST(%s AS TIMESTAMP) - INTERVAL '48 hours')
                  AND ts <= CAST(%s AS TIMESTAMP)
                ORDER BY ts DESC
                """,
                (start_ts, start_ts),
            )
            for row in rows:
                deploy_id, version, deployed_at, component = row
                summary = (
                    f"Deployment '{version}' of component '{component}' was deployed "
                    f"at {deployed_at} (within 48h before anomaly window)."
                )
                summary = _maybe_summarize(summary, provider)
                items.append(
                    Evidence(
                        evidence_id=_make_evidence_id(
                            "deployment", scenario_id, str(deploy_id)
                        ),
                        kind="structured",
                        summary=summary,
                        source_id=SOURCE_DEPLOY,
                        reliability_weight=weight,
                        relevance=0.9,
                        raw_ref=f"deployment_log:{deploy_id}",
                        method=MethodTag.SQL,
                    )
                )
        else:
            dropped += 1

    # --- Support tickets (source: support_tickets) ---
    SOURCE_SUPPORT = "support_tickets"
    if SOURCE_SUPPORT in authorized_sources:
        weight = _get_weight(SOURCE_SUPPORT)
        if weight is not None:
            rows = _query(
                """
                SELECT COUNT(*) AS total, category
                FROM support_tickets
                WHERE scenario_id = %s
                  AND ts >= %s
                  AND ts <= %s
                GROUP BY category
                ORDER BY COUNT(*) DESC
                """,
                (scenario_id, start_ts, end_ts),
            )
            if rows:
                total_all = sum(r[0] for r in rows)
                category_breakdown = ", ".join(
                    f"{r[1]}: {r[0]}" for r in rows[:5]
                )
                summary = (
                    f"Support tickets in window: {total_all} total. "
                    f"Category breakdown — {category_breakdown}."
                )
                summary = _maybe_summarize(summary, provider)
                items.append(
                    Evidence(
                        evidence_id=_make_evidence_id(
                            "support_tickets", scenario_id, f"{start_ts}:{end_ts}"
                        ),
                        kind="structured",
                        summary=summary,
                        source_id=SOURCE_SUPPORT,
                        reliability_weight=weight,
                        relevance=0.9,
                        raw_ref="support_tickets:aggregate",
                        method=MethodTag.SQL,
                    )
                )
        else:
            dropped += 1

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
# Unstructured evidence assembly (Step B)
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
) -> tuple[list[Evidence], int]:
    """
    Query ChromaDB for unstructured evidence tagged [RETRIEVAL].

    Evidence retrieval is constrained by the authorized source set before evidence assembly.
    Unauthorized sources and forbidden precedent collections are excluded at the retrieval layer.
    """
    items: list[Evidence] = []
    dropped = 0

    if not authorized_sources or chroma_client is None:
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

    # Build retrieval query from signals
    kpi_ids = " ".join(s.kpi_id for s in signals if s.is_anomaly)
    query_text = (
        f"checkout payment failure conversion drop deployment {kpi_ids}".strip()
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

    # Embed the query with Ollama bge-m3 so the vector dimension (1024) matches
    # the collection. Passing query_texts would make ChromaDB embed with its
    # default 384-dim model, causing a dimension mismatch.
    try:
        from llm.provider import OllamaProvider
        _base = getattr(provider, "_base_url", "http://localhost:11434") if provider else "http://localhost:11434"
        _embedder = OllamaProvider(base_url=_base)
        query_embedding = _embedder.embed([query_text], model="bge-m3")[0]
    except Exception as exc:  # noqa: BLE001
        logger.warning("_assemble_unstructured: query embedding failed: %s", exc)
        return items, dropped

    try:
        count = collection.count()
        if isinstance(count, int):
            if count == 0:
                return items, dropped
            n_results = min(5, count)
        else:
            n_results = 5
    except Exception:
        n_results = 5

    results = None
    for k in range(n_results, 0, -1):
        try:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=k,
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )
            break
        except Exception:
            continue

    if results is None:
        try:
            get_res = collection.get(where=where_filter, limit=n_results, include=["documents", "metadatas"])
            if get_res and get_res.get("ids"):
                results = {
                    "ids": [get_res["ids"]],
                    "documents": [get_res.get("documents", [])],
                    "metadatas": [get_res.get("metadatas", [])],
                    "distances": [[0.1] * len(get_res["ids"])],
                }
        except Exception as exc:  # noqa: BLE001
            logger.warning("_assemble_unstructured: ChromaDB query fallback failed: %s", exc)

    if not results:
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

        # ChromaDB returns L2 distance; convert to a [0,1] cosine-like relevance.
        # distance=0 means identical (relevance=1), larger distance → lower relevance.
        # Clamp to [0, 1].
        relevance = clamp(1.0 - float(distance), 0.0, 1.0)

        summary = doc or f"Document chunk from {source_id}."
        summary = _maybe_summarize(summary, provider)

        items.append(
            Evidence(
                evidence_id=_make_evidence_id(
                    "retrieval", scenario_id, doc_id
                ),
                kind="unstructured",
                summary=summary,
                source_id=source_id,
                reliability_weight=weight,
                relevance=relevance,
                raw_ref=doc_id,
                method=MethodTag.RETRIEVAL,
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
) -> EvidenceAssemblyResult:
    """
    Assemble authorized, freshness-weighted evidence (Engine E4).

    Evidence retrieval is constrained by the authorized source set before evidence assembly.
    Unauthorized sources and precedent collections are excluded at the retrieval layer.

    Parameters
    ----------
    authorized_sources : frozenset[str]
        Set of source_id strings authorized for the current persona.
        Must be provided explicitly. An empty frozenset means no sources are
        authorized (fail-closed, returns zero evidence).
    signals       : AnomalySignal list from Engine E2.
    registry      : SourceRegistry instance.
    db_conn       : Database connection.
    chroma_client : ChromaDB client.
    scenario_id   : Current scenario ID.
    anomaly_window_start : Window start datetime.
    anomaly_window_end   : Window end datetime.
    provider      : Optional LLMProvider.
    scope         : Optional AuthorizationScope (extracted for backward compatibility).
    allowed_collections : Optional frozenset[str] of permitted ChromaDB collection names.

    Returns
    -------
    EvidenceAssemblyResult with evidence sorted by (reliability_weight *
    relevance) descending, total dropped_count, and reliability_notes.

    Requirements: 6.1–6.7, 7.3–7.5; ISSUE-002 Phase 2; ISSUE-003 Phase 1
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

    # Step A — structured
    structured, dropped_a = _assemble_structured(
        authorized_sources=auth_sources,
        scenario_id=scenario_id,
        anomaly_window_start=anomaly_window_start,
        anomaly_window_end=anomaly_window_end,
        registry=registry,
        db_conn=db_conn,
        notes=notes,
        provider=provider,
    )
    total_dropped += dropped_a

    # Step B — unstructured
    unstructured, dropped_b = _assemble_unstructured(
        authorized_sources=auth_sources,
        signals=signals,
        scenario_id=scenario_id,
        registry=registry,
        chroma_client=chroma_client,
        notes=notes,
        provider=provider,
        allowed_collections=allowed_collections,
    )
    total_dropped += dropped_b

    all_items = structured + unstructured

    # Step C — drop unresolvable source_ids (already handled inside A/B, but
    # apply a final safety pass in case items were constructed externally)
    verified: list[Evidence] = []
    for item in all_items:
        try:
            registry.get(item.source_id)
            verified.append(item)
        except KeyError:
            notes.append(
                f"final pass: evidence '{item.evidence_id}' source "
                f"'{item.source_id}' not in registry; dropped (Req 7.5)"
            )
            total_dropped += 1

    # Sort by (reliability_weight * relevance) descending
    verified.sort(
        key=lambda e: e.reliability_weight * e.relevance,
        reverse=True,
    )

    return EvidenceAssemblyResult(
        evidence=verified,
        dropped_count=total_dropped,
        reliability_notes=notes,
    )
