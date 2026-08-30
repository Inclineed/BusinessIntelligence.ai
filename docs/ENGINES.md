# Engines Reference Guide (E1–E9)

This document provides a comprehensive technical reference for the nine core engines of **BusinessIntelligence.ai**. Each engine is documented using a standardized specification structure reflecting its concrete implementation.

---

## E1: KPI Store Engine

### Purpose
Loads connected KPI time-series values from the PostgreSQL relational store per the KPI Semantic Contract (`config/kpi_contract.yaml`) and tracks data freshness against defined SLAs.

### Inputs
- `scenario_id`: Unique identifier for the business incident (e.g., `"INC_001"`).
- `window_start`, `window_end`: Analysis time boundaries.
- `kpi_contract`: Semantic metric definitions.
- `db_conn`: Active PostgreSQL database connection.

### Outputs
- `KPILoadResult`: NamedTuple containing `kpi_values` (list of `KPIValue` instances) and `load_errors`.

### Core Logic
1. Queries table `kpi_values` for current and baseline historical windows.
2. Evaluates time elapsed since last measurement against `sla_minutes`.
3. Sets `FreshnessStatus` (`FRESH`, `STALE`, `CRITICAL_STALE`, or `UNKNOWN`).
4. Associates metric driver trees and expected directional impact from contract.

### Deterministic vs LLM Behavior
**100% Deterministic SQL.** No LLM is involved.

### Provenance Tag
`MethodTag.SQL`

### Failure/Abstention Behavior
If database connection is absent or a KPI is missing from the table, returns `KPILoadResult(kpi_values=[], load_errors=[...])`. Upstream orchestrator halts signal detection if essential KPIs cannot be loaded.

### Security Considerations
Only loads KPI metrics defined in the system registry. Does not expose unaggregated raw event payloads.

### Memory Interaction
None.

### Tests
- `tests/test_kpi_store.py`

### Relevant Source Files
- `engines/kpi_store.py`
- `config/kpi_contract.yaml`

---

## E2: Signal Detection Engine

### Purpose
Performs statistical anomaly detection across connected KPI time-series to identify significant deviations from historical baselines while enforcing corroboration guards.

### Inputs
- `kpi_values`: Output of Engine E1.
- `baseline_history`: Historical KPI distribution data.

### Outputs
- `list[AnomalySignal]`: Signals containing `z_score`, `baseline_mean`, `baseline_std`, `current_value`, `is_anomaly`, and `direction`.

### Core Logic
1. Computes z-score: $z = \frac{\text{current\_value} - \mu}{\sigma}$.
2. Evaluates statistical threshold ($|z| \ge 2.0$).
3. **Trailing Bucket Anomaly Guard**: Implements partial-window protection. If an anomaly is observed only in an incomplete trailing bucket without corroborating signals across leading indicators, flags the signal as non-anomalous to prevent false-alarm pipeline execution (as validated in `INC_005`).

### Deterministic vs LLM Behavior
**100% Deterministic Stats.** Pure mathematical calculation using `scipy.stats` / Python `math`.

### Provenance Tag
`MethodTag.STATS`

### Failure/Abstention Behavior
If $\sigma = 0$ or history is insufficient, returns neutral signals ($z=0.0, \text{is\_anomaly}=\text{False}$) with explanatory warning logs.

### Security Considerations
Processes aggregated numbers; no PII or sensitive text payloads involved.

### Memory Interaction
None.

### Tests
- `tests/test_signal.py`

### Relevant Source Files
- `engines/signal.py`

---

## E3: Diagnostic Decomposition Engine

### Purpose
Decomposes detected KPI anomalies across dimensional hierarchies (e.g., `device`, `region`, `channel`) to identify segment-level concentration and dominant contributors.

### Inputs
- `signals`: Anomalous signals from E2.
- `dimensions`: Target breakdown dimensions (from `config/kpi_contract.yaml`).
- `db_conn`: PostgreSQL connection.

### Outputs
- `list[DimensionContribution]`: Segment breakdowns containing `dimension`, `segment`, `current_value`, `baseline_value`, `delta`, and `contribution_pct`.

### Core Logic
1. Queries dimensionally segmented historical tables in PostgreSQL.
2. Computes the percentage contribution of each segment to the total metric delta:
   $$\text{contribution\_pct} = \frac{\Delta \text{segment}}{\sum |\Delta \text{segments}|} \times 100$$
3. Identifies the dominant dimensional contributor (e.g., Android device segment representing >70% of conversion drop).

### Deterministic vs LLM Behavior
**100% Deterministic SQL + Stats.**

### Provenance Tag
`MethodTag.SQL` / `MethodTag.STATS`

### Failure/Abstention Behavior
If dimensional tables have no data for a segment, logs warning and returns an empty contribution list without crashing the pipeline.

