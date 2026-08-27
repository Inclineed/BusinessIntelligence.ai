# Master Issues & Architectural Debt Register

This document serves as the central tracking register for all architectural issues, validation constraints, epistemological risks, and operational optimizations identified in **BusinessIntelligence.ai**.

---

## 1. Executive Status Dashboard

| Metric | Count | Details |
| :--- | :---: | :--- |
| **Total Tracked Issues** | **9** | `ISSUE-001` through `ISSUE-009` |
| **Resolved / Implemented** | **4** | `ISSUE-001`, `ISSUE-002`, `ISSUE-003`, `ISSUE-009` |
| **Operationally Mitigated (Source Pending)** | **1** | `ISSUE-008` |
| **Open / Future Review** | **4** | `ISSUE-004`, `ISSUE-005`, `ISSUE-006`, `ISSUE-007` |

---

## 2. Master Issues Register

| ID | Title & Focus Area | Severity | Status | Affected Components | Specification |
| :--- | :--- | :---: | :---: | :--- | :--- |
| **ISSUE-001** | **Semantic Hallucination**<br>LLM misrepresentation of evidence summaries | 🔴 Critical | **Resolved** | `models.py`, `engines/hypothesis.py` (E5), `engines/challenge.py` (E6) | [`ISSUE-001-semantic-hallucination.md`](./ISSUE-001-semantic-hallucination.md) |
| **ISSUE-002** | **Memory Contamination**<br>Self-reinforcing precedent feedback loop in E9 → E4 | 🔴 Critical | **Resolved** | `engines/memory.py` (E9), `engines/evidence.py` (E4), `config/memory_retention.yaml` | [`ISSUE-002-memory-contamination.md`](./ISSUE-002-memory-contamination.md) |
| **ISSUE-003** | **Authorization Boundary**<br>Enforce security entitlements at DB retrieval query level | 🔴 Critical | **Resolved** | `security/entitlements.py`, `engines/evidence.py` (E4), `pipeline/investigate.py` | [`ISSUE-003-authorization-boundary.md`](./ISSUE-003-authorization-boundary.md) |
| **ISSUE-004** | **Evaluator Overfitting**<br>Distinguishing genuine reasoning from scenario memorization | 🔴 Critical | **Open** | `evaluation/evaluator.py`, `data/ground_truth.json`, `etl/generate_scenarios.py` | [`ISSUE-004-evaluator-overfitting.md`](./ISSUE-004-evaluator-overfitting.md) |
| **ISSUE-005** | **Scoring Formula Validity**<br>Empirical justification for non-linear hypothesis challenge weights | 🔴 High | **Open** | `engines/challenge.py` (E6), `config/domain_semantics.yaml` | [`ISSUE-005-scoring-validity.md`](./ISSUE-005-scoring-validity.md) |
| **ISSUE-006** | **Confidence Calibration**<br>Transforming raw scores into empirical calibrated probabilities | 🔴 High | **Open** | `engines/challenge.py` (E6), `engines/decision.py` (E7), `web/src/` | [`ISSUE-006-confidence-calibration.md`](./ISSUE-006-confidence-calibration.md) |
| **ISSUE-007** | **Scenario Coverage & Generalization**<br>Expanding synthetic benchmark matrix beyond initial seeds | 🔴 High | **Open** | `etl/generate_scenarios.py`, `data/ground_truth.json`, `benchmarks/` | [`ISSUE-007-scenario-coverage.md`](./ISSUE-007-scenario-coverage.md) |
| **ISSUE-008** | **Simulated Outcome Contamination**<br>Preventing E8 scripted projections from becoming retrievable factual precedents in E9 | 🔴 High | **Mitigated** | `engines/outcome.py` (E8), `engines/memory.py` (E9), `models.py` | [`ISSUE-008-simulated-outcome-contamination.md`](./ISSUE-008-simulated-outcome-contamination.md) |
| **ISSUE-009** | **ChromaDB HNSW Contiguity on Small Datasets**<br>Eliminated at source via small-dataset exact cosine branch | 🟡 Medium | **Resolved** | `engines/evidence.py` (E4), `etl/load_to_chroma.py`, ChromaDB configuration | [`ISSUE-009-chromadb-hnsw-small-dataset-fallback.md`](./ISSUE-009-chromadb-hnsw-small-dataset-fallback.md) |

