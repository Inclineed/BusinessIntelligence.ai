# Security, Entitlements & Evidence Isolation

This document outlines the security architecture, authorization enforcement, fail-closed boundaries, and evidence isolation mechanics of **BusinessIntelligence.ai**.

---

## 1. The Pre-Retrieval Authorization Model (ISSUE-003)

Traditional retrieval-augmented generation (RAG) architectures frequently query databases or vector indexes globally and attempt to filter sensitive information afterwards, or rely on LLM system prompts to "ignore" unauthorized context. Both approaches are fundamentally vulnerable to context leakage, prompt injection, and hallucinated disclosures.

BusinessIntelligence.ai enforces a **Pre-Retrieval Authorization Boundary**:
```
User / Persona Request
       ↓
[SecurityEngine.authorize()] ──> Resolves AuthorizationScope
       ↓
       ↓
E3 Diagnostic Decomposition (Safe: Aggregates only)
       ↓
Pre-Query Source & Metadata Filters Applied
       ↓
PostgreSQL Queries          ChromaDB Vector Queries
(Only authorized tables)    (Only authorized metadata filters)
       ↓                            ↓
       └───────────┬────────────────┘
                   ↓
         [Secondary Check in E4]
                   ↓
        Authorized Evidence Set
                   ↓
         LLM Context & Prompts
```

**Security Invariant**: Unauthorized tables, documents, or collections are filtered out before querying. Data that a persona is not entitled to see is explicitly excluded from the evidence assembly layer and never enters an LLM prompt. (See Section 4 for the distinction between filter isolation and physical index isolation).

---

## 2. Authorization Scopes & Persona Definitions

Entitlements are configured in `config/entitlements.yaml` and resolved by `SecurityEngine` (`security/entitlements.py`).

### AuthorizationScope Schema
```python
@dataclass
class AuthorizationScope:
    persona: str
    authorized_sources: frozenset[str] = field(default_factory=frozenset)
    authorized_fields: dict[str, frozenset[str]] = field(default_factory=dict)
    authorized_regions: str = "all"          # "all" | "own_only"
    region_filter: Optional[str] = None      # set when authorized_regions == "own_only"
    is_empty: bool = False                   # True ⟹ fail-closed; no evidence allowed
```

### Persona Hierarchy

| Persona | Authorized Sources | Regional Scope | Operational Role |
|---|---|---|---|
| **`analyst`** | `orders`, `payment_gateway`, `inventory`, `marketing`, `deployment_log`, `support_tickets`, `release_notes` | `all` | Full technical & operational investigation access |
| **`manager`** | `orders`, `inventory` | `all` | Commercial and supply-chain overview |
| **`cfo`** | `orders`, `inventory` | `all` | Financial performance & commercial metrics |

---

## 3. Fail-Closed Security Mechanics

The `SecurityEngine` operates on a strict **fail-closed** policy:

1. **Missing or Corrupt Configuration**: If `config/entitlements.yaml` is missing, unreadable, or invalid YAML, the engine produces an `AuthorizationScope(is_empty=True)`.
2. **Unknown Persona**: Any persona string not explicitly defined in the configuration resolves to an empty scope (`is_empty=True`).
3. **Missing Regional Parameter**: If a persona is configured with `authorized_regions: "own_only"` and the request does not provide a specific region parameter, `SecurityEngine.authorize()` raises a `ValueError` immediately.
4. **Empty Scope Execution**: When `is_empty=True`, Engine E4 retrieves zero evidence, Engine E5 generates zero hypotheses, and the pipeline halts with deterministic abstention and zero recommended actions.
5. **E3 Exception**: Engine E3 (Diagnostic Decomposition) executes *before* the authorization boundary. This is structurally safe because E3 exclusively queries KPI-level aggregate metrics and dimensional segments defined in the semantic contract, not raw unaggregated evidence payloads. Raw data retrieval begins strictly at E4.

---

## 4. Query-Level Isolation Mechanics

### PostgreSQL Structured Isolation
Structured data queries in Engine E4 (`engines/evidence.py`) execute only against tables whose `source_id` exists in `scope.authorized_sources`:
```python
if "payment_gateway" in authorized_sources:
    cur.execute("SELECT ... FROM payment_events WHERE ...")
else:
    # Payment events query is skipped entirely
```

### ChromaDB Unstructured Metadata Filtering
Unstructured document retrieval constructs a pre-query metadata filter passed directly to the ChromaDB query API:
```python
auth_list = sorted(list(authorized_sources))
if len(auth_list) == 1:
    where_filter = {"source": auth_list[0]}
else:
    where_filter = {"source": {"$in": auth_list}}

results = collection.query(
    query_embeddings=[query_embedding],
    n_results=n_results,
    where=where_filter,  # Vector search restricted to authorized metadata
    include=["documents", "metadatas", "distances"],
)
```

### Important Architectural Distinction: Index Isolation vs. Filter Isolation
> [!NOTE]
> In the current implementation, ChromaDB operational documents reside in shared collections partitioned by document-level metadata (`source`). Authorization is enforced via pre-query metadata filtering (`where={"source": {"$in": ...}}`) and secondary post-query assertions. 
>
> The system does **not** maintain physically isolated vector index files per persona. True cryptographic or multi-tenant database-level index isolation would require separate ChromaDB collection instances per tenant or persona.

---

## 5. Defense-in-Depth Protections

1. **Secondary E4 Assertion**: Even after pre-query filtering, Engine E4 iterates over retrieved documents and verifies `source_id in authorized_sources` before constructing `Evidence` objects.
2. **Forbidden Precedent Collection**: Engine E4 is structurally barred from querying the ChromaDB collection `investigation_precedents`. Raw evidence assembly can only access operational collections (`support_tickets`, `release_notes`, `deployment_log`).
3. **API 403 Barrier**: The FastAPI endpoint (`api/main.py`) checks the persona scope upon request receipt and rejects unauthorized requests with HTTP 403 before executing pipeline logic.

---

## 6. Evaluation Security Protections (D13–D16)

The evaluation engine (`evaluation/evaluator.py`) verifies security and integrity across four strict dimensions:

- **Dimension 13 (Provenance Method Integrity)**: All evidence objects must carry valid method tags (`SQL`, `RETRIEVAL`, `ETL`). Unlabeled or LLM-generated evidence is rejected.
- **Dimension 14 (Zero Hallucinated Evidence IDs)**: Every evidence ID cited in a hypothesis must exist in the authoritative E4 evidence set. Phantom IDs are flagged and result in score penalties.
- **Dimension 15 (Zero Authorization Violations)**: Verifies that no evidence object in the final result originated from a source outside the persona's entitlement scope. Target = **0 violations**.
- **Dimension 16 (Citation Fidelity)**: Confirms that quoted summaries in citations match the exact text of the source evidence under string normalization.

---

## 7. Security Test Suite

The security boundary is validated by `tests/test_security.py`, covering:
- Fail-closed scope generation on missing YAML files.
- Unauthorized persona rejection.
- Zero-leakage verification when running restricted personas (`cfo`, `manager`) against scenarios containing technical deployment evidence (`INC_001`).
- Region-filtering enforcement.
- Query filter construction and secondary check validation.
