# ISSUE-005: Scoring Formula Lacks Empirical Justification

**Severity**: 🔴 High — Validity / Reliability  
**Status**: Open  
**Affects**: `engines/challenge.py` (E6)

---

## Problem Statement

The E6 Challenge Engine calculates `final_score` as:

```python
raw = (support_score + rule_modifier) - contradiction_penalty
final_score = clamp(normalize(raw), 0.0, 1.0)
```

Where `normalize(raw) = raw / _MAX_RAW` with `_MAX_RAW = 2.0`.

This formula is **deterministic** — identical inputs always produce identical outputs. But determinism is not validity. The formula's correctness is unproven.

### The Circularity Problem

The five rules and their weights in [`engines/challenge.py`](file:///e:/accenture/engines/challenge.py) (line 81):

```python
rule_weights = {
    "timeline":               0.25,
    "segment_alignment":      0.20,
    "kpi_corroboration":      0.20,
    "mechanism_consistency":  0.20,
    "contradiction":          0.15,
}
```

And the thresholds (line 69):

```python
high_threshold    = 0.70
medium_threshold  = 0.40
abstain_threshold = 0.30
min_gap           = 0.15
```

**Why these values?** The docstring says: _"Defaults are calibrated to produce the INC_001 expected outcome bands (H1=HIGH, H2<=MEDIUM, H3=LOW)."_

This is circular:
1. The scenarios were designed so that the correct hypothesis has strong evidence.
2. The weights were tuned so that strong evidence scores above 0.70.
3. The evaluator confirms that the correct hypothesis scores above 0.70.
4. Therefore the weights are "correct."

There is no independent evidence that these weights track actual hypothesis correctness. On a novel incident, we have no basis for knowing whether a score of 0.72 means the hypothesis is likely correct or merely that the evidence happened to align with the rule keywords.

### What "Valid" Would Look Like

- **Bayesian grounding**: `support_score` could be interpreted as a log-likelihood ratio. Each evidence item's contribution would be `log(P(evidence | hypothesis_true) / P(evidence | hypothesis_false))`. This requires estimating conditional probabilities — hard but principled.
- **Proper scoring rule**: The confidence mapping should satisfy the property that a well-calibrated system achieves minimum expected loss. Currently the mapping from `final_score` to `{HIGH, MEDIUM, LOW}` is an arbitrary binning.
- **Empirical calibration**: Run the engine on N incidents with independently known ground truth. Plot predicted confidence vs. actual correctness. Adjust thresholds to achieve calibration (e.g., of incidents scored HIGH, 70%+ are correct).

---

## Remediation Plan

### Phase 1: Document the Assumptions Explicitly

Add a `SCORING_RATIONALE.md` to `docs/` that states:
- The weights are heuristic, not empirically calibrated.
- The formula is an ordinal ranking mechanism, not a probabilistic model.
- The thresholds were selected to produce correct outcomes on the development scenarios.
- Users should **not** interpret `final_score = 0.82` as "82% probability of being correct."

### Phase 2: Sensitivity Analysis

Create a parameterized test suite that varies each weight independently and measures the effect on all four scenarios:

```python
@pytest.mark.parametrize("timeline_weight", [0.10, 0.15, 0.20, 0.25, 0.30, 0.35])
def test_timeline_weight_sensitivity(timeline_weight):
    """
    Vary the timeline rule weight while keeping others proportional.
    Assert:
      - H1 still wins INC_001 across the range (robustness)
      - Document the score range for each hypothesis
    """
```

Output: a sensitivity table showing which weight ranges preserve correct outcomes and which cause failures. This identifies whether the current weights are at a stable point or on a knife edge.

### Phase 3: Weight Learning from Retrospective Data

If retrospective incident data becomes available (real incidents with known root causes):
1. Encode each incident as a scenario with evidence, hypotheses, and ground truth.
2. Use logistic regression or grid search to find weights that maximize classification accuracy across all incidents.
3. Replace heuristic weights with empirically optimized ones.
4. Cross-validate to ensure generalization.

### Phase 4: Calibration Curve Infrastructure

Add a calibration measurement to the evaluator:

```python
def calibration_report(results: list[EvaluationResult]) -> CalibrationReport:
    """
    Across all evaluated scenarios, compute:
    - For each confidence band (HIGH/MEDIUM/LOW):
      - Count of predictions in that band
      - Count of correct predictions
      - Empirical accuracy = correct / total
    
    Ideal: HIGH band has >70% accuracy, MEDIUM 40-70%, LOW <40%.
    """
```

This is only useful with 10+ scenarios (see ISSUE-004), but establishing the infrastructure now allows measurement as scenarios accumulate.

---

## Impact Assessment

- **Risk if unfixed**: The system presents ordinal rankings as confidence judgments. Downstream users and integrators will interpret them probabilistically, leading to overconfidence in recommendations.
- **Remediation complexity**: Low for Phase 1-2 (documentation + sensitivity analysis). High for Phase 3 (requires real incident data).
- **Immediate action**: Phase 1 (documenting assumptions) has zero code changes and should be done immediately.
