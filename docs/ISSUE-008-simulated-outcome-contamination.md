# ISSUE-008: Simulated Outcomes in Memory Create an Epistemological Problem

**Severity**: 🔴 High — Validity / Reliability  
**Status**: Open  
**Affects**: `engines/outcome.py` (E8), `engines/memory.py` (E9), `engines/evidence.py` (E4)

---

## Problem Statement

Engine E8 (`engines/outcome.py`) projects simulated outcomes — e.g., _"Following a rollback, payment success rate and conversion are expected to recover to 85% of baseline within 2 hours."_ Engine E9 (`engines/memory.py`) stores the full investigation result, including this projection, as a precedent in ChromaDB.

The danger: three incidents from now, E4 retrieves the precedent and a future E5 sees: _"After the last Android checkout incident, revenue recovered within 2 hours."_ This was a **simulation**, not an **observation**. But the retrieval system treats all ChromaDB documents identically — there is no mechanism to distinguish a simulated outcome from an observed one.

### Current Code Evidence

In [`engines/outcome.py`](file:///e:/accenture/engines/outcome.py):
- `project_outcome()` (line 103) produces an `OutcomeProjection` with `outcome_type=OutcomeType.SIMULATED` and `method=MethodTag.SIMULATED`.
- The `SIMULATED_DISCLAIMER` (line 24): _"This projection is a simulated estimate based on scripted recovery patterns. It is not causal proof."_
- This tagging is correct for the current investigation's output.

In [`engines/memory.py`](file:///e:/accenture/engines/memory.py):
- `summarize_investigation()` (line 149) generates a text summary using the LLM. The prompt includes `recommended_action` but does **not** include the outcome projection or its `[SIMULATED]` tag.
- `store_precedent()` (line 220) stores metadata with `scenario_id`, `winning_hypothesis`, `recommendation`, `confidence_state`, and `summary`.
- **There is no `outcome_type` or `method` tag in the stored metadata.** The `[SIMULATED]` provenance is lost at storage time.

- `retrieve_precedents()` (line 388) returns precedents with no distinction between "this investigation had an observed outcome" and "this investigation had a simulated projection."

### The Compounding Problem

1. **Investigation 1**: INC_001 runs. E8 projects "85% recovery in 2h" (SIMULATED). E9 stores it.
2. **Investigation 2**: A similar incident occurs. E4/E9 retrieves the precedent summary: _"After a checkout rollback, the system recovered within 2 hours."_ E5 uses this as supporting evidence for a rollback recommendation. E7 writes: _"Based on a similar prior incident, recovery is expected within 2 hours."_
3. **Investigation 3**: Another similar incident. The precedent from Investigation 2 now says _"Based on a similar prior incident, recovery is expected within 2 hours"_ — which itself was based on a simulation from Investigation 1. The chain of simulated projections has been laundered into apparent factual precedent.

Each layer strips more provenance. By Investigation 3, the original `[SIMULATED]` tag is completely absent from the retrieved text.

### Why `method=MethodTag.SIMULATED` Doesn't Help

The method tag is set on the `OutcomeProjection` dataclass in the current investigation's result. It is **not** propagated into the ChromaDB document or metadata. When `retrieve_precedents()` returns a precedent dict, it stamps it with `MethodTag.RETRIEVAL` (line 478), not with the original outcome's method tag.

---

## Remediation Plan

### Phase 1: Exclude Simulated Outcomes from Stored Summaries

The most direct fix: when `summarize_investigation()` generates the text summary for ChromaDB storage, explicitly **exclude** the outcome projection:

```python
def summarize_investigation(self, result: InvestigationResult) -> str:
    # ... existing logic ...
    user_prompt = (
        f"Summarize this investigation:\n"
        f"  scenario_id: {result.scenario_id}\n"
        f"  winning_hypothesis: {winning_id or 'none'}\n"
        f"  recommended_action: {recommended_action or 'none (abstained)'}\n"
        # DO NOT include outcome projection in the summary.
        # Simulated projections must not become retrievable "evidence."
        f"\n"
        f"IMPORTANT: Do NOT mention any projected recovery timelines, "
        f"recovery percentages, or outcome predictions. Only summarize "
        f"the diagnosis and the recommended action.\n"
    )
```

### Phase 2: Outcome Provenance in Metadata

If outcome information must be stored (for audit purposes), add explicit metadata:

```python
metadata = {
    "scenario_id": scenario_id,
    "persona": result.persona.value,
    "winning_hypothesis": winning_id or "",
    "recommendation": (recommended_action or "")[:500],
    "confidence_state": confidence or "",
    "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    "summary": summary[:1000],
    # NEW: outcome provenance
    "has_outcome_projection": result.outcome is not None,
    "outcome_type": result.outcome.outcome_type.value if result.outcome else "",
    "outcome_is_simulated": True if result.outcome else False,
}
```

### Phase 3: Retrieval-Time Filtering

Modify `retrieve_precedents()` to either:
1. **Strip** any outcome-related sentences from retrieved summaries before returning them.
2. **Tag** each returned precedent with `"outcome_was_simulated": True/False` so E5 can be instructed to discount simulated-outcome claims.

```python
def retrieve_precedents(self, scenario_id, query_context=""):
    # ... existing retrieval ...
    for precedent in precedents:
        precedent["outcome_was_simulated"] = (
            meta.get("outcome_is_simulated", False)
        )
    return precedents
```

### Phase 4: E5 Prompt Guard

When precedents are included in the E5 hypothesis generation prompt, add an explicit instruction:

```python
# In engines/hypothesis.py — when precedents are part of the context
precedent_disclaimer = (
    "NOTE: Some precedent summaries may reference projected outcomes from "
    "prior investigations. These projections were SIMULATED estimates, not "
    "observed results. Do not treat projected recovery timelines or "
    "percentages as factual evidence."
)
```

### Phase 5: Observed Outcome Loop (Future)

Implement a mechanism to record **actual observed outcomes** after an incident is resolved:

```python
def record_observed_outcome(
    scenario_id: str,
    actual_recovery_pct: float,
    actual_recovery_hours: float,
) -> None:
    """
    Store the real-world outcome after the recommended action was taken.
    This creates a OBSERVED record that can be contrasted with the
    original SIMULATED projection for calibration.
    """
```

This closes the loop: future retrievals can distinguish "we projected 85% recovery" (simulated) from "actual recovery was 72% in 3 hours" (observed).

---

## Impact Assessment

- **Risk if unfixed**: Simulated projections are laundered into apparent factual precedent through 2-3 layers of retrieval and re-storage. Future investigations make decisions based on fictional recovery timelines presented as historical fact.
- **Remediation complexity**: Low-Medium. Phase 1 (excluding outcomes from summaries) is a prompt change. Phase 2-3 require metadata schema additions.
- **Urgency**: High. Every investigation that stores a simulated outcome contaminates the precedent store for all future investigations.
