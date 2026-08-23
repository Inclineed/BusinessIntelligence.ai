# BusinessIntelligence.ai — Implementation Plan (Revised)

> Accenture Hackathon Round 2 | Solo 8-Day Build
> Domain-agnostic, evidence-backed KPI decision engine.
> Framing: "Domain-agnostic KPI intelligence platform. The domain is a configuration. We demonstrate on retail; the same pipeline runs unchanged for any industry by swapping the KPI semantic contract."

## Guiding Principles
- A narrow, working vertical slice beats a broad collection of unfinished engines.
- The LLM is never the source of quantitative truth. Every output carries a method tag.
- Correctness is proven against hidden ground truth, not asserted by fluency.
- Optimize for: working end-to-end system, objective evaluation, requirement coverage, methodological transparency, credible business realism, defensible AI behavior, polished demo.

## Confirmed Decisions
- **LLM backend:** Local Ollama behind a provider/model abstraction (swap to Claude/Azure/Bedrock later without engine changes).
  - Default reasoning model: `qwen3:8b`. Quality fallback: `gemma3:12b`. Embeddings: `bge-m3`.
  - Telemetry: tokens, calls, latency, external cost = $0, plus a separate "equivalent cloud cost" estimate.
- **Data:** Synthetic-first, scenario-driven with causal mechanisms tied to hidden ground truth (never random noise). Optionally integrate lighter UCI Online Retail as a real transaction layer later.
- **Architecture:** Modular monolith. Nine engine modules + one orchestrator. No microservices, queues, or service discovery. Docker for Postgres + ChromaDB + app.

---

## A. Architecture

```
Config:            kpi_contracts.yaml | entitlements.yaml | sources.yaml (+ freshness registry)
Sources:           Orders (hourly, fresh) | Payment gateway (15-min, fresh)
                   Inventory (daily, fresh) | Marketing (daily, INTENTIONALLY STALE 5h)
                   Unstructured: support tickets | release notes | deployment_log
Storage:           Postgres (structured) | ChromaDB + bge-m3 (unstructured)

Pipeline (investigate(scenario, persona)):
  E1 KPI Store        [SQL]                connected KPIs + freshness surface
  E2 Signal           [STATS]              anomaly + corroboration + sparse/data-quality guards
  E3 Diagnostic       [SQL+STATS]          region x channel x device decomposition
  --- Entitlement boundary (role -> authorized data/evidence) ---
  E4 Evidence         [SQL]+[RETRIEVAL]    authorized + freshness-weighted reliability
  E5 Hypothesis       [LLM]                statements + supporting/contradictory evidence IDs (NO numbers)
  E6 Challenge        [RULES]+[LLM_NARRATIVE]  ALL confidence math + abstention (deterministic)
  E7 Decision         [LLM]                consumes deterministic confidence; abstain -> no actions
  E8 Outcome          [SIMULATED]          labeled replay, never causal proof
  E9 Memory           [RETRIEVAL+LLM]      precedent store/retrieve

Cross-cutting:     Telemetry dict threaded through pipeline
Surfaces:          FastAPI (server-side entitlement enforcement) -> Streamlit UI
Evaluation:        evaluator.py reads hidden ground_truth.json -> 15-dimension scorecard
```

### Method Tag System (non-negotiable, on every output)
`[SQL]` `[STATS]` `[ETL]` `[RULES]` `[RETRIEVAL]` `[LLM]` `[LLM_NARRATIVE]` `[RULES+LLM_NARRATIVE]` `[SIMULATED]`

### LLM vs Non-LLM ownership
- **Non-LLM (deterministic):** KPI calc (SQL), anomaly detection (stats), dimensional contribution (SQL/stats), freshness (rules), authorization (rules), evidence validation (rules), confidence scoring (deterministic), abstention (threshold/policy), evaluation (deterministic).
- **LLM:** hypothesis candidate generation, evidence summarization, persona narrative, action explanation.
- **Retrieval:** unstructured evidence retrieval, historical precedent retrieval.

---

## B. Task List (18 tasks)

