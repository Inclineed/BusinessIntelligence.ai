"""
tests/test_diagnostic.py — Unit tests for Engine E3: Diagnostic Engine

Covers:
- Android is the dominant contributor in INC_001 device decomposition (Req 12.2)
- contribution_pct values sum to 100 ±0.1 pp per dimension (Req 4.2)
- Tie-break uses lexicographic segment name (Req 4.4)
- Missing/insufficient data returns error string, no exception (Req 4.6)
- All contributions are stamped MethodTag.SQL (Req 4.5)
- Dominant segment identified as max abs contribution across ALL dimensions (Req 4.3)
- get_ordered_contributions sorts and limits results correctly

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 12.2
"""

from __future__ import annotations

import math
import pytest

from models import AnomalySignal, KPIValue, MethodTag, FreshnessStatus
from engines.diagnostic import (
    DecompositionResult,
    decompose,
    get_ordered_contributions,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_kpi(
    kpi_id: str,
    period: str,
    value: float,
    dimension_filters: dict = None,
) -> KPIValue:
    """Minimal KPIValue factory for testing."""
    return KPIValue(
        kpi_id=kpi_id,
        name=kpi_id,
        value=value,
        unit="ratio",
        period=period,
        dimension_filters=dimension_filters or {},
        source_id="orders",
        freshness=FreshnessStatus.FRESH,
        method=MethodTag.SQL,
    )


def _make_signal(
    kpi_id: str,
    observed: float,
    expected: float,
    is_anomaly: bool = True,
) -> AnomalySignal:
    """Minimal AnomalySignal factory for testing."""
    delta = (observed - expected) / abs(expected) * 100.0 if expected != 0 else 0.0
    return AnomalySignal(
        kpi_id=kpi_id,
        observed=observed,
        expected=expected,
        delta_pct=round(max(-100.0, min(100.0, delta)), 2),
        z_score=-4.5,
        is_anomaly=is_anomaly,
        corroborated_by=[],
        sparse_history=False,
        data_quality_suspect=False,
        method=MethodTag.STATS,
    )


# ---------------------------------------------------------------------------
# INC_001 device decomposition fixture
# ---------------------------------------------------------------------------

def _inc001_conversion_kpi_values() -> list[KPIValue]:
    """
    Mimics INC_001: hourly_conversion with Android down 17% and other devices stable.

    Baseline (T-1): android=0.30, ios=0.40, web=0.35 → agg mean ≈ 0.35
    Current  (T0):  android=0.249 (-17%), ios=0.40 (0%), web=0.35 (0%)
                    agg mean ≈ 0.333

    The signal represents the aggregate drop.
    """
    kpi_id = "hourly_conversion"
    # Baseline period
    rows = [
        # aggregate baseline
        _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.35),
        # segmented baseline
        _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.30, {"device": "android"}),
        _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40, {"device": "ios"}),
        _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.35, {"device": "web"}),
        # Current period
        _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.333),
        _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.249, {"device": "android"}),
        _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.400, {"device": "ios"}),
        _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.350, {"device": "web"}),
    ]
    return rows


# ---------------------------------------------------------------------------
# Test: Android dominance for INC_001 (Req 12.2)
# ---------------------------------------------------------------------------

