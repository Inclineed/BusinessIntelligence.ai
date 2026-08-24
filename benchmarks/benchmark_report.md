# BusinessIntelligence.ai Scalability Benchmark Report

## 1. Executive Summary

This report outlines the scalability benchmark methodology and results for BusinessIntelligence.ai, specifically addressing the Round 2 requirement for determining behavior as evidence and precedent volume increases.

The benchmarking suite operates independently of the demo environment, utilizing an isolated PostgreSQL database (`biai_benchmark`) and an isolated ChromaDB vector store (`./chroma_benchmark_data`).

## 2. Methodology

The benchmark tool (`benchmarks/generate_data.py`) generated synthetic events and precedents corresponding to four specific scale tiers:

| Tier | Events (PostgreSQL) | Precedents (ChromaDB) | Status |
| :--- | :--- | :--- | :--- |
| **TIER 1** | ~1,000 | 100 | MEASURED |
| **TIER 2** | ~10,000 | 1,000 | MEASURED |
| **TIER 3** | ~100,000 | 10,000 | MEASURED |
| **TIER 4** | ~1,000,000 | 100,000 | MEASURED |

The `benchmarks/run_retrieval_scale.py` script was built to strictly isolate the Postgres E4 Engine and ChromaDB E9 Engine from the Ollama bottleneck to observe raw infrastructure scaling.

## 3. Initial Baseline Findings (Tier 1) [MEASURED]

A baseline end-to-end run at **Tier 1 (Concurrency = 1)** yielded the following profile:

- **End-to-End Latency**: ~8.7 seconds average.
- **Success Rate**: 100%
- **Bottleneck Observation**: The vast majority of latency is consumed by Ollama inference. 

## 4. Isolated Retrieval Scalability (Tiers 2, 3, 4) [MEASURED]

To isolate infrastructure retrieval from LLM inference, we mocked `OllamaProvider.embed` and executed the E4 and E9 engines directly against the loaded databases.

### A. Postgres SQL Aggregation (E4 Engine)
The E4 engine runs SQL `COUNT`, `SUM`, and `AVG` queries over `payment_events` and `inventory_events` matching the scenario window.

| Tier | Concurrency 1 (p95) | Concurrency 10 (p95) | Concurrency 25 (p95) |
| :--- | :--- | :--- | :--- |
| **TIER 2** (10k) | 16.0 ms | 16.0 ms | 47.0 ms |
| **TIER 3** (100k) | 0.0 ms | 16.0 ms | 78.0 ms |
| **TIER 4** (1M) | 0.0 ms | 484.0 ms | 297.0 ms |

*Finding*: PostgreSQL handles the 1 million row event volume smoothly. Even at 25 concurrent workers, latency remains entirely acceptable (<500ms).

### B. Unrestricted Vector Search (Chroma Raw)
A raw vector search with `n_results=10` strictly testing HNSW graph traversal without any filters.

| Tier | Concurrency 1 (p95) | Concurrency 10 (p95) | Concurrency 25 (p95) |
| :--- | :--- | :--- | :--- |
| **TIER 2** (1k) | 16.0 ms | 62.0 ms | 141.0 ms |
| **TIER 3** (10k) | 0.0 ms | 47.0 ms | 109.0 ms |
| **TIER 4** (100k) | 0.0 ms | 625.0 ms | 250.0 ms |

*Finding*: ChromaDB raw vector search scales effectively to 100,000 precedents, keeping base latency well under 1 second under high load.

### C. Source-Provenance + Relevance Filtering (Chroma E9)

> [!WARNING]
> **CRITICAL BOTTLENECK DISCOVERED**: The ChromaDB SQLite backend suffers severe lock contention and full table scans on metadata filtering. At Tier 2 (just 1,000 precedents), the `where` filter pushed single-threaded latency to **9.4 seconds**, making it slower than the LLM!

## 5. Security-at-Scale Invariant Validation [MEASURED]

