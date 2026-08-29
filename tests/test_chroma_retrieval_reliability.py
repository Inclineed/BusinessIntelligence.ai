import pytest
import numpy as np
from unittest.mock import MagicMock
from datetime import datetime, timedelta

from models import (
    SourceRegistryEntry,
    FreshnessStatus,
    MethodTag,
    AuditVerdict,
    OutcomeType,
)
from config.registry import SourceRegistry
from security.entitlements import AuthorizationScope
from engines.evidence import assemble_evidence, _assemble_unstructured
from engines.memory import MemoryEngine


def _make_llm_provider(summary_text: str = "Test summary.") -> MagicMock:
    provider = MagicMock()
    llm_response = MagicMock()
    llm_response.text = summary_text
    provider.complete.return_value = llm_response
    provider.embed.return_value = [[0.1, 0.2, 0.3]]
    return provider


def _make_source_entry(source_id: str = "support_tickets") -> SourceRegistryEntry:
    return SourceRegistryEntry(
        source_id=source_id,
        name=source_id.replace("_", " ").title(),
        grain="hourly",
        cadence_minutes=60,
        last_refresh=datetime.utcnow() - timedelta(minutes=15),
        sla_minutes=60,
        freshness_status=FreshnessStatus.FRESH,
        data_quality=0.90,
        lineage=[],
        owner="test",
    )


def _make_registry(entries: list[SourceRegistryEntry]) -> SourceRegistry:
    reg = SourceRegistry([])
    for e in entries:
        reg._entries[e.source_id] = e
    return reg


def _generate_synthetic_embeddings(query_vector: list[float], distances: list[float]) -> list[list[float]]:
    """Generate exact unit vectors that produce specified cosine distances when dotted with query_vector."""
    q_raw = np.array(query_vector, dtype=np.float32)
    q = q_raw / np.linalg.norm(q_raw)

    rand_vec = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    if abs(np.dot(rand_vec, q)) > 0.9:
        rand_vec = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    u = rand_vec - np.dot(rand_vec, q) * q
    u = u / np.linalg.norm(u)

    embeddings = []
    for d in distances:
        s = 1.0 - float(d)
        y = float(np.sqrt(max(0.0, 1.0 - s**2)))
        doc_vec = (s * q + y * u).tolist()
        embeddings.append(doc_vec)
    return embeddings


# ---------------------------------------------------------------------------
# Test Suite A–E: E4 Unstructured Evidence Retrieval Reliability
# ---------------------------------------------------------------------------