class TestINC001AndroidDominance:
    def test_android_is_dominant_segment(self):
        """Android must be the dominant negative contributor (Req 12.2, 4.3)."""
        kpi_values = _inc001_conversion_kpi_values()
        # Observed: aggregate current; Expected: aggregate baseline
        signal = _make_signal("hourly_conversion", observed=0.333, expected=0.35)

        result = decompose(kpi_values, signal, dimensions=["device"])

        assert result.dominant_segment is not None
        dominant_dim, dominant_seg = result.dominant_segment
        assert dominant_dim == "device"
        assert dominant_seg == "android", (
            f"Expected android to be dominant but got '{dominant_seg}'"
        )

    def test_android_has_largest_abs_contribution(self):
        """Android contribution_pct must be the largest among device segments."""
        kpi_values = _inc001_conversion_kpi_values()
        signal = _make_signal("hourly_conversion", observed=0.333, expected=0.35)

        result = decompose(kpi_values, signal, dimensions=["device"])

        device_contribs = [c for c in result.contributions if c.dimension == "device"]
        assert device_contribs, "Expected device contributions"

        android_pct = next(
            (c.contribution_pct for c in device_contribs if c.segment == "android"),
            None,
        )
        assert android_pct is not None, "Android contribution not found"

        for c in device_contribs:
            assert abs(android_pct) >= abs(c.contribution_pct), (
                f"Android ({android_pct:.2f}%) should dominate {c.segment} "
                f"({c.contribution_pct:.2f}%)"
            )

    def test_android_segment_delta_pct_is_negative(self):
        """Android segment_delta_pct must be negative (dropped by ~17%)."""
        kpi_values = _inc001_conversion_kpi_values()
        signal = _make_signal("hourly_conversion", observed=0.333, expected=0.35)

        result = decompose(kpi_values, signal, dimensions=["device"])

        android_contrib = next(
            (c for c in result.contributions
             if c.dimension == "device" and c.segment == "android"),
            None,
        )
        assert android_contrib is not None
        assert android_contrib.segment_delta_pct < 0, (
            "Android segment_delta_pct should be negative"
        )
        # Approximately -17% (within 2 pp tolerance for test)
        assert android_contrib.segment_delta_pct < -15.0, (
            f"Android delta should be close to -17%, got {android_contrib.segment_delta_pct:.2f}%"
        )

    def test_no_errors_for_valid_data(self):
        """Valid INC_001 device data should produce no errors."""
        kpi_values = _inc001_conversion_kpi_values()
        signal = _make_signal("hourly_conversion", observed=0.333, expected=0.35)

        result = decompose(kpi_values, signal, dimensions=["device"])

        assert result.errors == [], f"Unexpected errors: {result.errors}"


# ---------------------------------------------------------------------------
# Test: contribution_pct sum == 100 ±0.1 pp (Req 4.2)
# ---------------------------------------------------------------------------

class TestContributionSumTo100:
    def test_device_contributions_sum_to_100(self):
        """Device contributions must sum to 100 ±0.1 pp (Req 4.2)."""
        kpi_values = _inc001_conversion_kpi_values()
        signal = _make_signal("hourly_conversion", observed=0.333, expected=0.35)

        result = decompose(kpi_values, signal, dimensions=["device"])

        device_pcts = [c.contribution_pct for c in result.contributions if c.dimension == "device"]
        assert device_pcts, "No device contributions produced"
        total = sum(device_pcts)
        assert abs(total - 100.0) <= 0.1, (
            f"Device contributions sum to {total:.4f}%, not within ±0.1 pp of 100%"
        )

    def test_sum_to_100_with_many_segments(self):
        """Sum invariant holds across 5 segments with unequal deltas."""
        kpi_id = "hourly_conversion"
        # 5 segments with varied movements
        segments = {
            "a": (0.50, 0.40),  # up 10
            "b": (0.30, 0.35),  # down 5
            "c": (0.20, 0.25),  # down 5
            "d": (0.10, 0.08),  # up 2
            "e": (0.60, 0.65),  # down 5
        }
        kpi_values = []
        for seg, (curr, base) in segments.items():
            kpi_values.append(
                _make_kpi(kpi_id, "2024-01-01T10:00:00", base, {"device": seg})
            )
            kpi_values.append(
                _make_kpi(kpi_id, "2024-01-01T11:00:00", curr, {"device": seg})
            )
        # Add aggregate rows
        kpi_values.append(_make_kpi(kpi_id, "2024-01-01T10:00:00", 0.35))
        kpi_values.append(_make_kpi(kpi_id, "2024-01-01T11:00:00", 0.34))

        signal = _make_signal(kpi_id, observed=0.34, expected=0.35)
        result = decompose(kpi_values, signal, dimensions=["device"])

        device_pcts = [c.contribution_pct for c in result.contributions if c.dimension == "device"]
        assert device_pcts
        total = sum(device_pcts)
        assert abs(total - 100.0) <= 0.1, (
            f"5-segment contributions sum to {total:.4f}%, not within ±0.1 pp of 100%"
        )

    def test_two_segment_sum_to_100(self):
        """Edge case: two segments should split to exactly 100."""
        kpi_id = "hourly_conversion"
        kpi_values = [
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40, {"region": "north"}),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.30, {"region": "north"}),  # -10
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40, {"region": "south"}),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.36, {"region": "south"}),  # -4
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.33),
        ]
        signal = _make_signal(kpi_id, observed=0.33, expected=0.40)
        result = decompose(kpi_values, signal, dimensions=["region"])

        region_pcts = [c.contribution_pct for c in result.contributions if c.dimension == "region"]
        assert len(region_pcts) == 2
        assert abs(sum(region_pcts) - 100.0) <= 0.1