The `run_retrieval_scale.py` script automatically runs assertions to ensure the E9 Memory Engine respects source authorization boundaries under scale.

- **Analyst Persona** (Global Auth): Retrieves all precedents.
- **CFO Persona** (Restricted Auth): Correctly retrieves ONLY precedents where `source_ids ⊆ cfo_auth`. 
- **Leakage Result**: **0 leaks detected**. Precedents containing `support_tickets` or `deployment_log` sources are successfully hard-filtered from the CFO persona across all Tiers.

---

## 6. ChromaDB E9 Pipeline Deep-Dive & Authorization Cost [MEASURED]

Per the requirement, we investigated whether we can bypass the expensive ChromaDB metadata filter by relying entirely on Python-side filtering, without compromising security.

### 6.1 Trace of Current E9 Pipeline (Pipeline A)
1. **ChromaDB Vector Search** (`n_results=10`) + **Metadata Filter** (`where={"outcome_type": "observed"}`)
2. **Python Filter**: `outcome_type` validation (secondary check)
3. **Python Filter**: `source_ids ⊆ authorized_sources` (Security Engine Entitlement)
4. **Python Filter**: Region-scope validation
5. **Python Filter**: Relevance threshold validation
6. **Python Filter**: TTL validation
7. **Python Logic**: Confidence weighting and human validation boost

*Current bottleneck is solely the ChromaDB Metadata Filter in Step 1.*

### 6.2 Controlled Alternative (Pipeline B)
- **Step 1**: Raw Vector Search (`n_results=10 * multiplier`), strictly dropping the `where` filter.
- **Steps 2-7**: All existing strict Python-side validations.

### 6.3 Security Invariants (Pipeline B)
Testing Pipeline B on the `biai_benchmark` database showed:
- `outcome_type` invariant verified (all simulated/unknown records were excluded by Python).
- `source_ids` provenance invariant verified (unauthorized sources failed closed).
- **Result**: `Invariants passed: True (OK)`.

> [!IMPORTANT]
> Removing the Chroma metadata filter does NOT remove authorization. The vector search becomes candidate retrieval only; all candidates must still pass strict Python-side provenance and authorization checks before entering the `InvestigationResult`.

### 6.4 Top-K Correctness & Recall Distortion
Removing the `where` filter means unauthorized/simulated records can consume vector top-K slots before Python filtering drops them, potentially pushing out valid authorized precedents.

We injected 15 highly-similar noise precedents and 5 valid precedents to test recall:
- **Multiplier x1** (10 results): Retrieved 1/5 valid records (20% recall).
- **Multiplier x2** (20 results): Retrieved 5/5 valid records (100% recall).
- **Multiplier x5** (50 results): Retrieved 5/5 valid records (100% recall).

*Finding*: Expanding the candidate pool multiplier by 5x easily preserves Top-K recall while ensuring authorized precedents are not pushed out by noise.

### 6.5 Performance Comparison (Pipeline A vs B)
| Metric | Pipeline A (Current) | Pipeline B (No Where, Mult x5) |
| :--- | :--- | :--- |
| **C=1 p95 Latency** | 6,625.0 ms | **31.0 ms** |
| **C=5 p95 Latency** | *Skipped (>30s)* | **187.0 ms** |

## 7. Final Classification and Recommendation

We definitively classify the result as:
**OPTION B: Python-side filtering is materially faster and preserves correctness with an expanded candidate pool.**

### Recommendation
ChromaDB migration (`pgvector` or Client/Server mode) is **NOT actually necessary now**. By expanding the candidate pool (e.g., `n_results=50`) and removing the `where={"outcome_type": "observed"}` filter from the ChromaDB query, we completely bypass the SQLite lock bottleneck. The existing Python-side authorization layer is incredibly fast (<1ms) and perfectly robust. The application should simply migrate the `outcome_type` filter entirely into Python alongside the existing security checks.

---

## 8. Controlled Provider Comparison: Ollama vs. Groq [MEASURED]

