# Implementation Plan: BusinessIntelligence.ai

## Overview

This plan converts the design into a sequence of incremental Python coding steps for a modular monolith (nine engines + orchestrator, Postgres + ChromaDB). It follows the implementation plan's 18-task structure and Tier ordering: foundation first, then a working INC_001 vertical slice as early as possible, then generalization to additional scenarios, surfaces, and the optional banking domain switch.

Every task builds on prior tasks and ends with wiring so no code is orphaned. Numbers are only ever produced by deterministic engines ([SQL]/[STATS]/[RULES]); the LLM only proposes hypotheses, summarizes evidence, and writes narrative. All code is Python (the design specifies Python throughout, so no language selection is required).

Task-to-plan mapping: Task 1→Plan T1, Task 2→T2, Task 3→T3, Task 4→T4, Task 5→T5, Task 7→T6, Task 8→T7, Task 9→T8, Task 10→T9, Task 11→T10, Task 12→T11, Task 13→T12, Task 15→T13, Task 16→T14, Task 17→T15, Task 18→T16, Task 19→T17, Task 20→T18. Tasks 6, 14, and 21 are validation checkpoints.

## Tasks

- [x] 1. Foundation: scaffold, Docker, config loaders, LLM abstraction, telemetry
  - [x] 1.1 Create repository scaffold and core data models
    - Create the target repo structure (`engines/`, `security/`, `pipeline/`, `api/`, `frontend/`, `evaluation/`, `etl/`, `config/`, `data/`, `tests/`) with `requirements.txt`
    - Implement all dataclasses and enums in a shared `models.py`: `MethodTag`, `Persona`, `FreshnessStatus`, `ConfidenceState`, `RuleVerdict`, `OutcomeType`, `SourceRegistryEntry`, `KPIValue`, `AnomalySignal`, `DimensionContribution`, `Evidence`, `Hypothesis`, `RuleResult`, `ScoredHypothesis`, `Decision`, `OutcomeProjection`, `Telemetry`, `InvestigationResult`
    - Add clamp helpers enforcing `[0,1]` on `reliability_weight`, `relevance`, `data_quality`, `final_score`
    - _Requirements: 7.1, 13.1_
  - [x] 1.2 Add Docker Compose and database schema
    - Author `docker-compose.yml` (Postgres + ChromaDB), `Dockerfile`, and `etl/schema.sql` for structured KPI/dimension tables
    - _Requirements: 19.1_
  - [x] 1.3 Implement config loaders and SourceRegistry with freshness
    - Load and schema-validate `kpi_contracts.yaml`, `entitlements.yaml`, `sources.yaml`; halt with a specific error on missing/invalid artifacts (no default-domain fallback)
    - Build `SourceRegistry` computing `staleness_minutes`, `is_within_sla`, and `freshness_status` (fresh/stale/unknown) from recorded `last_refresh` and per-source SLA (orders 120m, gateway 30m, inventory/marketing 48h)
    - Derive active domain solely from configuration
    - _Requirements: 1.3, 1.5, 1.6, 2.1, 2.2, 2.3, 19.1, 19.2, 19.3_
  - [x] 1.4 Implement the LLM provider abstraction
    - Define `LLMProvider` interface (`complete`, `embed`) and `LLMResponse`; implement `OllamaProvider` with default `qwen3:8b`, fallback `gemma3:12b`, embeddings `bge-m3`
    - Implement default→fallback model switching and a request timeout (default 30s) surfaced as an "unavailable" signal
    - Record tokens/latency into `Telemetry`; keep the backend swappable with zero engine changes
    - _Requirements: 10.5, 10.6, 19.5_
  - [x] 1.5 Implement the telemetry service
    - Record per-engine latency (1ms resolution), LLM call count, input/output token counts, external cost = $0.00, and equivalent cloud cost from a per-1K-token rate table
    - Mark individual metrics unavailable on failure without aborting; mark equivalent cost unavailable when the rate table lacks a model
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6_
  - [ ]* 1.6 Write unit tests for foundation
    - Test config schema validation/fail-closed, freshness/staleness computation vs SLA, provider default→fallback and timeout, telemetry recording and equivalent-cost fallback
    - _Requirements: 1.5, 1.6, 16.4, 16.5, 19.2_

