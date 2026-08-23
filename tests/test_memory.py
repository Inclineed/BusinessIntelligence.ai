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
    ConfidenceState,
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
        final_score=0.85,
        confidence_state=ConfidenceState.HIGH,
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

    The collection's query() returns the given ids/distances/metadatas/documents.
    """
    collection = MagicMock()
    collection.count.return_value = count

    if upsert_raises is not None:
        collection.upsert.side_effect = upsert_raises
    else:
        collection.upsert.return_value = None

    query_result = {
        "ids": [query_ids or []],
        "distances": [query_distances or []],
        "metadatas": [query_metadatas or []],
        "documents": [query_documents or []],
    }
    collection.query.return_value = query_result

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
            "confidence_state": "high",
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
            "confidence_state": "high",
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
            "confidence_state": "high",
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
             "confidence_state": "", "timestamp": "", "summary": "A"},
            {"scenario_id": "B", "winning_hypothesis": "", "recommendation": "",
             "confidence_state": "", "timestamp": "", "summary": "B"},
            {"scenario_id": "C", "winning_hypothesis": "", "recommendation": "",
             "confidence_state": "", "timestamp": "", "summary": "C"},
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
         "confidence_state": "", "timestamp": "", "summary": s}
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

    def _make_result_with_state(self, scenario_id: str, state: ConfidenceState) -> InvestigationResult:
        abstained = (state == ConfidenceState.ABSTAIN)
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
                final_score=0.9 if state == ConfidenceState.HIGH else (0.6 if state == ConfidenceState.MEDIUM else (0.2 if state == ConfidenceState.LOW else 0.0)),
                confidence_state=state,
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
        """Test A: HIGH confidence outcomes are stored with confidence_state=high."""
        chroma = _make_chroma_client()
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        res = self._make_result_with_state("INC_HIGH", ConfidenceState.HIGH)
        assert engine.store_precedent(res) is True
        col = chroma.get_or_create_collection.return_value
        meta = col.upsert.call_args.kwargs["metadatas"][0]
        assert meta["confidence_state"] == "high"
        assert meta["outcome_type"] == "observed"

    def test_b_medium_outcomes_are_stored(self):
        """Test B: MEDIUM confidence outcomes are stored with confidence_state=medium."""
        chroma = _make_chroma_client()
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        res = self._make_result_with_state("INC_MED", ConfidenceState.MEDIUM)
        assert engine.store_precedent(res) is True
        col = chroma.get_or_create_collection.return_value
        meta = col.upsert.call_args.kwargs["metadatas"][0]
        assert meta["confidence_state"] == "medium"

    def test_c_low_outcomes_are_stored(self):
        """Test C: LOW confidence outcomes are stored with confidence_state=low."""
        chroma = _make_chroma_client()
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        res = self._make_result_with_state("INC_LOW", ConfidenceState.LOW)
        assert engine.store_precedent(res) is True
        col = chroma.get_or_create_collection.return_value
        meta = col.upsert.call_args.kwargs["metadatas"][0]
        assert meta["confidence_state"] == "low"

    def test_d_abstain_outcomes_are_stored(self):
        """Test D: ABSTAIN outcomes are stored with confidence_state=abstain."""
        chroma = _make_chroma_client()
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        res = self._make_result_with_state("INC_ABSTAIN", ConfidenceState.ABSTAIN)
        assert engine.store_precedent(res) is True
        col = chroma.get_or_create_collection.return_value
        meta = col.upsert.call_args.kwargs["metadatas"][0]
        assert meta["confidence_state"] == "abstain"

    def test_e_retrieved_precedents_preserve_original_confidence_state(self):
        """Test E: Retrieved precedents preserve their original confidence state and retrieval weight."""
        chroma = _make_chroma_client(
            count=1,
            query_ids=["INC_002"],
            query_distances=[0.2],  # relevance 0.9
            query_metadatas=[{
                "scenario_id": "INC_002",
                "confidence_state": "abstain",
                "original_confidence_state": "abstain",
                "outcome_type": "observed",
                "summary": "Simultaneous causes caused abstention.",
            }],
            query_documents=["Simultaneous causes caused abstention."],
        )
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        results = engine.retrieve_precedents("INC_002")
        assert len(results) == 1
        p = results[0]
        assert p["confidence_state"] == "abstain"
        assert p["original_confidence_state"] == "abstain"
        assert p["retrieval_weight"] == 0.2
        assert p["retrieval_score"] == round(0.9 * 0.2, 4)

    def test_f_ranking_invariant_high_med_abstain_low(self):
        """Test F: Equivalent semantic relevance is ranked strictly HIGH (1.0) > MEDIUM (0.6) > ABSTAIN (0.2) > LOW (0.1)."""
        chroma = _make_chroma_client(
            count=4,
            query_ids=["P_LOW", "P_HIGH", "P_ABSTAIN", "P_MED"],
            query_distances=[0.2, 0.2, 0.2, 0.2],  # identical distance / relevance = 0.9
            query_metadatas=[
                {"scenario_id": "P_LOW", "confidence_state": "low", "outcome_type": "observed"},
                {"scenario_id": "P_HIGH", "confidence_state": "high", "outcome_type": "observed"},
                {"scenario_id": "P_ABSTAIN", "confidence_state": "abstain", "outcome_type": "observed"},
                {"scenario_id": "P_MED", "confidence_state": "medium", "outcome_type": "observed"},
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
            query_metadatas=[{"scenario_id": "P_ABSTAIN", "confidence_state": "abstain", "outcome_type": "observed"}],
            query_documents=["Ambiguous scenario text"],
        )
        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        results = engine.retrieve_precedents("QUERY")
        assert len(results) == 1
        assert results[0]["scenario_id"] == "P_ABSTAIN"
        assert results[0]["confidence_state"] == "abstain"

    def test_h_simulated_outcomes_excluded_from_normal_precedent_retrieval(self):
        """Test H: SIMULATED outcomes are excluded from standard observed precedent retrieval."""
        from models import OutcomeType
        chroma = _make_chroma_client(
            count=2,
            query_ids=["OBS_1", "SIM_1"],
            query_distances=[0.1, 0.1],
            query_metadatas=[
                {"scenario_id": "OBS_1", "confidence_state": "high", "outcome_type": OutcomeType.OBSERVED.value},
                {"scenario_id": "SIM_1", "confidence_state": "high", "outcome_type": OutcomeType.SIMULATED.value},
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