# ---------------------------------------------------------------------------
# Test: lexicographic tie-break (Req 4.4)
# ---------------------------------------------------------------------------

class TestLexicographicTieBreak:
    def test_tie_break_selects_lexicographically_first(self):
        """When two segments have equal contribution_pct, pick the lex-first (Req 4.4)."""
        kpi_id = "hourly_conversion"
        # Two segments with identical absolute movement
        kpi_values = [
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40, {"region": "zebra"}),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.30, {"region": "zebra"}),  # -0.10
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40, {"region": "alpha"}),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.30, {"region": "alpha"}),  # -0.10
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.30),
        ]
        signal = _make_signal(kpi_id, observed=0.30, expected=0.40)
        result = decompose(kpi_values, signal, dimensions=["region"])

        # Both segments contribute equally; tie-break must choose "alpha"
        assert result.dominant_segment is not None
        assert result.dominant_segment == ("region", "alpha"), (
            f"Tie-break should select 'alpha' but got '{result.dominant_segment}'"
        )

    def test_tie_break_selects_lex_first_among_three(self):
        """Tie among three segments: pick lexicographically first."""
        kpi_id = "hourly_conversion"
        # Three segments with identical absolute deltas
        segments = ["charlie", "alpha", "bravo"]
        kpi_values = []
        for seg in segments:
            kpi_values.append(_make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40, {"channel": seg}))
            kpi_values.append(_make_kpi(kpi_id, "2024-01-01T11:00:00", 0.30, {"channel": seg}))
        kpi_values.append(_make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40))
        kpi_values.append(_make_kpi(kpi_id, "2024-01-01T11:00:00", 0.30))

        signal = _make_signal(kpi_id, observed=0.30, expected=0.40)
        result = decompose(kpi_values, signal, dimensions=["channel"])

        assert result.dominant_segment == ("channel", "alpha"), (
            f"Expected ('channel', 'alpha'), got {result.dominant_segment}"
        )


# ---------------------------------------------------------------------------
# Test: missing / insufficient data (Req 4.6)
# ---------------------------------------------------------------------------

class TestMissingDataHandling:
    def test_missing_dimension_returns_error_not_exception(self):
        """Missing segmented data must produce an error string, not an exception (Req 4.6)."""
        kpi_id = "hourly_conversion"
        # Only aggregate rows — no "region" segmented data
        kpi_values = [
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.35),
        ]
        signal = _make_signal(kpi_id, observed=0.35, expected=0.40)

        # Should NOT raise; should return error indication
        result = decompose(kpi_values, signal, dimensions=["region"])

        assert len(result.errors) >= 1, "Expected at least one error for missing dimension"
        assert any("region" in e for e in result.errors), (
            f"Error should mention 'region', got: {result.errors}"
        )
        # No contributions produced for missing dimension
        region_contribs = [c for c in result.contributions if c.dimension == "region"]
        assert region_contribs == [], "No region contributions should be produced for missing data"

    def test_missing_one_dimension_does_not_affect_others(self):
        """Req 4.6: state for valid dimensions must not be mutated by a missing dimension."""
        kpi_id = "hourly_conversion"
        kpi_values = _inc001_conversion_kpi_values()  # has device; no region/channel
        signal = _make_signal("hourly_conversion", observed=0.333, expected=0.35)

        result = decompose(kpi_values, signal, dimensions=["device", "region"])

        # Device should still produce contributions
        device_contribs = [c for c in result.contributions if c.dimension == "device"]
        assert device_contribs, "Device contributions should still be produced"

        # Region should produce an error
        assert any("region" in e for e in result.errors)

    def test_empty_kpi_values_returns_errors(self):
        """Empty kpi_values must return errors for all requested dimensions."""
        signal = _make_signal("hourly_conversion", observed=0.30, expected=0.40)
        result = decompose([], signal, dimensions=["device", "region", "channel"])

        assert len(result.contributions) == 0
        assert len(result.errors) == 3
        assert result.dominant_segment is None

    def test_wrong_kpi_id_returns_errors(self):
        """KPIValues for a different kpi_id should cause errors for all dimensions."""
        kpi_values = _inc001_conversion_kpi_values()
        # Signal references a different kpi_id
        signal = _make_signal("hourly_revenue", observed=900.0, expected=1000.0)

        result = decompose(kpi_values, signal, dimensions=["device"])

        assert len(result.errors) >= 1, "Should error when no matching kpi_values"
        assert result.contributions == []

    def test_nan_segment_value_returns_error(self):
        """A NaN segment value must cause that dimension to return an error."""
        kpi_id = "hourly_conversion"
        kpi_values = [
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40, {"device": "android"}),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", float("nan"), {"device": "android"}),
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40, {"device": "ios"}),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.38, {"device": "ios"}),
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", float("nan")),
        ]
        signal = _make_signal(kpi_id, observed=float("nan"), expected=0.40)

        # Should not raise
        result = decompose(kpi_values, signal, dimensions=["device"])
        # NaN in observed anchor should produce an error
        assert len(result.errors) >= 1


