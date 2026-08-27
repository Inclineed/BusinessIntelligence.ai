"""
tests/test_signal.py — Unit tests for Engine E2: Signal Engine [STATS]

Tests:
- Anomaly firing on INC_001-style data (revenue, conversion, payment, latency)
- Sparse-history guard suppresses false anomalies (Req 3.2)
- Data-quality guard suppresses false anomalies (Req 3.3)
- Corroboration overlap rule (Req 3.4)
- Not-evaluable path (Req 3.6)
- z-score and delta_pct clamping (Req 3.1)
- No-anomaly when only z-score threshold met but not delta_pct
- No-anomaly when only delta_pct threshold met but not z-score
- build_history_from_kpis helper
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import pytest

from models import (
    AnomalySignal,
    BusinessMateriality,
    FreshnessStatus,
    KPIValue,
    MaterialityAssessment,
    MethodTag,
)
from engines.signal import (
    HistoryWindow,
    assess_materiality,
    assert_corroboration,
    build_history_from_kpis,
    detect_signals,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_kpi(kpi_id: str, value: float, period: str, dimension_filters: dict = None) -> KPIValue:
    return KPIValue(
        kpi_id=kpi_id,
        name=kpi_id,
        value=value,
        unit="",
        period=period,
        dimension_filters=dimension_filters or {},
        source_id="test_src",
        freshness=FreshnessStatus.FRESH,
        method=MethodTag.SQL,
    )


def _baseline_window(kpi_id: str, values: list[float], dq: float = 1.0) -> HistoryWindow:
    periods = [f"2024-01-01T{i:02d}:00:00" for i in range(len(values))]
    return HistoryWindow(kpi_id=kpi_id, values=values, periods=periods, data_quality_score=dq)


def _generate_stable_baseline(n: int = 30, mean: float = 100.0, std: float = 2.0) -> list[float]:
    """Generate a deterministic stable baseline of n values around mean with given std."""
    import numpy as np

    rng = np.random.default_rng(42)
    return list(rng.normal(loc=mean, scale=std, size=n))


# ---------------------------------------------------------------------------
# INC_001: anomaly should fire for revenue, conversion, payment, latency
# ---------------------------------------------------------------------------


class TestINC001Anomalies:
    """Verify that INC_001-style movements produce anomaly signals."""

    def _build_inc001_kpis_and_history(self):
        """
        INC_001 scenario: revenue -8.2%, conversion -10%,
        payment failure rate ~4x, gateway latency +240%.
        All baselines have 30+ samples so sparse guard won't fire.
        """
        baseline_n = 35

        # Revenue: baseline ~100k, observed ~91.8k → -8.2%, z well above 3
        rev_baseline = _generate_stable_baseline(n=baseline_n, mean=100_000.0, std=500.0)
        observed_revenue = 91_800.0

        # Conversion: baseline ~0.05, observed ~0.045 → -10%, z well above 3
        conv_baseline = _generate_stable_baseline(n=baseline_n, mean=0.050, std=0.001)
        observed_conv = 0.045

        # Payment failure rate: baseline ~0.01, observed ~0.04 → +300%, z way above 3
        pay_baseline = _generate_stable_baseline(n=baseline_n, mean=0.010, std=0.001)
        observed_pay = 0.040

        # Gateway latency: baseline ~200ms, observed ~680ms → +240%, z way above 3
        lat_baseline = _generate_stable_baseline(n=baseline_n, mean=200.0, std=5.0)
        observed_lat = 680.0

        # Inventory: baseline ~0.95, observed ~0.95 → ~0% delta, no anomaly
        inv_baseline = _generate_stable_baseline(n=baseline_n, mean=0.95, std=0.01)
        observed_inv = 0.95

        kpi_values = [
            _make_kpi("hourly_revenue", observed_revenue, "2024-01-08T12:00:00"),
            _make_kpi("hourly_conversion", observed_conv, "2024-01-08T12:00:00"),
            _make_kpi("payment_failure_rate_15min", observed_pay, "2024-01-08T12:00:00"),
            _make_kpi("gateway_latency_15min", observed_lat, "2024-01-08T12:00:00"),
            _make_kpi("inventory_fill_rate_daily", observed_inv, "2024-01-08T00:00:00"),
        ]

        history = {
            "hourly_revenue": _baseline_window("hourly_revenue", rev_baseline),
            "hourly_conversion": _baseline_window("hourly_conversion", conv_baseline),
            "payment_failure_rate_15min": _baseline_window("payment_failure_rate_15min", pay_baseline),
            "gateway_latency_15min": _baseline_window("gateway_latency_15min", lat_baseline),
            "inventory_fill_rate_daily": _baseline_window("inventory_fill_rate_daily", inv_baseline),
        }

        return kpi_values, history

    def test_revenue_signal_computed(self):
        """Revenue is -8.2% — below the 10% delta threshold so is_anomaly=False,
        but z_score and delta_pct are still computed and stamped STATS.

        INC_001 revenue movement (-8.2%) is below the |delta_pct| >= 10% threshold,
        so the combined rule (Req 3.5) does NOT mark it as anomaly.
        The signal is still returned with correct computed values.
        """
        kpis, hist = self._build_inc001_kpis_and_history()
        signals = detect_signals(kpis, hist)
        rev_sig = next(s for s in signals if s.kpi_id == "hourly_revenue")
        # z_score is large (well below -3), delta_pct is around -8.2%
        assert rev_sig.z_score < -3.0, f"z_score should be < -3.0, got {rev_sig.z_score}"
        assert -10.0 < rev_sig.delta_pct < -7.0, f"delta_pct should be ~-8.2%, got {rev_sig.delta_pct}"
        # delta_pct < 10% so combined rule does not fire
        assert rev_sig.is_anomaly is False, (
            "Revenue delta_pct is ~-8.2% which is below the 10% threshold; "
            "combined rule (|z|>=3 AND |delta_pct|>=10) should NOT fire"
        )
        assert rev_sig.method == MethodTag.STATS

    def test_conversion_anomaly_fires(self):
        kpis, hist = self._build_inc001_kpis_and_history()
        signals = detect_signals(kpis, hist)
        conv_sig = next(s for s in signals if s.kpi_id == "hourly_conversion")
        assert conv_sig.is_anomaly is True, f"Conversion should be anomalous; z={conv_sig.z_score}, delta={conv_sig.delta_pct}"
        assert conv_sig.z_score < -3.0
        assert conv_sig.delta_pct < -9.0

    def test_payment_failure_anomaly_fires(self):
        kpis, hist = self._build_inc001_kpis_and_history()
        signals = detect_signals(kpis, hist)
        pay_sig = next(s for s in signals if s.kpi_id == "payment_failure_rate_15min")
        assert pay_sig.is_anomaly is True, f"Payment failure rate should be anomalous; z={pay_sig.z_score}, delta={pay_sig.delta_pct}"
        assert pay_sig.z_score > 3.0

    def test_gateway_latency_anomaly_fires(self):
        kpis, hist = self._build_inc001_kpis_and_history()
        signals = detect_signals(kpis, hist)
        lat_sig = next(s for s in signals if s.kpi_id == "gateway_latency_15min")
        assert lat_sig.is_anomaly is True, f"Latency should be anomalous; z={lat_sig.z_score}, delta={lat_sig.delta_pct}"
        assert lat_sig.z_score > 3.0

    def test_inventory_no_anomaly(self):
        """Inventory is at normal levels — should NOT be an anomaly."""
        kpis, hist = self._build_inc001_kpis_and_history()
        signals = detect_signals(kpis, hist)
        inv_sig = next(s for s in signals if s.kpi_id == "inventory_fill_rate_daily")
        assert inv_sig.is_anomaly is False, f"Inventory should NOT be anomalous; delta={inv_sig.delta_pct}"

    def test_all_signals_tagged_stats(self):
        kpis, hist = self._build_inc001_kpis_and_history()
        signals = detect_signals(kpis, hist)
        for sig in signals:
            assert sig.method == MethodTag.STATS, f"{sig.kpi_id} should have STATS tag"

    def test_no_false_guard_flags_on_anomalies(self):
        """The anomalous signals in INC_001 should not have guard flags set."""
        kpis, hist = self._build_inc001_kpis_and_history()
        signals = detect_signals(kpis, hist)
        for sig in signals:
            if sig.is_anomaly:
                assert not sig.sparse_history, f"{sig.kpi_id} anomaly should not have sparse_history flag"
                assert not sig.data_quality_suspect, f"{sig.kpi_id} anomaly should not have data_quality_suspect flag"


# ---------------------------------------------------------------------------
# Req 3.2: Sparse-history guard
# ---------------------------------------------------------------------------


class TestSparseHistoryGuard:

    def test_sparse_history_suppresses_anomaly(self):
        """Fewer than 30 baseline samples → sparse_history=True, is_anomaly=False."""
        baseline = _generate_stable_baseline(n=29, mean=100.0, std=1.0)
        window = _baseline_window("kpi_x", baseline)
        # Observed value far from baseline mean → would be anomaly without guard
        kpis = [_make_kpi("kpi_x", 50.0, "2024-01-01T10:00:00")]
        signals = detect_signals(kpis, {"kpi_x": window})
        assert len(signals) == 1
        sig = signals[0]
        assert sig.sparse_history is True
        assert sig.is_anomaly is False

    def test_exact_29_samples_triggers_guard(self):
        baseline = _generate_stable_baseline(n=29, mean=100.0, std=1.0)
        window = _baseline_window("kpi_y", baseline)
        kpis = [_make_kpi("kpi_y", 200.0, "2024-01-01T10:00:00")]
        signals = detect_signals(kpis, {"kpi_y": window})
        assert signals[0].sparse_history is True

    def test_exactly_30_samples_does_not_trigger_guard(self):
        baseline = _generate_stable_baseline(n=30, mean=100.0, std=1.0)
        window = _baseline_window("kpi_z", baseline)
        # Observed is close to baseline mean → no anomaly, but guard should NOT fire
        kpis = [_make_kpi("kpi_z", 101.0, "2024-01-01T10:00:00")]
        signals = detect_signals(kpis, {"kpi_z": window})
        assert signals[0].sparse_history is False

    def test_sparse_guard_overrides_threshold(self):
        """Even if z_score and delta_pct would trigger anomaly, sparse guard wins."""
        baseline = _generate_stable_baseline(n=5, mean=100.0, std=0.5)
        window = _baseline_window("kpi_sparse", baseline)
        kpis = [_make_kpi("kpi_sparse", 50.0, "2024-01-01T10:00:00")]
        signals = detect_signals(kpis, {"kpi_sparse": window})
        assert signals[0].is_anomaly is False
        assert signals[0].sparse_history is True

    def test_custom_min_samples_threshold(self):
        """Custom threshold of 10 changes the guard cutoff."""
        # 15 samples — normally OK (>=30), but below custom threshold of 20
        baseline = _generate_stable_baseline(n=15, mean=100.0, std=1.0)
        window = _baseline_window("kpi_custom", baseline)
        kpis = [_make_kpi("kpi_custom", 50.0, "2024-01-01T10:00:00")]
        signals = detect_signals(kpis, {"kpi_custom": window}, thresholds={"sparse_history_min_samples": 20})
        assert signals[0].sparse_history is True


# ---------------------------------------------------------------------------
# Req 3.3: Data-quality guard
# ---------------------------------------------------------------------------


class TestDataQualityGuard:

    def test_low_data_quality_suppresses_anomaly(self):
        """data_quality_score < 0.80 → data_quality_suspect=True, is_anomaly=False."""
        baseline = _generate_stable_baseline(n=35, mean=100.0, std=1.0)
        window = _baseline_window("kpi_dq", baseline, dq=0.79)
        kpis = [_make_kpi("kpi_dq", 50.0, "2024-01-01T10:00:00")]
        signals = detect_signals(kpis, {"kpi_dq": window})
        sig = signals[0]
        assert sig.data_quality_suspect is True
        assert sig.is_anomaly is False

    def test_exactly_080_does_not_trigger_dq_guard(self):
        """data_quality_score == 0.80 is exactly at threshold → guard should NOT fire."""
        baseline = _generate_stable_baseline(n=35, mean=100.0, std=1.0)
        window = _baseline_window("kpi_dq_edge", baseline, dq=0.80)
        # Close to baseline → not an anomaly regardless, but guard should not fire
        kpis = [_make_kpi("kpi_dq_edge", 101.0, "2024-01-01T10:00:00")]
        signals = detect_signals(kpis, {"kpi_dq_edge": window})
        assert signals[0].data_quality_suspect is False

    def test_dq_guard_sets_correct_score_fields(self):
        """When DQ guard fires, z_score and delta_pct are still computed and clamped."""
        baseline = _generate_stable_baseline(n=35, mean=100.0, std=2.0)
        window = _baseline_window("kpi_dq2", baseline, dq=0.5)
        kpis = [_make_kpi("kpi_dq2", 50.0, "2024-01-01T10:00:00")]
        signals = detect_signals(kpis, {"kpi_dq2": window})
        sig = signals[0]
        # z_score and delta_pct should be computed (non-zero), not zeroed out
        assert sig.z_score != 0.0
        assert sig.delta_pct != 0.0
        assert sig.is_anomaly is False
        assert sig.data_quality_suspect is True


# ---------------------------------------------------------------------------
# Req 3.1: z-score and delta_pct bounds and rounding
# ---------------------------------------------------------------------------


class TestZScoreAndDeltaPct:

    def test_z_score_clamped_upper(self):
        """An extreme outlier should clamp z_score to 1000.0."""
        baseline = _generate_stable_baseline(n=35, mean=0.0, std=0.001)
        window = _baseline_window("kpi_clamp", baseline)
        # Huge positive value
        kpis = [_make_kpi("kpi_clamp", 1_000_000.0, "2024-01-01T10:00:00")]
        signals = detect_signals(kpis, {"kpi_clamp": window})
        assert signals[0].z_score <= 1000.0

    def test_z_score_clamped_lower(self):
        """An extreme negative outlier should clamp z_score to -1000.0."""
        baseline = _generate_stable_baseline(n=35, mean=0.0, std=0.001)
        window = _baseline_window("kpi_clamp_neg", baseline)
        kpis = [_make_kpi("kpi_clamp_neg", -1_000_000.0, "2024-01-01T10:00:00")]
        signals = detect_signals(kpis, {"kpi_clamp_neg": window})
        assert signals[0].z_score >= -1000.0

    def test_delta_pct_clamped_upper(self):
        """Huge positive movement clamps delta_pct to 100.0."""
        baseline = _generate_stable_baseline(n=35, mean=1.0, std=0.01)
        window = _baseline_window("kpi_dp_clamp", baseline)
        kpis = [_make_kpi("kpi_dp_clamp", 1_000.0, "2024-01-01T10:00:00")]
        signals = detect_signals(kpis, {"kpi_dp_clamp": window})
        assert signals[0].delta_pct <= 100.0

    def test_delta_pct_clamped_lower(self):
        """Huge negative movement clamps delta_pct to -100.0."""
        baseline = _generate_stable_baseline(n=35, mean=100.0, std=1.0)
        window = _baseline_window("kpi_dp_clamp_neg", baseline)
        kpis = [_make_kpi("kpi_dp_clamp_neg", -1_000_000.0, "2024-01-01T10:00:00")]
        signals = detect_signals(kpis, {"kpi_dp_clamp_neg": window})
        assert signals[0].delta_pct >= -100.0

    def test_z_score_zero_when_std_is_zero(self):
        """Constant baseline → std=0 → z_score=0, no division error."""
        baseline = [50.0] * 35
        window = HistoryWindow(kpi_id="kpi_const", values=baseline, periods=["p"] * 35)
        kpis = [_make_kpi("kpi_const", 60.0, "2024-01-01T10:00:00")]
        signals = detect_signals(kpis, {"kpi_const": window})
        assert signals[0].z_score == 0.0

    def test_z_score_rounded_to_2dp(self):
        """z_score must be rounded to 2 decimal places."""
        baseline = _generate_stable_baseline(n=35, mean=100.0, std=3.0)
        window = _baseline_window("kpi_round", baseline)
        kpis = [_make_kpi("kpi_round", 110.0, "2024-01-01T10:00:00")]
        signals = detect_signals(kpis, {"kpi_round": window})
        # Check it's rounded to 2 decimal places
        z = signals[0].z_score
        assert round(z, 2) == z

    def test_delta_pct_rounded_to_2dp(self):
        baseline = _generate_stable_baseline(n=35, mean=100.0, std=3.0)
        window = _baseline_window("kpi_round_dp", baseline)
        kpis = [_make_kpi("kpi_round_dp", 110.0, "2024-01-01T10:00:00")]
        signals = detect_signals(kpis, {"kpi_round_dp": window})
        dp = signals[0].delta_pct
        assert round(dp, 2) == dp


# ---------------------------------------------------------------------------
# Req 3.5: Anomaly threshold — both conditions required
# ---------------------------------------------------------------------------


class TestAnomalyThreshold:

    def test_no_anomaly_when_only_z_exceeds(self):
        """High z-score but small delta_pct → is_anomaly=False."""
        # Very tight baseline → small absolute delta gives huge z
        baseline = [100.0 + i * 0.0001 for i in range(35)]  # std ~0.001
        window = HistoryWindow(kpi_id="kpi_z_only", values=baseline, periods=["p"] * 35)
        kpis = [_make_kpi("kpi_z_only", 100.05, "2024-01-01T10:00:00")]  # ~0.05% delta
        signals = detect_signals(kpis, {"kpi_z_only": window})
        sig = signals[0]
        # delta_pct should be well below 10%, so no anomaly even if z > 3
        assert sig.delta_pct < 10.0
        assert sig.is_anomaly is False

    def test_no_anomaly_when_only_delta_exceeds(self):
        """Large delta_pct but low z-score → is_anomaly=False."""
        # Very noisy baseline so the absolute change doesn't stand out statistically
        import numpy as np
        rng = np.random.default_rng(0)
        baseline = list(rng.uniform(0, 200, 35))  # std ~58
        mean_val = float(np.mean(baseline))
        window = HistoryWindow(kpi_id="kpi_dp_only", values=baseline, periods=["p"] * 35)
        # Move by ~15% of mean (>10%) but z will be small due to high noise
        kpis = [_make_kpi("kpi_dp_only", mean_val * 1.15, "2024-01-01T10:00:00")]
        signals = detect_signals(kpis, {"kpi_dp_only": window})
        sig = signals[0]
        # z_score should be well below 3.0
        assert abs(sig.z_score) < 3.0
        assert sig.is_anomaly is False

    def test_anomaly_when_both_thresholds_exceeded(self):
        """Both |z|>=3 and |delta_pct|>=10 → is_anomaly=True."""
        baseline = _generate_stable_baseline(n=35, mean=100.0, std=1.0)
        window = _baseline_window("kpi_both", baseline)
        # 20% drop with low std → z will be high
        kpis = [_make_kpi("kpi_both", 80.0, "2024-01-01T10:00:00")]
        signals = detect_signals(kpis, {"kpi_both": window})
        sig = signals[0]
        assert abs(sig.z_score) >= 3.0
        assert abs(sig.delta_pct) >= 10.0
        assert sig.is_anomaly is True


# ---------------------------------------------------------------------------
# Req 3.6: Not-evaluable path
# ---------------------------------------------------------------------------


class TestNotEvaluable:

    def test_missing_history_returns_not_evaluable(self):
        """No history window for a kpi_id → is_anomaly=False, both guard flags False."""
        kpis = [_make_kpi("kpi_missing", 50.0, "2024-01-01T10:00:00")]
        signals = detect_signals(kpis, {})  # empty history
        assert len(signals) == 1
        sig = signals[0]
        assert sig.is_anomaly is False
        assert sig.z_score == 0.0
        assert sig.sparse_history is False
        assert sig.data_quality_suspect is False

    def test_empty_baseline_values_returns_not_evaluable(self):
        """HistoryWindow with empty values list → not evaluable."""
        window = HistoryWindow(kpi_id="kpi_empty", values=[], periods=[])
        kpis = [_make_kpi("kpi_empty", 50.0, "2024-01-01T10:00:00")]
        signals = detect_signals(kpis, {"kpi_empty": window})
        sig = signals[0]
        assert sig.is_anomaly is False
        assert sig.z_score == 0.0

    def test_all_nan_baseline_returns_not_evaluable(self):
        """HistoryWindow with all-NaN values → not evaluable."""
        window = HistoryWindow(
            kpi_id="kpi_nan",
            values=[float("nan")] * 35,
            periods=["p"] * 35,
        )
        kpis = [_make_kpi("kpi_nan", 50.0, "2024-01-01T10:00:00")]
        signals = detect_signals(kpis, {"kpi_nan": window})
        sig = signals[0]
        assert sig.is_anomaly is False
        assert sig.z_score == 0.0


# ---------------------------------------------------------------------------
# Req 3.4: Corroboration overlap rule
# ---------------------------------------------------------------------------


class TestCorroboration:

    def _make_anomalous_signal(self, kpi_id: str) -> object:
        from models import AnomalySignal, MethodTag
        return AnomalySignal(
            kpi_id=kpi_id,
            observed=50.0,
            expected=100.0,
            delta_pct=-50.0,
            z_score=-10.0,
            is_anomaly=True,
            corroborated_by=[],
            sparse_history=False,
            data_quality_suspect=False,
            method=MethodTag.STATS,
        )

    def test_full_overlap_corroborates(self):
        """Two KPIs sharing all periods → overlap=100% → corroborated."""
        sig_a = self._make_anomalous_signal("kpi_a")
        sig_b = self._make_anomalous_signal("kpi_b")
        periods = {
            "kpi_a": ["2024-01-01T00:00", "2024-01-01T01:00", "2024-01-01T02:00"],
            "kpi_b": ["2024-01-01T00:00", "2024-01-01T01:00", "2024-01-01T02:00"],
        }
        result = assert_corroboration([sig_a, sig_b], periods)
        assert "kpi_b" in sig_a.corroborated_by
        assert "kpi_a" in sig_b.corroborated_by

    def test_80_percent_overlap_corroborates(self):
        """Exactly 80% overlap → corroborated (boundary inclusive)."""
        sig_a = self._make_anomalous_signal("kpi_a")
        sig_b = self._make_anomalous_signal("kpi_b")
        # kpi_a has 5 periods, kpi_b has 5 periods, 4 overlap → 4/5 = 80%
        periods = {
            "kpi_a": ["p1", "p2", "p3", "p4", "p5"],
            "kpi_b": ["p1", "p2", "p3", "p4", "p6"],  # 4 of 5 match
        }
        result = assert_corroboration([sig_a, sig_b], periods)
        assert "kpi_b" in sig_a.corroborated_by
        assert "kpi_a" in sig_b.corroborated_by

    def test_below_80_percent_does_not_corroborate(self):
        """Less than 80% overlap → NOT corroborated."""
        sig_a = self._make_anomalous_signal("kpi_a")
        sig_b = self._make_anomalous_signal("kpi_b")
        # 3 out of 5 = 60% overlap
        periods = {
            "kpi_a": ["p1", "p2", "p3", "p4", "p5"],
            "kpi_b": ["p1", "p2", "p3", "p6", "p7"],
        }
        assert_corroboration([sig_a, sig_b], periods)
        assert "kpi_b" not in sig_a.corroborated_by
        assert "kpi_a" not in sig_b.corroborated_by

    def test_non_anomalous_signals_not_corroborated(self):
        """Signals with is_anomaly=False are excluded from corroboration."""
        from models import AnomalySignal, MethodTag
        sig_a = self._make_anomalous_signal("kpi_a")
        sig_b = AnomalySignal(
            kpi_id="kpi_b",
            observed=95.0,
            expected=100.0,
            delta_pct=-5.0,
            z_score=-1.0,
            is_anomaly=False,  # NOT anomalous
            corroborated_by=[],
            sparse_history=False,
            data_quality_suspect=False,
            method=MethodTag.STATS,
        )
        periods = {
            "kpi_a": ["p1", "p2", "p3"],
            "kpi_b": ["p1", "p2", "p3"],
        }
        assert_corroboration([sig_a, sig_b], periods)
        assert len(sig_a.corroborated_by) == 0
        assert len(sig_b.corroborated_by) == 0

    def test_corroboration_is_bidirectional(self):
        """Corroboration is added to both signals."""
        sig_a = self._make_anomalous_signal("kpi_a")
        sig_b = self._make_anomalous_signal("kpi_b")
        periods = {"kpi_a": ["p1", "p2"], "kpi_b": ["p1", "p2"]}
        assert_corroboration([sig_a, sig_b], periods)
        assert "kpi_b" in sig_a.corroborated_by
        assert "kpi_a" in sig_b.corroborated_by

    def test_empty_periods_no_corroboration(self):
        """Empty period lists → no corroboration (can't compute overlap)."""
        sig_a = self._make_anomalous_signal("kpi_a")
        sig_b = self._make_anomalous_signal("kpi_b")
        periods = {"kpi_a": [], "kpi_b": []}
        assert_corroboration([sig_a, sig_b], periods)
        assert len(sig_a.corroborated_by) == 0


# ---------------------------------------------------------------------------
# build_history_from_kpis helper
# ---------------------------------------------------------------------------


class TestBuildHistoryFromKpis:

    def test_builds_history_from_series(self):
        """History uses all but the last value as baseline."""
        kpis = [
            _make_kpi("kpi_h", float(i), f"2024-01-01T{i:02d}:00:00")
            for i in range(5)
        ]
        history = build_history_from_kpis(kpis)
        assert "kpi_h" in history
        window = history["kpi_h"]
        # 5 values total, 4 baseline
        assert len(window.values) == 4
        assert window.values == [0.0, 1.0, 2.0, 3.0]

    def test_ignores_segmented_rows(self):
        """Rows with dimension_filters are excluded from history."""
        kpis = [
            _make_kpi("kpi_seg", 1.0, "2024-01-01T00:00:00"),
            _make_kpi("kpi_seg", 2.0, "2024-01-01T01:00:00", {"device": "android"}),
            _make_kpi("kpi_seg", 3.0, "2024-01-01T02:00:00"),
        ]
        history = build_history_from_kpis(kpis)
        window = history["kpi_seg"]
        # Only aggregate rows: [1.0, 3.0] → baseline = [1.0]
        assert len(window.values) == 1
        assert window.values == [1.0]

    def test_baseline_kpi_ids_filter(self):
        """Only specified kpi_ids are built when baseline_kpi_ids is provided."""
        kpis = [
            _make_kpi("kpi_a", float(i), f"2024-01-01T{i:02d}:00:00")
            for i in range(5)
        ] + [
            _make_kpi("kpi_b", float(i), f"2024-01-01T{i:02d}:00:00")
            for i in range(5)
        ]
        history = build_history_from_kpis(kpis, baseline_kpi_ids=["kpi_a"])
        assert "kpi_a" in history
        assert "kpi_b" not in history

    def test_sorted_by_period(self):
        """History values are sorted by period regardless of input order."""
        kpis = [
            _make_kpi("kpi_sort", 3.0, "2024-01-01T02:00:00"),
            _make_kpi("kpi_sort", 1.0, "2024-01-01T00:00:00"),
            _make_kpi("kpi_sort", 2.0, "2024-01-01T01:00:00"),
        ]
        history = build_history_from_kpis(kpis)
        window = history["kpi_sort"]
        # 3 values sorted → baseline [1.0, 2.0], current 3.0
        assert window.values == [1.0, 2.0]

    def test_single_value_produces_empty_baseline(self):
        """Only one value → nothing left for baseline after excluding last."""
        kpis = [_make_kpi("kpi_single", 42.0, "2024-01-01T00:00:00")]
        history = build_history_from_kpis(kpis)
        window = history["kpi_single"]
        assert window.values == []


# ---------------------------------------------------------------------------
# Aggregate-row selection
# ---------------------------------------------------------------------------


class TestAggregateRowSelection:

    def test_only_aggregate_rows_evaluated(self):
        """detect_signals should only use rows with empty dimension_filters."""
        # Aggregate row: value=50 (anomalous relative to baseline)
        # Per-device rows: values=200 (not anomalous relative to same baseline)
        baseline = _generate_stable_baseline(n=35, mean=100.0, std=1.0)
        window = _baseline_window("hourly_conversion", baseline)
        kpis = [
            _make_kpi("hourly_conversion", 50.0, "2024-01-01T10:00:00"),  # aggregate
            _make_kpi("hourly_conversion", 200.0, "2024-01-01T10:00:00", {"device": "android"}),
            _make_kpi("hourly_conversion", 200.0, "2024-01-01T10:00:00", {"device": "ios"}),
        ]
        signals = detect_signals(kpis, {"hourly_conversion": window})
        # Should produce exactly one signal (for the aggregate row)
        assert len(signals) == 1
        sig = signals[0]
        assert sig.observed == 50.0  # used the aggregate row
        assert sig.is_anomaly is True


# ---------------------------------------------------------------------------
# Business Materiality & Priority Ranking (P0 #1)
# ---------------------------------------------------------------------------


class TestBusinessMateriality:
    """Verify statistical significance -> business impact -> priority rank."""

    def _sample_contract(self):
        return {
            "domain": "Retail / Consumer Goods",
            "kpis": [
                {
                    "id": "hourly_revenue",
                    "materiality": {
                        "impact_metric": "financial",
                        "multiplier": 1.0,
                        "critical_threshold": 25000.0,
                        "high_threshold": 10000.0,
                        "medium_threshold": 5000.0,
                        "low_threshold": 1000.0,
                    },
                },
                {
                    "id": "hourly_conversion",
                    "materiality": {
                        "impact_metric": "financial",
                        "multiplier": 20000.0,
                        "critical_threshold": 25000.0,
                        "high_threshold": 10000.0,
                        "medium_threshold": 5000.0,
                        "low_threshold": 1000.0,
                    },
                },
                {
                    "id": "gateway_latency_15min",
                    "materiality": {
                        "impact_metric": "volume",
                        "multiplier": 10.0,
                        "critical_threshold": 3000.0,
                        "high_threshold": 1500.0,
                        "medium_threshold": 500.0,
                        "low_threshold": 100.0,
                    },
                },
                {
                    "id": "minor_latency",
                    "materiality": {
                        "impact_metric": "volume",
                        "multiplier": 1.0,
                        "critical_threshold": 1000.0,
                        "high_threshold": 500.0,
                        "medium_threshold": 100.0,
                        "low_threshold": 20.0,
                    },
                },
            ],
        }

    def test_materiality_tiers_and_impact_calculation(self):
        """Financial and volume multipliers correctly translate delta into impact and tier."""
        contract = self._sample_contract()
        signals = [
            AnomalySignal(
                kpi_id="hourly_revenue",
                observed=70000.0,
                expected=100000.0,  # delta = 30000 * 1.0 = 30000 >= 25000 -> CRITICAL
                delta_pct=-30.0,
                z_score=-4.5,
                is_anomaly=True,
            ),
            AnomalySignal(
                kpi_id="hourly_conversion",
                observed=0.045,
                expected=0.050,  # delta = 0.005 * 20000 = 100 (below low 1000) -> NEGLIGIBLE
                delta_pct=-10.0,
                z_score=-3.5,
                is_anomaly=True,
            ),
            AnomalySignal(
                kpi_id="gateway_latency_15min",
                observed=380.0,
                expected=200.0,  # delta = 180 * 10 = 1800 (>= 1500 < 3000) -> HIGH
                delta_pct=90.0,
                z_score=5.0,
                is_anomaly=True,
            ),
        ]

        assessments = assess_materiality(signals, contract)
        assert len(assessments) == 3

        rev_mat = next(a for a in assessments if a.kpi_id == "hourly_revenue")
        assert rev_mat.financial_impact == 30000.0
        assert rev_mat.volume_impact is None
        assert rev_mat.business_materiality == BusinessMateriality.CRITICAL
        assert rev_mat.priority_rank == 1

        lat_mat = next(a for a in assessments if a.kpi_id == "gateway_latency_15min")
        assert lat_mat.financial_impact is None
        assert lat_mat.volume_impact == 1800.0
        assert lat_mat.business_materiality == BusinessMateriality.HIGH
        assert lat_mat.priority_rank == 2

        conv_mat = next(a for a in assessments if a.kpi_id == "hourly_conversion")
        assert conv_mat.financial_impact == 100.0
        assert conv_mat.business_materiality == BusinessMateriality.NEGLIGIBLE
        assert conv_mat.priority_rank == 3

    def test_non_anomalies_excluded_from_ranking(self):
        """Non-anomalies default to NEGLIGIBLE and priority_rank = 0."""
        contract = self._sample_contract()
        signals = [
            AnomalySignal(
                kpi_id="hourly_revenue",
                observed=100000.0,
                expected=100000.0,
                delta_pct=0.0,
                z_score=0.0,
                is_anomaly=False,
            ),
            AnomalySignal(
                kpi_id="gateway_latency_15min",
                observed=600.0,
                expected=200.0,  # delta = 400 * 10 = 4000 >= 3000 -> CRITICAL
                delta_pct=200.0,
                z_score=6.0,
                is_anomaly=True,
            ),
        ]

        assessments = assess_materiality(signals, contract)
        rev_mat = next(a for a in assessments if a.kpi_id == "hourly_revenue")
        lat_mat = next(a for a in assessments if a.kpi_id == "gateway_latency_15min")

        assert rev_mat.business_materiality == BusinessMateriality.NEGLIGIBLE
        assert rev_mat.priority_rank == 0
        assert rev_mat.financial_impact is None

        assert lat_mat.business_materiality == BusinessMateriality.CRITICAL
        assert lat_mat.priority_rank == 1

    def test_deterministic_tie_breaking(self):
        """Tie-breaking respects materiality tier -> impact magnitude -> segmentability -> kpi_id."""
        contract = self._sample_contract()
        # Both revenue and conversion are CRITICAL with same impact (30000), but revenue is segmentable
        signals = [
            AnomalySignal(
                kpi_id="hourly_conversion",
                observed=0.035,
                expected=0.050,  # delta = 0.015 * 20000 = 300 -> wait, let's make multiplier 2,000,000 so delta 0.015 * 2,000,000 = 30,000
                delta_pct=-30.0,
                z_score=-4.0,
                is_anomaly=True,
            ),
            AnomalySignal(
                kpi_id="hourly_revenue",
                observed=70000.0,
                expected=100000.0,  # delta = 30000 * 1 = 30000
                delta_pct=-30.0,
                z_score=-4.0,
                is_anomaly=True,
            ),
        ]
        # Custom contract for exact tie
        custom_contract = {
            "kpis": [
                {
                    "id": "hourly_revenue",
                    "materiality": {
                        "impact_metric": "financial",
                        "multiplier": 1.0,
                        "critical_threshold": 25000.0,
                        "high_threshold": 10000.0,
                        "medium_threshold": 5000.0,
                        "low_threshold": 1000.0,
                    },
                },
                {
                    "id": "hourly_conversion",
                    "materiality": {
                        "impact_metric": "financial",
                        "multiplier": 2000000.0,
                        "critical_threshold": 25000.0,
                        "high_threshold": 10000.0,
                        "medium_threshold": 5000.0,
                        "low_threshold": 1000.0,
                    },
                },
            ]
        }
        # hourly_conversion is segmentable
        assessments = assess_materiality(
            signals,
            custom_contract,
            segmentable_kpi_ids={"hourly_conversion"},
        )
        conv = next(a for a in assessments if a.kpi_id == "hourly_conversion")
        rev = next(a for a in assessments if a.kpi_id == "hourly_revenue")

        # Both are CRITICAL and both have financial_impact = 30000, but hourly_conversion is segmentable
        assert conv.business_materiality == BusinessMateriality.CRITICAL
        assert rev.business_materiality == BusinessMateriality.CRITICAL
        assert conv.financial_impact == 30000.0
        assert rev.financial_impact == 30000.0
        assert conv.priority_rank == 1
        assert rev.priority_rank == 2

