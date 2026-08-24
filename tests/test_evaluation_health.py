"""
tests/test_evaluation_health.py — Comprehensive Unit & Integration Tests for Continuous Evaluation & Drift Monitoring.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock
import pytest

from evaluation.health import (
    HealthMonitorService,
    HealthStatus,
    MetricHealthStatus,
    SampleState,
    evaluate_e2e_latency,
    evaluate_abstention_rate,
    evaluate_high_confidence_rate,
    evaluate_human_agreement,
    evaluate_citation_violations,
    evaluate_e9_relevance,
)


def _make_mock_investigation(
    scenario_id: str = "INC_001",
    persona: str = "analyst",
    latency_ms: float = 2500.0,
    abstained: bool = False,
    confidence_state: str = "high",
    has_violation: bool = False,
    precedent_relevance: float | None = 0.78,
) -> dict:
    violations = [{"violation_type": "phantom_id", "evidence_id": "phantom_1"}] if has_violation else []
    precedents = [{"relevance": precedent_relevance, "scenario_id": "PREC_1"}] if precedent_relevance is not None else []

    return {
        "scenario_id": scenario_id,
        "persona": persona,
        "telemetry": {
            "latency_ms_by_engine": {
                "signal": 10.0,
                "evidence": 20.0,
                "hypothesis": latency_ms - 50.0,
                "decision": 20.0,
            }
        },
        "decision": {
            "abstained": abstained,
            "recommended_action": None if abstained else "Action",
            "winning_hypothesis_id": None if abstained else "H1",
        },
        "scored": [
            {
                "hypothesis_id": "H1",
                "final_score": 0.85,
                "confidence_state": confidence_state,
                "violations": violations,
            }
        ],
        "precedents": precedents,
    }


def _make_mock_db_conn(inv_rows: list[tuple[str, dict]], feedback_counts: tuple[int, int] = (12, 3)):
    """Create a mock psycopg2 connection returning given investigation rows and feedback counts."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    def execute_side_effect(query, params=None):
        q = query.strip()
        if "FROM investigations" in q:
            mock_cur.fetchall.return_value = inv_rows
        elif "FROM feedback" in q:
            mock_cur.fetchone.return_value = feedback_counts
        else:
            mock_cur.fetchall.return_value = []
            mock_cur.fetchone.return_value = (0, 0)

    mock_cur.execute.side_effect = execute_side_effect
    return mock_conn


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_insufficient_data_under_20_runs():
    """1. Test that <20 investigations yields INSUFFICIENT_DATA."""
    inv_rows = [(f"INV_{i}", _make_mock_investigation()) for i in range(15)]
    db_conn = _make_mock_db_conn(inv_rows)

    report = HealthMonitorService.evaluate_health(db_conn)
    assert report.status == HealthStatus.INSUFFICIENT_DATA
    assert report.sample_state == SampleState.INSUFFICIENT_DATA
    assert report.total_investigations == 15
    assert len(report.metrics) == 0


def test_recent_only_20_to_49_runs():
    """2. Test that 20–49 investigations yields RECENT_ONLY with recent metrics and no baseline."""
    inv_rows = [(f"INV_{i}", _make_mock_investigation(latency_ms=2800.0, abstained=False)) for i in range(30)]
    db_conn = _make_mock_db_conn(inv_rows)

    report = HealthMonitorService.evaluate_health(db_conn)
    assert report.status == HealthStatus.HEALTHY
    assert report.sample_state == SampleState.RECENT_ONLY
    assert report.recent_window_size == 30
    assert report.baseline_window_size == 0

    m_lat = report.metrics["e2e_latency_p95_ms"]
    assert m_lat.recent_value is not None
    assert m_lat.baseline_value is None
    assert m_lat.delta is None


def test_partial_baseline_50_to_99_runs():
    """3. Test that 50–99 investigations yields PARTIAL_BASELINE (recent=50, baseline=remaining)."""
    inv_rows = [(f"INV_{i}", _make_mock_investigation()) for i in range(75)]
    db_conn = _make_mock_db_conn(inv_rows)

    report = HealthMonitorService.evaluate_health(db_conn)
    assert report.sample_state == SampleState.PARTIAL_BASELINE
    assert report.recent_window_size == 50
    assert report.baseline_window_size == 25
    assert report.status == HealthStatus.HEALTHY


