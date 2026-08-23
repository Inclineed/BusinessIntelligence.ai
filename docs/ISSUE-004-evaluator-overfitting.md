# ISSUE-004: Evaluator Cannot Distinguish Genuine Reasoning from Scenario Overfitting

**Severity**: 🔴 Critical — Structural / Correctness  
**Status**: Open  
**Affects**: `evaluation/evaluator.py`, `data/ground_truth.json`, `etl/generate_scenarios.py`

---

## Problem Statement

The system has four synthetic scenarios (INC_001 through INC_004) with known outcomes, evaluated by a fixed 15-dimension scorecard. The pipeline was developed and iteratively tuned against these exact scenarios. A 15/15 score on INC_001–INC_004 tells you the system works on INC_001–INC_004. It does not tell you the system generalizes.

This is the classic failure mode of evaluating on your training distribution. It is not malicious — it is the normal consequence of a closed development loop:

1. Developer writes INC_001 with known ground truth (H1 wins with HIGH).
2. Developer tunes E6 rule weights, thresholds, and keyword sets until H1 wins with HIGH.
3. Evaluator confirms 15/15.
4. Steps 2-3 repeat for INC_002, INC_003, INC_004.

### What's Missing

- **No held-out test set.** All four scenarios were visible during development. There is no scenario whose outcome was defined before the engine code was written and then evaluated without tuning.
- **No adversarial perturbation.** No tests that introduce noise (e.g., adding a 5th evidence item that partially supports H2, or reducing Android's contribution from 68% to 35%) to verify the engine degrades gracefully rather than flipping to a wrong answer.
- **No cross-scenario transfer test.** No test that verifies the engine's behavior on a novel KPI domain (e.g., SaaS churn rather than retail checkout) without retraining.
- **No calibration measurement.** When the engine says HIGH, how often is it actually correct? This is unknowable from 4 scenarios.

### Current Code Evidence

In [`evaluation/evaluator.py`](file:///e:/accenture/evaluation/evaluator.py):
- `evaluate()` (line 269) dispatches INC_001 to the full 15-dimension scorer, and INC_002–INC_004 to `_score_additional_scenario()`.
- The ground truth for each scenario is hardcoded in [`data/ground_truth.json`](file:///e:/accenture/data/ground_truth.json).
- The evaluator has **no mechanism** for loading novel scenarios or parameterized test inputs.

In [`engines/challenge.py`](file:///e:/accenture/engines/challenge.py):
- `ChallengeThresholds` defaults (line 60): `high_threshold=0.70`, `medium_threshold=0.40`, `abstain_threshold=0.30`, `min_gap=0.15`.
- These values were calibrated so that INC_001 H1 scores above 0.70 and INC_002's gap falls below 0.15.
- There is no documentation of how these thresholds would behave on a different evidence distribution.

---

## Remediation Plan

### Phase 1: Held-Out Scenario Generation

Create 3-5 new scenarios **before examining what the engine produces**. Define ground truth first, then run:

```
INC_005: Seasonal demand spike misinterpreted as anomaly
  - Expected: anomaly_detected=False (seasonal pattern, not an anomaly)
  - Tests E2's ability to distinguish seasonality from genuine anomaly

INC_006: Multi-root-cause incident (network + deployment)
  - Expected: H1 wins with HIGH confidence (two real causes, one strongly supported)
  - Tests E6's ability to handle partial truth in multiple hypotheses

INC_007: Gradual degradation (no sharp anomaly point)
  - Expected: anomaly_detected=True with HIGH confidence
  - Tests E2's sensitivity to slow-moving trends vs. sharp spikes
```

**Note on Confidence Semantics**: The evaluator treats `confidence_state` as a strict expected output. It is determined exclusively by the deterministic E6 scoring math (evidence relevance + heuristic rule compliance). A compound-cause (INC_006) or gradual-degradation (INC_007) classification does not inherently reduce confidence; if a hypothesis has strong evidence support, passes all rules, and maintains a sufficient score gap over runner-ups, it will correctly achieve `HIGH` confidence.

**Critical**: Lock the ground truth before running the pipeline. Evaluate honestly without tuning thresholds.

### Phase 2: Adversarial Perturbation Tests

Add parameterized pytest tests that perturb the INC_001 fixture:

```python
@pytest.mark.parametrize("android_contribution_pct", [68.0, 45.0, 30.0, 15.0])
def test_h1_degrades_gracefully_with_weaker_signal(android_contribution_pct):
    """
    As Android's contribution weakens, H1's score should decrease
    monotonically. It should NOT flip to H2 or H3 winning until
    Android contribution is below a defensible threshold.
    """

@pytest.mark.parametrize("marketing_reliability", [0.25, 0.50, 0.75, 0.95])
def test_h2_score_increases_with_fresher_marketing_data(marketing_reliability):
    """
    As marketing evidence becomes fresher (higher reliability_weight),
    H2's score should increase. If marketing is perfectly fresh,
    H2 should approach H1 (making the scenario genuinely ambiguous).
    """
```

### Phase 3: Cross-Domain Smoke Test

Create a minimal second domain (e.g., SaaS subscription churn) with:
- A new `kpi_contracts.yaml` for SaaS KPIs.
- A single scenario with known ground truth.
- Run the pipeline without changing engine code. Evaluate whether the domain-agnostic claim holds.

### Phase 4: Calibration Reporting

Instead of binary PASS/FAIL, report confidence calibration:
- Track the engine's confidence state predictions vs. actual correctness across all scenarios.
- Report: "Of N investigations where the engine predicted HIGH, X were actually correct." 
- Even with 4 scenarios this establishes the measurement framework. With 10+ scenarios it becomes meaningful.

### Phase 5: Evaluator Extensibility

Refactor `evaluator.py` to support dynamic scenario loading:

```python
class Evaluator:
    def evaluate(self, result: InvestigationResult) -> EvaluationResult:
        # Instead of hardcoded dispatch by scenario_id,
        # load evaluation_checks dynamically from ground_truth.json
        # for ANY scenario_id present in the file.
```

---

## Impact Assessment

- **Risk if unfixed**: A perfect 15/15 score creates false confidence. The system may fail silently on real-world incidents that don't match the four synthetic patterns.
- **Remediation complexity**: Medium-High. Phase 1 (held-out scenarios) requires new data engineering. Phase 2 (perturbation tests) is straightforward with pytest parametrize.
- **Timeline**: Phase 1-2 should be completed before any production deployment claim.
