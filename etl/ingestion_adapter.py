"""
etl/ingestion_adapter.py — Canonical Ingestion & Extraction Adapters

Provides typed interfaces and batch implementations for extracting heterogeneous
data sources into ExtractionResult streams and normalizing them into CanonicalEvidenceRecords.
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional, Protocol

import yaml

from models import (
    CanonicalEvidenceRecord,
    ExtractionResult,
    MethodTag,
    SourceRegistryEntry,
    TemporalAlignmentPolicy,
    calculate_reliability_decay,
    clamp,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# IngestionAdapter Protocol
# ---------------------------------------------------------------------------

class IngestionAdapter(Protocol):
    """
    Protocol for data extraction and canonical normalization.
    extract() returns an Iterator[ExtractionResult] to allow future streaming
    adapters to be plugged in without redesigning E4.
    """

    def extract(
        self,
        source_id: str,
        window_start: datetime,
        window_end: datetime,
        scenario_id: str = "",
    ) -> Iterator[ExtractionResult]:
        ...

    def normalize(
        self,
        extracted: ExtractionResult,
        source_entry: SourceRegistryEntry,
        scenario_id: str = "",
    ) -> Optional[CanonicalEvidenceRecord]:
        ...


# ---------------------------------------------------------------------------
# Batch SQL Ingestion Adapter
# ---------------------------------------------------------------------------

class BatchSQLIngestionAdapter:
    """
    Config-driven SQL adapter that extracts raw payloads and normalizes
    them into CanonicalEvidenceRecords based on evidence_mappings.yaml.
    """

    def __init__(
        self,
        db_conn: Any,
        mappings_path: Optional[str | Path] = None,
        mappings_config: Optional[dict] = None,
    ) -> None:
        self.db_conn = db_conn
        if mappings_config is not None:
            self.mappings = mappings_config.get("mappings", mappings_config)
        elif mappings_path is not None:
            p = Path(mappings_path)
            if p.exists():
                with p.open("r", encoding="utf-8") as fh:
                    raw = yaml.safe_load(fh) or {}
                    self.mappings = raw.get("mappings", raw)
            else:
                self.mappings = {}
        else:
            default_path = Path(__file__).resolve().parent.parent / "config" / "evidence_mappings.yaml"
            if default_path.exists():
                with default_path.open("r", encoding="utf-8") as fh:
                    raw = yaml.safe_load(fh) or {}
                    self.mappings = raw.get("mappings", raw)
            else:
                self.mappings = {}

    def extract(
        self,
        source_id: str,
        window_start: datetime,
        window_end: datetime,
        scenario_id: str = "",
    ) -> Iterator[ExtractionResult]:
        """
        Execute configured extraction SQL and yield ExtractionResult records.
        """
        if source_id not in self.mappings:
            logger.debug("BatchSQLIngestionAdapter: no mapping found for source_id '%s'", source_id)
            return

        cfg = self.mappings[source_id]
        if cfg.get("type") != "sql":
            return

        query = cfg.get("query")
        if not query or self.db_conn is None:
            return

        params = {
            "scenario_id": scenario_id,
            "start_ts": window_start.isoformat(),
            "end_ts": window_end.isoformat(),
        }

        try:
            cur = self.db_conn.cursor()
            cur.execute(query, params)
            col_names = [desc[0] for desc in cur.description] if cur.description else []
            rows = cur.fetchall()

            for row in rows:
                row_dict = dict(zip(col_names, row))
                raw_id = str(row_dict.get("raw_ref", f"{source_id}:{scenario_id}:{datetime.utcnow().isoformat()}"))
                yield ExtractionResult(
                    raw_payload=row_dict,
                    source_type="sql",
                    extracted_at=datetime.utcnow(),
                    raw_identifier=raw_id,
                )
        except Exception as exc:
            logger.warning("BatchSQLIngestionAdapter: query failed for source '%s': %s", source_id, exc)

    def normalize(
        self,
        extracted: ExtractionResult,
        source_entry: SourceRegistryEntry,
        scenario_id: str = "",
    ) -> Optional[CanonicalEvidenceRecord]:
        """
        Transform raw ExtractionResult into a validated CanonicalEvidenceRecord.
        """
        payload = extracted.raw_payload
        if not isinstance(payload, dict):
            return None

        cfg = self.mappings.get(source_entry.source_id, {})
        obs_template = cfg.get("observation_template", "")

        # Compute calculated fields if present
        total_count = payload.get("total_count", 0) or 0
        failure_count = payload.get("failure_count", 0) or 0
        failure_rate = (failure_count / total_count * 100.0) if total_count > 0 else 0.0
        avg_latency = float(payload.get("avg_latency") or 0.0)
        avg_fill_rate = float(payload.get("avg_fill_rate") or 0.0)

        # Check for empty aggregations (COUNT(*) = 0)
        if "total_count" in payload and total_count == 0 and "failure_count" in payload:
            return None
        if "avg_fill_rate" in payload and payload["avg_fill_rate"] is None:
            return None

        format_dict = {
            **payload,
            "failure_rate": failure_rate,
            "avg_latency": avg_latency,
            "avg_fill_rate": avg_fill_rate,
            "entity": payload.get("entity", cfg.get("entity_default", source_entry.name)),
        }

        observation = ""
        if obs_template:
            try:
                observation = obs_template.format(**format_dict).strip()
            except Exception:
                observation = f"Observation from {source_entry.source_id}: {payload}"
        else:
            observation = str(payload)

        # Calculate reliability weight via linear decay
        weight = calculate_reliability_decay(
            base_quality=source_entry.data_quality,
            staleness_minutes=source_entry.staleness_minutes,
            sla_minutes=float(source_entry.sla_minutes),
        )

        ts = payload.get("timestamp")
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts)
            except Exception:
                ts = datetime.utcnow()
        elif not isinstance(ts, datetime):
            ts = datetime.utcnow()

        val = payload.get("value")
        if val is not None:
            try:
                val = float(val)
            except (ValueError, TypeError):
                val = None

        return CanonicalEvidenceRecord(
            source_id=source_entry.source_id,
            source_name=source_entry.name,
            entity=str(payload.get("entity", cfg.get("entity_default", source_entry.name))),
            observation=observation,
            timestamp=ts,
            metric=payload.get("metric"),
            dimension={},
            value=val,
            freshness_minutes=source_entry.staleness_minutes,
            source_reliability=weight,
            confidence=0.9,
            method=MethodTag.SQL,
            lineage=list(cfg.get("lineage", source_entry.lineage)),
            raw_ref=extracted.raw_identifier,
            kind="structured",
        )


# ---------------------------------------------------------------------------
# Cached / Mock Unstructured Extractor for Tests & Demos
# ---------------------------------------------------------------------------

class MockUnstructuredExtractor:
    """
    Deterministic extractor for testing and demos when ENV_MODE=test.
    Returns canned ExtractionResult payloads without calling LLMs.
    """

    def __init__(self, fixtures: Optional[list[dict]] = None) -> None:
        self.fixtures = fixtures or [
            {
                "raw_identifier": "doc_fixture_001",
                "entity": "checkout-gateway",
                "observation": "Checkout gateway latency spiked following deployment v4.2.0.",
                "source": "release_notes",
                "timestamp": datetime.utcnow(),
            }
        ]

    def extract(self, query: str) -> Iterator[ExtractionResult]:
        for fix in self.fixtures:
            yield ExtractionResult(
                raw_payload=fix,
                source_type="vector",
                extracted_at=datetime.utcnow(),
                raw_identifier=fix.get("raw_identifier", "mock_id"),
            )