- [x] 2. INC_001 data across heterogeneous sources + hidden ground truth
  - [x] 2.1 Generate INC_001 structured data and load it
    - Implement `etl/load_synthetic.py` producing scenario-driven (not random) data for orders (hourly), payment gateway (15-min), inventory (daily), marketing (daily, intentionally stale 5h): revenue -8.2%, conversion -10% (Android -17%), payment failures ~4x, gateway latency +240%, inventory normal, AOV +2%, traffic stable
    - Load into Postgres per `schema.sql`
    - _Requirements: 1.2, 12.1_
  - [x] 2.2 Load unstructured evidence into ChromaDB
    - Implement `etl/load_unstructured.py` embedding support tickets (payment failures ~3x), `deployment_log` (v4.3), and release notes with `bge-m3` into ChromaDB
    - _Requirements: 12.1_
  - [x] 2.3 Author the hidden ground_truth.json
    - Create `data/ground_truth.json` with the 15 fields (true_cause, affected_kpi, affected_dimensions, recommended_action, expected_evidence, contradictory_evidence, irrelevant_evidence, expected_confidence_state=HIGH, expected_verification_metric, expected_winning_hypothesis=H1, hypothesis_ranking H1>H2>H3, etc.)
    - This file is authored for the evaluator only and is never imported/read by pipeline code
    - _Requirements: 18.3, 18.4_

- [x] 3. Engine E1 — KPI Store [SQL]
  - [x] 3.1 Implement load_kpis
    - Load 3-5 connected KPIs from >=2 sources with differing grains per the contract; apply the contract calculation; stamp each `KPIValue` with `source_id`, freshness (from registry), and `MethodTag.SQL`
    - Handle unavailable source (freshness=unavailable, retain last value, error indication) and missing driver (no value + error)
    - Enforce persona access restrictions from the contract (deny without disclosing value/source)
    - _Requirements: 1.1, 1.2, 1.4, 1.7, 2.4, 2.5, 2.6_
  - [ ]* 3.2 Write unit tests for KPI Store
    - Test KPI count bounds, differing grains, freshness stamping, unavailable-source and missing-driver handling
    - _Requirements: 1.1, 1.4, 1.7, 2.5_

- [x] 4. Engine E2 — Signal [STATS]
  - [x] 4.1 Implement anomaly detection and corroboration
    - Implement `detect_signals` computing bounded `z_score` and `delta_pct`; mark anomaly when both guards are false AND |z|>=3.00 AND |delta%|>=10.00; assert corroboration only for KPI pairs whose periods overlap >=80%
    - Suppress and mark not-evaluable when baseline data is absent
    - _Requirements: 3.1, 3.4, 3.5, 3.6_
  - [x] 4.2 Add sparse-history and data-quality guards
    - Set `sparse_history=True` and suppress anomaly when baseline samples < 30; set `data_quality_suspect=True` and suppress when data-quality score < 0.80 for the window
    - _Requirements: 3.2, 3.3_
  - [ ]* 4.3 Write unit tests for Signal
    - Test anomaly firing on INC_001, both guards suppressing false anomalies, corroboration overlap rule, not-evaluable path
    - _Requirements: 3.2, 3.3, 3.5, 3.6_

- [x] 5. Engine E3 — Diagnostic [SQL]+[STATS]
  - [x] 5.1 Implement dimensional decomposition
    - Implement `decompose` producing contribution percentages in `[0,100]` for region, channel, and device; identify dominant segment by max contribution with lexicographic tie-break; stamp `MethodTag.SQL`; error out per-dimension on missing/insufficient data without mutating state
    - Identify Android as the dominant negative contributor for INC_001
    - _Requirements: 4.1, 4.3, 4.4, 4.5, 4.6, 12.2_
  - [ ]* 5.2 Write property test for contribution sums
    - **Property: contribution percentages sum to the total movement within +/-0.1 pp**
    - **Validates: Requirements 4.2**
  - [ ]* 5.3 Write unit tests for Diagnostic
    - Test Android dominance on INC_001, tie-break, missing-dimension error
    - _Requirements: 4.3, 4.4, 4.6_