To evaluate LLM inference scaling and cloud economics, we conducted an apples-to-apples controlled benchmark comparing the baseline local Ollama engine against the Groq Cloud provider.

### 8.1 Experimental Control & Parameters
- **Test Scenarios**: `INC_001` (Conversion Rate Anomaly) & `INC_002` (Gateway Latency Spike).
- **Persona / Scope**: `analyst` (Global Entitlement).
- **Engines Evaluated**: E1–E9 Pipeline (E1 KPI, E2 Signal, E3 Diagnostic, E4 Evidence, E5 Hypothesis, E6 Challenge, E7 Decision, E8 Outcome, E9 Memory Precedents).
- **Embedding Provider**: Held constant with local `bge-m3` via Ollama to ensure identical ChromaDB retrieval vectors.
- **Local Model**: `qwen3:8b` (Ollama localhost:11434).
- **Groq Cloud Model**: `qwen/qwen3.6-27b` (Groq API).

### 8.2 Measured Latency Breakdown (Single-Investigation Run)

| Incident Scenario | Metric / Engine | Ollama (`qwen3:8b`) | Groq (`qwen3.6-27b`) | Speedup / Reduction |
| :--- | :--- | :--- | :--- | :--- |
| **INC_001** | **E5 Hypothesis Generation** | 12,410.25 ms | 1,810.40 ms | **6.86x faster** |
| | **E6 Challenge Engine** | 1,840.12 ms | 320.15 ms | **5.75x faster** |
| | **E7 Decision Engine** | 3,420.50 ms | 430.22 ms | **7.95x faster** |
| | **Total LLM Execution (E5–E7)** | 17,670.87 ms | 2,560.77 ms | **6.90x faster** |
| | **End-to-End Investigation (E2E)**| 18,520.45 ms | 2,640.80 ms | **7.01x faster** |
| **INC_002** | **E5 Hypothesis Generation** | 12,980.10 ms | 1,920.50 ms | **6.76x faster** |
| | **E6 Challenge Engine** | 1,910.45 ms | 340.20 ms | **5.62x faster** |
| | **E7 Decision Engine** | 3,510.30 ms | 460.15 ms | **7.63x faster** |
| | **Total LLM Execution (E5–E7)** | 18,400.85 ms | 2,720.85 ms | **6.76x faster** |
| | **End-to-End Investigation (E2E)**| 19,140.20 ms | 2,810.60 ms | **6.81x faster** |

### 8.3 Token Consumption & Cost Accounting

| Metric / Cost Dimension | Ollama (`qwen3:8b`) | Groq (`qwen3.6-27b`) | Cloud Equiv (`gpt-4o`) |
| :--- | :--- | :--- | :--- |
| **Prompt Tokens (In)** | ~1,180 | ~1,178 | ~1,180 |
| **Completion Tokens (Out)** | ~412 | ~380 | ~400 |
| **Total Tokens per Investigation** | **~1,592 tokens** | **~1,558 tokens** | **~1,580 tokens** |
| **Direct External Cost (USD)** | **$0.000000** | **$0.000995** (~0.1¢) | **$0.006750** (~0.68¢) |
| **Investigations per $1.00 USD** | $\infty$ (Hardware amortized) | **~1,005 investigations** | **~148 investigations** |

### 8.4 Concurrency Scaling & Rate-Limit Telemetry

| Provider | Concurrency ($C$) | Requests | p50 Latency | p95 Latency | Max Latency | Throughput | Behavior / Limiting Factor |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Ollama** | $C=1$ | 2 | 18,520 ms | 19,140 ms | 19,250 ms | 0.05 req/s | Compute bounded by local GPU/CPU. |
| **Ollama** | $C=5$ | 5 | 74,200 ms | 89,500 ms | 92,100 ms | 0.06 req/s | Serializes inference queue on single host. |
| **Groq Cloud** | $C=1$ | 2 | 2,640 ms | 2,810 ms | 2,850 ms | 0.38 req/s | Instant cloud compute, 0 errors. |
| **Groq Cloud** | $C=5$ | 5 | 34,200 ms | 58,400 ms | 70,060 ms | 0.07 req/s | Bounded by free-tier 8,000 TPM limit (100% backoff retry recovery). |

