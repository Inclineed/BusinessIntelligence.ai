# ISSUE-007: Scenario Coverage Is Far Too Thin

**Severity**: 🔴 High — Validity / Reliability  
**Status**: Open  
**Affects**: `etl/generate_scenarios.py`, `data/ground_truth.json`, `evaluation/evaluator.py`

---

## Problem Statement

Four scenarios is regression testing, not robustness demonstration.

| Scenario | Primary Mechanism Tested | Complexity |
|---|---|---|
| INC_001 | Single clear cause (checkout failure) | Low — one dominant signal |
| INC_002 | Ambiguity (two simultaneous causes) | Medium — but both are clean signals |
| INC_003 | Sparse history guard | Toy — 12 clean data points |
| INC_004 | Data quality guard | Toy — clean 4-hour NULL gap |

### What's Missing from Real Incidents

Real production incidents are messier in ways the current scenarios do not test:

1. **Multiple correlated KPIs moving simultaneously** with different magnitudes and different lag times. The current scenarios move 2-3 KPIs in lockstep.
2. **Segment splits with low statistical power.** The current INC_001 has Android at 68% contribution — an overwhelming signal. Real incidents often have the dominant segment at 30-40%, making localization ambiguous.
3. **Evidence arriving with different delays.** Currently all evidence is available simultaneously. In production, payment gateway data might arrive in real-time while deployment logs arrive with a 30-minute lag and marketing data with a 5-hour lag. The engine should handle partial evidence.
4. **Seasonality that looks like anomaly.** Black Friday, month-end, or lunch-hour traffic spikes can trigger false anomalies. There is no seasonal baseline correction in E2.
5. **Gradual degradation** rather than a sharp step function. A memory leak that slowly degrades latency over 8 hours doesn't produce a clean z-score spike.
6. **Conflicting evidence that doesn't resolve cleanly.** INC_002 has two causes but they're modeled as independent signals. Real incidents have entangled causes where evidence for one hypothesis partially supports and partially contradicts another.
7. **Noisy data** — real CSVs have duplicate rows, timezone mismatches, and inconsistent formats. The synthetic data is perfectly formatted.

### Why INC_003 and INC_004 Are Insufficient

- **INC_003** (sparse history): 12 perfectly clean daily data points. The guard fires because `12 < 30`. In production, you might have 28 points (below threshold) but with weekday/weekend patterns that make even 28 unreliable — the guard logic doesn't capture this.
- **INC_004** (data quality): A clean 4-hour gap with all NULLs. Real data quality issues are subtler — partial data delivery (50% of rows missing), schema drift (column renamed), or silent corruption (values present but wrong). The `data_quality_score < 0.80` check catches the clean-gap case but not the subtle ones.

---

## Remediation Plan

### Phase 1: Scenario Expansion (5 New Scenarios)

Generate the following scenarios in `etl/generate_scenarios.py`, each targeting a specific gap:

#### INC_005: Seasonal Pattern False Alarm
- **Design**: Model a normal Black Friday traffic spike. Revenue +40%, conversion stable, no technical issues.
- **Expected**: `anomaly_detected=True` (the movement is real) but E5 should recognize it as seasonal, and E6 should score the "technical failure" hypothesis LOW because no corroborating evidence exists.
- **Tests**: E2 detects the statistical anomaly but the pipeline correctly identifies it as a known pattern.

#### INC_006: Gradual Degradation
- **Design**: Memory leak causes latency to increase 5% per hour over 8 hours. No sharp spike.
- **Expected**: E2 should detect anomaly (cumulative z-score), but the signal is weaker than INC_001's sharp spike. Confidence should be MEDIUM, not HIGH.
- **Tests**: E2's ability to handle non-step-function anomalies.

#### INC_007: Low-Power Segment Split
- **Design**: Like INC_001 but Android contribution is only 35%, iOS is 30%, Desktop is 35%. The dominant segment is barely dominant.
- **Expected**: H1 still wins, but with lower confidence. The `segment_alignment` rule should score PARTIAL, not PASS.
- **Tests**: Graceful degradation when signals are weaker.

#### INC_008: Entangled Multi-Root-Cause
- **Design**: Network outage AND deployment failure happen within 30 minutes of each other. Both contribute to the same KPI movement. Evidence for the network hypothesis partially supports the deployment hypothesis (both affect latency).
- **Expected**: Either H1 or H2 wins, but with MEDIUM confidence and a small gap. The system should acknowledge uncertainty.
- **Tests**: E6's handling of entangled causes where evidence is shared.

#### INC_009: Partial Evidence Availability
- **Design**: Same as INC_001 but the deployment log arrives 45 minutes after the anomaly is detected. At the time of initial investigation, only payment gateway data is available.
- **Expected**: Without deployment evidence, the `timeline` rule scores PARTIAL. Confidence should be MEDIUM. If rerun with deployment data, confidence should increase to HIGH.
- **Tests**: Pipeline behavior under incomplete evidence.

### Phase 2: Noisy Data Variants

For each existing scenario, create a "noisy" variant:
- Add 2% duplicate rows to CSVs.
- Introduce timezone inconsistencies in 5% of timestamps.
- Add one column rename in one CSV (schema drift).
- Assert the pipeline handles all variants without crashing and with degraded (but not catastrophically wrong) results.

### Phase 3: Parameterized Stress Tests

```python
@pytest.mark.parametrize("noise_pct", [0.0, 0.02, 0.05, 0.10, 0.20])
def test_inc001_with_noise(noise_pct):
    """
    Add random noise to INC_001 evidence reliability weights.
    Assert H1 still wins at noise <= 0.10 but may not at 0.20.
    Document the robustness boundary.
    """
```

### Phase 4: Ground Truth Expansion

Extend `data/ground_truth.json` with entries for INC_005 through INC_009. Each entry should specify:
- `anomaly_detected`
- `expected_confidence_state`
- `winning_hypothesis_id` (or `null` for abstain)
- `abstain_expected`
- Any scenario-specific guards (`sparse_history_expected`, `data_quality_suspect_expected`)

---

## Impact Assessment

- **Risk if unfixed**: The system's correctness claims are based on 4 synthetic scenarios, 2 of which are toy cases. This is insufficient for any production deployment or stakeholder credibility.
- **Remediation complexity**: Medium. Data generation is mechanical; the hard part is defining honest ground truth for ambiguous scenarios.
- **Timeline**: Phase 1 (5 new scenarios) should be completed before the next evaluation cycle.
