# Provenance-Aware Precedent Memory (Engine E9)

This document details the architecture, storage lifecycle, confidence weighting, human validation, and retention mechanics of **Engine E9 (Memory Engine)**.

---

## 1. Memory Lifecycle Overview

Engine E9 (`engines/memory.py`) acts as the organizational memory of the system. It persists completed investigation results into ChromaDB collection `investigation_precedents` and enables semantic retrieval of past incidents.

```mermaid
flowchart TD
    subgraph Storage_Lifecycle ["1. Storage Lifecycle"]
        IR[InvestigationResult] --> SUM[LLM Summarization\n(or Template Fallback)]
        SUM --> EMB[bge-m3 Embedding\n(1024 dimensions)]
        EMB --> META[Assemble Metadata\n- scenario_id, evidence_ids\n- original_confidence_state\n- outcome_type: observed\n- human_validated: false]
        META --> UPSERT[Upsert to ChromaDB\n'investigation_precedents']
    end

    subgraph Retrieval_Lifecycle ["2. Retrieval Lifecycle (Search -> Oversample -> Filter)"]
        QUERY[Target Scenario Query] --> QEMB[bge-m3 Query Embedding]
        QEMB --> RAW_SEARCH[Raw Vector Candidate Search\nn_results = 10 x candidate_multiplier\n(No SQLite where filter)]
        RAW_SEARCH --> PY_FILTER[Authoritative Python Security & Provenance Filter\n1. outcome_type == 'observed'\n2. source_ids present & valid\n3. source_ids subset of authorized_sources\n4. region scope match\n5. relevance >= 0.70\n6. created_at + TTL >= now]
        PY_FILTER --> WEIGHT[Confidence Weighting\nHIGH=1.0, MED=0.6, ABS=0.2, LOW=0.1]
        WEIGHT --> BOOST[Human Validation Boost\n+0.1 if human_validated=true]
        BOOST --> RANK[Sort by retrieval_score Descending\nTruncate to MAX_RESULTS = 10]
    end
```

> [!NOTE]
> Precedent retrieval is fully implemented in Engine E9 and executed during investigation, but the retrieved precedents are not currently injected into the active investigation loop (they do not inform E5 or E7 context). They are attached to the `InvestigationResult` for visibility.

---

## 2. Precedent Metadata Schema

Every precedent record upserted into ChromaDB contains the following metadata attributes:

```json
{
  "scenario_id": "INC_001",
  "persona": "analyst",
  "source_ids": "inventory,payment_gateway,support_tickets",
  "winning_hypothesis": "H1",
  "recommendation": "Roll back release v4.3 to restore payment gateway connection pool and mitigate customer payment failures.",
  "confidence_state": "HIGH",
  "original_confidence_state": "HIGH",
  "outcome_type": "observed",
  "created_at": "2026-08-24T12:00:00+00:00",
  "timestamp": "2026-08-24T12:00:00+00:00",
  "evidence_ids": "3f76b0b41747a6a4,132f62a8fde1f82a,477ae5b90f7c4de0",
  "summary": "Payment failure rate of 2.2% with 99 payment support tickets following v4.3 release. Inventory was unaffected.",
  "human_validated": true,
  "validated_at": "2026-08-24T12:05:00+00:00"
}
```

---

## 3. Storage Invariants & State Preservation

### Shared Institutional Precedent Model
The memory engine maintains **one shared institutional precedent record per incident scenario** (`scenario_id`), rather than separate persona-siloed records:
- **Authoritative Ground Truth**: Precedents represent institutional operational history evaluated under the full Analyst cross-domain scope, capturing all contributing evidence sources.
- **Authoritative Record Preservation**: When an investigation is executed by a restricted persona (e.g. CFO or Manager), their run proceeds under scoped entitlements with partial evidence. `MemoryEngine.store_precedent()` checks whether an authoritative Analyst precedent already exists for that scenario and **preserves the authoritative Analyst record**, skipping overwrite by the restricted run. A restricted persona investigation does *not* create an independent degraded precedent.
- **Retrieval-Time Entitlement Bounding**: Role-based access control is enforced at retrieval time. A shared precedent is visible to a querying persona if and only if all contributing evidence sources lie within that persona's authorized entitlement scope:
  $$\text{Precedent is returned} \iff \text{Precedent.source\_ids} \subseteq \text{Persona.authorized\_sources}$$

