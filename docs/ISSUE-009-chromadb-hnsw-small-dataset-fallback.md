# ISSUE-009: ChromaDB HNSW Index Contiguity on Filtered & Small Datasets Resolved

**Severity**: 🟡 Medium — Operational Robustness & Vector Search Architecture  
**Status**: ✅ **Resolved & Verified** (Eliminated at Source via Filtered-Candidate Exact Cosine Branch in E4 and Small-Store Exact Cosine in E9)  
**Affects**: [`engines/evidence.py`](file:///e:/accenture/engines/evidence.py) (E4), [`engines/memory.py`](file:///e:/accenture/engines/memory.py) (E9), [`etl/load_unstructured.py`](file:///e:/accenture/etl/load_unstructured.py), [`etl/seed_scenario_evidence.py`](file:///e:/accenture/etl/seed_scenario_evidence.py)

---

## 1. Problem Statement

During unstructured evidence assembly in Stage E4 ([`engines/evidence.py`](file:///e:/accenture/engines/evidence.py)) and precedent memory retrieval in Stage E9 ([`engines/memory.py`](file:///e:/accenture/engines/memory.py)), querying ChromaDB collections with small document counts or small filtered subsets under metadata authorization filters triggered vector search runtime errors:

```text
_assemble_unstructured: vector query failed: {"error":"RuntimeError('Cannot return the results in a contigious 2D array. Probably ef or M is too small')"}
```

### Technical Root Cause

1. **HNSW Graph Topology on Tiny Filtered Subsets**:
   - The underlying `hnswlib` C++ library constructs a Hierarchical Navigable Small World graph.
   - When a collection contains a small corpus of documents ($N \le 50$) or when an `$in` metadata filter restricts the candidate set to $< 100$ items (even in a collection with $> 50$ total documents), the filtered exploration set is smaller than the HNSW graph search width.
   - `hnswlib` fails to return the expected contiguous 2D result buffer, raising `RuntimeError('Cannot return the results in a contigious 2D array. Probably ef or M is too small')`.
2. **Silent Degradation via Synthetic Distances**:
   - Previous fallbacks caught the exception and assigned a hardcoded dummy distance of `0.1` (falsely inflating relevance to `0.9`) on unranked SQLite records.
3. **Unpatched E9 Precedent Store**:
   - E9 precedent memory was previously unpatched, unconditionally calling `collection.query()` on small precedent databases.

---

## 2. Permanent Architectural Resolution

### 1. Filtered-Count Exact Cosine in E4 ([`engines/evidence.py`](file:///e:/accenture/engines/evidence.py#L355-L450))
- Applies the metadata authorization filter first via `collection.get(where=where_filter, include=["documents", "metadatas", "embeddings"])`.
- Evaluates the **filtered candidate count**:
  - If $\text{filtered\_count} = 0$: Returns a clean empty result `([], 0)` without exceptions.
  - If $\text{filtered\_count} \le 100$: Computes exact cosine similarity directly in NumPy (`np.dot(doc_vecs, q_vec)`), normalizes distances into $[0.0, 2.0]$, and ranks the top $k$ items with exact mathematical fidelity.
  - If $\text{filtered\_count} > 100$: Delegates to ChromaDB's HNSW vector index (`collection.query(where=where_filter)`).
- Safe Fallback: If embeddings are completely missing, distances are assigned a neutral baseline `0.5` (relevance `0.5`) with clear warning logs, completely eliminating fabricated `0.1` distances.

### 2. Exact-Cosine Precedent Ranking in E9 ([`engines/memory.py`](file:///e:/accenture/engines/memory.py#L580-L650))
- For precedent collections with $N \le 50$ documents:
  - Retrieves documents, metadatas, and embeddings via `collection.get()`.
  - Computes exact cosine distance in NumPy against the query vector.
  - Preserves candidate oversampling and provenance authorization filtering.
- For collections with $N > 50$ documents: Retains HNSW vector queries with configured oversampling multipliers.

### 3. Explicit HNSW Collection Parameters ([`etl/load_unstructured.py`](file:///e:/accenture/etl/load_unstructured.py), [`etl/seed_scenario_evidence.py`](file:///e:/accenture/etl/seed_scenario_evidence.py), [`engines/memory.py`](file:///e:/accenture/engines/memory.py))
- All ChromaDB collections explicitly configure:
  ```python
  metadata={
      "hnsw:space": "cosine",
      "hnsw:search_ef": 64,
      "hnsw:M": 32,
  }
  ```

---

## 3. Verification & Test Coverage

Automated coverage in [`tests/test_chroma_retrieval_reliability.py`](file:///e:/accenture/tests/test_chroma_retrieval_reliability.py):
* **Case A**: E4 collection with $> 50$ total docs (80 docs) and $\le 5$ filtered docs (4 docs) $\implies$ exact cosine ranking, 0 HNSW calls (**Passed**).
* **Case B**: E4 collection with $> 100$ filtered docs (120 docs) $\implies$ HNSW query permitted and invoked (**Passed**).
* **Case C**: E4 collection $\le 50$ docs $\implies$ exact cosine ranking (**Passed**).
* **Case D**: E4 metadata filter with 0 matches $\implies$ clean empty return without exception (**Passed**).
* **Case E**: E4 HNSW exception fallback $\implies$ safe degraded distance (`0.5`), zero fabricated `0.1` distances (**Passed**).
* **Case F**: E9 precedent store with $\le 50$ docs (5 docs) $\implies$ exact cosine ranking, 0 HNSW calls (**Passed**).
* **Case G**: E9 precedent store with $> 50$ docs (100 docs) $\implies$ HNSW vector query with oversampling preserved (**Passed**).
* **Case H**: Missing embeddings in database $\implies$ graceful neutral distance handling without crashing (**Passed**).

Live Verification:
* Tested against real ChromaDB instance with local Ollama `bge-m3` embeddings across 75-document collections and 12-precedent memory stores: **100% Passed**.
* Full automated suite: `150 passed in 13.75s`.
