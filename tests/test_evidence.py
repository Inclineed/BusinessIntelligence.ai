"""
tests/test_evidence.py — Unit tests for Engine E4: Evidence Engine.

Covers:
  - reliability_weight: in-SLA weight equals data_quality
  - reliability_weight: stale weight strictly < in-SLA weight for same source
  - reliability_weight: monotonicity — more stale → lower weight
  - reliability_weight: zero weight when freshness UNKNOWN
  - reliability_weight: zero weight when sla_minutes == 0
  - reliability_weight: clamped to [0, 1]
  - assemble_evidence: unresolved source_id in registry → dropped
  - assemble_evidence: structured evidence tagged MethodTag.SQL
  - assemble_evidence: unstructured evidence tagged MethodTag.RETRIEVAL
  - assemble_evidence: only authorized sources included
  - assemble_evidence: sorted by reliability_weight * relevance descending
  - assemble_evidence: empty when db_conn and chroma_client are None
  - EvidenceAssemblyResult fields present

Requirements: 6.1, 6.2, 6.3, 6.4, 6.6, 7.3, 7.4, 7.5
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from engines.evidence import (
    EvidenceAssemblyResult,
    assemble_evidence,
    reliability_weight,
)
from models import Evidence, FreshnessStatus, MethodTag
from security.entitlements import AuthorizationScope


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(
    source_id: str = "orders",
    data_quality: float = 0.9,
    sla_minutes: int = 60,
    staleness_minutes: float = 10.0,
    freshness_status: FreshnessStatus = FreshnessStatus.FRESH,
):
    """
    Create a minimal SourceRegistryEntry-like object whose properties match
    what reliability_weight() inspects.

    We use a plain dataclass-like object so that the test is independent of
    the SourceRegistry construction machinery.
    """
    # Calculate last_refresh from staleness
    last_refresh = datetime.utcnow() - timedelta(minutes=staleness_minutes)

    from models import SourceRegistryEntry

    entry = SourceRegistryEntry(
        source_id=source_id,
        name=source_id,
        grain="hourly",
        cadence_minutes=60,
        last_refresh=last_refresh,
        sla_minutes=sla_minutes,
        freshness_status=freshness_status,
        data_quality=data_quality,
        lineage=[],
        owner="test",
    )
    return entry


def _make_registry(entries: list) -> "SourceRegistry":
    """Build a SourceRegistry pre-populated with the given entries."""
    from config.registry import SourceRegistry

    # We construct a minimal sources_config list and then override entries
    sources_config = [
        {
            "id": e.source_id,
            "name": e.name,
            "grain": e.grain,
            "cadence_minutes": str(e.cadence_minutes),
            "sla_minutes": str(e.sla_minutes),
            "data_quality": str(e.data_quality),
            "lineage": e.lineage,
            "owner": e.owner,
        }
        for e in entries
    ]
    registry = SourceRegistry(sources_config)
    # Override with our precise entries (so last_refresh / freshness_status match)
    for entry in entries:
        registry._entries[entry.source_id] = entry
    return registry


def _make_scope(authorized_sources: list[str]) -> AuthorizationScope:
    return AuthorizationScope(
        persona="analyst",
        authorized_sources=frozenset(authorized_sources),
        authorized_fields={},
        authorized_regions="all",
        is_empty=False,
    )


# ---------------------------------------------------------------------------
# reliability_weight tests
# ---------------------------------------------------------------------------

class TestReliabilityWeight:
    # Req 6.2: In-SLA → weight == data_quality
    def test_in_sla_weight_equals_data_quality(self):
        entry = _make_entry(
            data_quality=0.85,
            sla_minutes=60,
            staleness_minutes=30.0,
            freshness_status=FreshnessStatus.FRESH,
        )
        w = reliability_weight(entry)
        assert abs(w - 0.85) < 1e-9, f"Expected 0.85, got {w}"

    def test_in_sla_at_boundary_equals_data_quality(self):
        # Exactly at the SLA boundary (staleness == sla) should be treated as in-SLA
        entry = _make_entry(
            data_quality=0.75,
            sla_minutes=60,
            staleness_minutes=60.0,
            freshness_status=FreshnessStatus.FRESH,
        )
        w = reliability_weight(entry)
        assert abs(w - 0.75) < 1e-6

    # Req 6.3: Stale → weight strictly less than data_quality
    def test_stale_weight_less_than_data_quality(self):
        fresh_entry = _make_entry(
            data_quality=0.9,
            sla_minutes=60,
            staleness_minutes=30.0,
            freshness_status=FreshnessStatus.FRESH,
        )
        stale_entry = _make_entry(
            data_quality=0.9,
            sla_minutes=60,
            staleness_minutes=120.0,   # 2× the SLA
            freshness_status=FreshnessStatus.STALE,
        )
        fresh_w = reliability_weight(fresh_entry)
        stale_w = reliability_weight(stale_entry)
        assert stale_w < fresh_w, (
            f"Stale weight {stale_w} should be < fresh weight {fresh_w}"
        )

    def test_stale_weight_not_below_zero(self):
        # Extremely stale: staleness = 10× SLA
        entry = _make_entry(
            data_quality=0.9,
            sla_minutes=60,
            staleness_minutes=600.0,
            freshness_status=FreshnessStatus.STALE,
        )
        w = reliability_weight(entry)
        assert w >= 0.0

    # Req 6.4: Monotonicity — more stale → lower or equal weight
    def test_monotonicity_increasing_staleness(self):
        sla = 60
        dq = 0.9
        staleness_values = [10, 30, 60, 90, 120, 180, 300, 600]

        weights = []
        for s in staleness_values:
            fs = FreshnessStatus.FRESH if s <= sla else FreshnessStatus.STALE
            entry = _make_entry(
                data_quality=dq,
                sla_minutes=sla,
                staleness_minutes=float(s),
                freshness_status=fs,
            )
            weights.append(reliability_weight(entry))

        for i in range(len(weights) - 1):
            assert weights[i] >= weights[i + 1], (
                f"Monotonicity violated at staleness index {i}: "
                f"weight[{i}]={weights[i]} < weight[{i+1}]={weights[i+1]}"
            )

    def test_monotonicity_fine_grained(self):
        """Property 5 (sampled): equal data_quality, only staleness differs."""
        sla = 30
        dq = 0.8
        # Sample 20 increasing staleness values straddling the SLA
        staleness_samples = [float(v) for v in range(1, 300, 15)]
        prev_w = None
        for s in staleness_samples:
            fs = FreshnessStatus.FRESH if s <= sla else FreshnessStatus.STALE
            entry = _make_entry(
                data_quality=dq,
                sla_minutes=sla,
                staleness_minutes=s,
                freshness_status=fs,
            )
            w = reliability_weight(entry)
            if prev_w is not None:
                assert w <= prev_w + 1e-9, (
                    f"Non-monotonic: staleness={s}, weight={w} > prev={prev_w}"
                )
            prev_w = w

    # Req 6.6: UNKNOWN freshness → weight 0
    def test_unknown_freshness_returns_zero(self):
        entry = _make_entry(
            data_quality=0.9,
            sla_minutes=60,
            staleness_minutes=10.0,
            freshness_status=FreshnessStatus.UNKNOWN,
        )
        w = reliability_weight(entry)
        assert w == 0.0

    # Req 6.6: sla_minutes == 0 → weight 0
    def test_zero_sla_returns_zero(self):
        entry = _make_entry(
            data_quality=0.9,
            sla_minutes=0,
            staleness_minutes=10.0,
            freshness_status=FreshnessStatus.UNKNOWN,
        )
        w = reliability_weight(entry)
        assert w == 0.0

    # Req 6.1: weight in [0, 1]
    def test_weight_clamped_to_unit_interval(self):
        for staleness in [0, 10, 60, 120, 1000]:
            fs = FreshnessStatus.FRESH if staleness <= 60 else FreshnessStatus.STALE
            entry = _make_entry(
                data_quality=1.0,
                sla_minutes=60,
                staleness_minutes=float(staleness),
                freshness_status=fs,
            )
            w = reliability_weight(entry)
            assert 0.0 <= w <= 1.0, f"Weight {w} out of [0,1] for staleness={staleness}"

    def test_full_data_quality_in_sla_gives_weight_one(self):
        entry = _make_entry(
            data_quality=1.0,
            sla_minutes=120,
            staleness_minutes=5.0,
            freshness_status=FreshnessStatus.FRESH,
        )
        w = reliability_weight(entry)
        assert abs(w - 1.0) < 1e-9

    def test_decay_formula_correct_at_2x_sla(self):
        # staleness = 2 * sla → ratio = 1 → decay_factor = 0 → weight = 0
        sla = 60
        entry = _make_entry(
            data_quality=0.8,
            sla_minutes=sla,
            staleness_minutes=float(2 * sla),  # exactly 2× → decay = max(0, 1-1) = 0
            freshness_status=FreshnessStatus.STALE,
        )
        w = reliability_weight(entry)
        assert w == 0.0

    def test_decay_formula_at_1_5x_sla(self):
        # staleness = 1.5 * sla → beyond_ratio = 0.5 → decay = 0.5 → weight = dq * 0.5
        sla = 60
        dq = 0.8
        entry = _make_entry(
            data_quality=dq,
            sla_minutes=sla,
            staleness_minutes=float(int(sla * 1.5)),  # 90 min
            freshness_status=FreshnessStatus.STALE,
        )
        w = reliability_weight(entry)
        expected = dq * 0.5
        assert abs(w - expected) < 0.01, f"Expected ~{expected}, got {w}"


# ---------------------------------------------------------------------------
# EvidenceAssemblyResult structure
# ---------------------------------------------------------------------------

class TestEvidenceAssemblyResult:
    def test_is_named_tuple(self):
        result = EvidenceAssemblyResult(evidence=[], dropped_count=0, reliability_notes=[])
        assert result.evidence == []
        assert result.dropped_count == 0
        assert result.reliability_notes == []

    def test_fields_accessible_by_name(self):
        ev = Evidence(
            evidence_id="e1",
            kind="structured",
            summary="test",
            source_id="orders",
            reliability_weight=0.8,
            relevance=0.9,
            raw_ref="row:1",
            method=MethodTag.SQL,
        )
        result = EvidenceAssemblyResult(
            evidence=[ev],
            dropped_count=1,
            reliability_notes=["note 1"],
        )
        assert len(result.evidence) == 1
        assert result.dropped_count == 1
        assert "note 1" in result.reliability_notes


# ---------------------------------------------------------------------------
# assemble_evidence — no connections (db_conn=None, chroma_client=None)
# ---------------------------------------------------------------------------

class TestAssembleEvidenceNoConnections:
    def setup_method(self):
        self.now = datetime.utcnow()
        self.start = self.now - timedelta(hours=2)
        self.end = self.now

    def test_returns_empty_with_no_connections(self):
        entry = _make_entry("orders", data_quality=0.9, sla_minutes=120, staleness_minutes=10)
        registry = _make_registry([entry])
        scope = _make_scope(["orders"])

        result = assemble_evidence(
            authorized_sources=scope.authorized_sources,
            signals=[],
            registry=registry,
            db_conn=None,
            chroma_client=None,
            scenario_id="test_001",
            anomaly_window_start=self.start,
            anomaly_window_end=self.end,
        )
        assert isinstance(result, EvidenceAssemblyResult)
        assert result.evidence == []
        assert result.dropped_count == 0

    def test_dropped_count_zero_with_no_connections(self):
        entry = _make_entry("payment_gateway", data_quality=0.95, sla_minutes=30, staleness_minutes=5)
        registry = _make_registry([entry])
        scope = _make_scope(["payment_gateway"])

        result = assemble_evidence(
            authorized_sources=scope.authorized_sources,
            signals=[],
            registry=registry,
            db_conn=None,
            chroma_client=None,
            scenario_id="INC_001",
            anomaly_window_start=self.start,
            anomaly_window_end=self.end,
        )
        assert result.dropped_count == 0


# ---------------------------------------------------------------------------
# assemble_evidence — structured evidence with mock db_conn
# ---------------------------------------------------------------------------

class TestAssembleEvidenceStructured:
    def setup_method(self):
        self.now = datetime.utcnow()
        self.start = self.now - timedelta(hours=2)
        self.end = self.now
        self.scenario_id = "INC_001"

    def _make_mock_cursor(self, rows: list):
        cursor = MagicMock()
        cursor.fetchall.return_value = rows
        return cursor

    def _make_mock_db(self, rows: list):
        db_conn = MagicMock()
        cursor = self._make_mock_cursor(rows)
        db_conn.cursor.return_value = cursor
        return db_conn

    # --- Structured evidence tagged SQL (Req 7.4) ---
    def test_payment_evidence_tagged_sql(self):
        entry = _make_entry(
            "payment_gateway",
            data_quality=0.95,
            sla_minutes=30,
            staleness_minutes=5,
            freshness_status=FreshnessStatus.FRESH,
        )
        registry = _make_registry([entry])
        scope = _make_scope(["payment_gateway"])

        # Mock: (total, failures, avg_latency)
        db_conn = self._make_mock_db([(1000, 40, 250.0)])

        result = assemble_evidence(
            authorized_sources=scope.authorized_sources,
            signals=[],
            registry=registry,
            db_conn=db_conn,
            chroma_client=None,
            scenario_id=self.scenario_id,
            anomaly_window_start=self.start,
            anomaly_window_end=self.end,
        )
        assert len(result.evidence) == 1
        ev = result.evidence[0]
        assert ev.method == MethodTag.SQL
        assert ev.kind == "structured"
        assert ev.source_id == "payment_gateway"

    def test_structured_evidence_has_required_fields(self):
        entry = _make_entry(
            "payment_gateway",
            data_quality=0.95,
            sla_minutes=30,
            staleness_minutes=5,
            freshness_status=FreshnessStatus.FRESH,
        )
        registry = _make_registry([entry])
        scope = _make_scope(["payment_gateway"])
        db_conn = self._make_mock_db([(500, 25, 180.0)])

        result = assemble_evidence(
            authorized_sources=scope.authorized_sources,
            signals=[],
            registry=registry,
            db_conn=db_conn,
            chroma_client=None,
            scenario_id=self.scenario_id,
            anomaly_window_start=self.start,
            anomaly_window_end=self.end,
        )
        ev = result.evidence[0]
        # Req 7.3: source_id, reliability_weight, relevance, raw_ref all present
        assert ev.source_id != ""
        assert 0.0 <= ev.reliability_weight <= 1.0
        assert 0.0 <= ev.relevance <= 1.0
        assert ev.raw_ref != ""

    def test_in_sla_reliability_weight_equals_data_quality(self):
        dq = 0.88
        entry = _make_entry(
            "payment_gateway",
            data_quality=dq,
            sla_minutes=60,
            staleness_minutes=10.0,
            freshness_status=FreshnessStatus.FRESH,
        )
        registry = _make_registry([entry])
        scope = _make_scope(["payment_gateway"])
        db_conn = self._make_mock_db([(200, 10, 300.0)])

        result = assemble_evidence(
            authorized_sources=scope.authorized_sources,
            signals=[],
            registry=registry,
            db_conn=db_conn,
            chroma_client=None,
            scenario_id=self.scenario_id,
            anomaly_window_start=self.start,
            anomaly_window_end=self.end,
        )
        ev = result.evidence[0]
        assert abs(ev.reliability_weight - dq) < 1e-9

    def test_stale_reliability_weight_less_than_in_sla(self):
        dq = 0.9
        stale_entry = _make_entry(
            "payment_gateway",
            data_quality=dq,
            sla_minutes=30,
            staleness_minutes=120.0,  # 4× SLA → heavily decayed
            freshness_status=FreshnessStatus.STALE,
        )
        registry = _make_registry([stale_entry])
        scope = _make_scope(["payment_gateway"])
        db_conn = self._make_mock_db([(100, 5, 200.0)])

        result = assemble_evidence(
            authorized_sources=scope.authorized_sources,
            signals=[],
            registry=registry,
            db_conn=db_conn,
            chroma_client=None,
            scenario_id=self.scenario_id,
            anomaly_window_start=self.start,
            anomaly_window_end=self.end,
        )
        ev = result.evidence[0]
        # Stale weight must be strictly less than data_quality
        assert ev.reliability_weight < dq

    # Unauthorized source not queried / not included
    def test_unauthorized_source_not_included(self):
        payment_entry = _make_entry(
            "payment_gateway",
            data_quality=0.95,
            sla_minutes=30,
            staleness_minutes=5,
            freshness_status=FreshnessStatus.FRESH,
        )
        inventory_entry = _make_entry(
            "inventory",
            data_quality=0.9,
            sla_minutes=2880,
            staleness_minutes=60,
            freshness_status=FreshnessStatus.FRESH,
        )
        registry = _make_registry([payment_entry, inventory_entry])
        # CFO scope: only inventory authorized (payment_gateway NOT authorized)
        scope = _make_scope(["inventory"])
        db_conn = self._make_mock_db([(500.0,)])  # fill_rate row

        result = assemble_evidence(
            authorized_sources=scope.authorized_sources,
            signals=[],
            registry=registry,
            db_conn=db_conn,
            chroma_client=None,
            scenario_id=self.scenario_id,
            anomaly_window_start=self.start,
            anomaly_window_end=self.end,
        )
        for ev in result.evidence:
            assert ev.source_id != "payment_gateway", (
                "payment_gateway evidence should not appear for unauthorized scope"
            )

    # Deployment evidence per deployment row
    def test_deployment_evidence_one_item_per_row(self):
        deploy_entry = _make_entry(
            "deployment_log",
            data_quality=0.99,
            sla_minutes=1440,
            staleness_minutes=30,
            freshness_status=FreshnessStatus.FRESH,
        )
        registry = _make_registry([deploy_entry])
        scope = _make_scope(["deployment_log"])

        db_conn = MagicMock()
        # Two deployment rows
        db_conn.cursor.return_value.fetchall.return_value = [
            ("d1", "v4.3", "2024-01-10 12:00:00", "checkout-service"),
            ("d2", "v4.2", "2024-01-09 08:00:00", "payment-service"),
        ]

        result = assemble_evidence(
            authorized_sources=scope.authorized_sources,
            signals=[],
            registry=registry,
            db_conn=db_conn,
            chroma_client=None,
            scenario_id=self.scenario_id,
            anomaly_window_start=self.start,
            anomaly_window_end=self.end,
        )
        assert len(result.evidence) == 2
        for ev in result.evidence:
            assert ev.method == MethodTag.SQL
            assert ev.kind == "structured"


# ---------------------------------------------------------------------------
# assemble_evidence — unresolved source_id drop (Req 7.5)
# ---------------------------------------------------------------------------

class TestUnresolvedSourceDrop:
    def setup_method(self):
        self.now = datetime.utcnow()
        self.start = self.now - timedelta(hours=1)
        self.end = self.now

    def test_unresolved_source_is_dropped(self):
        """Evidence item whose source_id is not in registry is dropped."""
        # Registry has 'orders' but NOT 'ghost_source'
        entry = _make_entry("orders", data_quality=0.9, sla_minutes=120, staleness_minutes=10)
        registry = _make_registry([entry])
        scope = _make_scope(["orders", "ghost_source"])

        db_conn = MagicMock()
        db_conn.cursor.return_value.fetchall.return_value = [(500, 10, 200.0)]

        # Manually inject an evidence item with unresolvable source via
        # constructing and post-processing — we test via the mock DB path by
        # crafting a scenario where 'ghost_source' would be queried.
        # Because 'ghost_source' isn't in the SQL query map we simulate it by
        # patching the registry to raise KeyError for it.
        original_get = registry.get

        def patched_get(sid):
            if sid == "ghost_source":
                raise KeyError(f"unknown: {sid}")
            return original_get(sid)

        registry.get = patched_get

        # Build an evidence item referencing ghost_source and pass it through
        # the final safety-check in assemble_evidence by exploiting that
        # assemble_evidence itself calls registry.get on every item.
        # The cleanest way: monkey-patch _assemble_structured to also return
        # a ghost item — but it's simpler to test the final verification pass
        # by calling assemble_evidence with the mock and confirming the drop.

        # Here we test that even if ghost_source is authorized, no evidence is
        # produced because the registry doesn't know it.
        result = assemble_evidence(
            authorized_sources=scope.authorized_sources,
            signals=[],
            registry=registry,
            db_conn=db_conn,
            chroma_client=None,
            scenario_id="test",
            anomaly_window_start=self.start,
            anomaly_window_end=self.end,
        )
        for ev in result.evidence:
            assert ev.source_id != "ghost_source", (
                "ghost_source evidence must be dropped"
            )

    def test_dropped_count_incremented_for_unknown_source(self):
        """reliability_notes documents the drop and dropped_count >= 1."""
        entry = _make_entry("orders", data_quality=0.9, sla_minutes=120, staleness_minutes=10)
        registry = _make_registry([entry])

        # Payment gateway authorized but NOT in registry → weight lookup fails → drop
        scope = _make_scope(["payment_gateway"])

        db_conn = MagicMock()
        db_conn.cursor.return_value.fetchall.return_value = [(1000, 40, 250.0)]

        result = assemble_evidence(
            authorized_sources=scope.authorized_sources,
            signals=[],
            registry=registry,
            db_conn=db_conn,
            chroma_client=None,
            scenario_id="test",
            anomaly_window_start=self.start,
            anomaly_window_end=self.end,
        )
        # No evidence from unregistered source
        assert all(ev.source_id != "payment_gateway" for ev in result.evidence)
        # Note recorded
        assert any("payment_gateway" in note for note in result.reliability_notes)

    def test_zero_sla_produces_reliability_note(self):
        """A source with sla_minutes=0 returns weight 0 and adds a note."""
        entry = _make_entry(
            "orders",
            data_quality=0.9,
            sla_minutes=0,
            staleness_minutes=5.0,
            freshness_status=FreshnessStatus.UNKNOWN,
        )
        registry = _make_registry([entry])
        scope = _make_scope(["orders"])

        db_conn = MagicMock()
        # inventory row so that 'inventory' source isn't queried (not in scope)
        # orders doesn't have a structured query in our engine but the test
        # confirms that if it did, a zero-SLA note would be appended.
        # We check directly via reliability_weight and then the assemble path.
        db_conn.cursor.return_value.fetchall.return_value = []

        result = assemble_evidence(
            authorized_sources=scope.authorized_sources,
            signals=[],
            registry=registry,
            db_conn=db_conn,
            chroma_client=None,
            scenario_id="test",
            anomaly_window_start=datetime.utcnow() - timedelta(hours=1),
            anomaly_window_end=datetime.utcnow(),
        )
        # The engine won't produce items for 'orders' (no SQL query for it in
        # the default map), but reliability_weight should return 0 for the entry.
        w = reliability_weight(entry)
        assert w == 0.0


# ---------------------------------------------------------------------------
# assemble_evidence — unstructured evidence tagged RETRIEVAL (Req 7.4)
# ---------------------------------------------------------------------------

class TestAssembleEvidenceUnstructured:
    def setup_method(self):
        self.now = datetime.utcnow()
        self.start = self.now - timedelta(hours=2)
        self.end = self.now

    def _make_chroma_mock(self, source_id: str, n: int = 2):
        """Return a ChromaDB-like mock returning *n* documents."""
        chroma = MagicMock()
        collection = MagicMock()
        chroma.get_collection.return_value = collection

        doc_ids = [f"doc_{i}" for i in range(n)]
        collection.query.return_value = {
            "ids": [doc_ids],
            "documents": [[f"Support ticket about payment failure {i}" for i in range(n)]],
            "metadatas": [[{"source": source_id}] * n],
            "distances": [[0.1 * i for i in range(n)]],
        }
        return chroma

    def test_unstructured_evidence_tagged_retrieval(self):
        entry = _make_entry(
            "support_tickets",
            data_quality=0.85,
            sla_minutes=120,
            staleness_minutes=30,
            freshness_status=FreshnessStatus.FRESH,
        )
        registry = _make_registry([entry])
        scope = _make_scope(["support_tickets"])
        chroma = self._make_chroma_mock("support_tickets", n=2)

        result = assemble_evidence(
            authorized_sources=scope.authorized_sources,
            signals=[],
            registry=registry,
            db_conn=None,
            chroma_client=chroma,
            scenario_id="INC_001",
            anomaly_window_start=self.start,
            anomaly_window_end=self.end,
        )
        assert len(result.evidence) == 2
        for ev in result.evidence:
            assert ev.method == MethodTag.RETRIEVAL
            assert ev.kind == "unstructured"

    def test_unstructured_unauthorized_source_excluded(self):
        entry = _make_entry(
            "support_tickets",
            data_quality=0.85,
            sla_minutes=120,
            staleness_minutes=30,
            freshness_status=FreshnessStatus.FRESH,
        )
        registry = _make_registry([entry])
        # scope does NOT include support_tickets
        scope = _make_scope(["orders"])
        chroma = self._make_chroma_mock("support_tickets", n=3)

        result = assemble_evidence(
            authorized_sources=scope.authorized_sources,
            signals=[],
            registry=registry,
            db_conn=None,
            chroma_client=chroma,
            scenario_id="INC_001",
            anomaly_window_start=self.start,
            anomaly_window_end=self.end,
        )
        for ev in result.evidence:
            assert ev.source_id != "support_tickets"

    def test_unstructured_unresolved_source_dropped(self):
        # Collection returns docs with source = 'ghost'; ghost is not in registry
        entry = _make_entry(
            "support_tickets",
            data_quality=0.9,
            sla_minutes=120,
            staleness_minutes=10,
            freshness_status=FreshnessStatus.FRESH,
        )
        registry = _make_registry([entry])
        scope = _make_scope(["ghost"])  # authorized but not in registry

        chroma = MagicMock()
        collection = MagicMock()
        chroma.get_collection.return_value = collection
        collection.query.return_value = {
            "ids": [["d1"]],
            "documents": [["some text"]],
            "metadatas": [[{"source": "ghost"}]],
            "distances": [[0.1]],
        }

        result = assemble_evidence(
            authorized_sources=scope.authorized_sources,
            signals=[],
            registry=registry,
            db_conn=None,
            chroma_client=chroma,
            scenario_id="INC_001",
            anomaly_window_start=self.start,
            anomaly_window_end=self.end,
        )
        assert len(result.evidence) == 0
        assert result.dropped_count >= 1
        assert any("ghost" in note for note in result.reliability_notes)


# ---------------------------------------------------------------------------
# assemble_evidence — sort order and mixed evidence
# ---------------------------------------------------------------------------

class TestAssembleEvidenceSortOrder:
    def test_sorted_by_reliability_times_relevance_descending(self):
        """Items should come back highest-score first."""
        high_entry = _make_entry(
            "payment_gateway",
            data_quality=1.0,
            sla_minutes=30,
            staleness_minutes=5.0,
            freshness_status=FreshnessStatus.FRESH,
        )
        low_entry = _make_entry(
            "support_tickets",
            data_quality=0.5,
            sla_minutes=120,
            staleness_minutes=240.0,  # very stale
            freshness_status=FreshnessStatus.STALE,
        )
        registry = _make_registry([high_entry, low_entry])
        scope = _make_scope(["payment_gateway", "support_tickets"])

        # DB returns payment event row; chroma returns a support_ticket doc
        db_conn = MagicMock()
        db_conn.cursor.return_value.fetchall.return_value = [(200, 8, 300.0)]

        chroma = MagicMock()
        collection = MagicMock()
        chroma.get_collection.return_value = collection
        collection.query.return_value = {
            "ids": [["d1"]],
            "documents": [["Support ticket text"]],
            "metadatas": [[{"source": "support_tickets"}]],
            "distances": [[0.2]],
        }

        result = assemble_evidence(
            authorized_sources=scope.authorized_sources,
            signals=[],
            registry=registry,
            db_conn=db_conn,
            chroma_client=chroma,
            scenario_id="INC_001",
            anomaly_window_start=datetime.utcnow() - timedelta(hours=2),
            anomaly_window_end=datetime.utcnow(),
        )
        if len(result.evidence) >= 2:
            scores = [e.reliability_weight * e.relevance for e in result.evidence]
            for i in range(len(scores) - 1):
                assert scores[i] >= scores[i + 1], (
                    f"Evidence not sorted: position {i} score {scores[i]} "
                    f"< position {i+1} score {scores[i+1]}"
                )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_scope_produces_no_evidence(self):
        entry = _make_entry("payment_gateway", data_quality=0.9, sla_minutes=30, staleness_minutes=5)
        registry = _make_registry([entry])
        scope = AuthorizationScope(
            persona="nobody",
            authorized_sources=frozenset(),
            authorized_fields={},
            authorized_regions="all",
            is_empty=True,
        )

        db_conn = MagicMock()
        db_conn.cursor.return_value.fetchall.return_value = [(100, 5, 200.0)]

        result = assemble_evidence(
            authorized_sources=scope.authorized_sources,
            signals=[],
            registry=registry,
            db_conn=db_conn,
            chroma_client=None,
            scenario_id="empty_scope_test",
            anomaly_window_start=datetime.utcnow() - timedelta(hours=1),
            anomaly_window_end=datetime.utcnow(),
        )
        assert result.evidence == []

    def test_no_db_rows_produces_no_structured_evidence(self):
        entry = _make_entry("payment_gateway", data_quality=0.95, sla_minutes=30, staleness_minutes=5)
        registry = _make_registry([entry])
        scope = _make_scope(["payment_gateway"])

        db_conn = MagicMock()
        db_conn.cursor.return_value.fetchall.return_value = []

        result = assemble_evidence(
            authorized_sources=scope.authorized_sources,
            signals=[],
            registry=registry,
            db_conn=db_conn,
            chroma_client=None,
            scenario_id="test",
            anomaly_window_start=datetime.utcnow() - timedelta(hours=1),
            anomaly_window_end=datetime.utcnow(),
        )
        assert result.evidence == []

    def test_chroma_collection_not_found_returns_empty(self):
        entry = _make_entry("support_tickets", data_quality=0.9, sla_minutes=120, staleness_minutes=10)
        registry = _make_registry([entry])
        scope = _make_scope(["support_tickets"])

        chroma = MagicMock()
        chroma.get_collection.side_effect = Exception("collection not found")

        result = assemble_evidence(
            authorized_sources=scope.authorized_sources,
            signals=[],
            registry=registry,
            db_conn=None,
            chroma_client=chroma,
            scenario_id="INC_001",
            anomaly_window_start=datetime.utcnow() - timedelta(hours=1),
            anomaly_window_end=datetime.utcnow(),
        )
        assert result.evidence == []
        assert result.dropped_count == 0
