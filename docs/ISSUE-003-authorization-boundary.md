# ISSUE-003: Authorization Boundary — Architectural Claim vs. Demonstrated Property

**Severity**: 🔴 Critical — Structural / Correctness  
**Status**: Open  
**Affects**: `security/entitlements.py`, `engines/evidence.py` (E4), `engines/hypothesis.py` (E5), `pipeline/investigate.py`

---

## Problem Statement

The architecture document calls the entitlement boundary "impenetrable." In reality, it is a runtime Python filter — `SecurityEngine.filter_evidence()` in [`security/entitlements.py`](file:///e:/accenture/security/entitlements.py) (line 164). The function iterates `candidates` and checks `item.source_id in scope.authorized_sources`. This is correct for final-output filtering but insufficient as a security guarantee because it only operates on the **output boundary**, not on the entire information flow.

### Four Unaddressed Leakage Vectors

#### 1. Pre-Filter LLM Prompt Leakage
The orchestrator in [`pipeline/investigate.py`](file:///e:/accenture/pipeline/investigate.py) runs the entitlement filter before E4. But E4's `assemble_evidence()` calls `_assemble_unstructured()`, which queries ChromaDB. If ChromaDB returns documents that include unauthorized content in its vector search results — even if those results are subsequently filtered — the query itself may have been influenced by unauthorized embeddings in the similarity computation. The filter removes the item from the `Evidence` list, but the similarity ranking of authorized items may have been affected by the presence of unauthorized items in the index.

#### 2. Intermediate Object State
Evidence objects are Python objects in memory. Between the time `assemble_evidence()` constructs them and `filter_evidence()` strips unauthorized ones, they exist in an intermediate list. If any logging, telemetry, or debugging code reads this intermediate list, unauthorized evidence content is exposed.

**Current code in `engines/evidence.py`**: `assemble_evidence()` (around line 180+) builds all evidence items first, then the orchestrator filters. Any `logger.debug()` call that logs evidence summaries before filtering would constitute a leakage.

#### 3. Cache Leakage in ChromaDB
ChromaDB maintains internal caches and indexes. When unauthorized documents are stored in the same collection as authorized ones, the unauthorized content participates in the HNSW graph's nearest-neighbor structure. Even after filtering the output, the unauthorized documents have influenced which authorized documents are returned and in what order.

#### 4. Evaluator Blind Spot
The 15-dimension evaluator checks D15 (`authorization_violation_count`) by inspecting `result.evidence` — the **final** filtered list. An unauthorized fact that influenced the LLM's hypothesis generation (via ChromaDB proximity or intermediate state) but was removed from the final output passes D15 cleanly.

### Current Test Coverage Gap

In [`tests/test_security.py`](file:///e:/accenture/tests/test_security.py):
- Tests verify that `filter_evidence()` returns the correct subset.
- Tests verify idempotency and fail-closed behavior.
- **No tests** verify: prompt content doesn't contain unauthorized data, ChromaDB query doesn't return unauthorized chunks to E5, log output doesn't leak unauthorized summaries.

---

## Remediation Plan

### Phase 1: Pre-Assembly Filtering (Defense in Depth)

Move the authorization check **before** evidence assembly, not after:

```python
# In pipeline/investigate.py — current flow:
#   E4: assemble_evidence() → returns ALL evidence
#   Security: filter_evidence() → strips unauthorized
#
# Proposed flow:
#   Security: resolve scope → pass authorized_sources to E4
#   E4: assemble_evidence(scope) → only queries authorized sources
```

Modify `engines/evidence.py::assemble_evidence()` to accept `authorized_sources: frozenset[str]` and **only query** data sources that are in the authorized set. For ChromaDB, apply a `where` filter: `{"source_id": {"$in": list(authorized_sources)}}`.

This eliminates vectors 1, 2, and 3 because unauthorized data is never loaded into memory or returned by ChromaDB.

### Phase 2: Log Sanitization Audit

Audit all `logger.debug()` and `logger.info()` calls in:
- `engines/evidence.py`
- `pipeline/investigate.py`
- `engines/hypothesis.py`

Ensure no log statement emits evidence summaries, source content, or raw ChromaDB documents before the authorization filter has been applied. Add a linting rule or code comment contract:

```python
# SECURITY: No evidence content may be logged before authorization filtering.
```

### Phase 3: ChromaDB Collection-Level Isolation

For strict multi-tenant deployments, store evidence per-persona in separate ChromaDB collections:
- `evidence_{persona}` — only contains documents from authorized sources.
- Populated at ETL time based on `entitlements.yaml`.

This eliminates the HNSW graph contamination vector entirely.

### Phase 4: Integration Test — Prompt Verification

Add a new test class `tests/test_security_integration.py`:

```python
class TestPromptLeakage:
    def test_unauthorized_evidence_never_in_llm_prompt(self):
        """
        Run the full pipeline with a persona that lacks access to
        'payment_gateway'. Intercept the LLM prompt in E5. Assert
        that the prompt text does not contain any payment_gateway
        evidence summaries or IDs.
        """
        
    def test_chromadb_query_filtered_by_source(self):
        """
        Assert that E4's ChromaDB query includes a where-filter
        for authorized source IDs only.
        """
```

### Phase 5: Documentation Correction

Replace "impenetrable" with accurate language in all documentation:
- _"Server-side entitlement filtering enforced before evidence assembly. Unauthorized source IDs are excluded from database queries. Defense-in-depth: post-assembly filtering is retained as a secondary check."_

---

## Impact Assessment

- **Risk if unfixed**: An unauthorized fact could influence hypothesis generation through ChromaDB proximity ranking or intermediate object state, while passing all 15 evaluation dimensions.
- **Remediation complexity**: Medium. Phase 1 (pre-assembly filtering) is the highest-value change and requires modifying the `assemble_evidence()` signature and the orchestrator call site.
- **Breaking changes**: None. The API contract is unchanged; only internal plumbing moves the filter earlier.