class TestE4ChromaRetrievalReliability:

    def setup_method(self):
        self.entry = _make_source_entry("support_tickets")
        self.registry = _make_registry([self.entry])
        self.scope = AuthorizationScope(
            persona="analyst",
            authorized_sources=frozenset(["support_tickets"]),
        )
        self.provider = MagicMock()
        self.provider.embed.return_value = [[0.1, 0.2, 0.3]]
        self.query_vec = [0.1, 0.2, 0.3]
        self.start = datetime.utcnow() - timedelta(hours=2)
        self.end = datetime.utcnow()

    def test_a_collection_large_filtered_subset_small_exact_cosine(self):
        """
        Case A: Collection has >50 total documents, but filtered candidate count <= 100 (e.g. 4 docs).
        Must use exact NumPy cosine ranking via collection.get() and MUST NOT call collection.query().
        """
        chroma = MagicMock()
        collection = MagicMock()
        chroma.get_collection.return_value = collection
        collection.count.return_value = 80

        # Filtered subset has 4 items with distinct distances: 0.10, 0.40, 0.20, 0.70
        doc_ids = ["doc_1", "doc_2", "doc_3", "doc_4"]
        target_distances = [0.10, 0.40, 0.20, 0.70]
        embs = _generate_synthetic_embeddings(self.query_vec, target_distances)

        collection.get.return_value = {
            "ids": doc_ids,
            "documents": [f"Ticket text {i}" for i in range(4)],
            "metadatas": [{"source": "support_tickets"}] * 4,
            "embeddings": embs,
        }

        result = assemble_evidence(
            authorized_sources=self.scope.authorized_sources,
            signals=[],
            registry=self.registry,
            db_conn=None,
            chroma_client=chroma,
            scenario_id="INC_001",
            anomaly_window_start=self.start,
            anomaly_window_end=self.end,
            provider=self.provider,
        )

        # HNSW query() must NOT be called
        collection.query.assert_not_called()
        collection.get.assert_called_once()

        # Evidence must be exactly ranked by cosine distance (0.10 -> 0.20 -> 0.40 -> 0.70)
        assert len(result.evidence) == 4
        ranked_ids = [e.raw_ref for e in result.evidence]
        assert ranked_ids == ["doc_1", "doc_3", "doc_2", "doc_4"]

        # Relevance scores should be exact: clamp(1 - distance, 0, 1)
        expected_relevances = [0.90, 0.80, 0.60, 0.30]
        for ev, exp_rel in zip(result.evidence, expected_relevances):
            assert ev.confidence == pytest.approx(exp_rel, abs=1e-3)

    def test_b_collection_large_filtered_subset_large_exact_cosine(self):
        """
        Case B: Collection has >100 filtered documents matching metadata filter (e.g. 120 docs).
        Computes exact cosine ranking across all filtered candidates in NumPy without HNSW contiguity errors.
        """
        chroma = MagicMock()
        collection = MagicMock()
        chroma.get_collection.return_value = collection
        collection.count.return_value = 150

        doc_ids = [f"doc_{i}" for i in range(120)]
        target_dists = [0.05 + 0.01 * i for i in range(120)]
        embs = _generate_synthetic_embeddings(self.query_vec, target_dists)

        collection.get.return_value = {
            "ids": doc_ids,
            "documents": [f"Doc {i}" for i in range(120)],
            "metadatas": [{"source": "support_tickets"}] * 120,
            "embeddings": embs,
        }

        result = assemble_evidence(
            authorized_sources=self.scope.authorized_sources,
            signals=[],
            registry=self.registry,
            db_conn=None,
            chroma_client=chroma,
            scenario_id="INC_001",
            anomaly_window_start=self.start,
            anomaly_window_end=self.end,
            provider=self.provider,
        )

        # HNSW query() must NOT be called; exact cosine ranks top 5
        collection.query.assert_not_called()
        assert len(result.evidence) == 5
        assert [e.raw_ref for e in result.evidence] == ["doc_0", "doc_1", "doc_2", "doc_3", "doc_4"]

    def test_c_collection_small_exact_cosine(self):
        """
        Case C: Small collection (total count <= 50).
        Uses exact cosine directly without HNSW.
        """
        chroma = MagicMock()
        collection = MagicMock()
        chroma.get_collection.return_value = collection
        collection.count.return_value = 10

        doc_ids = ["d1", "d2"]
        embs = _generate_synthetic_embeddings(self.query_vec, [0.15, 0.05])
        collection.get.return_value = {
            "ids": doc_ids,
            "documents": ["Text 1", "Text 2"],
            "metadatas": [{"source": "support_tickets"}, {"source": "support_tickets"}],
            "embeddings": embs,
        }

        result = assemble_evidence(
            authorized_sources=self.scope.authorized_sources,
            signals=[],
            registry=self.registry,
            db_conn=None,
            chroma_client=chroma,
            scenario_id="INC_001",
            anomaly_window_start=self.start,
            anomaly_window_end=self.end,
            provider=self.provider,
        )

        collection.query.assert_not_called()
        assert [e.raw_ref for e in result.evidence] == ["d2", "d1"]

    def test_d_metadata_filter_no_matches_clean_empty(self):
        """
        Case D: Metadata filter matches 0 documents.
        Returns clean empty list without exception or dummy results.
        """
        chroma = MagicMock()
        collection = MagicMock()
        chroma.get_collection.return_value = collection
        collection.count.return_value = 20

        # No matching documents for authorized source
        collection.get.return_value = {
            "ids": [],
            "documents": [],
            "metadatas": [],
            "embeddings": [],
        }

        result = assemble_evidence(
            authorized_sources=self.scope.authorized_sources,
            signals=[],
            registry=self.registry,
            db_conn=None,
            chroma_client=chroma,
            scenario_id="INC_001",
            anomaly_window_start=self.start,
            anomaly_window_end=self.end,
            provider=self.provider,
        )

        collection.query.assert_not_called()
        assert len(result.evidence) == 0
        assert result.dropped_count == 0

    def test_e_hnsw_failure_safe_degraded_fallback_no_fabricated_distances(self):
        """
        Case E: When HNSW throws RuntimeError, emergency fallback must NOT fabricate 0.1 distances.
        It must compute exact cosine on available embeddings or assign neutral 0.5 baseline distance.
        """
        chroma = MagicMock()
        collection = MagicMock()
        chroma.get_collection.return_value = collection
        collection.count.value = 150

        # Initial get says 120 documents (>100)
        collection.get.side_effect = [
            {
                "ids": [f"doc_{i}" for i in range(120)],
                "documents": [f"Doc {i}" for i in range(120)],
                "metadatas": [{"source": "support_tickets"}] * 120,
                "embeddings": None,
            },
            # Fallback get when HNSW fails: missing embeddings
            {
                "ids": ["fb_1", "fb_2"],
                "documents": ["Fallback 1", "Fallback 2"],
                "metadatas": [{"source": "support_tickets"}, {"source": "support_tickets"}],
                "embeddings": None,
            }
        ]

        collection.query.side_effect = RuntimeError("Cannot return the results in a contigious 2D array. Probably ef or M is too small")

        result = assemble_evidence(
            authorized_sources=self.scope.authorized_sources,
            signals=[],
            registry=self.registry,
            db_conn=None,
            chroma_client=chroma,
            scenario_id="INC_001",
            anomaly_window_start=self.start,
            anomaly_window_end=self.end,
            provider=self.provider,
        )

        assert len(result.evidence) == 5
        # Verify distance is neutral 0.5 (relevance = 1.0 - 0.5 = 0.5), NEVER synthetic 0.9 (from distance 0.1)
        for ev in result.evidence:
            assert ev.confidence == pytest.approx(0.5, abs=1e-3)

    def test_h_missing_embeddings_explicit_neutral_distance(self):
        """
        Case H: Small collection has documents but embeddings are None in database.
        Must assign neutral baseline distance 0.5 (relevance 0.5) without crashing.
        """
        chroma = MagicMock()
        collection = MagicMock()
        chroma.get_collection.return_value = collection
        collection.count.return_value = 5

        collection.get.return_value = {
            "ids": ["doc_no_emb_1", "doc_no_emb_2"],
            "documents": ["Doc with no vector 1", "Doc with no vector 2"],
            "metadatas": [{"source": "support_tickets"}, {"source": "support_tickets"}],
            "embeddings": None,
        }

        result = assemble_evidence(
            authorized_sources=self.scope.authorized_sources,
            signals=[],
            registry=self.registry,
            db_conn=None,
            chroma_client=chroma,
            scenario_id="INC_001",
            anomaly_window_start=self.start,
            anomaly_window_end=self.end,
            provider=self.provider,
        )

        assert len(result.evidence) == 2
        for ev in result.evidence:
            assert ev.confidence == pytest.approx(0.5, abs=1e-3)

        assert len(result.evidence) == 2
        for ev in result.evidence:
            assert ev.confidence == pytest.approx(0.5, abs=1e-3)


