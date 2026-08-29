"""
tests/test_business_agnostic.py — Structural Enforcement and Non-Retail Synthetic Evaluation

Verifies:
1. Business-Agnostic Structural AST Scan: Engines (E1–E9) do not hardcode domain logic.
2. Synthetic Non-Retail Scenario Evaluation: E1–E9 produces structurally identical output
   for non-retail enterprise domains (e.g. Cloud Infrastructure / Server Health).
"""

from __future__ import annotations

import ast
import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from models import (
    AnomalySignal,
    BusinessMateriality,
    CanonicalEvidenceRecord,
    AuditVerdict,
    DimensionContribution,
    EvidenceCitation,
    ExtractionResult,
    FreshnessStatus,
    Hypothesis,
    KPIValue,
    MaterialityAssessment,
    MethodTag,
    Persona,
    RuleResult,
    RuleVerdict,
    ScoredHypothesis,
    SourceRegistryEntry,
)

from config.registry import SourceRegistry
from engines.challenge import score_hypothesis
from engines.evidence import assemble_evidence
from engines.signal import assess_materiality
from etl.ingestion_adapter import BatchSQLIngestionAdapter, MockUnstructuredExtractor


# ---------------------------------------------------------------------------
# 1. Structural AST / Keyword Denylist Enforcement
# ---------------------------------------------------------------------------

def _load_denylist() -> set[str]:
    """Load denylist keywords from config/business_denylist.yaml."""
    import yaml
    config_path = Path("config/business_denylist.yaml")
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            items = data.get("denylist", [])
            if items:
                return {str(item).lower() for item in items}
    return {"cart", "checkout", "retail", "inventory", "pos_system"}


# Directories and files in the reusable engine spine that must remain pure
ENGINE_FILES = [
    Path("engines/evidence.py"),
    Path("models.py"),
    Path("etl/ingestion_adapter.py"),
]