def test_full_comparison_100_plus_runs():
    """4. Test that >=100 investigations yields FULL_COMPARISON (recent=50, baseline=50)."""
    inv_rows = [(f"INV_{i}", _make_mock_investigation()) for i in range(120)]
    db_conn = _make_mock_db_conn(inv_rows)

    report = HealthMonitorService.evaluate_health(db_conn)
    assert report.sample_state == SampleState.FULL_COMPARISON
    assert report.recent_window_size == 50
    assert report.baseline_window_size == 50
    assert report.status == HealthStatus.HEALTHY


def test_all_healthy_metrics():
    """5. Test that stable metrics across windows evaluate to HEALTHY."""
    recent = [_make_mock_investigation(latency_ms=2500.0, abstained=False, confidence_state="high") for _ in range(50)]
    baseline = [_make_mock_investigation(latency_ms=2400.0, abstained=False, confidence_state="high") for _ in range(50)]

    m_lat = evaluate_e2e_latency(recent, baseline)
    assert m_lat.status == MetricHealthStatus.HEALTHY

    m_abs = evaluate_abstention_rate(recent, baseline)
    assert m_abs.status == MetricHealthStatus.HEALTHY

    m_conf = evaluate_high_confidence_rate(recent, baseline)
    assert m_conf.status == MetricHealthStatus.HEALTHY


def test_watch_threshold_trigger():
    """6. Test that an abstention rate shift >= 0.15 triggers WATCH status."""
    # Baseline: 0% abstention, Recent: 20% abstention (delta = +0.20 >= 0.15)
    recent = [_make_mock_investigation(abstained=(i < 10)) for i in range(50)]
    baseline = [_make_mock_investigation(abstained=False) for _ in range(50)]

    m_abs = evaluate_abstention_rate(recent, baseline)
    assert m_abs.status == MetricHealthStatus.WATCH
    assert m_abs.delta == pytest.approx(0.20, abs=0.01)

    inv_rows = [(f"REC_{i}", recent[i]) for i in range(50)] + [(f"BASE_{i}", baseline[i]) for i in range(50)]
    db_conn = _make_mock_db_conn(inv_rows)
    report = HealthMonitorService.evaluate_health(db_conn)
    assert report.status == HealthStatus.WATCH


def test_degraded_threshold_trigger():
    """7. Test that an abstention rate shift >= 0.30 triggers DEGRADED status."""
    # Baseline: 0% abstention, Recent: 40% abstention (delta = +0.40 >= 0.30)
    recent = [_make_mock_investigation(abstained=(i < 20)) for i in range(50)]
    baseline = [_make_mock_investigation(abstained=False) for _ in range(50)]

    m_abs = evaluate_abstention_rate(recent, baseline)
    assert m_abs.status == MetricHealthStatus.DEGRADED

    inv_rows = [(f"REC_{i}", recent[i]) for i in range(50)] + [(f"BASE_{i}", baseline[i]) for i in range(50)]
    db_conn = _make_mock_db_conn(inv_rows)
    report = HealthMonitorService.evaluate_health(db_conn)
    assert report.status == HealthStatus.DEGRADED


def test_feedback_under_10_yields_not_enough_feedback():
    """8. Test that <10 feedback records yields NOT_ENOUGH_FEEDBACK and does not degrade overall status."""
    db_conn = MagicMock()
    mock_cur = MagicMock()
    db_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchone.return_value = (3, 1)  # Total 4 feedback items (< 10)

    m_agr = evaluate_human_agreement(["INV_1"], ["INV_2"], db_conn)
    assert m_agr.status == MetricHealthStatus.NOT_ENOUGH_FEEDBACK
    assert m_agr.delta is None