### Security Considerations
Occurs *prior* to the entitlement boundary. E3 is safe to run before authorization because it operates exclusively on KPI-level aggregate data and dimensional segments defined in the semantic contract. It does not retrieve or expose raw unstructured evidence payloads. Results are naturally constrained by the persona scope in the subsequent E4 step.

### Memory Interaction
None.

### Tests
- `tests/test_diagnostic.py`

### Relevant Source Files
- `engines/diagnostic.py`

---

## E4: Evidence Assembly Engine

### Purpose
Assembles authorized, freshness-weighted evidence from structured SQL tables and unstructured ChromaDB vector collections.

### Inputs
- `authorized_sources`: `frozenset[str]` passed from Security Engine.
- `scenario_id`: Target incident identifier.
- `anomaly_window_start`, `anomaly_window_end`: Time window.
- `registry`: `SourceRegistry` containing SLA and data quality ratings.
- `db_conn`: PostgreSQL connection.
- `chroma_client`: ChromaDB client.
- `llm_provider`: Optional LLM provider for long text summarization.

### Outputs
- `EvidenceAssemblyResult`: `evidence` (list of `Evidence` objects with `evidence_id`, `reliability_weight`, `relevance`), `dropped_count`, `reliability_notes`.

### Core Logic
1. **Pre-Retrieval Authorization Filter**: Only queries tables/collections present in `authorized_sources`.
2. **Structured Querying**: Extracts records from `payment_events`, `inventory_events`, `deployment_log`, and `support_tickets`.
3. **Unstructured Vector Querying**: Queries ChromaDB using Ollama `bge-m3` embeddings (1024 dimensions) with metadata filter `{"source": {"$in": authorized_sources}}`.
4. **Reliability Weight Decay**:
   $$\text{reliability\_weight} = \text{data\_quality} \times \max\left(0, 1 - \frac{\text{staleness\_minutes} - \text{sla\_minutes}}{\text{sla\_minutes}}\right)$$
5. **Deterministic ID Generation**: Creates stable SHA-256 evidence hashes (`prefix:scenario_id:suffix`).

### Deterministic vs LLM Behavior
- Retrieval and reliability weights are **100% Deterministic**.
- Optional single-sentence compression for texts >200 words via LLM (with fallback to raw text on failure).

### Provenance Tag
`MethodTag.SQL`, `MethodTag.RETRIEVAL`, `MethodTag.ETL`

### Failure/Abstention Behavior
If a data source is missing from `SourceRegistry`, drops the item and records note (Requirement 7.5). If all sources are unauthorized, returns an empty evidence list.

### Security Considerations
**Crucial Boundary**: E4 enforces pre-retrieval source filtering and secondary post-query validation. Explicitly forbidden from accessing the `investigation_precedents` ChromaDB collection.

### Memory Interaction
None (reads operational collections only; never reads precedent memory).

### Tests
- `tests/test_evidence.py`

### Relevant Source Files
- `engines/evidence.py`
- `config/sources.yaml`

---

## E5: Hypothesis Generation Engine

### Purpose
Generates competing candidate causal hypotheses grounded in the KPI driver space, linking anomalies to observed evidence.

### Inputs
- `signals`: Anomalous KPI signals from E2.
- `contributions`: Dimensional contributions from E3.
- `evidence`: Authorized evidence items from E4.
- `llm_provider`: Ollama provider (`qwen3:8b`).

### Outputs
- `list[Hypothesis]`: Hypotheses with `hypothesis_id`, `statement`, `supporting_evidence_ids`, `contradictory_evidence_ids`, `reasoning`, `citations`.

### Core Logic
1. Constructs a structured prompt presenting the metric movements, dominant segments, and available evidence IDs.
2. Invokes LLM with `temperature=0.0` and a strict JSON schema.
3. **Citation Canonicalization**: Extracts exact evidence IDs and summaries.
4. **Validation Guard**: Verifies that every cited evidence ID exists in the E4 evidence set. Drops hypotheses with hallucinated evidence IDs.

### Deterministic vs LLM Behavior
**LLM-Generated Narrative.** The LLM writes statements, reasoning, and role linkages. The LLM is strictly prohibited from generating numbers, probabilities, or confidence scores. While downstream scoring is deterministic conditional on the LLM's structured outputs, the LLM generation itself is not bit-for-bit deterministic, even with `temperature=0.0`.

### Provenance Tag
`MethodTag.LLM`

### Failure/Abstention Behavior
If the LLM is unreachable or returns malformed JSON, returns an empty hypothesis list, which triggers deterministic abstention in E6/E7.

### Security Considerations
Only receives evidence that passed the E4 authorization filter.

### Memory Interaction
None.

