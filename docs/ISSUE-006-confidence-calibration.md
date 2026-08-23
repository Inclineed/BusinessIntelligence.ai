# ISSUE-006: Confidence Scores Are Not Calibrated Probabilities

**Severity**: 🔴 High — Validity / Reliability  
**Status**: Open  
**Affects**: `engines/challenge.py` (E6), `engines/decision.py` (E7), `frontend/app.py`

---

## Problem Statement

A `final_score` of 0.82 mapped to `ConfidenceState.HIGH` is used by E7 (`engines/decision.py`) to trigger an automated action recommendation. The mapping in [`engines/challenge.py`](file:///e:/accenture/engines/challenge.py) (line 69):

```python
high_threshold    = 0.70   # >= this → HIGH
medium_threshold  = 0.40   # >= this → MEDIUM
abstain_threshold = 0.30   # < this → ABSTAIN
```

The `final_score` is computed as `(support_score + rule_modifier - contradiction_penalty) / 2.0`, clamped to [0, 1]. This is a **weighted combination of rule evaluations and evidence weights** — it is not a probability.

### Why This Matters

1. **E7 acts on it as if it were probability.** The Decision Engine receives `ConfidenceState.HIGH` and produces `recommended_action = "Roll back v4.3"`. There is no calibration step between the score and the action. A score of 0.71 (barely HIGH) triggers the same action recommendation as 0.99 (overwhelmingly HIGH).
2. **The UI presents it as confidence.** The Streamlit frontend displays "Confidence: HIGH" alongside the score. Users — especially CFOs and managers — will interpret this probabilistically: "the system is 82% sure."
3. **The score's relationship to actual correctness rate is unknown.** With only 4 synthetic scenarios, we cannot measure: "of all hypotheses scored 0.70–0.80, what fraction were actually correct?" The answer might be 30% or 95% — we don't know.

### What "Calibrated" Would Mean

A calibrated confidence system satisfies: _"When the system says HIGH (>= 0.70), it is correct at least 70% of the time."_ This requires:
- A test set of N incidents with known ground truth.
- Computing accuracy within each confidence band.
- Adjusting thresholds so that the accuracy within each band matches the implied confidence level.

Currently this is impossible because N = 4 and all 4 were used during development.

---

## Remediation Plan

### Phase 1: Explicit Labeling (Immediate — Zero Code Risk)

Add disclaimers in all user-facing outputs:

**In `engines/decision.py`** — modify the persona narrative generation to include:
```
"Note: Confidence levels (HIGH/MEDIUM/LOW) represent an ordinal ranking 
based on evidence alignment and rule evaluation, not a calibrated probability. 
They should be interpreted as relative signal strength, not as a percentage 
likelihood of correctness."
```

**In `frontend/app.py`** — add a tooltip or footnote wherever confidence is displayed:
```
ℹ️ Confidence is an ordinal ranking, not a calibrated probability.
```

### Phase 2: Graded Action Recommendations

Currently E7 has a binary decision: if `confidence_state != ABSTAIN`, recommend an action. Introduce gradation:

```python
def decide(scored, persona, provider) -> Decision:
    winner = ranked[0]
    
    if winner.confidence_state == ConfidenceState.HIGH:
        # Strong recommendation
        action_prefix = "Recommended action"
        
    elif winner.confidence_state == ConfidenceState.MEDIUM:
        # Tentative recommendation with verification emphasis
        action_prefix = "Tentative action (requires verification before execution)"
        
    elif winner.confidence_state == ConfidenceState.LOW:
        # Investigation recommendation, not action
        action_prefix = "Suggested investigation direction (insufficient evidence for action)"
```

This prevents a barely-MEDIUM score from triggering the same confident action as a strong HIGH.

### Phase 3: Score Bucketing with Honest Labels

Replace the single HIGH/MEDIUM/LOW taxonomy with a more honest labeling:

| Score Range | Current Label | Proposed Label |
|---|---|---|
| >= 0.70 | HIGH | **Strong Evidence Alignment** |
| 0.40 – 0.69 | MEDIUM | **Partial Evidence Alignment** |
| 0.30 – 0.39 | LOW | **Weak Evidence Alignment** |
| < 0.30 | ABSTAIN | **Insufficient Evidence — No Recommendation** |

The word "confidence" should be replaced with "evidence alignment" throughout to avoid the probability interpretation.

### Phase 4: Calibration Infrastructure (Requires ISSUE-004 Phase 1)

Once held-out scenarios exist (ISSUE-004), build a calibration curve:

```python
def compute_calibration(evaluations: list[EvaluationResult]) -> dict:
    """
    For each confidence band, compute:
    - n_predictions: how many hypotheses fell in this band
    - n_correct: how many were actually correct (per ground truth)
    - empirical_accuracy: n_correct / n_predictions
    
    Report whether empirical accuracy tracks the ordinal ranking.
    """
```

---

## Impact Assessment

- **Risk if unfixed**: Users interpret ordinal scores as probabilities, leading to overconfidence in automated recommendations. A barely-above-threshold score triggers the same action as an overwhelming one.
- **Remediation complexity**: Low for Phase 1-2 (labeling + graded actions). Phase 3-4 are terminology and infrastructure changes.
- **Immediate action**: Phase 1 (disclaimers) can be shipped today with no risk.