- [~] 6. Checkpoint - deterministic detection layer
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Security entitlement boundary + Engine E4 Evidence
  - [x] 7.1 Implement the Security_Engine entitlement boundary
    - Implement `authorize(persona, entitlements)` → `AuthorizationScope` (authorized source ids + per-source authorized fields) and `filter_evidence(scope, candidate)` removing unauthorized sources/fields; make it idempotent and never scope-widening
    - Fail closed to empty scope when `entitlements.yaml` is missing/unreadable/invalid; build access-denied results listing excluded source ids without leaking content
    - _Requirements: 5.1, 5.3, 5.5, 5.6, 5.8, 5.9, 8.7_
  - [ ]* 7.2 Write property test for authorization soundness
    - **Property 4: filter_evidence never widens scope and is idempotent (re-filtering an already-filtered set returns an identical set)**
    - **Validates: Requirements 5.4, 5.5**
  - [ ]* 7.3 Write security unit tests
    - Test unauthorized evidence never reaches the LLM prompt, fail-closed on missing/invalid `entitlements.yaml`, field-level removal, 10k-item filter under 2s
    - _Requirements: 5.4, 5.6, 5.8, 5.9_
  - [x] 7.4 Implement Evidence assembly with freshness-weighted reliability
    - Implement `assemble_evidence` (runs after the boundary) and `reliability_weight(entry)`: in-SLA weight = data_quality; stale-beyond-SLA weight strictly less and monotonically non-increasing with staleness; weight = 0 with indication when freshness/SLA is undeterminable
    - Tag structured evidence `[SQL]`, unstructured `[RETRIEVAL]`; attach source_id, reliability_weight, relevance, raw_ref; drop evidence whose source_id does not resolve in the registry
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.6, 7.3, 7.4, 7.5_
  - [ ]* 7.5 Write property test for freshness monotonicity
    - **Property 5: for sources equal except staleness, greater staleness yields reliability_weight <= the fresher source's weight**
    - **Validates: Requirements 6.4, 6.5**
  - [ ]* 7.6 Write unit tests for Evidence
    - Test in-SLA vs stale decay, zero-weight on missing metadata, unresolved-source drop, structured/unstructured tagging
    - _Requirements: 6.2, 6.3, 6.6, 7.5_

- [x] 8. Engine E5 — Hypothesis [LLM] (no numbers)
  - [x] 8.1 Implement hypothesis generation
    - Implement `generate_hypotheses` consuming only entitlement-filtered evidence; produce hypotheses with statement, supporting/contradictory evidence id lists, and reasoning; stamp `MethodTag.LLM`
    - Generate INC_001 H1 (checkout/payment), H2 (competitor pricing), H3 (inventory shortage)
    - _Requirements: 8.1, 8.2, 8.6, 8.7_
  - [x] 8.2 Add hypothesis validation guards
    - Reject and exclude any hypothesis referencing an evidence id absent from the filtered input set (record unknown id); reject any statement containing a quantitative-truth value (record offending statement)
    - _Requirements: 8.3, 8.4, 8.5_
  - [ ]* 8.3 Write unit tests for Hypothesis
    - Test field-shape constraints, hallucinated-id rejection, numeric-truth rejection, LLM tag
    - _Requirements: 8.1, 8.3, 8.5_

- [x] 9. Engine E6 — Challenge [RULES] (deterministic confidence)
  - [x] 9.1 Implement rule evaluation and scoring
    - Implement `evaluate_rule` for timeline, segment_alignment, kpi_corroboration, mechanism_consistency, contradiction (PASS/PARTIAL/FAIL) and `score_hypothesis`: support_score and contradiction_penalty each = sum(reliability_weight * relevance) over the respective evidence, plus rule modifier; combine, normalize, clamp `[0,1]`; map to HIGH/MEDIUM/LOW; KeyError on hallucinated ids feeds deterministic lower score
    - Ensure the function depends only on rule verdicts, weights, relevance, and thresholds (no wall-clock/random/external state)
    - _Requirements: 9.1, 9.2, 9.3, 9.8, 6.7_
  - [x] 9.2 Implement abstention resolution
    - Implement `resolve_abstention`: set top hypothesis to ABSTAIN when top score < abstain threshold OR gap to runner-up < min_gap; ABSTAIN with score fields unmodified when no hypothesis is available
    - Enforce INC_001 expected bands: H1 HIGH and winner, H3 LOW (fresh inventory-normal contradiction), H2 <= MEDIUM
    - _Requirements: 9.6, 9.7, 12.3, 12.4, 12.5_
  - [x] 9.3 Add optional LLM narrative that never mutates the score
    - Produce optional `[LLM_NARRATIVE]`; guarantee final_score and confidence_state are identical with or without narrative
    - _Requirements: 9.5_
  - [ ]* 9.4 Write property tests for Challenge
    - **Property: final_score in [0,1] for arbitrary evidence weights/relevance**
    - **Property 2: confidence reproducibility — identical inputs (including shuffled evidence order) yield an equal multiset of (hypothesis_id, final_score, confidence_state)**
    - **Validates: Requirements 9.3, 9.4**
  - [ ]* 9.5 Write unit tests for Challenge
    - Test threshold banding, abstention gap logic, hallucinated-id handling, narrative-non-mutation, INC_001 H1/H2/H3 bands
    - _Requirements: 9.1, 9.5, 9.6, 12.3, 12.5_