### Tests
- `tests/test_challenge_smoke.py`
- `tests/test_citation_validation.py`

### Relevant Source Files
- `engines/hypothesis.py`

---

## E6: Challenge & Scoring Engine

### Purpose
Evaluates competing hypotheses against five deterministic operational rules, computes mathematical support and contradiction penalties, and determines final confidence states.

### Inputs
- `hypotheses`: Generated hypotheses from E5.
- `evidence_by_id`: Lookup mapping of all assembled E4 evidence.
- `signals`: Anomaly signals from E2.
- `contributions`: Dimensional contributions from E3.
- `thresholds`: `ChallengeThresholds` (`high_threshold=0.70`, `medium_threshold=0.40`, `abstain_threshold=0.30`, `min_gap=0.15`).

### Outputs
- `ChallengeResult`: `scored_hypotheses`, `confidence_state` (`HIGH`, `MEDIUM`, `LOW`, `ABSTAIN`), `winning_hypothesis_id`, `abstained` flag.

### Core Logic
1. **Citation Validation (D16)**: Verifies no duplicate citations, no phantom IDs, and exact normalized summary matching. Note: Formatting and whitespace drift is normalized away via canonicalization, so minor text drifts are not fatal. However, material quote mismatches, duplicate citations, and phantom (hallucinated) IDs are fatal citation violations that immediately disqualify the hypothesis (`final_score=0.0, confidence=ABSTAIN`).
2. **Five Operational Rules**:
   - `timeline` (0.25): Verifies root cause precedes KPI anomaly.
   - `segment_alignment` (0.20): Verifies hypothesis accounts for dominant segment skew.
   - `kpi_corroboration` (0.20): Verifies leading and lagging metrics corroborate.
   - `mechanism_consistency` (0.20): Verifies evidence supports proposed physical failure mechanism.
   - `contradiction` (0.15): Evaluates presence of high-reliability refuting evidence.
3. **Deterministic Weakest-Link Scoring Formula**:
   $$\text{rule\_score} = \sum_{r} \text{weight}_r \times \text{verdict\_val}_r \quad (\text{PASS}=1.0, \text{PARTIAL}=0.5, \text{FAIL}=0.0)$$
   $$\text{grounding\_factor} = \text{support\_score} \times (1.0 - \text{contradiction\_score})$$
   $$\text{final\_audit\_score} = \text{clamp}(\text{rule\_score} \times \text{grounding\_factor}, 0.0, 1.0)$$
4. **Root-Cause Evidence Gate**:
   A candidate hypothesis cannot achieve `VERIFIED` status without passing the root-cause evidence gate (corroboration by at least one internal release, deployment record, or direct system trace).
5. **Winner & Audit Verdict Determination**:
   - `final_audit_score >= 0.70` $\rightarrow$ `VERIFIED`
   - `0.40 <= final_audit_score < 0.70` $\rightarrow$ `MARGINAL`
   - `final_audit_score < 0.40` $\rightarrow$ `REJECTED`
   - Score gap between top two candidate hypotheses $< 0.15$ $\rightarrow$ `ABSTAIN`

### Deterministic vs LLM Behavior
**100% Deterministic Rule Engine.** Zero LLM involvement in score calculation or rule evaluation.

### Provenance Tag
`MethodTag.RULES`

### Failure/Abstention Behavior
If zero hypotheses are provided, or top score is below abstain threshold, or top score gap $< 0.15$, sets `abstained=True` and `audit_verdict=ABSTAIN`.

### Security Considerations
Pure computational logic; handles evidence IDs strictly within scope.

### Memory Interaction
None.

### Tests
- `tests/test_challenge_smoke.py`
- `tests/test_citation_validation.py`
- `tests/test_causal_e6_isolation.py`

### Relevant Source Files
- `engines/challenge.py`

---

## E7: Decision Engine

### Purpose
Produces actionable mitigation recommendations for the winning hypothesis tailored to the target executive persona, enforcing strict abstention invariants and governed action safety.

### Inputs
- `challenge_result`: Output from E6.
- `persona`: Target user persona (`analyst`, `manager`, `cfo`).
- `llm_provider`: Pluggable LLM provider (Ollama / Groq / OpenAI / Anthropic).

### Outputs
- `Decision`: `winning_hypothesis_id`, `recommended_action`, `overall_verdict`, `persona_narrative`, `abstained`, `method`.

### Core Logic
1. **Abstention Invariant**: If `challenge_result.abstained == True` or confidence is `ABSTAIN`, immediately returns `Decision(abstained=True, recommended_action=None)`.
2. **Action Governance**:
   - For `VERIFIED` verdicts: Formulates a concrete, high-confidence mitigation action (e.g. immediate rollback, cache invalidation, supplier reroute).
   - For `MARGINAL` verdicts: Emits a guarded exploratory / telemetry gathering directive without irreversible automated intervention.