1. Scaffold + Docker (Postgres+Chroma) + contract/entitlements/sources loaders + LLM abstraction + telemetry
2. INC_001 checkout/payment data across heterogeneous sources + hidden 15-field ground truth
3. Engine 1 KPI Store (connected KPIs + freshness surface)
4. Engine 2 Signal (anomaly + corroboration + freshness/sparse/data-quality guards)
5. Engine 3 Diagnostic (region x channel x device decomposition)
6. Engine 4 Evidence (entitlement-scoped + freshness-weighted reliability)
7. Engine 5 Hypothesis (LLM: statements + supporting/contradictory evidence IDs, NO numbers)
8. Engine 6 Challenge (deterministic: all confidence math + abstention; LLM narrative only)
9. Engine 7 Decision (consumes deterministic confidence; abstain -> no actions)
10. Pipeline orchestrator (first-class persona + backend security boundary + telemetry)
11. Engine 8 Outcome (SIMULATED-labeled) + Engine 9 Memory
12. Evaluation framework (15-dimension scorecard)
13. FastAPI (server-side entitlement enforcement)
14. Streamlit UI (method ownership, freshness, OBSERVED vs SIMULATED, access-denied)
15. Additional scenarios (abstain, sparse-history, data-quality false anomaly)
16. Persona narrative refinement + feedback capture wiring
17. Banking domain switch (Tier 3, optional)
18. Submission (README + LLM-vs-non-LLM table + scorecard + reproducibility + video)

---

## C. Priority Ladder (Tiers)

- **Tier 0 — non-negotiable:** end-to-end vertical slice; ground-truth evaluation; LLM vs non-LLM separation; evidence provenance; backend security boundary.
- **Tier 1 — Round 2 requirements:** 3-5 connected KPIs; 2-3 heterogeneous sources w/ freshness; 2 personas; abstention scenario; sparse-history scenario; data-quality false-anomaly scenario; runtime telemetry; feedback capture.
- **Tier 2 — polish:** strong UI; outcome replay; org memory; persona narratives; evidence visualization.
- **Tier 3 — bonus (abandon first):** banking domain switch; causal inference; GraphRAG; multiple external LLM providers; heavier ML.

---

## D. Critical Path (8 Days)

- **Day 1:** Tasks 1-2. Exit: sources load, freshness computes, ground truth hidden.
- **Day 2:** Tasks 3-4. Exit: INC_001 anomaly fires, normal window silent.
- **Day 3:** Tasks 5-6. Exit: Android slice surfaces; unauthorized data excluded; stale evidence down-weighted.
- **Day 4:** Tasks 7-8. Exit: H1 strong, H3 refuted, confidence numbers reproducible.
- **Day 5:** Tasks 9-10. Exit: investigate(INC_001, persona) runs end-to-end.
- **Day 6:** Tasks 11-12. **SUBMISSION-SAFE MILESTONE.** Exit: 15-check scorecard all-pass.
- **Day 7:** Tasks 13-14 (API + polished UI transparency panels).
- **Day 8:** Tasks 15-16 + 18 (extra scenarios, feedback, README, video). Task 17 only if time remains.

---

## E. Fallback If Time Runs Short

End of Day 6 is the guaranteed submission-safe state: working, method-tagged, security-enforced, freshness-aware INC_001 investigation with deterministic confidence + passing 15-dimension scorecard, runnable via one command.
Drop order under pressure: Task 17 -> advanced Tier-2 visualization -> extra scenarios (15) -> UI polish. Never drop Tasks 1-12.

---

## F. INC_001 Specification — Checkout/Payment Degradation

- **True cause (hidden):** Checkout release v4.3 degraded the payment path — gateway latency +240%, payment failures ~4x — collapsing conversion (-10%, Android -17%) and revenue (-8.2%). Traffic stable, AOV +2%, inventory normal.
- **Connected KPIs:** hourly revenue; hourly conversion (device segment); 15-min payment failure rate; 15-min gateway latency; daily inventory fill rate; daily marketing/competitor (stale source).
- **Sources & cadence:** orders hourly/fresh; payment gateway 15-min/fresh; inventory daily/fresh; marketing daily/STALE 5h; unstructured: support tickets (payment failures ~3x), deployment_log (v4.3), release notes.
- **Hypotheses:** H1 checkout/payment degradation; H2 competitor pricing pressure; H3 inventory shortage.
- **Expected behavior:** H1 leading (temporal v4.3 + Android segment + payment/latency corroboration + mechanism consistency); H2 weakened (segment mismatch + stale/low-reliability marketing evidence); H3 REFUTED by fresh inventory-normal contradiction. Confidence computed deterministically by the Challenge Engine; LLM only proposes and explains.
- **Recommended action:** roll back v4.3 checkout/pricing module, reprocess affected transactions. **Verification metric:** payment success rate + conversion recovery within defined window.
- **Hidden ground-truth fields:** true_cause, affected_kpi, affected_dimensions, recommended_action, expected_evidence, contradictory_evidence, irrelevant_evidence, expected_confidence_state (HIGH), expected_verification_metric, expected_winning_hypothesis (H1), hypothesis_ranking (H1>H2>H3).