---

## 3. Detailed Issue Summaries & Future Actions

### [`ISSUE-001`](./ISSUE-001-semantic-hallucination.md): Semantic Hallucination (E5 / E6)
- **Summary**: Addressed LLM hallucinations where generated hypotheses cited non-existent evidence or altered quoted text.
- **Resolution**: Strict verification checks in `engines/hypothesis.py` and `engines/challenge.py` ensuring verbatim citation matching and rejection of unsupported claims.

### [`ISSUE-002`](./ISSUE-002-memory-contamination.md): Memory Contamination (E9 → E4)
- **Summary**: Addressed self-reinforcing bias where flawed past decisions stored in ChromaDB contaminated future investigations.
- **Resolution**: Separate collection boundaries (`evidence_<scenario>` vs `precedents`), retention scoring, and structural isolation.

### [`ISSUE-003`](./ISSUE-003-authorization-boundary.md): Authorization Boundary (E4 / Security)
- **Summary**: Addressed defense-in-depth where unauthorized sources were filtered after retrieval rather than at the database query level.
- **Resolution**: Query-level metadata `where` filtering in ChromaDB and SQL table authorization gating.

### [`ISSUE-004`](./ISSUE-004-evaluator-overfitting.md): Evaluator Overfitting
- **Summary**: The benchmark evaluation suite may evaluate fixed ground-truth strings rather than assessing underlying causal reasoning structures.
- **Future Action**: Introduce dynamic synthetic perturbation testing and out-of-distribution incident scenarios.

### [`ISSUE-005`](./ISSUE-005-scoring-validity.md): Scoring Formula Validity (E6)
- **Summary**: Hardcoded support scoring formulas ($3.519$) and contradiction penalties lack empirical calibration across diverse incident domains.
- **Future Action**: Calibrate weights against historical incident dataset baselines.

### [`ISSUE-006`](./ISSUE-006-confidence-calibration.md): Confidence Calibration (E6 / E7)
- **Summary**: Confidence outputs ($0.95$, $0.85$) reflect heuristic rule scores rather than true statistical probabilities of decision correctness.
- **Future Action**: Implement Platt scaling / isotonic regression over benchmark validation runs.

### [`ISSUE-007`](./ISSUE-007-scenario-coverage.md): Scenario Coverage
- **Summary**: 6 synthetic scenarios (`INC_001` to `INC_006`) provide a focused core but do not cover the full combinatorics of multi-system failures.
- **Future Action**: Expand generator in `etl/generate_scenarios.py` to generate $50+$ parameterized scenarios.

### [`ISSUE-008`](./ISSUE-008-simulated-outcome-contamination.md): Simulated Outcome Contamination (E8 → E9)
- **Summary**: Scripted recovery curves in E8 should not be stored as factual historical outcomes in E9 memory.
- **Current State**: `outcome_type: SIMULATED` provenance tags enforced; excluded from factual summary retrieval.

### [`ISSUE-009`](./ISSUE-009-chromadb-hnsw-small-dataset-fallback.md): ChromaDB HNSW Index Array Contiguity
- **Summary**: `collection.query()` in ChromaDB can throw `RuntimeError('Cannot return the results in a contigious 2D array')` when querying small collections ($N \le 15$) with `$in` metadata filters.
- **Current State**: Operationally mitigated with fallback to `collection.get()`.
- **Future Action**: Implement small-dataset exact cosine distance branch for collections with $N \le 50$ documents to eliminate the issue at source.
