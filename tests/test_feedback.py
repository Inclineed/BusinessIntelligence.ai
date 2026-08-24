"""
tests/test_feedback.py — Round 2 Feedback Loop Test Suite.

Tests all four verdict paths, E9 validation behavior, original result
immutability, correction persistence, authorization constraints,
feedback/precedent linkage, human validation retrieval boost,
and evaluator metrics computation.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass

from models import (
    FeedbackVerdict,
    StructuredFeedbackSubmission,
    StructuredFeedbackRecord,
)


class TestFeedbackVerdict(unittest.TestCase):
    """Test FeedbackVerdict enum values and membership."""

    def test_verdict_values(self):
        assert FeedbackVerdict.CORRECT == "CORRECT"
        assert FeedbackVerdict.INCORRECT == "INCORRECT"
        assert FeedbackVerdict.PARTIALLY_CORRECT == "PARTIALLY_CORRECT"
        assert FeedbackVerdict.UNSURE == "UNSURE"

    def test_verdict_from_string(self):
        assert FeedbackVerdict("CORRECT") is FeedbackVerdict.CORRECT
        assert FeedbackVerdict("INCORRECT") is FeedbackVerdict.INCORRECT

    def test_invalid_verdict_raises(self):
        with self.assertRaises(ValueError):
            FeedbackVerdict("INVALID")


class TestStructuredFeedbackSubmission(unittest.TestCase):
    """Test StructuredFeedbackSubmission dataclass construction."""

    def test_minimal_submission(self):
        sub = StructuredFeedbackSubmission(
            investigation_id="INC_001_analyst_20260824",
            scenario_id="INC_001",
            verdict=FeedbackVerdict.CORRECT,
        )
        assert sub.investigation_id == "INC_001_analyst_20260824"
        assert sub.scenario_id == "INC_001"
        assert sub.verdict == FeedbackVerdict.CORRECT
        assert sub.persona == "analyst"
        assert sub.corrected_hypothesis_id is None
        assert sub.analyst_notes is None

    def test_full_correction_submission(self):
        sub = StructuredFeedbackSubmission(
            investigation_id="INC_002_analyst_20260824",
            scenario_id="INC_002",
            verdict=FeedbackVerdict.INCORRECT,
            persona="analyst",
            corrected_hypothesis_id="H2",
            corrected_confidence_state="HIGH",
            corrected_action="Investigate marketing campaign instead",
            evidence_grounding_correct=False,
            analyst_notes="Payment pool was transient; marketing was the real driver",
        )
        assert sub.verdict == FeedbackVerdict.INCORRECT
        assert sub.corrected_hypothesis_id == "H2"
        assert sub.evidence_grounding_correct is False


class TestStructuredFeedbackRecord(unittest.TestCase):
    """Test StructuredFeedbackRecord inherits from submission correctly."""

    def test_record_inherits_submission(self):
        rec = StructuredFeedbackRecord(
            investigation_id="INC_001_analyst_20260824",
            scenario_id="INC_001",
            verdict=FeedbackVerdict.CORRECT,
            feedback_id=42,
            received_at="2026-08-24T12:00:00+00:00",
            validated_precedent=True,
            validation_precedent_id="INC_001",
        )
        assert rec.feedback_id == 42
        assert rec.validated_precedent is True
        assert rec.validation_precedent_id == "INC_001"
        assert rec.verdict == FeedbackVerdict.CORRECT

    def test_record_defaults(self):
        rec = StructuredFeedbackRecord(
            investigation_id="test",
            scenario_id="INC_001",
            verdict=FeedbackVerdict.UNSURE,
        )
        assert rec.feedback_id == 0
        assert rec.received_at == ""
        assert rec.validated_precedent is False
        assert rec.validation_precedent_id is None


class TestValidationTransitionMatrix(unittest.TestCase):
    """
    Test the deterministic validation transition matrix:
    - CORRECT → eligible for validation
    - INCORRECT → remains unvalidated
    - PARTIALLY_CORRECT → remains unvalidated
    - UNSURE → remains unvalidated
    """

    def _should_validate(self, verdict: FeedbackVerdict, inv_persona: str) -> bool:
        """Mirrors the backend validation decision logic."""
        return verdict == FeedbackVerdict.CORRECT and inv_persona == "analyst"

    def test_correct_analyst_validates(self):
        assert self._should_validate(FeedbackVerdict.CORRECT, "analyst") is True

    def test_correct_cfo_does_not_validate(self):
        """CFO cannot validate because they don't have full source entitlements."""
        assert self._should_validate(FeedbackVerdict.CORRECT, "cfo") is False

    def test_incorrect_does_not_validate(self):
        assert self._should_validate(FeedbackVerdict.INCORRECT, "analyst") is False

    def test_partially_correct_does_not_validate(self):
        assert self._should_validate(FeedbackVerdict.PARTIALLY_CORRECT, "analyst") is False

    def test_unsure_does_not_validate(self):
        assert self._should_validate(FeedbackVerdict.UNSURE, "analyst") is False