### Deterministic Confidence (Challenge Engine)
- Rules per hypothesis: timeline, segment_alignment, kpi_corroboration, mechanism_consistency, contradiction -> PASS/PARTIAL/FAIL.
- support_score = sum(reliability_weight * relevance) over supporting evidence.
- contradiction_penalty = sum over contradictory evidence.
- final_score = weighted combine -> clamp [0,1]; thresholds -> HIGH/MEDIUM/LOW; abstain if top < threshold or gap-to-H2 too small.
- reliability_weight decays for stale-beyond-SLA sources. Numbers reproducible across runs; LLM narrative never alters the score object.

---

## G. Round 2 Requirement -> Implementation Mapping

| Requirement | Where implemented |
|---|---|
| 3-5 connected KPIs, 2-3 sources, different grains/cadences | Tasks 2-3 |
| KPI semantic contract (defs, calc, drivers, thresholds, lineage, access) | kpi_contracts.yaml (T1), lineage (T3), access via entitlements.yaml |
| >=2 personas, different narratives/actions | Task 10 (mechanism) + Task 16 (narratives) |
| Multi-factor KPI movement with known drivers | INC_001 (T2), decomposition (T5) |
| Low-confidence abstention | Deterministic Challenge (T8) + scenario (T15) |
| Sparse-history KPI | Signal guard (T4) + scenario (T15) |
| Role-based security/entitlement | Backend boundary (T1, T6, T10, T13); UI access-denied (T14) |
| Freshness, method, contribution, confidence, lineage per output | T3, T6, T8 |
| Visible LLM vs non-LLM breakdown | Method tags + ownership panel (T14) |
| Runtime telemetry (latency, calls, tokens, cost) | Telemetry dict (T1, T10) |
| Learn from feedback | Feedback capture (T16) |
| LLM not source of quantitative truth | Numbers only in deterministic engines (T1-3, T6) |

---

## H. Do NOT Build Unless All Tier 0/1 Complete

- Banking / any second domain switch
- Causal inference (DoWhy/CausalML) or any causal-proof claim from replay
- GraphRAG / knowledge graphs
- Multiple external LLM providers (keep Ollama; abstraction proves swap-ability)
- Heavier/custom ML or custom embeddings
- Multi-agent orchestration, microservices, queues, distributed tracing
- Production IAM, real-time streaming, multimodal ingestion, autonomous action execution

---

## Repository Structure (target)

```
businessintelligence-ai/
  data/            raw/ (gitignored) | synthetic/*.csv | release_notes/ | ground_truth.json (evaluator only)
  config/          kpi_contracts.yaml | entitlements.yaml | sources.yaml
  etl/             load_public_data.py | load_synthetic.py | schema.sql
  engines/         kpi_store.py | signal.py | diagnostic.py | evidence.py | hypothesis.py |
                   challenge.py | decision.py | outcome.py | memory.py
  security/        entitlements.py (role -> authorized query/evidence)
  pipeline/        investigate.py (orchestrator + telemetry + persona)
  api/             main.py (FastAPI)
  frontend/        app.py (Streamlit)
  evaluation/      evaluator.py | benchmark_results.md
  tests/           test_signal.py | test_diagnostic.py | test_evidence.py |
                   test_challenge.py | test_security.py | test_pipeline.py
  docker-compose.yml | Dockerfile | requirements.txt | README.md
```

## Technology Stack
Python | PostgreSQL | ChromaDB (bge-m3 embeddings via Ollama) | Pandas | SciPy/NumPy |
Ollama (qwen3:8b default, gemma3:12b fallback) behind provider abstraction | FastAPI | Streamlit | PyYAML | Docker Compose | GitHub.
Do not use: LangChain, Spark, dbt.