- [x] 10. Engine E7 — Decision [LLM]
  - [x] 10.1 Implement decision generation
    - Implement `decide` consuming deterministic confidence (never recomputing it); on non-abstain produce recommended_action + verification_metric with persona narrative; for INC_001 recommend rolling back v4.3 with verification metric = payment success rate + conversion recovery
    - _Requirements: 12.6_
  - [x] 10.2 Implement abstention safety and provider-unavailability handling
    - When winning state is ABSTAIN (or score < 0.60 default), set status abstained, empty recommended action, 1-10 verification steps, and a machine-readable reason; on provider-unavailable after fallback, abstain with that reason while retaining deterministic numeric outputs unchanged
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_
  - [ ]* 10.3 Write property test for abstention safety
    - **Property 6: decision.abstained ⇒ recommended_action is None**
    - **Validates: Requirements 10.1**
  - [ ]* 10.4 Write unit tests for Decision
    - Test non-abstain action/verification for INC_001, abstain reasons, provider-unavailability path
    - _Requirements: 10.4, 10.5, 12.6_

- [x] 11. Pipeline orchestrator — investigate(scenario, persona)
  - [x] 11.1 Implement the orchestrator for E1→E7
    - Implement `investigate(scenario_id, persona, deps)` running E1→E7 in order with the entitlement boundary applied before E4; thread telemetry per engine; treat persona as first-class; reject unsupported personas with an error; return `method_ownership` map (each engine once); enforce that only authorized evidence reaches the LLM
    - _Requirements: 5.2, 11.1, 11.6, 13.5, 16.7_
  - [x] 11.2 Enforce LLM/non-LLM method separation
    - Reject and exclude any numeric field emitted by an LLM-tagged engine (record offending engine); restrict LLM output to hypothesis statements, evidence summaries, persona narrative, action explanation; reject outputs with an undefined Method_Tag
    - _Requirements: 7.2, 13.1, 13.2, 13.3, 13.4_
  - [ ]* 11.3 Write property test for persona invariance
    - **Property 7: quantitative fields of investigate(s, p1) equal those of investigate(s, p2); narratives differ**
    - **Validates: Requirements 11.2, 11.4**
  - [ ]* 11.4 Write end-to-end pipeline test for INC_001
    - **Validates Properties 1, 3, 9**: winner H1 HIGH, ranking H1>H2>H3, H3 refuted, zero hallucinated evidence, all numeric fields from SQL/STATS/RULES
    - _Requirements: 12.2, 12.3, 12.6, 13.1_

- [x] 12. Engine E8 Outcome [SIMULATED] + Engine E9 Memory
  - [x] 12.1 Implement Outcome projection
    - Implement `project_outcome` setting outcome_type=SIMULATED, `MethodTag.SIMULATED`, and a not-causal-proof disclaimer; withhold any projection lacking the SIMULATED tag
    - _Requirements: 14.1, 14.2, 14.3, 14.5_
  - [x] 12.2 Implement Memory store/retrieve
    - Implement `store_precedent` (within 5s, retry queue up to 3 attempts on failure with error indication) and `retrieve_precedents` (up to 10 with relevance >= 0.7, sorted desc; empty set + indication when none); stamp retrieved precedents `[RETRIEVAL]`
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_
  - [x] 12.3 Wire E8 and E9 into the orchestrator
    - Extend `investigate` to call E8 and E9 after E7, retrieve precedents at start, store the precedent on completion, and include outcome + precedents + telemetry in `InvestigationResult`
    - _Requirements: 15.1, 15.3, 16.7_
  - [ ]* 12.4 Write property test for simulation honesty
    - **Property 8: every outcome has outcome_type == SIMULATED and is never causal proof**
    - **Validates: Requirements 14.1, 14.3**
  - [ ]* 12.5 Write unit tests for Memory and Outcome
    - Test disclaimer/label, withhold-untagged projection, precedent threshold/ordering/empty, store retry
    - _Requirements: 14.5, 15.2, 15.4_