### Why All Confidence States Are Stored
The memory engine stores precedents across **all** confidence states:
- **`HIGH`**: Established, high-evidence incident patterns.
- **`MEDIUM`**: Plausible, partially corroborated incident patterns.
- **`ABSTAIN`**: Inconclusive incidents with conflicting evidence or narrow score gaps.
- **`LOW`**: Refuted or contradicted hypotheses.

Storing `ABSTAIN` and `LOW` records is critical: historical knowledge of failed hypotheses or inconclusive investigations prevents operational teams from repeating previously refuted theories.

### Immutable Confidence State
A precedent's confidence state is stamped at creation time (`original_confidence_state`). Retrieval operations never modify or overwrite this value.

---

## 4. Retrieval Scoring & Confidence Weighting

ChromaDB uses cosine distance space ($d \in [0, 2]$). E9 converts distance to semantic relevance:
$$\text{relevance} = \max\left(0.0, \min\left(1.0, 1.0 - \frac{\text{distance}}{2}\right)\right)$$

Precedents with $\text{relevance} < 0.70$ are discarded.

### Confidence Retrieval Weights
To prevent low-confidence or refuted precedents from dominating retrieval results over high-confidence precedents with similar semantic text, raw relevance is scaled by the **Retrieval Weight**:

| Confidence State | Retrieval Weight (`conf_weight`) | Rationale |
|---|---|---|
| **`HIGH`** | **`1.0`** | Fully corroborated baseline |
| **`MEDIUM`** | **`0.6`** | Moderately supported baseline |
| **`ABSTAIN`** | **`0.2`** | Inconclusive investigation |
| **`LOW`** | **`0.1`** | Refuted mechanism |

$$\text{base\_retrieval\_score} = \text{round}(\text{relevance} \times \text{conf\_weight}, 4)$$

---

## 5. Human Validation Provenance

Precedents created autonomously default to `human_validated: False` and `validated_at: ""`.

### Validation API
Analysts can validate precedents using `MemoryEngine.mark_validated()`:
```python
memory_engine.mark_validated(
    scenario_id="INC_001",
    validated_at=datetime.now(timezone.utc)
)
```
This updates ChromaDB metadata to `human_validated=True` without mutating the underlying confidence states or evidence IDs.

### Validation Boost
When ranking precedents, human-validated records receive an additive boost:
$$\text{retrieval\_score} = \text{round}(\text{base\_retrieval\_score} + \text{HUMAN\_VALIDATION\_BOOST}, 4)$$
Where `HUMAN_VALIDATION_BOOST = 0.1`. This ensures that when two precedents have similar relevance and confidence, the human-confirmed resolution ranks higher.

---

## 6. Domain Retention & Decay

Precedents are subject to time-to-live (TTL) expiration managed in `config/memory_retention.yaml`:

```yaml
retention:
  default_ttl_days: 90
  by_source:
    - source_id: payment_gateway
      ttl_days: 60
    - source_id: marketing
      ttl_days: 30
    - source_id: deployment_log
      ttl_days: 365
```

### Expiry Filtering Logic
During `retrieve_precedents()`, if `retention_config` is provided:
1. Calculates $\text{expiry\_date} = \text{created\_at} + \text{TTL\_days}$.
2. If $\text{current\_time} > \text{expiry\_date}$, the precedent is filtered out.
3. **Safe Default**: Records with missing or unparseable `created_at` timestamps are treated as expired and excluded.

---

## 7. Contamination Prevention

To prevent memory contamination and feedback loops:

1. **Observed vs. Simulated Segregation**: Simulated outcome projections from Engine E8 are stored with `outcome_type="simulated"`. Post-retrieval Python filtering enforces `outcome_type == "observed"`. Simulated scenarios are never returned as historical truth.
2. **Legacy / Unknown Provenance Exclusion**: Any record lacking an explicit `outcome_type="observed"` tag is filtered out by default.
3. **Collection Boundary Protection**: Engine E4 (evidence assembly) is strictly barred from querying the `investigation_precedents` collection. Precedents can never masquerade as direct empirical evidence for current investigations.

---

## 8. Memory Reset & Rebuild Procedures

To reset memory to a clean, verified state, use `scripts/rebuild_memory.py`:
```bash
python scripts/rebuild_memory.py
```
This drops the `investigation_precedents` collection, recreates it with cosine space metadata, and re-indexes clean provenance-complete precedents for baseline scenarios (`INC_001` through `INC_008`) with their `human_validated` field initialized to `False`.

---

## 9. Scalability Architecture: Search → Oversample → Filter Policy

### 9.1 The ChromaDB Metadata Bottleneck & Solution
Scalability benchmarking revealed that applying ChromaDB metadata filters (`where={"outcome_type": "observed"}`) inside local embedded ChromaDB triggers full SQLite table scans and severe lock contention (9.4s+ latency at just 1,000 precedents).

By removing the `where` filter from the ChromaDB query and delegating all provenance, security, and status filtering to Python, retrieval latency drops to **<25ms at 100,000 precedents**.

### 9.2 The Search → Oversample → Filter Pipeline
1. **Raw Vector Search**: Queries ChromaDB for $N = \text{desired\_results} \times \text{candidate\_multiplier}$ candidates (default: $10 \times 5 = 50$ candidates).
2. **Authoritative Python Security & Provenance Filter**:
   1. `outcome_type == "observed"`
   2. `source_ids` present and non-empty (fail-closed)
   3. `source_ids` $\subseteq$ `authorized_sources` (Security Engine Entitlement Invariant)
   4. Region scope matching
   5. Relevance threshold filtering ($\text{relevance} \ge 0.70$)
   6. Domain TTL expiration
3. **Confidence Weighting & Validation Boost**: Applies `RETRIEVAL_WEIGHTS` and `HUMAN_VALIDATION_BOOST`.
4. **Ranking & Truncation**: Sorts by `retrieval_score` descending and truncates to `MAX_RESULTS = 10`.

### 9.3 Benchmark Evidence & Absence of Theoretical Guarantee
> [!IMPORTANT]
> **Benchmark-Backed Parameter**: The default candidate multiplier **x5** achieved **100% recall** across controlled adversarial noise distributions (simulated noise, unauthorized noise, and mixed noise up to 40 noise items). However, **x5 is an operational parameter, NOT a universal theoretical guarantee**. In extreme synthetic adversarial fixtures with $\ge 50$ dense noise items occupying all 50 candidate slots, recall requires higher oversampling (e.g. x10).

### 9.4 Revalidation Triggers
The candidate oversampling factor must be re-benchmarked when any of the following operational triggers occur:
* **Corpus Growth**: Total precedent collection exceeds 50,000 records.
* **Distribution Shift**: Proportion of simulated or restricted precedents in the database exceeds 70%.
* **Latency Regression**: E9 retrieval p95 latency exceeds 50ms under normal concurrency ($C=5$).
* **Recall Regression**: Retrieval recall falls below 95% on automated validation benchmarks.
* **New Metadata Dimensions**: Additional post-filtering constraints (e.g. new multi-tenant tags) are introduced.

### 9.5 Migration Triggers for pgvector / Chroma Server
Architecture migration to `pgvector` or client/server ChromaDB should be revisited only when measured empirical evidence justifies it:
* E9 p95 latency under high concurrency ($C=25$) exceeds 250ms.
* Precedent corpus exceeds 500,000 records causing memory pressure on in-process HNSW graphs.
* Complex SQL joins between relational transactions and vector distance become mandatory.