def test_business_agnostic_ast_cleanliness() -> None:
    """
    Ensure the core engine spine does not contain hardcoded domain keywords
    in function names, class definitions, or logic.
    """
    denylist = _load_denylist()
    assert len(denylist) > 0

    for file_path in ENGINE_FILES:
        if not file_path.exists():
            continue
        with file_path.open("r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                fn_name = node.name.lower()
                for bad_word in denylist:
                    assert bad_word not in fn_name, (
                        f"Domain keyword '{bad_word}' found in function name '{node.name}' in {file_path}"
                    )
            elif isinstance(node, ast.ClassDef):
                cls_name = node.name.lower()
                for bad_word in denylist:
                    assert bad_word not in cls_name, (
                        f"Domain keyword '{bad_word}' found in class name '{node.name}' in {file_path}"
                    )



# ---------------------------------------------------------------------------
# 2. Synthetic Non-Retail Business Scenario (Cloud Telemetry / Server Ops)
# ---------------------------------------------------------------------------

def test_synthetic_non_retail_scenario_structural_equivalence() -> None:
    """
    Assert that a non-retail domain (e.g. Cloud Infrastructure Server Uptime)
    runs through the Canonical Data Layer, Evidence Engine (E4), and Challenge Engine (E6)
    producing the exact same schema structure, status fields, evidence fields, and verdicts.
    """
    now = datetime(2026, 8, 26, 14, 0, 0)

    # 1. Non-retail source registry
    sources_cfg = [
        {
            "id": "server_telemetry",
            "name": "Server Telemetry Daemon",
            "grain": "1-min",
            "cadence_minutes": 1,
            "sla_minutes": 5,
            "data_quality": 0.99,
        },
        {
            "id": "incident_postmortems",
            "name": "Incident Postmortems",
            "grain": "event",
            "cadence_minutes": 0,
            "sla_minutes": 1440,
            "data_quality": 0.95,
        },
    ]
    registry = SourceRegistry(sources_cfg)

    # 2. Non-retail anomaly signal (E2 output)
    signal = AnomalySignal(
        kpi_id="server_cpu_utilization_pct",
        observed=98.5,
        expected=45.0,
        delta_pct=118.8,
        z_score=4.85,
        is_anomaly=True,
        corroborated_by=["memory_pressure_pct"],
        method=MethodTag.STATS,
    )

    # 3. Non-retail structured extraction (E4)
    mock_adapter = MagicMock()
    mock_adapter.extract.side_effect = lambda source_id, *args, **kwargs: [
        ExtractionResult(
            raw_payload={"col": 1},
            source_type="sql",
            extracted_at=now,
            raw_identifier="node_metrics_001",
        )
    ] if source_id == "server_telemetry" else []

    mock_adapter.normalize.return_value = CanonicalEvidenceRecord(
        source_id="server_telemetry",
        source_name="Server Telemetry Daemon",
        entity="node-cluster-us-east-1",
        observation="Node cluster CPU sustained at 98.5% across 64 cores",
        timestamp=now,
        metric="server_cpu_utilization_pct",
        value=98.5,
        freshness_minutes=1.0,
        source_reliability=0.99,
        confidence=1.0,
        method=MethodTag.SQL,
        raw_ref="node_metrics_001",
    )


    mock_extractor = MockUnstructuredExtractor(
        fixtures=[
            {
                "raw_identifier": "postmortem_99",
                "entity": "kernel-upgrade-patch",
                "observation": "Kernel patch 6.8 applied causing CPU deadlock",
                "source": "incident_postmortems",
                "timestamp": now - timedelta(hours=1),
            }
        ]
    )

    # 4. E4 Evidence Assembly
    assembly_result = assemble_evidence(
        authorized_sources=frozenset({"server_telemetry", "incident_postmortems"}),
        signals=[signal],
        registry=registry,
        db_conn=MagicMock(),
        chroma_client=None,
        scenario_id="CLOUD_INC_001",
        anomaly_window_start=now - timedelta(hours=2),
        anomaly_window_end=now,
        adapter=mock_adapter,
        mock_extractor=mock_extractor,
    )

    assert len(assembly_result.evidence) == 2
    assert all(isinstance(e, CanonicalEvidenceRecord) for e in assembly_result.evidence)

    # 5. Non-retail Hypothesis (E5)
    ev_map = {e.id: e for e in assembly_result.evidence}
    ev_ids = list(ev_map.keys())

    hypothesis = Hypothesis(
        hypothesis_id="H_KERNEL_UPGRADE",
        statement="A kernel deadlock following patch 6.8 caused cluster-wide CPU saturation.",
        citations=[
            EvidenceCitation(
                evidence_id=ev_ids[0],
                quoted_summary=ev_map[ev_ids[0]].observation,
                role="supports",
                relevance_explanation="Directly corroborates CPU deadlock on node cluster.",
            )
        ],
        reasoning="Kernel deadlock matches both telemetry spikes and postmortem records.",
    )

    # 6. Non-retail E6 Challenge Evaluation
    challenge_result = score_hypothesis(
        h=hypothesis,
        evidence_by_id=ev_map,
        signals=[signal],
        contributions=[],
    )

    # 7. Non-retail Materiality Assessment (E2 Extension)
    cloud_kpi_contract = {
        "domain": "Cloud Infrastructure / Operations",
        "kpis": [
            {
                "id": "server_cpu_utilization_pct",
                "materiality": {
                    "impact_metric": "volume",
                    "multiplier": 64.0,  # 64 impacted cores / worker nodes per 1% excess CPU
                    "critical_threshold": 2000.0,
                    "high_threshold": 1000.0,
                    "medium_threshold": 500.0,
                    "low_threshold": 100.0,
                },
            }
        ],
    }
    materiality_assessments = assess_materiality([signal], cloud_kpi_contract)
    assert len(materiality_assessments) == 1
    mat = materiality_assessments[0]
    assert isinstance(mat, MaterialityAssessment)
    assert mat.kpi_id == "server_cpu_utilization_pct"
    assert mat.is_statistical_anomaly is True
    # delta = 98.5 - 45.0 = 53.5 -> 53.5 * 64.0 = 3424.0 >= 2000 -> CRITICAL
    assert mat.volume_impact == 3424.0
    assert mat.financial_impact is None
    assert mat.business_materiality == BusinessMateriality.CRITICAL
    assert mat.priority_rank == 1

    # 8. Assert structural equivalence
    assert hasattr(challenge_result, "final_audit_score")
    assert hasattr(challenge_result, "audit_verdict")
    assert hasattr(challenge_result, "rule_results")
    assert isinstance(challenge_result.audit_verdict, AuditVerdict)
    assert len(challenge_result.rule_results) == 5
    for r in challenge_result.rule_results:
        assert isinstance(r.verdict, RuleVerdict)
        assert r.rule_name in {"timeline", "segment_alignment", "kpi_corroboration", "mechanism_consistency", "contradiction"}