3. **Persona Synthesis**: Invokes LLM with persona context:
   - `analyst`: Technical root-cause details and deployment rollbacks.
   - `manager`: Operational timeline, team ownership, and customer impact.
   - `cfo`: Financial exposure, revenue loss mitigation, and SLA impact.

### Deterministic vs LLM Behavior
- Abstention gate and action governance policy are **100% Deterministic**.
- Narrative synthesis is **LLM-Generated** (`temperature=0.0`).

### Provenance Tag
`MethodTag.LLM`

### Failure/Abstention Behavior
If the LLM fails or times out, returns `abstained=True` with `persona_narrative="LLM unavailable"`.

### Security Considerations
Persona entitlement filters are preserved; narrative only discusses evidence present in the authorized result.

### Memory Interaction
None.

### Tests
- `tests/test_challenge_smoke.py`

### Relevant Source Files
- `engines/decision.py`

---

## E8: Outcome Projection Engine

### Purpose
Simulates metric recovery trajectories following the execution of the recommended mitigation action under strict simulation boundaries.

### Inputs
- `decision`: Output from E7.
- `kpi_values`: Original KPI values from E1.
- `signals`: Detected signals from E2.

### Outputs
- `ProjectedOutcome`: `projected_kpi_values`, `recovery_time_hours`, `confidence_interval`, `outcome_type="SIMULATED"`, `disclaimer`.

### Core Logic
1. Computes expected metric rebound towards baseline mean based on historical recovery curves.
2. Attaches mandatory disclaimer: *"Simulation model projection only. Not causal proof."*
3. Stamps all records with `outcome_type="SIMULATED"`.

### Deterministic vs LLM Behavior
**Deterministic Simulation Model.**

### Provenance Tag
`MethodTag.SIMULATED`

### Failure/Abstention Behavior
If decision is abstained, returns empty outcome projection.

### Security Considerations
Projections are clearly segregated from actual database records.

### Memory Interaction
Precedents stored in E9 with simulated outcomes are tagged `outcome_type="simulated"` and excluded from standard retrieval.

### Tests
- `tests/test_memory.py`

### Relevant Source Files
- `engines/outcome.py`

---

## E9: Provenance-Aware Memory Engine

### Purpose
Persists complete investigation records into ChromaDB vector memory (`investigation_precedents`) and retrieves semantically similar past incidents weighted by historical confidence, human validation, and retention decay. (Note: Precedent retrieval occurs pre-run, but the retrieved precedents are not currently injected into the active investigation loop; they are simply surfaced in the `InvestigationResult`).

### Inputs
- **Storage**: `InvestigationResult`, `outcome_type` (`OBSERVED` or `SIMULATED`).
- **Retrieval**: `scenario_id`, `query_context`, `include_simulated` flag, `retention_config`.

### Outputs
- **Storage**: Boolean status (True on upsert).
- **Retrieval**: `list[dict]` containing precedent metadata, `relevance`, `retrieval_weight`, `retrieval_score`, and `human_validated` flags.

### Core Logic
1. **Summary & Embedding**: Summarizes result (or deterministic fallback) and embeds using Ollama `bge-m3`.
2. **Metadata Upsert**: Saves complete provenance: `scenario_id`, `persona`, `confidence_state`, `original_confidence_state`, `outcome_type`, `evidence_ids`, `created_at`, `human_validated=False`, `validated_at=""`.
3. **Retrieval Scoring**:
   $$\text{retrieval\_score} = \text{round}(\text{relevance} \times \text{conf\_weight} + \text{human\_boost}, 4)$$
   - `HIGH`: 1.0 | `MEDIUM`: 0.6 | `ABSTAIN`: 0.2 | `LOW`: 0.1
   - `human_boost`: +0.1 if `human_validated == True`
4. **TTL Expiry**: Filters precedents older than their domain-specific TTL (`config/memory_retention.yaml`).

### Deterministic vs LLM Behavior
- Retrieval, filtering, and scoring are **100% Deterministic**.
- Precedent summarization uses **LLM** with deterministic template fallback.

### Provenance Tag
`MethodTag.RETRIEVAL`

### Failure/Abstention Behavior
On ChromaDB write timeout (>5.0s) or failure, enqueues item in in-memory `_pending` queue for up to 3 retries via `flush_pending()`.

### Security Considerations
E4 evidence assembly is strictly forbidden from querying `investigation_precedents`. Retrieval filters unverified legacy and simulated records by default.

### Memory Interaction
This engine owns the ChromaDB collection `investigation_precedents`.

### Tests
- `tests/test_memory.py`

### Relevant Source Files
- `engines/memory.py`
- `config/memory_retention.yaml`
- `scripts/rebuild_memory.py`