# ---------------------------------------------------------------------------
# Test Suite F–G: E9 Precedent Memory Retrieval Reliability
# ---------------------------------------------------------------------------

class TestE9ChromaRetrievalReliability:

    def setup_method(self):
        self.provider = _make_llm_provider("Test query summary")
        self.query_vec = [0.1, 0.2, 0.3]

    def test_f_e9_collection_small_exact_cosine_no_hnsw_query(self):
        """
        Case F: Precedent collection has count <= 50 (e.g. 5 precedents).
        Must use exact cosine NumPy ranking via collection.get() and NOT call collection.query().
        """
        chroma = MagicMock()
        collection = MagicMock()
        chroma.get_or_create_collection.return_value = collection
        collection.count.return_value = 5

        ids = ["PREC_1", "PREC_2", "PREC_3"]
        distances = [0.20, 0.05, 0.50]  # PREC_2 closest (d=0.05)
        embs = _generate_synthetic_embeddings(self.query_vec, distances)

        collection.get.return_value = {
            "ids": ids,
            "documents": ["Doc 1", "Doc 2", "Doc 3"],
            "metadatas": [
                {"scenario_id": "PREC_1", "outcome_type": "observed", "audit_verdict": "verified"},
                {"scenario_id": "PREC_2", "outcome_type": "observed", "audit_verdict": "verified"},
                {"scenario_id": "PREC_3", "outcome_type": "observed", "audit_verdict": "verified"},
            ],
            "embeddings": embs,
        }

        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider)
        results = engine.retrieve_precedents("QUERY")

        # HNSW query() must NOT be called for count <= 50
        collection.query.assert_not_called()
        collection.get.assert_called_once()

        assert len(results) == 3
        # PREC_2 has lowest distance (0.05) -> highest relevance -> ranks first
        assert [r["scenario_id"] for r in results] == ["PREC_2", "PREC_1", "PREC_3"]
        assert results[0]["relevance"] == pytest.approx(1.0 - 0.05/2.0, abs=1e-3)

    def test_g_e9_collection_large_hnsw_query_preserved(self):
        """
        Case G: Precedent collection has count > 50 (e.g. 100 precedents).
        HNSW vector query is called with candidate oversampling.
        """
        chroma = MagicMock()
        collection = MagicMock()
        chroma.get_or_create_collection.return_value = collection
        collection.count.return_value = 100

        collection.query.return_value = {
            "ids": [["PREC_10", "PREC_20"]],
            "distances": [[0.10, 0.15]],
            "metadatas": [[
                {"scenario_id": "PREC_10", "outcome_type": "observed", "audit_verdict": "verified"},
                {"scenario_id": "PREC_20", "outcome_type": "observed", "audit_verdict": "verified"},
            ]],
            "documents": [["Doc 10", "Doc 20"]],
        }

        engine = MemoryEngine(chroma_client=chroma, llm_provider=self.provider, candidate_multiplier=5)
        results = engine.retrieve_precedents("QUERY")

        collection.query.assert_called_once()
        assert collection.query.call_args.kwargs.get("n_results") == 50
        assert len(results) == 2