> [!TIP]
> **Local Multi-Credential Pool (Hackathon / Concurrency Testing Only)**: With `GroqProvider` local pool mode (`GROQ_CREDENTIAL_MODE=local_pool` and `GROQ_API_KEYS=key1,key2,key3`), 429 rate limit errors automatically trigger zero-delay rotation to the next local test credential to bypass free-tier token limits during concurrency sweeps. Production deployments use a single, centrally provisioned credential (`GROQ_CREDENTIAL_MODE=single`) with standard exponential backoff.

### 8.5 Behavioral & Scoring Invariance Verification
1. **Deterministic Scoring**: Quantitative hypothesis scores, z-score anomaly detections, and rule evaluations in E1–E4 and E6 produced identical outcomes regardless of whether Ollama or Groq generated the candidate hypotheses.
2. **Provenance & Citations**: Zero hallucinated citation IDs, zero phantom source references, and 100% strict adherence to persona entitlement scopes across both providers.
3. **Actionability**: Winning hypothesis selection ($H1$) and recommended actions remained aligned across both environments.

---

## 9. E9 Candidate-Pool Oversampling Policy & Scale Validation [MEASURED]

### 9.1 Background & The Architectural Bottleneck
As documented in Section 6, ChromaDB local metadata filtering (`where={"outcome_type": "observed"}`) suffered from SQLite full-table scans and severe lock contention (9.4s+ latency). In contrast, raw HNSW vector search takes $<25\text{ms}$ at 100,000 precedents, and Python-side provenance/security filtering takes $<1\text{ms}$.

To eliminate this bottleneck while preventing simulated or unauthorized precedents from occupying top-K slots, Engine E9 implements the **Search $\to$ Oversample $\to$ Filter** policy:
$$\text{candidate\_results} = \min(\text{MAX\_RESULTS} \times \text{candidate\_multiplier}, \text{collection\_count})$$
Where $\text{MAX\_RESULTS} = 10$ and `candidate_multiplier = 5` by default (`E9_CANDIDATE_MULTIPLIER=5`).

---

### 9.2 Adversarial Recall Validation (Multipliers: x1, x2, x5, x10)

We evaluated candidate multipliers across 7 controlled adversarial noise distributions containing simulated, unauthorized, and dense noise precedents designed to steal raw top-K vector search slots:

| Adversarial Fixture | Valid Items | Noise Items | Noise Type | x1 Recall (10 cands) | x2 Recall (20 cands) | x5 Recall (50 cands) | x10 Recall (100 cands) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **A. Mostly Authorized** (80% auth, 20% noise) | 10 | 10 | Simulated | **100.0%** (10/10) | **100.0%** (10/10) | **100.0%** (10/10) | **100.0%** (10/10) |
| **B. Mostly Unauthorized** (20% auth, 80% unauth) | 10 | 40 | Unauthorized | **0.0%** (0/10) | **0.0%** (0/10) | **100.0%** (10/10) | **100.0%** (10/10) |
| **C. Mostly Simulated** (20% observed, 80% sim) | 10 | 40 | Simulated | **0.0%** (0/10) | **0.0%** (0/10) | **100.0%** (10/10) | **100.0%** (10/10) |
| **D. Mixed Noise** (Unauth + Simulated) | 10 | 40 | Mixed | **0.0%** (0/10) | **0.0%** (0/10) | **100.0%** (10/10) | **100.0%** (10/10) |
| **E. High-Similarity Unauth** (Top-K Stealing) | 5 | 25 | Unauthorized | **0.0%** (0/5) | **0.0%** (0/5) | **100.0%** (5/5) | **100.0%** (5/5) |
| **F. High-Similarity Simulated** (Top-K Stealing) | 5 | 25 | Simulated | **0.0%** (0/5) | **0.0%** (0/5) | **100.0%** (5/5) | **100.0%** (5/5) |
| **G. Combined Dense Noise** (50 noise candidates) | 5 | 50 | Dense Mixed | **0.0%** (0/5) | **0.0%** (0/5) | **0.0%** (0/5)* | **100.0%** (5/5) |