- [x] 13. Evaluation framework — 15-dimension scorecard
  - [x] 13.1 Implement the evaluator
    - Implement `evaluation/evaluator.py` reading the hidden `ground_truth.json` only within the evaluator process; score 15 dimensions (winning-hypothesis correctness, ranking, contradiction handling, expected confidence state, recommended action, verification metric, hallucinated-evidence count, authorization-violation count, ...) each in `[0,1]`
    - _Requirements: 18.1, 18.2_
  - [x] 13.2 Implement pass/fail and ground-truth isolation guard
    - Mark run passed only if hallucinated-evidence count == 0 AND authorization-violation count == 0; add a guard asserting pipeline modules never import/read the ground-truth file (failed access recorded as an authorization violation)
    - _Requirements: 18.3, 18.4, 18.5_
  - [ ]* 13.3 Write evaluator tests and run the INC_001 scorecard
    - Assert all 15 dimensions pass for INC_001 and that pipeline imports do not reference the ground-truth file
    - _Requirements: 18.1, 18.3, 18.5_

- [x] 14. Checkpoint - SUBMISSION-SAFE MILESTONE (end of vertical slice)
  - Ensure all tests pass and the 15-dimension scorecard is all-pass for INC_001, ask the user if questions arise. At this point the method-tagged, security-enforced, freshness-aware INC_001 investigation with deterministic reproducible confidence runs end-to-end — this is the guaranteed submission-safe state.

- [x] 15. FastAPI surface with server-side entitlement enforcement
  - [x] 15.1 Implement the investigate API endpoint
    - Implement `api/main.py` exposing `investigate` with server-side entitlement enforcement; return access-denied results listing excluded source ids (no excluded content); return entitlements-unresolvable access-denied when scope resolution fails
    - _Requirements: 5.6, 5.7, 5.8_
  - [ ]* 15.2 Write API tests
    - Test end-to-end investigate response, access-denied payload shape, fail-closed behavior
    - _Requirements: 5.6, 5.8_

- [x] 16. Streamlit UI transparency panels
  - [x] 16.1 Build the method-ownership panel
    - Render each engine, its Method_Tag(s), and a grouping separating LLM-tagged engines from SQL/STATS/RULES engines, from the method-ownership map
    - _Requirements: 13.6_
  - [x] 16.2 Add provenance and freshness display
    - Surface source freshness (last-updated timestamp), method tag, dimensional contribution, confidence state, and lineage per output; show freshness badges
    - _Requirements: 7.6_
  - [x] 16.3 Add OBSERVED vs SIMULATED labeling
    - Render a persistent SIMULATED label distinguishing simulated from observed outcomes for as long as displayed
    - _Requirements: 14.4_
  - [x] 16.4 Add the access-denied panel
    - Display excluded source ids without rendering or granting access to excluded evidence content
    - _Requirements: 5.7_

- [ ] 17. Additional scenarios (abstain, sparse-history, data-quality false anomaly)
  - [x] 17.1 Build the abstention scenario
    - Add data + hidden ground truth where the top confidence is below threshold or the gap is too small, driving ABSTAIN and no recommended action
    - _Requirements: 10.1, 10.2_
  - [x] 17.2 Build the sparse-history scenario
    - Add data + ground truth with baseline samples < 30 so the sparse-history guard suppresses a false anomaly
    - _Requirements: 3.2_
  - [x] 17.3 Build the data-quality false-anomaly scenario
    - Add data + ground truth where a movement coincides with a quality dip (< 0.80) so the data-quality guard suppresses the anomaly
    - _Requirements: 3.3_
  - [ ]* 17.4 Run the scorecard across all scenarios
    - Execute the evaluator over INC_001 plus the three new scenarios and assert expected pass/fail per scenario
    - _Requirements: 18.1, 18.5_