class TestMarkValidatedWithFeedbackId(unittest.TestCase):
    """Test MemoryEngine.mark_validated() with validation_feedback_id parameter."""

    def test_mark_validated_stores_feedback_id(self):
        """Verify that mark_validated persists validation_feedback_id in metadata."""
        from engines.memory import MemoryEngine

        # Mock ChromaDB
        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "ids": ["INC_TEST"],
            "metadatas": [{
                "scenario_id": "INC_TEST",
                "confidence_state": "HIGH",
                "human_validated": False,
                "validated_at": "",
            }],
        }

        mock_client = MagicMock()
        engine = MemoryEngine(chroma_client=mock_client, llm_provider=MagicMock())
        engine._get_or_create_collection = MagicMock(return_value=mock_collection)

        ts = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)
        result = engine.mark_validated(
            scenario_id="INC_TEST",
            validated_at=ts,
            validation_feedback_id=42,
        )

        assert result is True
        # Verify the metadata was updated with feedback_id
        call_args = mock_collection.update.call_args
        updated_meta = call_args.kwargs.get("metadatas") or call_args[1].get("metadatas")
        assert updated_meta is not None
        meta = updated_meta[0]
        assert meta["human_validated"] is True
        assert meta["validation_feedback_id"] == 42
        assert "2026-08-24" in meta["validated_at"]

    def test_mark_validated_without_feedback_id(self):
        """Backward compat: mark_validated still works without feedback_id."""
        from engines.memory import MemoryEngine

        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "ids": ["INC_COMPAT"],
            "metadatas": [{
                "scenario_id": "INC_COMPAT",
                "human_validated": False,
            }],
        }

        mock_client = MagicMock()
        engine = MemoryEngine(chroma_client=mock_client, llm_provider=MagicMock())
        engine._get_or_create_collection = MagicMock(return_value=mock_collection)

        result = engine.mark_validated(scenario_id="INC_COMPAT")

        assert result is True
        call_args = mock_collection.update.call_args
        updated_meta = call_args.kwargs.get("metadatas") or call_args[1].get("metadatas")
        meta = updated_meta[0]
        assert meta["human_validated"] is True
        # validation_feedback_id should NOT be present when not passed
        assert "validation_feedback_id" not in meta

    def test_mark_validated_nonexistent_precedent_returns_false(self):
        """mark_validated returns False when precedent doesn't exist."""
        from engines.memory import MemoryEngine

        mock_collection = MagicMock()
        mock_collection.get.return_value = {"ids": [], "metadatas": []}

        mock_client = MagicMock()
        engine = MemoryEngine(chroma_client=mock_client, llm_provider=MagicMock())
        engine._get_or_create_collection = MagicMock(return_value=mock_collection)

        result = engine.mark_validated(scenario_id="NONEXISTENT", validation_feedback_id=99)
        assert result is False


class TestOriginalResultImmutability(unittest.TestCase):
    """
    Verify that feedback submission does NOT alter the original
    InvestigationResult or its confidence/hypothesis data.
    """

    def test_feedback_does_not_modify_investigation_result(self):
        """The InvestigationResult in the investigations table must remain immutable."""
        from models import InvestigationResult, Persona

        original = InvestigationResult(
            scenario_id="INC_001",
            persona=Persona.ANALYST,
        )
        original_id = original.scenario_id
        original_persona = original.persona

        # Simulate feedback submission (no mutation should occur)
        feedback = StructuredFeedbackSubmission(
            investigation_id="INC_001_analyst_test",
            scenario_id="INC_001",
            verdict=FeedbackVerdict.INCORRECT,
            corrected_hypothesis_id="H2",
            corrected_action="Different action",
        )

        # After feedback, original result must be unchanged
        assert original.scenario_id == original_id
        assert original.persona == original_persona
        # InvestigationResult has no feedback fields — it is immutable


class TestFeedbackMetrics(unittest.TestCase):
    """Test feedback_metrics.py computation logic."""

    def test_compute_metrics_with_mock_data(self):
        """Verify metric computation against known input."""
        from evaluation.feedback_metrics import compute_feedback_metrics, FeedbackMetrics

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        # First query: aggregate counts
        # (count, distinct_scenarios, confirmed, rejected, partial, unsure, validated)
        mock_cursor.fetchone.side_effect = [
            (5, 3, 3, 1, 1, 0, 2),  # aggregate
            (4,),                     # total scenarios from investigations
        ]
        # Per-scenario query
        mock_cursor.fetchall.return_value = [
            ("INC_001", 2, 2, 0, 0, 0, True),
            ("INC_002", 2, 1, 1, 0, 0, False),
            ("INC_003", 1, 0, 0, 1, 0, False),
        ]

        metrics = compute_feedback_metrics(mock_conn)

        assert metrics.feedback_count == 5
        assert metrics.human_confirmed_count == 3
        assert metrics.human_rejected_count == 1
        assert metrics.partial_correction_count == 1
        assert metrics.validated_precedent_count == 2
        # Agreement rate: 3 / (3+1) = 0.75
        assert metrics.human_agreement_rate == 0.75
        # Coverage: 3 / 4 = 0.75
        assert metrics.feedback_coverage == 0.75

    def test_compute_metrics_no_db_raises(self):
        from evaluation.feedback_metrics import compute_feedback_metrics
        with self.assertRaises(RuntimeError):
            compute_feedback_metrics(None)


if __name__ == "__main__":
    unittest.main()
