"""
tests/test_security.py — Unit tests for the Security_Engine entitlement boundary.

Covers:
  - authorize() for known personas (cfo, analyst, manager)
  - authorize() for unknown persona returns empty scope (fail-closed)
  - authorize() for own_only persona without region raises ValueError
  - filter_evidence() removes unauthorized sources
  - filter_evidence() idempotency
  - filter_evidence() never widens scope
  - get_access_denied_result() shape (no evidence content)
  - from_yaml() with real entitlements.yaml
  - from_yaml() fail-closed on missing file
  - from_yaml() fail-closed on invalid yaml content
  - authorize_and_filter() convenience function
  - filter_evidence() with 10,000 items completes in < 2 seconds (Req 5.9)

Requirements: 5.1, 5.3, 5.4, 5.5, 5.6, 5.8, 5.9
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from models import Evidence, MethodTag
from security.entitlements import (
    AuthorizationScope,
    EntitlementError,
    SecurityEngine,
    authorize_and_filter,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

ENTITLEMENTS_CONFIG = {
    "personas": {
        "cfo": {
            "description": "CFO sees aggregate revenue and inventory only",
            "authorized_sources": ["orders", "inventory"],
            "authorized_fields": {
                "orders": ["revenue", "conversion"],
                "inventory": ["fill_rate"],
            },
            "authorized_regions": "all",
        },
        "analyst": {
            "description": "Analyst has full access",
            "authorized_sources": ["orders", "payment_gateway", "inventory", "marketing"],
            "authorized_fields": {
                "orders": ["revenue", "conversion", "aov", "device", "channel"],
                "payment_gateway": ["success", "latency_ms", "error_code"],
                "inventory": ["fill_rate", "in_stock", "sku_id"],
                "marketing": ["spend", "impressions", "channel"],
            },
            "authorized_regions": "all",
        },
        "manager": {
            "description": "Manager sees their own region only",
            "authorized_sources": ["orders", "inventory"],
            "authorized_fields": {
                "orders": ["revenue", "conversion", "aov"],
                "inventory": ["fill_rate", "in_stock"],
            },
            "authorized_regions": "own_only",
        },
    }
}


def make_evidence(source_id: str, evidence_id: str = None) -> Evidence:
    """Factory for a minimal Evidence object."""
    eid = evidence_id or f"ev_{source_id}"
    return Evidence(
        evidence_id=eid,
        kind="structured",
        summary="test summary",
        source_id=source_id,
        reliability_weight=0.9,
        relevance=0.8,
        raw_ref="row:1",
        method=MethodTag.SQL,
    )


# ---------------------------------------------------------------------------
# SecurityEngine construction
# ---------------------------------------------------------------------------

class TestSecurityEngineConstruction:
    def test_construct_with_valid_config(self):
        engine = SecurityEngine(ENTITLEMENTS_CONFIG)
        assert engine is not None

    def test_construct_with_empty_config(self):
        engine = SecurityEngine({})
        # every authorize should return empty scope
        scope = engine.authorize("analyst")
        assert scope.is_empty is True

    def test_construct_with_no_personas_key(self):
        engine = SecurityEngine({"other_key": {}})
        scope = engine.authorize("cfo")
        assert scope.is_empty is True


# ---------------------------------------------------------------------------
# authorize() — persona resolution
# ---------------------------------------------------------------------------

class TestAuthorize:
    def setup_method(self):
        self.engine = SecurityEngine(ENTITLEMENTS_CONFIG)

    def test_authorize_analyst_returns_full_sources(self):
        scope = self.engine.authorize("analyst")
        assert not scope.is_empty
        assert "orders" in scope.authorized_sources
        assert "payment_gateway" in scope.authorized_sources
        assert "inventory" in scope.authorized_sources
        assert "marketing" in scope.authorized_sources

    def test_authorize_cfo_limited_sources(self):
        scope = self.engine.authorize("cfo")
        assert not scope.is_empty
        assert scope.authorized_sources == frozenset({"orders", "inventory"})
        # CFO cannot see payment_gateway or marketing
        assert "payment_gateway" not in scope.authorized_sources
        assert "marketing" not in scope.authorized_sources

    def test_authorize_analyst_authorized_fields(self):
        scope = self.engine.authorize("analyst")
        assert "revenue" in scope.authorized_fields["orders"]
        assert "latency_ms" in scope.authorized_fields["payment_gateway"]

    def test_authorize_cfo_field_restrictions(self):
        scope = self.engine.authorize("cfo")
        # CFO can only see revenue and conversion on orders
        assert scope.authorized_fields["orders"] == frozenset({"revenue", "conversion"})

    def test_authorize_unknown_persona_returns_empty_scope(self):
        scope = self.engine.authorize("unknown_role")
        assert scope.is_empty is True
        assert scope.authorized_sources == frozenset()
        assert scope.authorized_fields == {}

    def test_authorize_unknown_persona_is_empty_flag(self):
        scope = self.engine.authorize("superadmin")
        assert scope.is_empty is True

    def test_authorize_case_insensitive(self):
        # persona key lookup is lowercase-normalised
        scope_lower = self.engine.authorize("analyst")
        scope_upper = self.engine.authorize("ANALYST")
        assert scope_lower.authorized_sources == scope_upper.authorized_sources

    def test_authorize_manager_own_only_requires_region(self):
        with pytest.raises(ValueError, match="own_only"):
            self.engine.authorize("manager")  # no region supplied

    def test_authorize_manager_with_region(self):
        scope = self.engine.authorize("manager", region="EMEA")
        assert not scope.is_empty
        assert scope.authorized_regions == "own_only"
        assert scope.region_filter == "EMEA"
        assert "orders" in scope.authorized_sources
        assert "inventory" in scope.authorized_sources

    def test_authorize_all_regions_persona_ignores_region_filter(self):
        scope = self.engine.authorize("analyst", region="APAC")
        # authorized_regions is "all" — region_filter should be None
        assert scope.authorized_regions == "all"
        assert scope.region_filter is None

    def test_authorize_returns_frozensets(self):
        scope = self.engine.authorize("analyst")
        assert isinstance(scope.authorized_sources, frozenset)
        for v in scope.authorized_fields.values():
            assert isinstance(v, frozenset)

    def test_authorize_scope_persona_matches(self):
        scope = self.engine.authorize("cfo")
        assert scope.persona == "cfo"


# ---------------------------------------------------------------------------
# filter_evidence() — core filtering behaviour
# ---------------------------------------------------------------------------

class TestFilterEvidence:
    def setup_method(self):
        self.engine = SecurityEngine(ENTITLEMENTS_CONFIG)
        self.analyst_scope = self.engine.authorize("analyst")
        self.cfo_scope = self.engine.authorize("cfo")

    # Basic filtering
    def test_authorized_evidence_passes_through(self):
        evidence = [make_evidence("orders"), make_evidence("inventory")]
        authorized, denied = self.engine.filter_evidence(self.cfo_scope, evidence)
        assert len(authorized) == 2
        assert denied == []

    def test_unauthorized_evidence_removed(self):
        evidence = [
            make_evidence("orders"),
            make_evidence("payment_gateway"),  # not in CFO scope
            make_evidence("marketing"),        # not in CFO scope
        ]
        authorized, denied = self.engine.filter_evidence(self.cfo_scope, evidence)
        assert len(authorized) == 1
        assert authorized[0].source_id == "orders"
        assert "payment_gateway" in denied
        assert "marketing" in denied

    def test_all_unauthorized_returns_empty_list(self):
        evidence = [make_evidence("payment_gateway"), make_evidence("marketing")]
        authorized, denied = self.engine.filter_evidence(self.cfo_scope, evidence)
        assert authorized == []
        assert set(denied) == {"payment_gateway", "marketing"}

    def test_empty_input_returns_empty_output(self):
        authorized, denied = self.engine.filter_evidence(self.analyst_scope, [])
        assert authorized == []
        assert denied == []

    # Idempotency (Requirement 5.5)
    def test_filter_is_idempotent(self):
        evidence = [
            make_evidence("orders"),
            make_evidence("payment_gateway"),
            make_evidence("marketing"),
        ]
        first_pass, _ = self.engine.filter_evidence(self.analyst_scope, evidence)
        second_pass, denied_second = self.engine.filter_evidence(self.analyst_scope, first_pass)

        assert [e.evidence_id for e in first_pass] == [e.evidence_id for e in second_pass]
        assert denied_second == []

    def test_re_filter_cfo_already_filtered_is_unchanged(self):
        # Filtering with CFO scope then re-filtering with the same scope
        evidence = [make_evidence("orders"), make_evidence("inventory")]
        first, _ = self.engine.filter_evidence(self.cfo_scope, evidence)
        second, denied = self.engine.filter_evidence(self.cfo_scope, first)
        assert [e.evidence_id for e in first] == [e.evidence_id for e in second]
        assert denied == []

    # Never widens scope
    def test_filter_never_widens_scope(self):
        # analyst has more access than CFO; filtering the full set with CFO scope
        # then with analyst scope must not add anything back
        evidence = [
            make_evidence("orders"),
            make_evidence("payment_gateway"),
            make_evidence("inventory"),
            make_evidence("marketing"),
        ]
        cfo_filtered, _ = self.engine.filter_evidence(self.cfo_scope, evidence)
        # Re-filter with analyst (wider) scope on the already CFO-filtered set
        analyst_re_filtered, denied = self.engine.filter_evidence(
            self.analyst_scope, cfo_filtered
        )
        # Must not gain anything over the CFO-filtered set
        cfo_ids = {e.source_id for e in cfo_filtered}
        re_ids = {e.source_id for e in analyst_re_filtered}
        assert re_ids == cfo_ids

    # denied_source_ids are sorted deterministically
    def test_denied_ids_are_sorted(self):
        evidence = [
            make_evidence("z_source"),
            make_evidence("a_source"),
            make_evidence("m_source"),
        ]
        empty_scope = AuthorizationScope(
            persona="nobody",
            authorized_sources=frozenset(),
            authorized_fields={},
            authorized_regions="all",
            is_empty=True,
        )
        _, denied = self.engine.filter_evidence(empty_scope, evidence)
        assert denied == sorted(denied)

    # Fail-closed scope rejects everything
    def test_empty_scope_rejects_all_evidence(self):
        evidence = [make_evidence("orders"), make_evidence("inventory")]
        scope = self.engine.authorize("nonexistent_persona")
        authorized, denied = self.engine.filter_evidence(scope, evidence)
        assert authorized == []
        assert set(denied) == {"orders", "inventory"}

    # Order preservation
    def test_filter_preserves_order_of_authorized_items(self):
        evidence = [
            make_evidence("orders", "ev1"),
            make_evidence("inventory", "ev2"),
            make_evidence("orders", "ev3"),
        ]
        authorized, _ = self.engine.filter_evidence(self.cfo_scope, evidence)
        assert [e.evidence_id for e in authorized] == ["ev1", "ev2", "ev3"]


# ---------------------------------------------------------------------------
# get_access_denied_result()
# ---------------------------------------------------------------------------

class TestGetAccessDeniedResult:
    def setup_method(self):
        self.engine = SecurityEngine(ENTITLEMENTS_CONFIG)

    def test_access_denied_flag_is_true(self):
        scope = self.engine.authorize("cfo")
        result = self.engine.get_access_denied_result(scope, ["payment_gateway"])
        assert result["access_denied"] is True

    def test_excluded_sources_in_result(self):
        scope = self.engine.authorize("cfo")
        result = self.engine.get_access_denied_result(scope, ["payment_gateway", "marketing"])
        assert set(result["excluded_sources"]) == {"payment_gateway", "marketing"}

    def test_persona_in_result(self):
        scope = self.engine.authorize("cfo")
        result = self.engine.get_access_denied_result(scope, [])
        assert result["persona"] == "cfo"

    def test_no_evidence_content_in_result(self):
        scope = self.engine.authorize("cfo")
        result = self.engine.get_access_denied_result(scope, ["payment_gateway"])
        # Only allowed keys — must not contain evidence data
        allowed_keys = {"access_denied", "excluded_sources", "persona"}
        assert set(result.keys()) == allowed_keys

    def test_excluded_sources_are_sorted(self):
        scope = self.engine.authorize("cfo")
        result = self.engine.get_access_denied_result(
            scope, ["z_source", "a_source", "m_source"]
        )
        assert result["excluded_sources"] == sorted(result["excluded_sources"])

    def test_duplicate_denied_sources_deduplicated(self):
        scope = self.engine.authorize("cfo")
        result = self.engine.get_access_denied_result(
            scope, ["payment_gateway", "payment_gateway"]
        )
        assert result["excluded_sources"].count("payment_gateway") == 1


# ---------------------------------------------------------------------------
# from_yaml() — file loading and fail-closed behaviour
# ---------------------------------------------------------------------------

class TestFromYaml:
    def test_load_real_entitlements_yaml(self):
        yaml_path = Path(__file__).parent.parent / "config" / "entitlements.yaml"
        if not yaml_path.exists():
            pytest.skip("entitlements.yaml not found at config/entitlements.yaml")

        engine = SecurityEngine.from_yaml(yaml_path)
        scope = engine.authorize("analyst")
        assert not scope.is_empty
        assert "orders" in scope.authorized_sources

    def test_fail_closed_on_missing_file(self, tmp_path):
        missing = tmp_path / "does_not_exist.yaml"
        with pytest.warns(UserWarning):
            engine = SecurityEngine.from_yaml(missing)
        scope = engine.authorize("analyst")
        assert scope.is_empty is True

    def test_fail_closed_on_invalid_yaml(self, tmp_path):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text(":::invalid yaml:::", encoding="utf-8")
        with pytest.warns(UserWarning):
            engine = SecurityEngine.from_yaml(bad_yaml)
        scope = engine.authorize("analyst")
        assert scope.is_empty is True

    def test_fail_closed_on_yaml_missing_personas_key(self, tmp_path):
        no_personas = tmp_path / "no_personas.yaml"
        no_personas.write_text("other_key: {}\n", encoding="utf-8")
        with pytest.warns(UserWarning):
            engine = SecurityEngine.from_yaml(no_personas)
        scope = engine.authorize("analyst")
        assert scope.is_empty is True

    def test_from_yaml_with_valid_yaml_file(self, tmp_path):
        import yaml as _yaml

        yaml_content = {
            "personas": {
                "testuser": {
                    "authorized_sources": ["src_a", "src_b"],
                    "authorized_fields": {"src_a": ["field1"], "src_b": ["field2"]},
                    "authorized_regions": "all",
                }
            }
        }
        yaml_path = tmp_path / "entitlements.yaml"
        yaml_path.write_text(_yaml.dump(yaml_content), encoding="utf-8")

        engine = SecurityEngine.from_yaml(yaml_path)
        scope = engine.authorize("testuser")
        assert not scope.is_empty
        assert "src_a" in scope.authorized_sources


# ---------------------------------------------------------------------------
# fail_closed() class method
# ---------------------------------------------------------------------------

class TestFailClosed:
    def test_fail_closed_engine_returns_empty_scope(self):
        engine = SecurityEngine.fail_closed()
        scope = engine.authorize("analyst")
        assert scope.is_empty is True

    def test_fail_closed_engine_filters_all_evidence(self):
        engine = SecurityEngine.fail_closed()
        scope = engine.authorize("analyst")
        evidence = [make_evidence("orders"), make_evidence("payment_gateway")]
        authorized, denied = engine.filter_evidence(scope, evidence)
        assert authorized == []
        assert set(denied) == {"orders", "payment_gateway"}


# ---------------------------------------------------------------------------
# authorize_and_filter() — convenience function
# ---------------------------------------------------------------------------

class TestAuthorizeAndFilter:
    def test_returns_tuple_of_three(self):
        candidates = [make_evidence("orders"), make_evidence("payment_gateway")]
        result = authorize_and_filter("cfo", None, ENTITLEMENTS_CONFIG, candidates)
        assert len(result) == 3

    def test_authorized_evidence_correct(self):
        candidates = [make_evidence("orders"), make_evidence("payment_gateway")]
        authorized, scope, denied = authorize_and_filter(
            "cfo", None, ENTITLEMENTS_CONFIG, candidates
        )
        assert len(authorized) == 1
        assert authorized[0].source_id == "orders"

    def test_scope_returned(self):
        candidates = [make_evidence("orders")]
        _, scope, _ = authorize_and_filter(
            "analyst", None, ENTITLEMENTS_CONFIG, candidates
        )
        assert isinstance(scope, AuthorizationScope)
        assert not scope.is_empty

    def test_denied_sources_returned(self):
        candidates = [make_evidence("orders"), make_evidence("payment_gateway")]
        _, _, denied = authorize_and_filter("cfo", None, ENTITLEMENTS_CONFIG, candidates)
        assert "payment_gateway" in denied

    def test_with_region_for_manager(self):
        candidates = [make_evidence("orders"), make_evidence("payment_gateway")]
        authorized, scope, denied = authorize_and_filter(
            "manager", "EMEA", ENTITLEMENTS_CONFIG, candidates
        )
        assert scope.region_filter == "EMEA"
        assert authorized[0].source_id == "orders"
        assert "payment_gateway" in denied

    def test_unknown_persona_returns_empty(self):
        candidates = [make_evidence("orders")]
        authorized, scope, denied = authorize_and_filter(
            "ghost", None, ENTITLEMENTS_CONFIG, candidates
        )
        assert authorized == []
        assert scope.is_empty is True
        assert "orders" in denied


# ---------------------------------------------------------------------------
# Performance test — Requirement 5.9: 10,000 items < 2 seconds
# ---------------------------------------------------------------------------

class TestPerformance:
    def test_filter_10k_items_under_2_seconds(self):
        engine = SecurityEngine(ENTITLEMENTS_CONFIG)
        scope = engine.authorize("analyst")

        # Build 10,000 evidence items spread across sources
        sources = ["orders", "payment_gateway", "inventory", "marketing", "unknown_source"]
        candidates = [
            make_evidence(sources[i % len(sources)], f"ev_{i}")
            for i in range(10_000)
        ]

        start = time.perf_counter()
        authorized, denied = engine.filter_evidence(scope, candidates)
        elapsed = time.perf_counter() - start

        assert elapsed < 2.0, (
            f"filter_evidence on 10,000 items took {elapsed:.3f}s (must be < 2s)"
        )
        # Sanity: analyst sees all sources except unknown_source
        denied_set = set(denied)
        assert "unknown_source" in denied_set
        assert len(authorized) + sum(
            1 for c in candidates if c.source_id in denied_set
        ) == 10_000