- [x] 18. Persona narrative refinement + feedback capture
  - [x] 18.1 Refine persona narrative framing
    - Refine Decision_Engine persona framing so CFO/Analyst/Manager narratives differ in text while the winning hypothesis id and all quantitative fields remain exactly equal; omit fields a persona lacks entitlement to while retaining their computed values internally
    - _Requirements: 11.3, 11.4, 11.5_
  - [x] 18.2 Implement feedback persistence and API endpoint
    - Persist feedback (1-5000 chars) with investigation id and receipt timestamp; reject empty/oversized feedback and unknown investigation ids; return an error and no partial entry on persistence failure
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5_
  - [x] 18.3 Wire the feedback widget into the UI
    - Add a Streamlit feedback control that submits to the feedback endpoint and surfaces validation errors
    - _Requirements: 17.1, 17.3_
  - [ ]* 18.4 Write feedback tests
    - Test persistence, invalid-content rejection, unknown-investigation rejection, persistence-failure handling
    - _Requirements: 17.3, 17.4, 17.5_

- [ ] 19. Banking domain switch (Tier 3, OPTIONAL)
  - [ ]* 19.1 Add banking-domain configuration and verify zero engine changes
    - Provide banking `kpi_contracts.yaml`/`entitlements.yaml`/`sources.yaml` and demonstrate the identical engine pipeline runs unchanged (no engine source edits, no recompilation) — clearly optional, build only if all Tier 0/1 work is complete
    - _Requirements: 19.3_

- [x] 20. Submission reproducibility artifacts
  - [x] 20.1 Add a one-command reproducibility runner
    - Create a script that boots Docker, loads data, runs `investigate` for INC_001, and prints the scorecard, so the full slice runs from a single command
    - _Requirements: 18.1_
  - [x] 20.2 Generate the LLM-vs-non-LLM table and scorecard artifact
    - Emit `evaluation/benchmark_results.md` from the method-ownership map and evaluator output (LLM vs non-LLM breakdown + 15-dimension scorecard)
    - _Requirements: 13.5, 18.1_

- [x] 21. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional (tests and the optional banking switch) and can be skipped for a faster MVP; core implementation tasks are never optional.
- Each task references the specific requirement clauses it implements for traceability.
- The vertical slice reaches a working, evaluated INC_001 investigation by Task 13; Task 14 marks the submission-safe milestone.
- Property-based tests use the `hypothesis` library and validate the design's universal correctness properties; unit tests cover specific examples and edge cases.
- Numbers are produced only by deterministic engines ([SQL]/[STATS]/[RULES]); the LLM never produces quantitative truth.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4", "1.5"] },
    { "id": 2, "tasks": ["1.6", "2.1", "2.2"] },
    { "id": 3, "tasks": ["2.3", "3.1"] },
    { "id": 4, "tasks": ["3.2", "4.1", "7.1"] },
    { "id": 5, "tasks": ["4.2", "7.2", "7.3"] },
    { "id": 6, "tasks": ["4.3", "5.1", "7.4"] },
    { "id": 7, "tasks": ["5.2", "5.3", "7.5", "7.6", "8.1"] },
    { "id": 8, "tasks": ["8.2", "8.3", "9.1"] },
    { "id": 9, "tasks": ["9.2"] },
    { "id": 10, "tasks": ["9.3"] },
    { "id": 11, "tasks": ["9.4", "9.5", "10.1"] },
    { "id": 12, "tasks": ["10.2"] },
    { "id": 13, "tasks": ["10.3", "10.4", "11.1"] },
    { "id": 14, "tasks": ["11.2"] },
    { "id": 15, "tasks": ["11.3", "11.4", "12.1", "12.2"] },
    { "id": 16, "tasks": ["12.3"] },
    { "id": 17, "tasks": ["12.4", "12.5", "13.1"] },
    { "id": 18, "tasks": ["13.2"] },
    { "id": 19, "tasks": ["13.3", "15.1"] },
    { "id": 20, "tasks": ["15.2", "16.1"] },
    { "id": 21, "tasks": ["16.2"] },
    { "id": 22, "tasks": ["16.3"] },
    { "id": 23, "tasks": ["16.4"] },
    { "id": 24, "tasks": ["17.1", "17.2", "17.3"] },
    { "id": 25, "tasks": ["17.4", "18.1"] },
    { "id": 26, "tasks": ["18.2"] },
    { "id": 27, "tasks": ["18.3"] },
    { "id": 28, "tasks": ["18.4", "19.1", "20.1"] },
    { "id": 29, "tasks": ["20.2"] }
  ]
}
```