# ---------------------------------------------------------------------------
# Test: all contributions stamped MethodTag.SQL (Req 4.5)
# ---------------------------------------------------------------------------

class TestMethodTagSQL:
    def test_all_contributions_are_tagged_sql(self):
        """Every DimensionContribution must carry MethodTag.SQL (Req 4.5)."""
        kpi_values = _inc001_conversion_kpi_values()
        signal = _make_signal("hourly_conversion", observed=0.333, expected=0.35)

        result = decompose(kpi_values, signal, dimensions=["device"])

        assert result.contributions, "Expected contributions"
        for c in result.contributions:
            assert c.method == MethodTag.SQL, (
                f"Contribution for {c.dimension}/{c.segment} has method={c.method!r}, "
                "expected MethodTag.SQL"
            )

    def test_multiple_dimensions_all_tagged_sql(self):
        """SQL tag must apply across all dimensions when multiple are requested."""
        kpi_id = "hourly_conversion"
        kpi_values = [
            # device
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40, {"device": "android"}),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.33, {"device": "android"}),
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40, {"device": "ios"}),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.40, {"device": "ios"}),
            # region
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40, {"region": "north"}),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.30, {"region": "north"}),
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40, {"region": "south"}),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.40, {"region": "south"}),
            # aggregate
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.36),
        ]
        signal = _make_signal(kpi_id, observed=0.36, expected=0.40)
        result = decompose(kpi_values, signal, dimensions=["device", "region"])

        for c in result.contributions:
            assert c.method == MethodTag.SQL


# ---------------------------------------------------------------------------
# Test: contribution_pct range [0, 100] (Req 4.1)
# ---------------------------------------------------------------------------

class TestContributionRange:
    def test_all_contribution_pct_in_range(self):
        """Every contribution_pct must be in [0, 100] (Req 4.1)."""
        kpi_values = _inc001_conversion_kpi_values()
        signal = _make_signal("hourly_conversion", observed=0.333, expected=0.35)

        result = decompose(kpi_values, signal, dimensions=["device"])

        for c in result.contributions:
            assert 0.0 <= c.contribution_pct <= 100.0, (
                f"contribution_pct={c.contribution_pct} out of [0, 100]"
            )

    def test_zero_movement_produces_zero_contributions(self):
        """When there is no movement, all contribution_pct values should be 0."""
        kpi_id = "hourly_conversion"
        # Both periods identical => zero delta for all segments
        kpi_values = [
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40, {"device": "android"}),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.40, {"device": "android"}),
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40, {"device": "ios"}),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.40, {"device": "ios"}),
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.40),
        ]
        signal = _make_signal(kpi_id, observed=0.40, expected=0.40, is_anomaly=False)
        result = decompose(kpi_values, signal, dimensions=["device"])

        for c in result.contributions:
            assert c.contribution_pct == 0.0, (
                f"Expected 0 contribution when no movement, got {c.contribution_pct}"
            )


# ---------------------------------------------------------------------------
# Test: get_ordered_contributions
# ---------------------------------------------------------------------------

