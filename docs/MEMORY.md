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

    subgraph Retrieval_Lifecycle ["2. Retrieval Lifecycle"]
        QUERY[Target Scenario Query] --> QEMB[bge-m3 Query Embedding]
        QEMB --> CHROMA_Q[ChromaDB Cosine Search\nwhere outcome_type = 'observed']
        CHROMA_Q --> FILTER1[Relevance Filter\nrelevance >= 0.70]
        FILTER1 --> FILTER2[Domain Retention Filter\ncreated_at + TTL >= now]
        FILTER2 --> WEIGHT[Confidence Weighting\nHIGH=1.0, MED=0.6, ABS=0.2, LOW=0.1]
        WEIGHT --> BOOST[Human Validation Boost\n+0.1 if human_validated=true]
        BOOST --> RANK[Sort by retrieval_score Descending]
    end
```

---

## 2. Precedent Metadata Schema

Every precedent record upserted into ChromaDB contains the following metadata attributes:

```json
{
  "scenario_id": "INC_001",
  "persona": "analyst",
  "winning_hypothesis": "H1",
  "recommendation": "Roll back checkout-service v4.3.1 to v4.2.3 immediately...",
  "confidence_state": "HIGH",
  "original_confidence_state": "HIGH",
  "outcome_type": "observed",
  "created_at": "2024-01-15T12:30:00+00:00",
  "timestamp": "2024-01-15T12:30:00+00:00",
  "evidence_ids": "ev_sql_pay_01,ev_chroma_dep_01",
  "summary": "Investigation INC_001 for analyst. Winning hypothesis: H1. Confidence: HIGH...",
  "human_validated": false,
  "validated_at": ""
}
```

---

## 3. Storage Invariants & State Preservation

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

## 4. Retrieval Scoring & Confidence Weighting (ISSUE-002 Phase 1 & 2)

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

## 5. Human Validation Provenance (ISSUE-002 Phase 3)

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

## 6. Domain Retention & Decay (ISSUE-002 Phase 4)

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

## 7. Contamination Prevention (ISSUE-002 & ISSUE-008)

To prevent memory contamination and feedback loops:

1. **Observed vs. Simulated Segregation**: Simulated outcome projections from Engine E8 are stored with `outcome_type="simulated"`. Normal precedent retrieval queries ChromaDB with `where={"outcome_type": "observed"}`. Simulated scenarios are never returned as historical truth.
2. **Legacy / Unknown Provenance Exclusion**: Any record lacking an explicit `outcome_type="observed"` tag is filtered out by default.
3. **Collection Boundary Protection**: Engine E4 (evidence assembly) is strictly barred from querying the `investigation_precedents` collection. Precedents can never masquerade as direct empirical evidence for current investigations.

---

## 8. Memory Reset & Rebuild Procedures

To reset memory to a clean, verified state, use `scripts/rebuild_memory.py`:
```bash
python scripts/rebuild_memory.py
```
This drops the `investigation_precedents` collection, recreates it with cosine space metadata, and re-indexes verified baseline scenarios (`INC_001` through `INC_008`) with complete provenance metadata.
