# ISSUE-002: Memory Contamination — Self-Reinforcing Error Loop in E9 → E4

**Severity**: 🔴 Critical — Structural / Correctness  
**Status**: Open  
**Affects**: `engines/memory.py` (E9), `engines/evidence.py` (E4), `pipeline/investigate.py`

---

## Problem Statement

Engine E9 (`engines/memory.py`) stores investigation conclusions as precedents in ChromaDB via `store_precedent()`. Engine E4 (`engines/evidence.py`) retrieves unstructured evidence from the same ChromaDB instance. This creates a feedback loop:

1. E5 proposes a **wrong** hypothesis (e.g., "inventory shortage caused the revenue drop").
2. E6 scores it — perhaps incorrectly due to sparse evidence or a semantic hallucination (ISSUE-001).
3. E7 writes a confident narrative around it.
4. E9 stores that narrative as a precedent: _"Investigation INC_005: winning hypothesis was inventory shortage, recommended action was emergency restock."_
5. A future investigation on a similar anomaly hits E4, which queries ChromaDB. The wrong precedent surfaces with high cosine similarity.
6. E5 sees the precedent as "evidence" supporting inventory shortage. It proposes the same wrong hypothesis.
7. E6 scores it higher because it now has supporting evidence (the precedent). The error is amplified.

**The loop is invisible to the evaluator** because `evaluation/evaluator.py` only inspects the current `InvestigationResult` — it has no visibility into what's in ChromaDB or the provenance chain of retrieved documents.

### Current Code Gap

In [`engines/memory.py`](file:///e:/accenture/engines/memory.py):
- `store_precedent()` (line 220) stores a precedent with metadata including `confidence_state`, `winning_hypothesis`, and `recommendation`.
- **There is no differential weighting by confidence state.** An `ABSTAIN` result and a `HIGH` result are both stored with identical embedding weight into the same collection (`investigation_precedents`).
- The metadata key `"confidence_state"` is stored as a string, but `retrieve_precedents()` (line 388) performs a pure cosine-similarity search with a flat `RELEVANCE_THRESHOLD = 0.7`. It does **not** filter or weight by `confidence_state`.

In [`engines/evidence.py`](file:///e:/accenture/engines/evidence.py):
- `assemble_evidence()` retrieves unstructured evidence from ChromaDB. If precedents are stored in the same ChromaDB namespace or a namespace that E4 queries, they can surface as evidence without being identified as prior conclusions vs. primary evidence.

---

## Remediation Plan

### Phase 1: Confidence-Gated Storage

Modify `engines/memory.py::store_precedent()`:

```python
# Do NOT store precedents from low-confidence or abstained investigations.
# Only investigations with HIGH confidence should become retrievable precedents.
STORABLE_CONFIDENCE_STATES = {ConfidenceState.HIGH}

def store_precedent(self, result: InvestigationResult) -> bool:
    # Gate: only store if the top hypothesis achieved HIGH confidence
    if result.scored:
        top = max(result.scored, key=lambda s: s.final_score)
        if top.confidence_state not in STORABLE_CONFIDENCE_STATES:
            logger.info(
                "store_precedent: skipping storage for scenario=%s "
                "(confidence_state=%s is below storage threshold).",
                result.scenario_id, top.confidence_state.value,
            )
            return True  # Not an error — intentionally skipped
    ...
```

### Phase 2: Collection Separation

Store precedents in a **separate** ChromaDB collection (`investigation_precedents`) that is **never queried by E4's evidence assembly**. E4 should only query the primary evidence collections. E9's `retrieve_precedents()` is the only code that queries the precedent collection, and its results flow into `InvestigationResult.precedents` (a list of strings), not into E4's evidence list.

**Current state audit**: The `MemoryEngine` uses collection `"investigation_precedents"`. E4's `_assemble_unstructured()` queries a different collection (scenario-specific evidence). **This separation may already exist** — but it must be hardened with an explicit assertion and documented invariant:

```python
# In engines/evidence.py — add a guard
assert collection_name != MemoryEngine.COLLECTION_NAME, \
    "E4 must never query the precedent collection"
```

### Phase 3: Precedent Provenance Tagging

When E9 retrieves precedents and surfaces them in the `InvestigationResult.precedents` list, tag each precedent with:
- `source_type: "precedent"` (vs. `"primary_evidence"`)
- `original_confidence_state`: the confidence state from the prior investigation
- `original_scenario_id`: so downstream consumers know this is a prior conclusion, not observed data

### Phase 4: Decay / Expiry

Add a TTL or recency weight to stored precedents:
- Precedents older than N days (configurable, default 90) are excluded from retrieval.
- Precedents are weighted by recency in the retrieval score: `retrieval_relevance * recency_factor`.

### Phase 5: Evaluator Extension

Add a new evaluation dimension or audit log entry:
- Track how many precedents influenced the current investigation.
- Flag if a precedent's `original_scenario_id` matches a known incorrect result.

---

## Impact Assessment

- **Risk if unfixed**: Incorrect conclusions accumulate in vector storage and bias future investigations toward the same errors. The system becomes progressively less reliable over time, and the evaluator cannot detect it.
- **Remediation complexity**: Medium. Phase 1 (confidence gate) and Phase 2 (collection separation hardening) are straightforward. Phase 3-4 require metadata schema changes.
- **Urgency**: High. Every investigation run potentially contaminates future runs.
