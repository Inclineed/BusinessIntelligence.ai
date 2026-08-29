"""
tests/test_memory.py — Unit tests for Engine E9: Memory Engine.

Covers:
  - store_precedent: returns True on success
  - store_precedent: queues retry on first failure (Req 15.2)
  - store_precedent: returns False after MAX_RETRY_ATTEMPTS exhausted (Req 15.2)
  - retrieve_precedents: returns empty list when collection is empty (Req 15.4)
  - retrieve_precedents: filters results below RELEVANCE_THRESHOLD (Req 15.3)
  - retrieve_precedents: stamps results with MethodTag.RETRIEVAL (Req 15.5)
  - retrieve_precedents: returns sorted by relevance descending (Req 15.3)
  - retrieve_precedents: returns at most MAX_RESULTS items (Req 15.3)
  - summarize_investigation: falls back to template when LLM fails
  - module-level store_precedent and retrieve_precedents convenience functions

Requirements: 15.1, 15.2, 15.3, 15.4, 15.5
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest

from engines.memory import (
    MemoryEngine,
    _build_fallback_summary,
    _cosine_to_relevance,
    store_precedent,
    retrieve_precedents,
)
from models import (
    AuditVerdict,
    Decision,
    InvestigationResult,
    MethodTag,
    Persona,
    ScoredHypothesis,
    Telemetry,
)
from llm.provider import LLMUnavailableError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(
    scenario_id: str = "INC_001",
    persona: Persona = Persona.ANALYST,
    winning_hypothesis: Optional[str] = "H1",
    recommended_action: Optional[str] = "Roll back v4.3.",
) -> InvestigationResult:
    """Minimal InvestigationResult for testing."""
    decision = Decision(
        abstained=False,
        recommended_action=recommended_action,
        verification_metric="payment_success_rate",
        winning_hypothesis_id=winning_hypothesis,
        persona_narrative="Test narrative.",
        method=MethodTag.LLM,
    )
    scored = ScoredHypothesis(
        hypothesis_id="H1",
        final_audit_score=0.85,
        audit_verdict=AuditVerdict.VERIFIED,
    )
    return InvestigationResult(
        scenario_id=scenario_id,
        persona=persona,
        decision=decision,
        scored=[scored],
        telemetry=Telemetry(),
    )


def _make_llm_provider(summary_text: str = "Test summary.") -> MagicMock:
    """Return a mock LLMProvider whose complete() and embed() succeed."""
    provider = MagicMock()
    llm_response = MagicMock()
    llm_response.text = summary_text
    provider.complete.return_value = llm_response
    # embed returns a list of one vector
    provider.embed.return_value = [[0.1, 0.2, 0.3]]
    return provider


def _make_chroma_client(
    *,
    count: int = 0,
    query_ids: Optional[list[str]] = None,
    query_distances: Optional[list[float]] = None,
    query_metadatas: Optional[list[dict]] = None,
    query_documents: Optional[list[str]] = None,
    upsert_raises: Optional[Exception] = None,
) -> MagicMock:
    """
    Return a mock ChromaDB client.

    The collection's query() and get() return the given ids/distances/metadatas/documents.
    """
    import numpy as np

    collection = MagicMock()
    collection.count.return_value = count

    if upsert_raises is not None:
        collection.upsert.side_effect = upsert_raises
    else:
        collection.upsert.return_value = None

    ids_list = query_ids or []
    distances_list = query_distances or [0.1 * i for i in range(len(ids_list))]
    metadatas_list = query_metadatas or [{}] * len(ids_list)
    documents_list = query_documents or [f"Doc {i}" for i in range(len(ids_list))]

    # Generate synthetic embeddings that produce exact query_distances when dotted with q_vec=[0.1, 0.2, 0.3]
    q_raw = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    q = q_raw / np.linalg.norm(q_raw)
    rand_vec = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    if abs(np.dot(rand_vec, q)) > 0.9:
        rand_vec = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    u = rand_vec - np.dot(rand_vec, q) * q
    u = u / np.linalg.norm(u)

    embeddings_list = []
    for d in distances_list:
        s = 1.0 - float(d)
        y = float(np.sqrt(max(0.0, 1.0 - s**2)))
        doc_vec = (s * q + y * u).tolist()
        embeddings_list.append(doc_vec)

    query_result = {
        "ids": [ids_list],
        "distances": [distances_list],
        "metadatas": [metadatas_list],
        "documents": [documents_list],
    }
    collection.query.return_value = query_result

    get_result = {
        "ids": ids_list,
        "metadatas": metadatas_list,
        "documents": documents_list,
        "embeddings": embeddings_list,
    }
    collection.get.return_value = get_result

    client = MagicMock()
    client.get_or_create_collection.return_value = collection
    return client


# ---------------------------------------------------------------------------
# _cosine_to_relevance helper
# ---------------------------------------------------------------------------

def test_cosine_to_relevance_identical():
    """Distance 0 → relevance 1.0."""
    assert _cosine_to_relevance(0.0) == pytest.approx(1.0)


def test_cosine_to_relevance_opposite():
    """Distance 2 → relevance 0.0."""
    assert _cosine_to_relevance(2.0) == pytest.approx(0.0)


def test_cosine_to_relevance_midpoint():
    """Distance 1 → relevance 0.5."""
    assert _cosine_to_relevance(1.0) == pytest.approx(0.5)


def test_cosine_to_relevance_clamp_negative():
    """Negative distances are clamped to 0."""
    assert _cosine_to_relevance(-1.0) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# _build_fallback_summary helper
# ---------------------------------------------------------------------------

def test_fallback_summary_contains_scenario_id():
    result = _make_result(scenario_id="TEST_001")
    summary = _build_fallback_summary(result)
    assert "TEST_001" in summary


def test_fallback_summary_contains_winning_hypothesis():
    result = _make_result(winning_hypothesis="H2")
    summary = _build_fallback_summary(result)
    assert "H2" in summary


def test_fallback_summary_abstained():
    """Abstained result has no recommended action — summary still builds."""
    result = _make_result(recommended_action=None)
    summary = _build_fallback_summary(result)
    assert isinstance(summary, str)
    assert len(summary) > 0


# ---------------------------------------------------------------------------
# summarize_investigation
# ---------------------------------------------------------------------------

def test_summarize_investigation_uses_llm():
    """When the LLM succeeds, its text is returned."""
    provider = _make_llm_provider(summary_text="LLM generated summary.")
    engine = MemoryEngine(chroma_client=None, llm_provider=provider)
    result = _make_result()
    summary = engine.summarize_investigation(result)
    assert summary == "LLM generated summary."
    provider.complete.assert_called_once()


def test_summarize_investigation_llm_unavailable_falls_back():
    """When LLM raises LLMUnavailableError, fallback summary is returned."""
    provider = MagicMock()
    provider.complete.side_effect = LLMUnavailableError("provider down")
    engine = MemoryEngine(chroma_client=None, llm_provider=provider)
    result = _make_result()
    summary = engine.summarize_investigation(result)
    # Must be a non-empty string (fallback template)
    assert isinstance(summary, str)
    assert len(summary) > 0
    assert "INC_001" in summary


def test_summarize_investigation_empty_llm_response_falls_back():
    """When LLM returns empty text, fallback summary is used."""
    provider = _make_llm_provider(summary_text="")
    engine = MemoryEngine(chroma_client=None, llm_provider=provider)
    result = _make_result()
    summary = engine.summarize_investigation(result)
    assert len(summary) > 0


# ---------------------------------------------------------------------------
# store_precedent — success path
# ---------------------------------------------------------------------------

def test_store_precedent_returns_true_on_success():
    """Happy-path store returns True (Req 15.1)."""
    provider = _make_llm_provider()
    chroma = _make_chroma_client(count=0)
    engine = MemoryEngine(chroma_client=chroma, llm_provider=provider)
    result = _make_result()
    ok = engine.store_precedent(result)
    assert ok is True


def test_store_precedent_calls_upsert():
    """store_precedent upserts into the ChromaDB collection."""
    provider = _make_llm_provider()
    chroma = _make_chroma_client()
    engine = MemoryEngine(chroma_client=chroma, llm_provider=provider)
    result = _make_result(scenario_id="UPSERT_TEST")
    engine.store_precedent(result)
    collection = chroma.get_or_create_collection.return_value
    collection.upsert.assert_called_once()
    call_kwargs = collection.upsert.call_args
    # The id should be the scenario_id
    assert "UPSERT_TEST" in call_kwargs.kwargs.get("ids", []) or \
           "UPSERT_TEST" in call_kwargs[1].get("ids", call_kwargs[0][0] if call_kwargs[0] else [])


# ---------------------------------------------------------------------------
# store_precedent — failure & retry queue (Req 15.2)
# ---------------------------------------------------------------------------

def test_store_precedent_queues_retry_on_first_failure():
    """
    When the first upsert fails, the result is queued for retry.
    The pending queue should have one entry after the first failed call.
    (Req 15.2)
    """
    provider = _make_llm_provider()
    chroma = _make_chroma_client(upsert_raises=RuntimeError("DB down"))
    engine = MemoryEngine(chroma_client=chroma, llm_provider=provider)
    result = _make_result()
    ok = engine.store_precedent(result)
    assert ok is False
    assert len(engine._pending) == 1
    assert engine._pending[0].attempts == 1


def test_store_precedent_returns_false_after_max_retries_exhausted():
    """
    After MAX_RETRY_ATTEMPTS failed retries, store_precedent returns False
    and the pending queue is empty (Req 15.2).
    """
    provider = _make_llm_provider()
    chroma = _make_chroma_client(upsert_raises=RuntimeError("persistent failure"))
    engine = MemoryEngine(chroma_client=chroma, llm_provider=provider)
    result = _make_result()

    # First call — queues retry (attempt 1)
    ok1 = engine.store_precedent(result)
    assert ok1 is False
    assert len(engine._pending) == 1

    # Drain the pending queue through flush_pending to exhaust retries
    # (attempt 2 and 3 via flush)
    summary = engine.flush_pending()
    # After two more attempts (2 + 3 = MAX_RETRY_ATTEMPTS), item is dropped
    assert summary["failed"] >= 1
    assert len(engine._pending) == 0


# ---------------------------------------------------------------------------
# retrieve_precedents — empty collection (Req 15.4)
# ---------------------------------------------------------------------------

def test_retrieve_precedents_empty_collection_returns_empty_list():
    """
    When the collection has no items, retrieve_precedents returns [] (Req 15.4).
    """
    provider = _make_llm_provider()
    chroma = _make_chroma_client(count=0)
    engine = MemoryEngine(chroma_client=chroma, llm_provider=provider)
    results = engine.retrieve_precedents("INC_001", "checkout degradation")
    assert results == []


# ---------------------------------------------------------------------------
# retrieve_precedents — relevance filtering (Req 15.3)
# ---------------------------------------------------------------------------

def test_retrieve_precedents_filters_below_threshold():
    """
    Results with relevance < RELEVANCE_THRESHOLD are excluded (Req 15.3).
    Distance 1.5 → relevance 0.25 — below 0.7 threshold, should be filtered.
    """
    provider = _make_llm_provider()
    chroma = _make_chroma_client(
        count=1,
        query_ids=["OLD_001"],
        query_distances=[1.5],   # relevance = 0.25 → below threshold
        query_metadatas=[{
            "scenario_id": "OLD_001",
            "winning_hypothesis": "H1",
            "recommendation": "Fix it.",
            "audit_verdict": "high",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "summary": "Old scenario.",
        }],
        query_documents=["Old scenario."],
    )
    engine = MemoryEngine(chroma_client=chroma, llm_provider=provider)
    results = engine.retrieve_precedents("INC_001", "")
    assert results == []


def test_retrieve_precedents_includes_above_threshold():
    """
    Results with relevance >= RELEVANCE_THRESHOLD are included (Req 15.3).
    Distance 0.2 → relevance 0.9 — above threshold.
    """
    provider = _make_llm_provider()
    chroma = _make_chroma_client(
        count=1,
        query_ids=["PREV_001"],
        query_distances=[0.2],   # relevance = 0.9 → above threshold
        query_metadatas=[{
            "scenario_id": "PREV_001",
            "winning_hypothesis": "H1",
            "recommendation": "Roll back v4.3.",
            "audit_verdict": "high",
            "outcome_type": "observed",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "summary": "Previous payment degradation.",
        }],
        query_documents=["Previous payment degradation."],
    )
    engine = MemoryEngine(chroma_client=chroma, llm_provider=provider)
    results = engine.retrieve_precedents("INC_001", "payment issue")
    assert len(results) == 1
    assert results[0]["scenario_id"] == "PREV_001"
    assert results[0]["relevance"] == pytest.approx(0.9, abs=0.01)


# ---------------------------------------------------------------------------
# retrieve_precedents — RETRIEVAL stamp (Req 15.5)
# ---------------------------------------------------------------------------

def test_retrieve_precedents_stamps_retrieval_tag():
    """
    Retrieved precedents are stamped with MethodTag.RETRIEVAL (Req 15.5).
    """
    provider = _make_llm_provider()
    chroma = _make_chroma_client(
        count=1,
        query_ids=["PREV_001"],
        query_distances=[0.1],
        query_metadatas=[{
            "scenario_id": "PREV_001",
            "winning_hypothesis": "H1",
            "recommendation": "Rollback.",
            "audit_verdict": "high",
            "outcome_type": "observed",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "summary": "Prior investigation.",
        }],
        query_documents=["Prior investigation."],
    )
    engine = MemoryEngine(chroma_client=chroma, llm_provider=provider)
    results = engine.retrieve_precedents("INC_001", "")
    assert len(results) == 1
    assert results[0]["method"] == MethodTag.RETRIEVAL


# ---------------------------------------------------------------------------
# retrieve_precedents — sorted descending by relevance (Req 15.3)
# ---------------------------------------------------------------------------

def test_retrieve_precedents_sorted_by_relevance_descending():
    """
    Results are sorted by relevance in descending order (Req 15.3).
    """
    provider = _make_llm_provider()
    chroma = _make_chroma_client(
        count=3,
        query_ids=["A", "B", "C"],
        query_distances=[0.5, 0.1, 0.3],  # relevances: 0.75, 0.95, 0.85
        query_metadatas=[
            {"scenario_id": "A", "winning_hypothesis": "", "recommendation": "",
             "audit_verdict": "", "outcome_type": "observed", "timestamp": "", "summary": "A"},
            {"scenario_id": "B", "winning_hypothesis": "", "recommendation": "",
             "audit_verdict": "", "outcome_type": "observed", "timestamp": "", "summary": "B"},
            {"scenario_id": "C", "winning_hypothesis": "", "recommendation": "",
             "audit_verdict": "", "outcome_type": "observed", "timestamp": "", "summary": "C"},
        ],
        query_documents=["A", "B", "C"],
    )
    engine = MemoryEngine(chroma_client=chroma, llm_provider=provider)
    results = engine.retrieve_precedents("TEST", "")
    assert len(results) == 3
    relevances = [r["relevance"] for r in results]
    assert relevances == sorted(relevances, reverse=True)


# ---------------------------------------------------------------------------
# retrieve_precedents — up to MAX_RESULTS (Req 15.3)
# ---------------------------------------------------------------------------

def test_retrieve_precedents_respects_max_results():
    """
    retrieve_precedents requests at most MAX_RESULTS items from ChromaDB (Req 15.3).
    """
    provider = _make_llm_provider()
    n = MemoryEngine.MAX_RESULTS + 5  # more items than the limit
    ids = [f"S{i}" for i in range(n)]
    distances = [0.1] * n  # all above threshold
    metadatas = [
        {"scenario_id": s, "winning_hypothesis": "", "recommendation": "",
         "audit_verdict": "", "outcome_type": "observed", "timestamp": "", "summary": s}
        for s in ids
    ]
    documents = ids

    chroma = _make_chroma_client(
        count=n,
        query_ids=ids[:MemoryEngine.MAX_RESULTS],
        query_distances=distances[:MemoryEngine.MAX_RESULTS],
        query_metadatas=metadatas[:MemoryEngine.MAX_RESULTS],
        query_documents=documents[:MemoryEngine.MAX_RESULTS],
    )
    engine = MemoryEngine(chroma_client=chroma, llm_provider=provider)
    results = engine.retrieve_precedents("TEST", "")
    assert len(results) <= MemoryEngine.MAX_RESULTS


# ---------------------------------------------------------------------------
# retrieve_precedents — ChromaDB error → empty list
# ---------------------------------------------------------------------------

def test_retrieve_precedents_chroma_error_returns_empty():
    """
    When ChromaDB raises an exception, retrieve_precedents returns [] gracefully.
    """
    provider = _make_llm_provider()
    chroma = MagicMock()
    chroma.get_or_create_collection.side_effect = RuntimeError("DB error")
    engine = MemoryEngine(chroma_client=chroma, llm_provider=provider)
    results = engine.retrieve_precedents("INC_001", "")
    assert results == []


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

def test_module_store_precedent_success():
    """Module-level store_precedent returns True on success."""
    provider = _make_llm_provider()
    chroma = _make_chroma_client()
    result = _make_result()
    ok = store_precedent(result, chroma, provider)
    assert ok is True


def test_module_retrieve_precedents_empty():
    """Module-level retrieve_precedents returns [] for an empty collection."""
    provider = _make_llm_provider()
    chroma = _make_chroma_client(count=0)
    results = retrieve_precedents("INC_001", "context", chroma, provider)
    assert results == []


# ---------------------------------------------------------------------------
# ISSUE-002 Phase 1 & 2 — Memory Contamination Remediation Tests
# ---------------------------------------------------------------------------

class TestMemoryContaminationRemediation:
    def setup_method(self):
        self.provider = _make_llm_provider("Investigation summary.")

    def _make_result_with_state(self, scenario_id: str, state: AuditVerdict) -> InvestigationResult:
        abstained = (state == AuditVerdict.ABSTAIN)
        decision = Decision(
            abstained=abstained,
            recommended_action=None if abstained else "Action",
            verification_metric="metric",
            winning_hypothesis_id=None if abstained else "H1",
            persona_narrative="Narrative",
        )
        scored = [
            ScoredHypothesis(
                hypothesis_id="H1",
                final_audit_score=0.9 if state == AuditVerdict.VERIFIED else (0.6 if state == AuditVerdict.MARGINAL else (0.2 if state == AuditVerdict.REJECTED else 0.0)),
                audit_verdict=state,
            )
        ]
        return InvestigationResult(
            scenario_id=scenario_id,
            persona=Persona.ANALYST,
            decision=decision,
            scored=scored,
            telemetry=Telemetry(),
        )

    def test_a_high_outcomes_are_stored(self):
        """Test A: HIGH confidence outcomes are stored with audit_verdict=verified."""
        chroma = _make_chroma_client()
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        res = self._make_result_with_state("INC_HIGH", AuditVerdict.VERIFIED)
        assert engine.store_precedent(res) is True
        col = chroma.get_or_create_collection.return_value
        meta = col.upsert.call_args.kwargs["metadatas"][0]
        assert meta["audit_verdict"] == "verified"
        assert meta["outcome_type"] == "observed"

    def test_b_medium_outcomes_are_stored(self):
        """Test B: MEDIUM confidence outcomes are stored with audit_verdict=marginal."""
        chroma = _make_chroma_client()
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        res = self._make_result_with_state("INC_MED", AuditVerdict.MARGINAL)
        assert engine.store_precedent(res) is True
        col = chroma.get_or_create_collection.return_value
        meta = col.upsert.call_args.kwargs["metadatas"][0]
        assert meta["audit_verdict"] == "marginal"

    def test_c_low_outcomes_are_stored(self):
        """Test C: LOW confidence outcomes are stored with audit_verdict=rejected."""
        chroma = _make_chroma_client()
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        res = self._make_result_with_state("INC_LOW", AuditVerdict.REJECTED)
        assert engine.store_precedent(res) is True
        col = chroma.get_or_create_collection.return_value
        meta = col.upsert.call_args.kwargs["metadatas"][0]
        assert meta["audit_verdict"] == "rejected"

    def test_d_abstain_outcomes_are_stored(self):
        """Test D: ABSTAIN outcomes are stored with audit_verdict=abstain."""
        chroma = _make_chroma_client()
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        res = self._make_result_with_state("INC_ABSTAIN", AuditVerdict.ABSTAIN)
        assert engine.store_precedent(res) is True
        col = chroma.get_or_create_collection.return_value
        meta = col.upsert.call_args.kwargs["metadatas"][0]
        assert meta["audit_verdict"] == "abstain"

    def test_e_retrieved_precedents_preserve_original_audit_verdict(self):
        """Test E: Retrieved precedents preserve their original confidence state and retrieval weight."""
        chroma = _make_chroma_client(
            count=1,
            query_ids=["INC_002"],
            query_distances=[0.2],  # relevance 0.9
            query_metadatas=[{
                "scenario_id": "INC_002",
                "audit_verdict": "abstain",
                "original_audit_verdict": "abstain",
                "outcome_type": "observed",
                "summary": "Simultaneous causes caused abstention.",
            }],
            query_documents=["Simultaneous causes caused abstention."],
        )
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        results = engine.retrieve_precedents("INC_002")
        assert len(results) == 1
        p = results[0]
        assert p["audit_verdict"] == "abstain"
        assert p["original_audit_verdict"] == "abstain"
        assert p["retrieval_weight"] == 0.2
        assert p["retrieval_score"] == round(0.9 * 0.2, 4)

    def test_f_ranking_invariant_high_med_abstain_low(self):
        """Test F: Equivalent semantic relevance is ranked strictly HIGH (1.0) > MEDIUM (0.6) > ABSTAIN (0.2) > LOW (0.1)."""
        chroma = _make_chroma_client(
            count=4,
            query_ids=["P_LOW", "P_HIGH", "P_ABSTAIN", "P_MED"],
            query_distances=[0.2, 0.2, 0.2, 0.2],  # identical distance / relevance = 0.9
            query_metadatas=[
                {"scenario_id": "P_LOW", "audit_verdict": "low", "outcome_type": "observed"},
                {"scenario_id": "P_HIGH", "audit_verdict": "high", "outcome_type": "observed"},
                {"scenario_id": "P_ABSTAIN", "audit_verdict": "abstain", "outcome_type": "observed"},
                {"scenario_id": "P_MED", "audit_verdict": "medium", "outcome_type": "observed"},
            ],
            query_documents=["Low", "High", "Abstain", "Med"],
        )
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        results = engine.retrieve_precedents("QUERY")
        assert len(results) == 4
        ordered_ids = [r["scenario_id"] for r in results]
        assert ordered_ids == ["P_HIGH", "P_MED", "P_ABSTAIN", "P_LOW"]
        scores = [r["retrieval_score"] for r in results]
        assert scores[0] > scores[1] > scores[2] > scores[3]

    def test_g_abstain_precedents_not_discarded(self):
        """Test G: ABSTAIN precedents are retained and retrievable, not dropped due to ambiguity."""
        chroma = _make_chroma_client(
            count=1,
            query_ids=["P_ABSTAIN"],
            query_distances=[0.1],  # relevance 0.95
            query_metadatas=[{"scenario_id": "P_ABSTAIN", "audit_verdict": "abstain", "outcome_type": "observed"}],
            query_documents=["Ambiguous scenario text"],
        )
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        results = engine.retrieve_precedents("QUERY")
        assert len(results) == 1
        assert results[0]["scenario_id"] == "P_ABSTAIN"
        assert results[0]["audit_verdict"] == "abstain"

    def test_h_simulated_outcomes_excluded_from_normal_precedent_retrieval(self):
        """Test H: SIMULATED outcomes are excluded from standard observed precedent retrieval."""
        from models import OutcomeType
        chroma = _make_chroma_client(
            count=2,
            query_ids=["OBS_1", "SIM_1"],
            query_distances=[0.1, 0.1],
            query_metadatas=[
                {"scenario_id": "OBS_1", "audit_verdict": "high", "outcome_type": OutcomeType.OBSERVED.value},
                {"scenario_id": "SIM_1", "audit_verdict": "high", "outcome_type": OutcomeType.SIMULATED.value},
            ],
            query_documents=["Observed", "Simulated projection"],
        )
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        # Standard retrieval excludes SIMULATED
        results = engine.retrieve_precedents("QUERY", include_simulated=False)
        assert len(results) == 1
        assert results[0]["scenario_id"] == "OBS_1"

        # Explicit request with include_simulated=True returns both
        results_all = engine.retrieve_precedents("QUERY", include_simulated=True)
        assert len(results_all) == 2

    def test_i_e9_precedent_collections_cannot_enter_e4_evidence_retrieval(self):
        """Test I: E4 assemble_evidence rejects forbidden precedent collections."""
        from datetime import datetime, timedelta
        from engines.evidence import assemble_evidence
        from models import FreshnessStatus, SourceRegistryEntry

        entry = SourceRegistryEntry(
            source_id="support_tickets",
            name="support_tickets",
            grain="hourly",
            cadence_minutes=60,
            last_refresh=datetime.utcnow() - timedelta(minutes=5),
            sla_minutes=120,
            freshness_status=FreshnessStatus.FRESH,
            data_quality=0.9,
            lineage=[],
            owner="test",
        )
        registry = MagicMock()
        registry.get.return_value = entry

        chroma = MagicMock()
        col = MagicMock()
        chroma.get_collection.return_value = col
        col.query.return_value = {
            "ids": [["doc_1"]],
            "documents": [["text"]],
            "metadatas": [[{"source": "support_tickets"}]],
            "distances": [[0.1]],
        }

        # Attempting to pass precedent collection as allowed_collections or scenario_id
        res = assemble_evidence(
            authorized_sources=frozenset({"support_tickets"}),
            signals=[],
            registry=registry,
            db_conn=None,
            chroma_client=chroma,
            scenario_id="investigation_precedents",  # matching forbidden collection
            anomaly_window_start=datetime.utcnow() - timedelta(hours=1),
            anomaly_window_end=datetime.utcnow(),
            allowed_collections=frozenset({"investigation_precedents"}),
        )
        # Should not query ChromaDB for precedent collection
        assert res.evidence == []
        col.query.assert_not_called()

    def test_j_collection_boundary_enforced_structurally(self):
        """Test J: Structural collection contract in assemble_evidence skips unauthorized collection names."""
        from datetime import datetime, timedelta
        from engines.evidence import assemble_evidence
        from models import FreshnessStatus, SourceRegistryEntry

        entry = SourceRegistryEntry(
            source_id="support_tickets",
            name="support_tickets",
            grain="hourly",
            cadence_minutes=60,
            last_refresh=datetime.utcnow() - timedelta(minutes=5),
            sla_minutes=120,
            freshness_status=FreshnessStatus.FRESH,
            data_quality=0.9,
            lineage=[],
            owner="test",
        )
        registry = MagicMock()
        registry.get.return_value = entry

        chroma = MagicMock()
        col = MagicMock()
        chroma.get_collection.return_value = col

        # Allowed collections explicitly set to evidence_INC_001, but scenario_id is INC_002
        res = assemble_evidence(
            authorized_sources=frozenset({"support_tickets"}),
            signals=[],
            registry=registry,
            db_conn=None,
            chroma_client=chroma,
            scenario_id="INC_002",
            anomaly_window_start=datetime.utcnow() - timedelta(hours=1),
            anomaly_window_end=datetime.utcnow(),
            allowed_collections=frozenset({"evidence_INC_001"}),
        )
        assert res.evidence == []
        col.query.assert_not_called()

    def test_k_legacy_unknown_provenance_records_excluded_from_normal_retrieval(self):
        """
        Test K: Legacy records lacking outcome_type or tagged unknown are NEVER
        treated as observed historical evidence and are excluded from normal retrieval.
        """
        chroma = _make_chroma_client(
            count=3,
            query_ids=["LEGACY_NO_KEY", "LEGACY_UNKNOWN", "VALID_OBSERVED"],
            query_distances=[0.1, 0.1, 0.1],  # all high relevance (0.95)
            query_metadatas=[
                {
                    "scenario_id": "LEGACY_NO_KEY",
                    "audit_verdict": "high",
                    "summary": "Legacy record without outcome_type key.",
                },
                {
                    "scenario_id": "LEGACY_UNKNOWN",
                    "audit_verdict": "high",
                    "outcome_type": "unknown",
                    "summary": "Record with unknown outcome_type.",
                },
                {
                    "scenario_id": "VALID_OBSERVED",
                    "audit_verdict": "high",
                    "outcome_type": "observed",
                    "summary": "Properly tagged observed precedent.",
                },
            ],
            query_documents=[
                "Legacy record without outcome_type key.",
                "Record with unknown outcome_type.",
                "Properly tagged observed precedent.",
            ],
        )
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)

        # Normal retrieval (include_simulated=False) must ONLY return VALID_OBSERVED
        results = engine.retrieve_precedents("QUERY", include_simulated=False)
        assert len(results) == 1
        assert results[0]["scenario_id"] == "VALID_OBSERVED"
        assert results[0]["outcome_type"] == "observed"

        # Verify ChromaDB small-collection exact-cosine branch calls get() without where filter
        collection = chroma.get_or_create_collection.return_value
        collection.get.assert_called_once()
        assert collection.get.call_args.kwargs.get("where") is None


# ---------------------------------------------------------------------------
# ISSUE-002 Phase 3 — Human Validation Provenance Tests
# ---------------------------------------------------------------------------

class TestPhase3HumanValidation:
    """Tests L–P for ISSUE-002 Phase 3: Human Validation Provenance."""

    def setup_method(self):
        self.provider = _make_llm_provider("Investigation summary.")

    def _make_result_with_state(self, scenario_id: str, state: AuditVerdict) -> InvestigationResult:
        abstained = (state == AuditVerdict.ABSTAIN)
        decision = Decision(
            abstained=abstained,
            recommended_action=None if abstained else "Action",
            verification_metric="metric",
            winning_hypothesis_id=None if abstained else "H1",
            persona_narrative="Narrative",
        )
        scored = [
            ScoredHypothesis(
                hypothesis_id="H1",
                final_audit_score=0.9 if state == AuditVerdict.VERIFIED else 0.5,
                audit_verdict=state,
            )
        ]
        return InvestigationResult(
            scenario_id=scenario_id,
            persona=Persona.ANALYST,
            decision=decision,
            scored=scored,
            telemetry=Telemetry(),
        )

    def test_l_stored_precedents_default_to_unvalidated(self):
        """Test L: Stored precedents default to human_validated=False, validated_at=''."""
        chroma = _make_chroma_client()
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        res = self._make_result_with_state("INC_VAL_L", AuditVerdict.VERIFIED)
        assert engine.store_precedent(res) is True
        col = chroma.get_or_create_collection.return_value
        meta = col.upsert.call_args.kwargs["metadatas"][0]
        assert meta["human_validated"] is False
        assert meta["validated_at"] == ""

    def test_m_mark_validated_updates_metadata_without_changing_confidence(self):
        """Test M: mark_validated() updates human_validated without altering confidence."""
        chroma = _make_chroma_client()
        collection = chroma.get_or_create_collection.return_value
        # Simulate existing record
        collection.get.return_value = {
            "ids": ["INC_VAL_M"],
            "metadatas": [{
                "scenario_id": "INC_VAL_M",
                "audit_verdict": "high",
                "original_audit_verdict": "high",
                "human_validated": False,
                "validated_at": "",
            }],
        }
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        from datetime import datetime, timezone
        ts = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        assert engine.mark_validated("INC_VAL_M", validated_at=ts) is True

        updated_meta = collection.update.call_args.kwargs["metadatas"][0]
        assert updated_meta["human_validated"] is True
        assert updated_meta["validated_at"] == ts.isoformat()
        # Confidence NOT altered
        assert updated_meta["audit_verdict"] == "high"
        assert updated_meta["original_audit_verdict"] == "high"

    def test_n_human_validated_ranks_higher_than_unvalidated(self):
        """Test N: Human-validated precedent ranks above unvalidated with identical relevance/confidence."""
        chroma = _make_chroma_client(
            count=2,
            query_ids=["VALIDATED", "UNVALIDATED"],
            query_distances=[0.2, 0.2],  # identical relevance = 0.9
            query_metadatas=[
                {
                    "scenario_id": "VALIDATED",
                    "audit_verdict": "high",
                    "outcome_type": "observed",
                    "human_validated": True,
                    "validated_at": "2026-06-01T00:00:00+00:00",
                },
                {
                    "scenario_id": "UNVALIDATED",
                    "audit_verdict": "high",
                    "outcome_type": "observed",
                    "human_validated": False,
                    "validated_at": "",
                },
            ],
            query_documents=["Validated summary.", "Unvalidated summary."],
        )
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        results = engine.retrieve_precedents("QUERY")
        assert len(results) == 2
        assert results[0]["scenario_id"] == "VALIDATED"
        assert results[0]["human_validated"] is True
        assert results[1]["scenario_id"] == "UNVALIDATED"
        assert results[1]["human_validated"] is False
        assert results[0]["retrieval_score"] > results[1]["retrieval_score"]

    def test_o_unvalidated_high_distinguishable_from_validated_high(self):
        """Test O: Unvalidated HIGH precedents remain distinguishable from human-confirmed HIGH."""
        chroma = _make_chroma_client(
            count=2,
            query_ids=["HV_HIGH", "UV_HIGH"],
            query_distances=[0.2, 0.2],
            query_metadatas=[
                {
                    "scenario_id": "HV_HIGH",
                    "audit_verdict": "high",
                    "original_audit_verdict": "high",
                    "outcome_type": "observed",
                    "human_validated": True,
                    "validated_at": "2026-06-01T00:00:00+00:00",
                },
                {
                    "scenario_id": "UV_HIGH",
                    "audit_verdict": "high",
                    "original_audit_verdict": "high",
                    "outcome_type": "observed",
                    "human_validated": False,
                    "validated_at": "",
                },
            ],
            query_documents=["HV.", "UV."],
        )
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        results = engine.retrieve_precedents("QUERY")
        hv = next(r for r in results if r["scenario_id"] == "HV_HIGH")
        uv = next(r for r in results if r["scenario_id"] == "UV_HIGH")
        # Both are HIGH confidence, but distinguishable by human_validated
        assert hv["audit_verdict"] == uv["audit_verdict"] == "high"
        assert hv["human_validated"] is True
        assert uv["human_validated"] is False
        # Scores differ due to validation boost
        assert hv["retrieval_score"] != uv["retrieval_score"]

    def test_p_legacy_records_missing_human_validated_default_to_false(self):
        """Test P: Legacy records without human_validated field default to False on retrieval."""
        chroma = _make_chroma_client(
            count=1,
            query_ids=["LEGACY_P"],
            query_distances=[0.2],
            query_metadatas=[{
                "scenario_id": "LEGACY_P",
                "audit_verdict": "high",
                "outcome_type": "observed",
                # No human_validated or validated_at keys
            }],
            query_documents=["Legacy record."],
        )
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        results = engine.retrieve_precedents("QUERY")
        assert len(results) == 1
        assert results[0]["human_validated"] is False
        assert results[0]["validated_at"] == ""


# ---------------------------------------------------------------------------
# ISSUE-002 Phase 4 — Domain-Specific Expiry Tests
# ---------------------------------------------------------------------------

class TestPhase4DomainExpiry:
    """Tests Q–U for ISSUE-002 Phase 4: Domain-Specific Expiry."""

    def setup_method(self):
        self.provider = _make_llm_provider("Investigation summary.")
        self.retention_config = {
            "default_ttl_days": 90,
            "by_source": {
                "payment_gateway": 60,
                "marketing": 30,
                "deployment_log": 365,
            },
        }

    def test_q_unexpired_precedent_with_source_ttl_is_returned(self):
        """Test Q: Precedent within its source-specific TTL is returned normally."""
        from datetime import datetime, timezone, timedelta
        recent = (datetime.now(tz=timezone.utc) - timedelta(days=10)).isoformat()
        chroma = _make_chroma_client(
            count=1,
            query_ids=["RECENT_Q"],
            query_distances=[0.2],
            query_metadatas=[{
                "scenario_id": "RECENT_Q",
                "audit_verdict": "high",
                "outcome_type": "observed",
                "created_at": recent,
                "source_id": "payment_gateway",
            }],
            query_documents=["Recent payment gateway precedent."],
        )
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        results = engine.retrieve_precedents(
            "QUERY", retention_config=self.retention_config
        )
        assert len(results) == 1
        assert results[0]["scenario_id"] == "RECENT_Q"

    def test_r_expired_precedent_with_source_ttl_is_filtered(self):
        """Test R: Precedent beyond its source-specific TTL is filtered out."""
        from datetime import datetime, timezone, timedelta
        old = (datetime.now(tz=timezone.utc) - timedelta(days=100)).isoformat()
        chroma = _make_chroma_client(
            count=1,
            query_ids=["OLD_R"],
            query_distances=[0.2],
            query_metadatas=[{
                "scenario_id": "OLD_R",
                "audit_verdict": "high",
                "outcome_type": "observed",
                "created_at": old,
                "source_id": "payment_gateway",  # TTL = 60 days
            }],
            query_documents=["Old payment gateway precedent."],
        )
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        results = engine.retrieve_precedents(
            "QUERY", retention_config=self.retention_config
        )
        assert len(results) == 0

    def test_s_different_sources_different_ttls(self):
        """Test S: Only the source whose TTL has elapsed is filtered; the other remains."""
        from datetime import datetime, timezone, timedelta
        now = datetime.now(tz=timezone.utc)
        # marketing TTL=30 days, created 40 days ago → expired
        marketing_ts = (now - timedelta(days=40)).isoformat()
        # deployment_log TTL=365 days, created 40 days ago → valid
        deploy_ts = (now - timedelta(days=40)).isoformat()

        chroma = _make_chroma_client(
            count=2,
            query_ids=["MKTG_S", "DEPLOY_S"],
            query_distances=[0.2, 0.2],
            query_metadatas=[
                {
                    "scenario_id": "MKTG_S",
                    "audit_verdict": "high",
                    "outcome_type": "observed",
                    "created_at": marketing_ts,
                    "source_id": "marketing",
                },
                {
                    "scenario_id": "DEPLOY_S",
                    "audit_verdict": "high",
                    "outcome_type": "observed",
                    "created_at": deploy_ts,
                    "source_id": "deployment_log",
                },
            ],
            query_documents=["Marketing.", "Deploy."],
        )
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        results = engine.retrieve_precedents(
            "QUERY", retention_config=self.retention_config
        )
        assert len(results) == 1
        assert results[0]["scenario_id"] == "DEPLOY_S"

    def test_t_precedent_without_created_at_treated_as_expired(self):
        """Test T: Precedent with missing created_at is safely filtered when retention is active."""
        chroma = _make_chroma_client(
            count=1,
            query_ids=["NO_TS_T"],
            query_distances=[0.2],
            query_metadatas=[{
                "scenario_id": "NO_TS_T",
                "audit_verdict": "high",
                "outcome_type": "observed",
                # No created_at key
            }],
            query_documents=["No timestamp."],
        )
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        results = engine.retrieve_precedents(
            "QUERY", retention_config=self.retention_config
        )
        assert len(results) == 0

    def test_u_load_memory_retention_validates_schema(self):
        """Test U: load_memory_retention raises ConfigError on invalid schema."""
        import tempfile, os, yaml
        from config.loader import load_memory_retention, ConfigError

        # Missing default_ttl_days
        bad_config = {"retention": {"by_source": []}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            yaml.dump(bad_config, f)
            bad_path = f.name
        try:
            with pytest.raises(ConfigError, match="default_ttl_days"):
                load_memory_retention(bad_path)
        finally:
            os.unlink(bad_path)

        # Valid config
        good_config = {
            "retention": {
                "default_ttl_days": 90,
                "by_source": [
                    {"source_id": "orders", "ttl_days": 120},
                ],
            }
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            yaml.dump(good_config, f)
            good_path = f.name
        try:
            result = load_memory_retention(good_path)
            assert result["default_ttl_days"] == 90
            assert result["by_source"]["orders"] == 120
        finally:
            os.unlink(good_path)

    def test_v_no_expiry_filtering_when_retention_config_is_none(self):
        """Test V: Without retention_config, no expiry filtering occurs (backwards compatible)."""
        from datetime import datetime, timezone, timedelta
        very_old = (datetime.now(tz=timezone.utc) - timedelta(days=9999)).isoformat()
        chroma = _make_chroma_client(
            count=1,
            query_ids=["ANCIENT_V"],
            query_distances=[0.2],
            query_metadatas=[{
                "scenario_id": "ANCIENT_V",
                "audit_verdict": "high",
                "outcome_type": "observed",
                "created_at": very_old,
            }],
            query_documents=["Ancient record."],
        )
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        # No retention_config → no filtering
        results = engine.retrieve_precedents("QUERY", retention_config=None)
        assert len(results) == 1
        assert results[0]["scenario_id"] == "ANCIENT_V"


class TestMemoryEngineAuthorizationProvenance:
    """Tests for E9 precedent source provenance and persona entitlement filtering."""

    def setup_method(self):
        self.provider = _make_llm_provider()

    def test_store_precedent_persists_evidence_source_ids(self):
        """store_precedent derives source_ids from result.evidence and saves in metadata."""
        from models import Evidence, MethodTag
        chroma = _make_chroma_client(count=0)
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)

        result = _make_result(scenario_id="TEST_PROV_01")
        result.evidence = [
            Evidence(
                evidence_id="ev_01",
                source_id="payment_gateway",
                kind="structured",
                reliability_weight=0.99,
                relevance=0.95,
                summary="Payment pool saturated",
                raw_ref="sql://payment_events",
                method=MethodTag.SQL,
            ),
            Evidence(
                evidence_id="ev_02",
                source_id="deployment_log",
                kind="unstructured",
                reliability_weight=1.0,
                relevance=0.90,
                summary="Deploy v4.3",
                raw_ref="doc://deploy.log",
                method=MethodTag.RETRIEVAL,
            ),
        ]

        ok = engine.store_precedent(result)
        assert ok is True

        collection = chroma.get_or_create_collection.return_value
        assert collection.upsert.called
        call_kwargs = collection.upsert.call_args.kwargs
        metas = call_kwargs["metadatas"][0]
        assert "source_ids" in metas
        assert metas["source_ids"] == "deployment_log,payment_gateway"

    def test_cfo_retrieval_excludes_unauthorized_infrastructure_sources(self):
        """CFO scope (orders, inventory) excludes precedents requiring payment_gateway or deployment_log."""
        cfo_sources = frozenset({"orders", "inventory"})
        chroma = _make_chroma_client(
            count=3,
            query_ids=["INC_006", "INC_005", "INC_008"],
            query_distances=[0.1, 0.2, 0.15],
            query_metadatas=[
                {
                    "scenario_id": "INC_006",
                    "source_ids": "payment_gateway,deployment_log,support_tickets",
                    "audit_verdict": "high",
                    "outcome_type": "observed",
                    "summary": "Payment gateway connection regression.",
                },
                {
                    "scenario_id": "INC_005",
                    "source_ids": "orders,inventory",
                    "audit_verdict": "high",
                    "outcome_type": "observed",
                    "summary": "Inventory stockout across key catalog SKUs.",
                },
                {
                    "scenario_id": "INC_008",
                    "source_ids": "release_notes,support_tickets",
                    "audit_verdict": "high",
                    "outcome_type": "observed",
                    "summary": "SSO authentication failure on enterprise tenant.",
                },
            ],
            query_documents=[
                "Payment gateway regression.",
                "Inventory stockout.",
                "SSO authentication failure.",
            ],
        )
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)

        results = engine.retrieve_precedents(
            "INC_001",
            authorized_sources=cfo_sources,
            persona="cfo",
        )

        # INC_006 and INC_008 require unauthorized sources; only INC_005 (orders, inventory) is allowed
        assert len(results) == 1
        assert results[0]["scenario_id"] == "INC_005"
        assert set(results[0]["source_ids"]).issubset(cfo_sources)

    def test_analyst_retrieval_includes_cross_domain_precedents(self):
        """Analyst scope (7 sources) receives matching precedents across infrastructure & business domains."""
        analyst_sources = frozenset({
            "orders", "payment_gateway", "inventory", "marketing",
            "deployment_log", "support_tickets", "release_notes",
        })
        chroma = _make_chroma_client(
            count=3,
            query_ids=["INC_006", "INC_005", "INC_008"],
            query_distances=[0.1, 0.2, 0.15],
            query_metadatas=[
                {
                    "scenario_id": "INC_006",
                    "source_ids": "payment_gateway,deployment_log,support_tickets",
                    "audit_verdict": "high",
                    "outcome_type": "observed",
                    "summary": "Payment gateway connection regression.",
                },
                {
                    "scenario_id": "INC_005",
                    "source_ids": "orders,inventory",
                    "audit_verdict": "high",
                    "outcome_type": "observed",
                    "summary": "Inventory stockout across key catalog SKUs.",
                },
                {
                    "scenario_id": "INC_008",
                    "source_ids": "release_notes,support_tickets",
                    "audit_verdict": "high",
                    "outcome_type": "observed",
                    "summary": "SSO authentication failure.",
                },
            ],
            query_documents=["Payment issue.", "Inventory issue.", "SSO issue."],
        )
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)

        results = engine.retrieve_precedents(
            "INC_001",
            authorized_sources=analyst_sources,
            persona="analyst",
        )

        assert len(results) == 3
        for r in results:
            assert set(r["source_ids"]).issubset(analyst_sources)

    def test_fail_closed_empty_scope_blocks_all_precedents(self):
        """Empty authorization scope returns zero precedents."""
        empty_sources = frozenset()
        chroma = _make_chroma_client(
            count=1,
            query_ids=["INC_006"],
            query_distances=[0.1],
            query_metadatas=[{
                "scenario_id": "INC_006",
                "source_ids": "payment_gateway",
                "audit_verdict": "high",
                "outcome_type": "observed",
            }],
            query_documents=["Payment issue."],
        )
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)

        results = engine.retrieve_precedents(
            "INC_001",
            authorized_sources=empty_sources,
            persona="unknown",
        )
        assert len(results) == 0

    def test_fail_closed_on_missing_source_ids_under_authorization(self):
        """Precedents lacking verified source_ids fail closed under active authorization."""
        cfo_sources = frozenset({"orders", "inventory"})
        chroma = _make_chroma_client(
            count=2,
            query_ids=["LEGACY_NO_PROV", "VERIFIED_CFO"],
            query_distances=[0.1, 0.2],
            query_metadatas=[
                {
                    "scenario_id": "LEGACY_NO_PROV",
                    "audit_verdict": "high",
                    "outcome_type": "observed",
                    "source_ids": "",  # missing provenance
                    "summary": "Legacy incident without source provenance.",
                },
                {
                    "scenario_id": "VERIFIED_CFO",
                    "audit_verdict": "high",
                    "outcome_type": "observed",
                    "source_ids": "orders,inventory",  # verified provenance
                    "summary": "Verified inventory stockout precedent.",
                },
            ],
            query_documents=["Legacy incident.", "Verified precedent."],
        )
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)

        results = engine.retrieve_precedents(
            "INC_001",
            authorized_sources=cfo_sources,
            persona="cfo",
        )

        assert len(results) == 1
        assert results[0]["scenario_id"] == "VERIFIED_CFO"

    def test_controlled_fixture_ranking_quality(self):
        """
        Controlled retrieval quality fixture:
          A: Highly relevant HIGH     (dist=0.20 -> rel=0.90, conf=HIGH    -> score=0.90)
          B: Highly relevant ABSTAIN  (dist=0.16 -> rel=0.92, conf=ABSTAIN -> score=0.184)
          C: Moderately relevant HIGH (dist=0.60 -> rel=0.70, conf=HIGH    -> score=0.70)
          D: Irrelevant HIGH          (dist=1.00 -> rel=0.50, conf=HIGH    -> score=0.50 -> EXCLUDED by 0.65 threshold)

        Expected ranking order: A (0.90) > C (0.70) > B (0.184). D is excluded.
        """
        chroma = _make_chroma_client(
            count=4,
            query_ids=["PREC_A", "PREC_B", "PREC_C", "PREC_D"],
            query_distances=[0.20, 0.16, 0.60, 1.00],
            query_metadatas=[
                {
                    "scenario_id": "PREC_A",
                    "audit_verdict": "high",
                    "outcome_type": "observed",
                    "source_ids": "orders",
                    "summary": "Highly relevant confirmed root cause.",
                },
                {
                    "scenario_id": "PREC_B",
                    "audit_verdict": "abstain",
                    "outcome_type": "observed",
                    "source_ids": "orders",
                    "summary": "Highly relevant ambiguous investigation.",
                },
                {
                    "scenario_id": "PREC_C",
                    "audit_verdict": "high",
                    "outcome_type": "observed",
                    "source_ids": "orders",
                    "summary": "Moderately relevant confirmed root cause.",
                },
                {
                    "scenario_id": "PREC_D",
                    "audit_verdict": "high",
                    "outcome_type": "observed",
                    "source_ids": "orders",
                    "summary": "Irrelevant historical incident below threshold.",
                },
            ],
            query_documents=["A", "B", "C", "D"],
        )
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)

        results = engine.retrieve_precedents("QUERY")

        assert len(results) == 3
        # D is excluded because relevance 0.50 < 0.65
        assert [r["scenario_id"] for r in results] == ["PREC_A", "PREC_C", "PREC_B"]

        # Verify exact retrieval scores and metrics
        prec_a = results[0]
        prec_c = results[1]
        prec_b = results[2]

        assert prec_a["relevance"] == pytest.approx(0.90, abs=0.01)
        assert prec_a["retrieval_score"] == pytest.approx(0.90, abs=0.01)
        assert prec_a["audit_verdict"] == "high"

        assert prec_c["relevance"] == pytest.approx(0.70, abs=0.01)
        assert prec_c["retrieval_score"] == pytest.approx(0.70, abs=0.01)
        assert prec_c["audit_verdict"] == "high"

        assert prec_b["relevance"] == pytest.approx(0.92, abs=0.01)
        assert prec_b["retrieval_score"] == pytest.approx(0.184, abs=0.01)
        assert prec_b["audit_verdict"] == "abstain"


# ---------------------------------------------------------------------------
# E9 Scalability & Candidate-Pool Oversampling Tests (Round 2)
# ---------------------------------------------------------------------------

class TestE9CandidatePoolOversampling:
    """Comprehensive test suite for the benchmark-backed E9 candidate oversampling policy."""

    def setup_method(self):
        self.provider = _make_llm_provider("Candidate oversampling summary.")

    def test_multiplier_applied_correctly(self):
        """Verify ChromaDB query receives candidate_results = min(MAX_RESULTS * multiplier, count)."""
        chroma = _make_chroma_client(
            count=100,
            query_ids=[f"P_{i}" for i in range(50)],
            query_distances=[0.1] * 50,
            query_metadatas=[
                {
                    "scenario_id": f"P_{i}",
                    "audit_verdict": "high",
                    "outcome_type": "observed",
                    "source_ids": "orders",
                }
                for i in range(50)
            ],
            query_documents=["Doc"] * 50,
        )
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider, candidate_multiplier=5)
        engine.retrieve_precedents("QUERY")

        collection = chroma.get_or_create_collection.return_value
        collection.query.assert_called_once()
        # With MAX_RESULTS=10 and multiplier=5, n_results must be 50
        assert collection.query.call_args.kwargs.get("n_results") == 50
        assert collection.query.call_args.kwargs.get("where") is None

    def test_explicit_runtime_multiplier_override(self):
        """Verify candidate_multiplier argument in retrieve_precedents overrides constructor default."""
        chroma = _make_chroma_client(
            count=100,
            query_ids=[f"P_{i}" for i in range(20)],
            query_distances=[0.1] * 20,
            query_metadatas=[
                {
                    "scenario_id": f"P_{i}",
                    "audit_verdict": "high",
                    "outcome_type": "observed",
                    "source_ids": "orders",
                }
                for i in range(20)
            ],
            query_documents=["Doc"] * 20,
        )
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider, candidate_multiplier=5)
        engine.retrieve_precedents("QUERY", candidate_multiplier=2)

        collection = chroma.get_or_create_collection.return_value
        assert collection.query.call_args.kwargs.get("n_results") == 20

    def test_env_var_multiplier_override(self, monkeypatch):
        """Verify E9_CANDIDATE_MULTIPLIER environment variable is respected."""
        monkeypatch.setenv("E9_CANDIDATE_MULTIPLIER", "3")
        import importlib
        import engines.memory
        importlib.reload(engines.memory)

        chroma = _make_chroma_client(
            count=100,
            query_ids=[f"P_{i}" for i in range(30)],
            query_distances=[0.1] * 30,
            query_metadatas=[
                {
                    "scenario_id": f"P_{i}",
                    "audit_verdict": "high",
                    "outcome_type": "observed",
                    "source_ids": "orders",
                }
                for i in range(30)
            ],
            query_documents=["Doc"] * 30,
        )
        engine = engines.memory.MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        engine.retrieve_precedents("QUERY")

        collection = chroma.get_or_create_collection.return_value
        assert collection.query.call_args.kwargs.get("n_results") == 30


    def test_final_result_count_bounded_by_max_results(self):
        """Verify that even with 50 returned candidates, output is truncated to MAX_RESULTS (10)."""
        chroma = _make_chroma_client(
            count=100,
            query_ids=[f"P_{i}" for i in range(50)],
            query_distances=[0.1] * 50,
            query_metadatas=[
                {
                    "scenario_id": f"P_{i}",
                    "audit_verdict": "high",
                    "outcome_type": "observed",
                    "source_ids": "orders",
                }
                for i in range(50)
            ],
            query_documents=["Doc"] * 50,
        )
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider, candidate_multiplier=5)
        results = engine.retrieve_precedents("QUERY")
        assert len(results) == 10

    def test_simulated_and_unknown_records_excluded_by_python(self):
        """Verify simulated and unknown provenance records in candidate pool are dropped by Python."""
        chroma = _make_chroma_client(
            count=10,
            query_ids=["SIM_1", "UNK_2", "OBS_3"],
            query_distances=[0.05, 0.06, 0.07],
            query_metadatas=[
                {"scenario_id": "SIM_1", "outcome_type": "simulated", "audit_verdict": "high", "source_ids": "orders"},
                {"scenario_id": "UNK_2", "outcome_type": "unknown", "audit_verdict": "high", "source_ids": "orders"},
                {"scenario_id": "OBS_3", "outcome_type": "observed", "audit_verdict": "high", "source_ids": "orders"},
            ],
            query_documents=["Sim", "Unk", "Obs"],
        )
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        results = engine.retrieve_precedents("QUERY", include_simulated=False)
        assert len(results) == 1
        assert results[0]["scenario_id"] == "OBS_3"

    def test_unauthorized_sources_fail_closed_in_oversampled_pool(self):
        """Verify unauthorized candidates are dropped by Python entitlement checks."""
        chroma = _make_chroma_client(
            count=10,
            query_ids=["UNAUTH_1", "AUTH_2"],
            query_distances=[0.05, 0.10],
            query_metadatas=[
                {"scenario_id": "UNAUTH_1", "outcome_type": "observed", "audit_verdict": "high", "source_ids": "support_tickets,deployment_log"},
                {"scenario_id": "AUTH_2", "outcome_type": "observed", "audit_verdict": "high", "source_ids": "orders,inventory"},
            ],
            query_documents=["Unauth", "Auth"],
        )
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        results = engine.retrieve_precedents("QUERY", authorized_sources=frozenset(["orders", "inventory"]))
        assert len(results) == 1
        assert results[0]["scenario_id"] == "AUTH_2"

    def test_recall_under_controlled_adversarial_noise(self):
        """
        Verify that when 15 noise candidates (simulated/unauthorized) rank ahead of 5 valid candidates,
        x1 multiplier fails (drops valid candidates) while x5 multiplier achieves 100% recall.
        """
        noise_ids = [f"NOISE_{i}" for i in range(15)]
        noise_distances = [0.01 + i * 0.005 for i in range(15)] # highly similar noise
        noise_metas = [
            {"scenario_id": f"NOISE_{i}", "outcome_type": "simulated", "audit_verdict": "high", "source_ids": "orders"}
            for i in range(15)
        ]

        valid_ids = [f"VALID_{i}" for i in range(5)]
        valid_distances = [0.15 + i * 0.01 for i in range(5)]
        valid_metas = [
            {"scenario_id": f"VALID_{i}", "outcome_type": "observed", "audit_verdict": "high", "source_ids": "orders"}
            for i in range(5)
        ]

        all_ids = noise_ids + valid_ids
        all_distances = noise_distances + valid_distances
        all_metas = noise_metas + valid_metas
        all_docs = ["Doc"] * 20

        # Scenario A: Multiplier x1 queries top 10 -> receives only 10 noise records -> 0% recall
        chroma_x1 = _make_chroma_client(
            count=20,
            query_ids=all_ids[:10],
            query_distances=all_distances[:10],
            query_metadatas=all_metas[:10],
            query_documents=all_docs[:10],
        )
        engine_x1 = MemoryEngine(chroma_client=chroma_x1, llm_provider=self.provider, candidate_multiplier=1)
        res_x1 = engine_x1.retrieve_precedents("QUERY")
        assert len(res_x1) == 0  # all 10 were noise

        # Scenario B: Multiplier x5 queries top 20 -> receives all 20 records -> 100% recall of valid
        chroma_x5 = _make_chroma_client(
            count=20,
            query_ids=all_ids,
            query_distances=all_distances,
            query_metadatas=all_metas,
            query_documents=all_docs,
        )
        engine_x5 = MemoryEngine(chroma_client=chroma_x5, llm_provider=self.provider, candidate_multiplier=5)
        res_x5 = engine_x5.retrieve_precedents("QUERY")
        assert len(res_x5) == 5
        assert {r["scenario_id"] for r in res_x5} == {f"VALID_{i}" for i in range(5)}