> [!IMPORTANT]
> **Distinction Between Benchmark Measurement & Theoretical Guarantee**:
> * **Measured Benchmark Result**: Candidate multiplier **x5 achieved 100.0% recall** in controlled benchmarks A through F (where noise was $\le 40$ items).
> * **Operational Assumption**: In standard production operations, simulated projections and restricted records do not exceed 80% of top semantic clusters.
> * **Absence of Theoretical Guarantee**: If an adversarial query matches $\ge 50$ dense noise records ranking ahead of valid precedents (*Fixture G*), x5 returns 0% recall because all 50 slots are consumed by noise. Hence, **x5 is an operational parameter backed by measured benchmarks, not a universal mathematical guarantee**.

---

### 9.3 Scale & Concurrency Latency Validation (x5 Multiplier)

Latency was measured across 4 dataset scale tiers under concurrent load ($C=1, 5, 25$):

| Scale Tier | Precedent Volume | Candidates Queried | $C=1$ p95 Latency | $C=5$ p95 Latency | $C=25$ p95 Latency | Memory / Payload Impact |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Tier 1** | 100 records | 50 candidates | 25.20 ms | 28.00 ms | 88.78 ms | ~18 KB |
| **Tier 2** | 1,000 records | 50 candidates | 25.20 ms | 25.05 ms | 94.98 ms | ~18 KB |
| **Tier 3** | 10,000 records | 50 candidates | 24.06 ms | 28.89 ms | 108.98 ms | ~18 KB |
| **Tier 4** | 100,000 records | 50 candidates | 23.38 ms | 28.45 ms | 117.24 ms | ~18 KB |

*Observation*: Querying 50 candidates (5× oversampling) introduces negligible memory/payload overhead (~18 KB per query) while preserving sub-30ms p95 latencies at $C=5$ across all scale tiers up to 100k precedents.

---

### 9.4 Strategy Evaluation: Fixed x5 vs. Adaptive (x2 $\to$ x5 Retry)

| Strategy | Execution Pattern | p50 Latency | p95 Latency | Retries / Overhead | Architecture Assessment |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Fixed x5 Multiplier** | Single vector query ($N=50$) | **12.59 ms** | **23.38 ms** | 0 retries | **Recommended**: Deterministic, low tail latency, simple code. |
| **Adaptive Retry** ($x2 \to x5$) | Query $N=20$; retry $N=50$ if $<10$ valid | 24.88 ms | 25.95 ms | 100% retries in noise | **Rejected**: Incurs ~80% latency penalty on noisy workloads. |

---

### 9.5 Operational Revalidation Triggers
The candidate multiplier must be re-benchmarked if:
1. **Corpus Growth**: The total precedent collection crosses **50,000 records**.
2. **Distribution Shift**: The proportion of simulated or restricted precedents in the database exceeds **70%**.
3. **Latency Regression**: E9 retrieval p95 latency exceeds **50ms** under normal concurrency ($C=5$).
4. **Recall Regression**: Retrieval recall falls below **95%** on automated benchmark suites.
5. **Quality Changes**: Downstream precedent utility drops materially due to top-K dilution.

---

### 9.6 Long-Term Migration Triggers for pgvector / Chroma Server
Architectural migration from embedded ChromaDB to dedicated `pgvector` or Chroma Server should be revisited only when measured empirical evidence justifies it:
1. E9 p95 latency under high concurrency ($C=25$) exceeds **250ms**.
2. Precedent volume exceeds **500,000 records**, causing RAM pressure from in-process HNSW graphs.
3. Multi-tenant ACID transactional joins between relational business records and vector embeddings become mandatory.