def test_feedback_over_10_evaluates_agreement():
    """9. Test that >=10 feedback records computes agreement rate correctly."""
    db_conn = MagicMock()
    mock_cur = MagicMock()
    db_conn.cursor.return_value.__enter__.return_value = mock_cur
    # 12 CORRECT, 3 INCORRECT -> 12/15 = 80%
    mock_cur.fetchone.return_value = (12, 3)

    m_agr = evaluate_human_agreement(["INV_1"], ["INV_2"], db_conn)
    assert m_agr.recent_value == pytest.approx(0.80, abs=0.01)


def test_e9_relevance_insufficient_sample():
    """10. Test that <10 precedent-bearing runs yields INSUFFICIENT_E9_SAMPLE."""
    # Only 4 runs have precedents
    recent = [_make_mock_investigation(precedent_relevance=0.85 if i < 4 else None) for i in range(50)]
    baseline = [_make_mock_investigation(precedent_relevance=0.85 if i < 4 else None) for i in range(50)]

    m_e9 = evaluate_e9_relevance(recent, baseline)
    assert m_e9.status == MetricHealthStatus.INSUFFICIENT_E9_SAMPLE
    assert m_e9.delta is None


def test_zero_baseline_rate_handling():
    """11. Test zero baseline rate handling (relative_change is None, delta is safe)."""
    recent = [_make_mock_investigation(has_violation=False) for _ in range(50)]
    baseline = [_make_mock_investigation(has_violation=False) for _ in range(50)]

    m_cit = evaluate_citation_violations(recent, baseline)
    assert m_cit.recent_value == 0.0
    assert m_cit.baseline_value == 0.0
    assert m_cit.delta == 0.0
    assert m_cit.relative_change is None
    assert m_cit.status == MetricHealthStatus.HEALTHY


def test_citation_violations_triggers_degraded():
    """12. Test that citation violation rate >= 0.10 triggers DEGRADED."""
    # 6 out of 50 runs have violations = 12% >= 10%
    recent = [_make_mock_investigation(has_violation=(i < 6)) for i in range(50)]
    baseline = [_make_mock_investigation(has_violation=False) for _ in range(50)]

    m_cit = evaluate_citation_violations(recent, baseline)
    assert m_cit.status == MetricHealthStatus.DEGRADED

    inv_rows = [(f"REC_{i}", recent[i]) for i in range(50)] + [(f"BASE_{i}", baseline[i]) for i in range(50)]
    db_conn = _make_mock_db_conn(inv_rows)
    report = HealthMonitorService.evaluate_health(db_conn)
    assert report.status == HealthStatus.DEGRADED


def test_deterministic_reproducibility():
    """13. Test that identical database inputs produce identical JSON health outputs."""
    inv_rows = [(f"INV_{i}", _make_mock_investigation()) for i in range(100)]
    db_conn = _make_mock_db_conn(inv_rows)

    report1 = HealthMonitorService.evaluate_health(db_conn)
    report2 = HealthMonitorService.evaluate_health(db_conn)

    assert report1.to_dict()["status"] == report2.to_dict()["status"]
    assert report1.to_dict()["sample_state"] == report2.to_dict()["sample_state"]
    assert json.dumps(report1.to_dict()["metrics"], sort_keys=True) == json.dumps(report2.to_dict()["metrics"], sort_keys=True)


def test_api_get_evaluation_health_endpoint():
    """14. Test FastAPI GET /evaluation/health endpoint contract."""
    from fastapi.testclient import TestClient
    from api.main import app

    with TestClient(app) as client:
        res = client.get("/evaluation/health")
        assert res.status_code == 200
        payload = res.json()
        assert "status" in payload
        assert "sample_state" in payload
        assert "total_investigations" in payload
        assert "recent_window_size" in payload
        assert "baseline_window_size" in payload
        assert "metrics" in payload
        assert "e2e_latency_p95_ms" in payload["metrics"]
        assert "abstention_rate" in payload["metrics"]
        assert "high_confidence_rate" in payload["metrics"]
        assert "human_agreement_rate" in payload["metrics"]
        assert "citation_violation_rate" in payload["metrics"]
        assert "e9_retrieval_relevance" in payload["metrics"]

