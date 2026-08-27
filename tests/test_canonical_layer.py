"""
tests/test_canonical_layer.py — Comprehensive Test Suite for Canonical Data & Evidence Layer

Validates:
1. Multi-grain normalization (hourly, daily, event-level)
2. ExtractionResult contract and CanonicalEvidenceRecord ID hashing with raw_identifier
3. TemporalAlignmentPolicy semantic contracts
4. Pinned continuous linear reliability decay function
5. Cached extraction fixtures in test/demo mode
6. E4 Dual-Retrieval assembly (structured + unstructured)
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from models import (
    AnomalySignal,
    CanonicalEvidenceRecord,
    Evidence,
    ExtractionResult,
    FreshnessStatus,
    MethodTag,
    SourceRegistryEntry,
    TemporalAlignmentPolicy,
    calculate_reliability_decay,
)
from config.registry import SourceRegistry
from etl.ingestion_adapter import (
    BatchSQLIngestionAdapter,
    MockUnstructuredExtractor,
)
from engines.evidence import assemble_evidence, reliability_weight


# ---------------------------------------------------------------------------
# 1. ExtractionResult Contract & Hashing
# ---------------------------------------------------------------------------

def test_extraction_result_contract() -> None:
    """Validate ExtractionResult accepts any payload type (SQL tuple, dict, str)."""
    now = datetime.utcnow()

    res_sql = ExtractionResult(
        raw_payload={"col1": "val1", "count": 10},
        source_type="sql",
        extracted_at=now,
        raw_identifier="sql_row_001",
    )
    assert res_sql.source_type == "sql"
    assert res_sql.raw_identifier == "sql_row_001"

    res_txt = ExtractionResult(
        raw_payload="System log line: gateway restarted",
        source_type="log",
        extracted_at=now,
        raw_identifier="log_chunk_002",
    )
    assert isinstance(res_txt.raw_payload, str)


def test_canonical_evidence_record_id_hashing() -> None:
    """Verify CanonicalEvidenceRecord.id hashes raw_identifier, source_id, timestamp, entity, observation."""
    now = datetime(2026, 8, 26, 12, 0, 0)
    rec1 = CanonicalEvidenceRecord(
        source_id="payment_gateway",
        entity="checkout-gateway",
        observation="Latency spike observed",
        timestamp=now,
        raw_ref="raw_event_123",
    )
    assert len(rec1.id) == 16
    assert rec1.evidence_id == rec1.id
    assert rec1.raw_ref == "raw_event_123"

    # Different raw_ref must produce a different ID
    rec2 = CanonicalEvidenceRecord(
        source_id="payment_gateway",
        entity="checkout-gateway",
        observation="Latency spike observed",
        timestamp=now,
        raw_ref="raw_event_999",
    )
    assert rec1.id != rec2.id


# ---------------------------------------------------------------------------
# 2. TemporalAlignmentPolicy Contract
# ---------------------------------------------------------------------------

def test_temporal_alignment_policy_enum() -> None:
    """Verify all 5 semantic alignment policies exist and are typed."""
    policies = {p.value for p in TemporalAlignmentPolicy}
    assert "snapshot" in policies
    assert "period_total" in policies
    assert "average" in policies
    assert "rate" in policies
    assert "last_known_value" in policies


# ---------------------------------------------------------------------------
# 3. Linear Reliability Decay Function
# ---------------------------------------------------------------------------

def test_calculate_reliability_decay_linear() -> None:
    """Verify pinned continuous linear decay formula across bounds."""
    # 1. In-SLA (staleness <= SLA): returns base quality
    assert calculate_reliability_decay(base_quality=0.95, staleness_minutes=20, sla_minutes=30) == 0.95
    assert calculate_reliability_decay(base_quality=0.95, staleness_minutes=30, sla_minutes=30) == 0.95

    # 2. Halfway stale (staleness = 1.5 * SLA): decay_factor = 0.5 -> 0.5 * 0.90 = 0.45
    assert pytest.approx(calculate_reliability_decay(base_quality=0.90, staleness_minutes=45, sla_minutes=30), 0.001) == 0.45

    # 3. Fully stale (staleness >= 2.0 * SLA): returns 0.0
    assert calculate_reliability_decay(base_quality=0.90, staleness_minutes=60, sla_minutes=30) == 0.0
    assert calculate_reliability_decay(base_quality=0.90, staleness_minutes=120, sla_minutes=30) == 0.0

    # 4. Undefined SLA / zero quality guards
    assert calculate_reliability_decay(base_quality=0.0, staleness_minutes=10, sla_minutes=30) == 0.0
    assert calculate_reliability_decay(base_quality=0.90, staleness_minutes=10, sla_minutes=0) == 0.0


# ---------------------------------------------------------------------------
# 4. Multi-Grain Normalization (Hourly, Daily, Event)
# ---------------------------------------------------------------------------

def test_multi_grain_normalization_end_to_end() -> None:
    """
    Test that hourly, daily, and event-level sources normalize into uniform
    CanonicalEvidenceRecord instances via BatchSQLIngestionAdapter.
    """
    mock_db = MagicMock()
    mock_cur = MagicMock()
    mock_db.cursor.return_value = mock_cur

    # Mock SQL responses for 3 grains:
    # 1. Hourly payment events
    # 2. Daily inventory snapshot
    # 3. Event deployment log
    mappings = {
        "payment_gateway": {
            "type": "sql",
            "entity_default": "checkout-gateway",
            "query": "SELECT ...",
            "observation_template": "Failures: {failure_count} / {total_count}",
        },
        "inventory": {
            "type": "sql",
            "entity_default": "warehouse-inventory",
            "query": "SELECT ...",
            "observation_template": "Fill rate: {avg_fill_rate:.1%}",
        },
        "deployment_log": {
            "type": "sql",
            "entity_default": "deploy-svc",
            "query": "SELECT ...",
            "observation_template": "Deploy {version} of {component}",
        },
    }

    adapter = BatchSQLIngestionAdapter(db_conn=mock_db, mappings_config=mappings)

    now = datetime.utcnow()
    last_refresh = now - timedelta(minutes=5)
    entry_hourly = SourceRegistryEntry(
        source_id="payment_gateway",
        name="Payment Gateway",
        grain="hourly",
        cadence_minutes=60,
        last_refresh=last_refresh,
        sla_minutes=120,
        freshness_status=FreshnessStatus.FRESH,
        data_quality=0.98,
    )
    entry_daily = SourceRegistryEntry(
        source_id="inventory",
        name="Inventory Snapshot",
        grain="daily",
        cadence_minutes=1440,
        last_refresh=last_refresh,
        sla_minutes=2880,
        freshness_status=FreshnessStatus.FRESH,
        data_quality=0.95,
    )
    entry_event = SourceRegistryEntry(
        source_id="deployment_log",
        name="Deployment Log",
        grain="event",
        cadence_minutes=0,
        last_refresh=last_refresh,
        sla_minutes=10080,
        freshness_status=FreshnessStatus.FRESH,
        data_quality=1.00,
    )

    # 1. Hourly normalize
    ext_hourly = ExtractionResult(
        raw_payload={"total_count": 100, "failure_count": 5, "avg_latency": 150.0, "timestamp": now.isoformat()},
        source_type="sql",
        extracted_at=now,
        raw_identifier="pay_001",
    )
    rec_hourly = adapter.normalize(ext_hourly, entry_hourly)
    assert isinstance(rec_hourly, CanonicalEvidenceRecord)
    assert rec_hourly.observation == "Failures: 5 / 100"
    assert rec_hourly.source_reliability == 0.98

    # 2. Daily normalize
    ext_daily = ExtractionResult(
        raw_payload={"avg_fill_rate": 0.94, "timestamp": now.isoformat()},
        source_type="sql",
        extracted_at=now,
        raw_identifier="inv_001",
    )
    rec_daily = adapter.normalize(ext_daily, entry_daily)
    assert isinstance(rec_daily, CanonicalEvidenceRecord)
    assert rec_daily.observation == "Fill rate: 94.0%"
    assert rec_daily.source_reliability == 0.95

    # 3. Event normalize
    ext_event = ExtractionResult(
        raw_payload={"version": "v4.2", "component": "payment-api", "timestamp": now.isoformat()},
        source_type="sql",
        extracted_at=now,
        raw_identifier="dep_001",
    )
    rec_event = adapter.normalize(ext_event, entry_event)
    assert isinstance(rec_event, CanonicalEvidenceRecord)
    assert rec_event.observation == "Deploy v4.2 of payment-api"
    assert rec_event.source_reliability == 1.00

    # All three produce the exact same uniform record contract
    for r in [rec_hourly, rec_daily, rec_event]:
        assert hasattr(r, "id")
        assert hasattr(r, "provenance_hash")
        assert hasattr(r, "source_reliability")
        assert hasattr(r, "confidence")
        assert hasattr(r, "timestamp")


# ---------------------------------------------------------------------------
# 5. Dual-Retrieval E4 Assembly with Cached Test Fixtures
# ---------------------------------------------------------------------------

def test_assemble_evidence_dual_retrieval_and_fixtures() -> None:
    """Verify E4 assemble_evidence combines structured and unstructured evidence."""
    now = datetime.utcnow()
    sources_cfg = [
        {
            "id": "payment_gateway",
            "name": "Payment Gateway",
            "grain": "15-min",
            "cadence_minutes": 15,
            "sla_minutes": 30,
            "data_quality": 0.99,
        },
        {
            "id": "release_notes",
            "name": "Release Notes",
            "grain": "event",
            "cadence_minutes": 0,
            "sla_minutes": 10080,
            "data_quality": 1.00,
        },
    ]
    registry = SourceRegistry(sources_cfg)

    # Mock structured adapter returning 1 record for payment_gateway, 0 for release_notes
    mock_adapter = MagicMock()
    mock_adapter.extract.side_effect = lambda source_id, *args, **kwargs: [
        ExtractionResult(
            raw_payload={"col": 1},
            source_type="sql",
            extracted_at=now,
            raw_identifier="pay_1",
        )
    ] if source_id == "payment_gateway" else []

    mock_adapter.normalize.return_value = CanonicalEvidenceRecord(
        source_id="payment_gateway",
        source_name="Payment Gateway",
        entity="checkout-gateway",
        observation="Payment latency spiked to 1200ms",
        timestamp=now,
        source_reliability=0.99,
        confidence=0.9,
        method=MethodTag.SQL,
    )


    # Mock unstructured extractor returning 1 record
    mock_extractor = MockUnstructuredExtractor(
        fixtures=[
            {
                "raw_identifier": "rel_doc_1",
                "entity": "release-v4.2",
                "observation": "Release notes for v4.2.0 deployed to prod",
                "source": "release_notes",
                "timestamp": now,
            }
        ]
    )

    signal = AnomalySignal(
        kpi_id="payment_failure_rate_15min",
        observed=12.5,
        expected=0.5,
        delta_pct=2400.0,
        z_score=5.2,
        is_anomaly=True,
    )

    result = assemble_evidence(
        authorized_sources=frozenset({"payment_gateway", "release_notes"}),
        signals=[signal],
        registry=registry,
        db_conn=MagicMock(),
        chroma_client=None,
        scenario_id="INC_001",
        anomaly_window_start=now - timedelta(hours=2),
        anomaly_window_end=now,
        adapter=mock_adapter,
        mock_extractor=mock_extractor,
    )

    assert len(result.evidence) == 2
    assert result.dropped_count == 0
    # Check that both structured and unstructured are unified
    methods = {e.method for e in result.evidence}
    assert MethodTag.SQL in methods
    assert MethodTag.RETRIEVAL in methods
    # Sorted by reliability * confidence descending
    assert result.evidence[0].source_reliability * result.evidence[0].confidence >= (
        result.evidence[1].source_reliability * result.evidence[1].confidence
    )