class TestGetOrderedContributions:
    def test_returns_sorted_descending_by_abs(self):
        """Results must be sorted by abs(contribution_pct) descending."""
        kpi_values = _inc001_conversion_kpi_values()
        signal = _make_signal("hourly_conversion", observed=0.333, expected=0.35)
        result = decompose(kpi_values, signal, dimensions=["device"])

        ordered = get_ordered_contributions(result, top_n=10)

        for i in range(len(ordered) - 1):
            assert abs(ordered[i].contribution_pct) >= abs(ordered[i + 1].contribution_pct), (
                f"Results not sorted: index {i} ({ordered[i].contribution_pct}) "
                f"< index {i+1} ({ordered[i+1].contribution_pct})"
            )

    def test_top_n_limits_results(self):
        """top_n must cap the number of returned contributions."""
        kpi_values = _inc001_conversion_kpi_values()
        signal = _make_signal("hourly_conversion", observed=0.333, expected=0.35)
        result = decompose(kpi_values, signal, dimensions=["device"])

        ordered = get_ordered_contributions(result, top_n=1)
        assert len(ordered) == 1

    def test_top_n_larger_than_total_returns_all(self):
        """When top_n > total contributions, return all of them."""
        kpi_values = _inc001_conversion_kpi_values()
        signal = _make_signal("hourly_conversion", observed=0.333, expected=0.35)
        result = decompose(kpi_values, signal, dimensions=["device"])

        all_ordered = get_ordered_contributions(result, top_n=1000)
        assert len(all_ordered) == len(result.contributions)

    def test_empty_result_returns_empty_list(self):
        """Empty DecompositionResult should return an empty list."""
        empty_result = DecompositionResult(
            contributions=[], dominant_segment=None, errors=[]
        )
        assert get_ordered_contributions(empty_result) == []

    def test_android_is_first_in_ordered_results(self):
        """For INC_001, android should be the first item in ordered contributions."""
        kpi_values = _inc001_conversion_kpi_values()
        signal = _make_signal("hourly_conversion", observed=0.333, expected=0.35)
        result = decompose(kpi_values, signal, dimensions=["device"])

        ordered = get_ordered_contributions(result)
        assert ordered, "Expected at least one contribution"
        assert ordered[0].segment == "android", (
            f"Expected 'android' first, got '{ordered[0].segment}'"
        )


# ---------------------------------------------------------------------------
# Test: dominant_segment across multiple dimensions
# ---------------------------------------------------------------------------

class TestDominantSegmentCrossAxis:
    def test_dominant_is_picked_across_all_dimensions(self):
        """
        dominant_segment must be the global max across ALL dimensions (Req 4.3).

        Each dimension normalises its segments to sum to 100 independently.
        When both device and region each have one clearly dominant segment (that
        gets 100%), the tie is broken lexicographically.

        In this test:
          - device: android has a large delta, ios has zero  → android gets 100%
          - region: north has a large delta, south has zero  → north gets 100%
          - Both are 100%; "android" < "north" lexicographically → android wins.
        """
        kpi_id = "hourly_conversion"
        kpi_values = [
            # device: android moves, ios is flat
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40, {"device": "android"}),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.20, {"device": "android"}),  # big drop
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40, {"device": "ios"}),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.40, {"device": "ios"}),  # flat
            # region: north moves, south is flat
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40, {"region": "north"}),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.10, {"region": "north"}),  # big drop
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40, {"region": "south"}),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.40, {"region": "south"}),  # flat
            # aggregate
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.27),
        ]
        signal = _make_signal(kpi_id, observed=0.27, expected=0.40)
        result = decompose(kpi_values, signal, dimensions=["device", "region"])

        # Both android and north get 100% within their respective dimensions.
        # Tie-break is lexicographic: "android" < "north" → android is dominant.
        assert result.dominant_segment is not None
        assert result.dominant_segment == ("device", "android"), (
            f"Expected ('device', 'android') via lex tie-break, got {result.dominant_segment}"
        )

    def test_dominant_unique_winner_is_selected(self):
        """When one dimension has a clearly higher absolute contribution, it wins."""
        kpi_id = "hourly_conversion"
        # device: two segments, android = 70%, ios = 30%
        # region: two segments, north = 60%, south = 40%
        # android at 70% must beat north at 60%
        kpi_values = [
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40, {"device": "android"}),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.26, {"device": "android"}),  # delta -0.14
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40, {"device": "ios"}),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.34, {"device": "ios"}),     # delta -0.06
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40, {"region": "north"}),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.28, {"region": "north"}),   # delta -0.12
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40, {"region": "south"}),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.32, {"region": "south"}),   # delta -0.08
            _make_kpi(kpi_id, "2024-01-01T10:00:00", 0.40),
            _make_kpi(kpi_id, "2024-01-01T11:00:00", 0.30),
        ]
        signal = _make_signal(kpi_id, observed=0.30, expected=0.40)
        result = decompose(kpi_values, signal, dimensions=["device", "region"])

        # device/android: 0.14/(0.14+0.06) * 100 = 70%
        # region/north:   0.12/(0.12+0.08) * 100 = 60%
        # android (70%) > north (60%) → android is the global dominant
        assert result.dominant_segment is not None
        assert result.dominant_segment == ("device", "android"), (
            f"Expected ('device', 'android') as dominant with 70%, got {result.dominant_segment}"
        )
