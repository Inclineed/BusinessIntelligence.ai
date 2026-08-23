# Requirements Document

## Introduction

BusinessIntelligence.ai is a domain-agnostic, evidence-backed KPI decision engine. Given a business scenario (a KPI movement) and a persona (CFO, Analyst, or Manager), a nine-engine pipeline detects the anomaly, decomposes it across dimensions, gathers only entitlement-authorized evidence, proposes competing hypotheses with a large language model, scores those hypotheses deterministically, and either recommends an action or abstains. Every output carries a method tag, and no quantitative value is produced by the language model.

These requirements are derived from the approved design document (`design.md`) and the implementation plan (`docs/IMPLEMENTATION_PLAN.md`). They are scoped to the Tier 0 and Tier 1 priorities: an end-to-end vertical slice, hidden ground-truth evaluation, LLM-vs-non-LLM separation, evidence provenance, and a backend security boundary, demonstrated on the retail scenario INC_001. Banking (or any second domain), causal inference, GraphRAG, and multiple external LLM providers are explicitly out of scope for the MVP; the domain-agnostic configuration requirement notes extensibility only.

Each design correctness property (Properties 1 through 9) is traceable to acceptance criteria in this document so that the design's "Validates: Requirements X.Y" references can be satisfied.

## Glossary

- **System**: The complete BusinessIntelligence.ai application, comprising the nine engines, the orchestrator, the security layer, the telemetry service, the API, and the user interface.
- **Orchestrator**: The pipeline coordinator (`pipeline/investigate.py`) that runs engines E1 through E9 in order, applies the entitlement boundary before evidence assembly, threads telemetry, and returns an Investigation Result.
- **KPI_Store**: Engine E1 (`engines/kpi_store.py`), which loads connected KPI values and their freshness surface using SQL.
- **Signal_Engine**: Engine E2 (`engines/signal.py`), which performs anomaly detection, corroboration, and the sparse-history and data-quality guards using statistics.
- **Diagnostic_Engine**: Engine E3 (`engines/diagnostic.py`), which decomposes a movement across region, channel, and device dimensions.
- **Security_Engine**: The entitlement boundary (`security/entitlements.py`), which maps a persona to an authorization scope and filters evidence before any LLM prompt is assembled.
- **Evidence_Engine**: Engine E4 (`engines/evidence.py`), which assembles authorized, freshness-weighted evidence.
- **Hypothesis_Engine**: Engine E5 (`engines/hypothesis.py`), the language-model engine that proposes hypothesis statements with supporting and contradictory evidence identifiers and reasoning.
- **Challenge_Engine**: Engine E6 (`engines/challenge.py`), the deterministic engine that owns all confidence math and abstention.
- **Decision_Engine**: Engine E7 (`engines/decision.py`), which consumes deterministic confidence to recommend an action or abstain, and writes persona narrative.
- **Outcome_Engine**: Engine E8 (`engines/outcome.py`), which produces a SIMULATED-labeled outcome projection.
- **Memory_Engine**: Engine E9 (`engines/memory.py`), which stores and retrieves organizational precedents.
- **Telemetry_Service**: The cross-cutting facility that records latency, model calls, token usage, external cost, and equivalent cloud cost.
- **Evaluator**: The evaluation component (`evaluation/evaluator.py`) that scores a run across 15 dimensions using the hidden ground truth.
- **LLM_Provider**: The backend-agnostic language-model abstraction (`llm/provider.py`), backed by local Ollama for the MVP.
- **Method_Tag**: A provenance label attached to every engine output, drawn from {SQL, STATS, ETL, RULES, RETRIEVAL, LLM, LLM_NARRATIVE, RULES+LLM_NARRATIVE, SIMULATED}.
- **Persona**: A presentation lens with value CFO, Analyst, or Manager, defined in `entitlements.yaml`.
- **KPI_Semantic_Contract**: The configuration artifact (`kpi_contracts.yaml`) defining each KPI's definition, calculation, drivers, thresholds, lineage, and access restrictions.
- **Source_Registry**: The freshness registry (from `sources.yaml`) tracking each source's grain, cadence, last refresh, SLA, freshness status, data quality, lineage, and owner.
- **Reliability_Weight**: A value in [0, 1] assigned to evidence, decayed for sources that are stale beyond their SLA.
- **Confidence_State**: One of HIGH, MEDIUM, LOW, or ABSTAIN, produced by the Challenge_Engine.
- **Ground_Truth**: The hidden `ground_truth.json` file, read only by the Evaluator and never by the pipeline.
- **INC_001**: The retail demonstration scenario, a checkout/payment degradation caused by release v4.3.
- **SLA**: The maximum allowed staleness for a source, expressed in minutes.

## Requirements

### Requirement 1: Connected KPIs Across Heterogeneous Sources

**User Story:** As a business analyst, I want a set of connected KPIs drawn from data sources with different grains and refresh cadences, so that I can investigate a KPI movement across the systems that actually drive it.

#### Acceptance Criteria

1. WHEN the Orchestrator investigates a scenario, THE KPI_Store SHALL load between 3 and 5 (inclusive) connected KPIs defined in the KPI_Semantic_Contract.
2. THE KPI_Store SHALL draw the connected KPIs from at least 2 data sources whose recorded grains differ (grain values are not identical across the selected sources).
3. THE Source_Registry SHALL record the orders source at hourly grain, the payment gateway source at 15-minute grain, the inventory source at daily grain, and the marketing source at daily grain.
4. WHEN the KPI_Store returns a KPI value, THE KPI_Store SHALL stamp the value with its source identifier, its freshness status (one of fresh, stale, or unavailable), and the Method_Tag SQL.
5. WHILE a source's elapsed time since its last successful refresh is within its SLA threshold, THE Source_Registry SHALL report that source's freshness status as fresh.
6. IF a source's elapsed time since its last successful refresh exceeds its SLA threshold (orders source: 120 minutes; payment gateway source: 30 minutes; inventory source: 48 hours; marketing source: 48 hours), THEN THE Source_Registry SHALL report that source's freshness status as stale.
7. IF a source is unavailable when the KPI_Store attempts to load a connected KPI, THEN THE KPI_Store SHALL return the KPI value stamped with freshness status unavailable, retain the last successfully loaded value, and include an error indication identifying the affected source.

### Requirement 2: KPI Semantic Contract

**User Story:** As a data governance owner, I want each KPI to carry a semantic contract, so that definitions, calculations, drivers, thresholds, lineage, and access rules are explicit and auditable.

#### Acceptance Criteria

1. THE KPI_Semantic_Contract SHALL define, for each connected KPI, all six of the following elements as non-empty values: a definition, a calculation, at least one driver, at least one threshold, a lineage record identifying every upstream source, and access restrictions.
2. THE KPI_Semantic_Contract SHALL define, for each connected KPI, the set of personas permitted to view the KPI value and the set of personas permitted to view its underlying source, where any persona not listed is treated as denied.
3. IF a KPI_Semantic_Contract for a connected KPI is missing or contains an empty value for any of the six required elements (definition, calculation, drivers, thresholds, lineage, access restrictions), THEN THE System SHALL reject registration of that KPI and return an error indicating which element is missing, leaving the existing contract configuration unchanged.
4. WHEN the KPI_Store computes a KPI value, THE KPI_Store SHALL apply the calculation specified in the KPI_Semantic_Contract for that KPI.
5. IF the calculation specified in the KPI_Semantic_Contract cannot be applied because a required driver value is unavailable, THEN THE KPI_Store SHALL not produce a KPI value and SHALL return an error indicating the unavailable driver.
6. WHEN a persona requests a KPI value or its underlying source and that persona is not listed in the applicable access restriction set, THE System SHALL deny the request and return an error indicating access is not permitted, without disclosing the KPI value or source.
7. WHERE a KPI is retargeted to a different domain, THE System SHALL obtain the KPI's definition, calculation, drivers, thresholds, lineage, and access restrictions solely from the KPI_Semantic_Contract configuration without any code changes.

### Requirement 3: Anomaly Detection With Sparse-History and Data-Quality Guards

**User Story:** As an analyst, I want anomaly detection that suppresses false alarms from thin history or degraded data, so that I only act on trustworthy signals.

#### Acceptance Criteria

1. WHEN the Signal_Engine evaluates a KPI against its baseline window, THE Signal_Engine SHALL compute a z-score in the range -1000.00 to 1000.00 (2 decimal places) and a delta percentage in the range -100.00 to 100.00 (2 decimal places) for that KPI.
2. IF a KPI's baseline sample count is below the minimum sample threshold of 30 samples, THEN THE Signal_Engine SHALL set the sparse-history guard flag to true and suppress the anomaly for that KPI within the same evaluation cycle.
3. IF a KPI movement occurs while the KPI's data-quality score for the same evaluation window is below 0.80 on a 0.00 to 1.00 scale, THEN THE Signal_Engine SHALL set the data-quality-suspect guard flag to true and suppress the anomaly for that KPI within the same evaluation cycle.
4. WHEN the Signal_Engine asserts corroboration between two KPIs, THE Signal_Engine SHALL restrict corroboration to KPI pairs whose observation periods overlap by at least 80 percent of the shorter period's duration.
5. WHEN both the sparse-history guard flag and the data-quality-suspect guard flag are false and the absolute z-score is greater than or equal to 3.00 and the absolute delta percentage is greater than or equal to 10.00, THE Signal_Engine SHALL mark the KPI as an anomaly.
6. IF the Signal_Engine cannot compute a z-score or delta percentage for a KPI because required baseline data is absent, THEN THE Signal_Engine SHALL suppress the anomaly for that KPI and record a status indication that the metric was not evaluable, retaining the KPI's existing baseline data unchanged.

### Requirement 4: Dimensional Decomposition

**User Story:** As an analyst, I want a KPI movement decomposed across region, channel, and device, so that I can identify the dominant contributing segment.

#### Acceptance Criteria

1. WHEN the Diagnostic_Engine decomposes an anomaly signal, THE Diagnostic_Engine SHALL produce a contribution percentage in the range 0.00 to 100.00 for each segment within the requested dimensions region, channel, and device.
2. WHEN the Diagnostic_Engine decomposes a movement along a single dimension, THE Diagnostic_Engine SHALL produce contribution percentages that sum to the total movement within a tolerance of plus or minus 0.1 percentage point.
3. WHEN the Diagnostic_Engine completes a decomposition, THE Diagnostic_Engine SHALL identify the dominant segment as the segment with the maximum contribution percentage.
4. IF multiple segments share the maximum contribution percentage, THEN THE Diagnostic_Engine SHALL select the dominant segment as the segment with the lexicographically smallest segment identifier among the tied segments.
5. WHEN the Diagnostic_Engine returns a dimension contribution, THE Diagnostic_Engine SHALL stamp it with the Method_Tag SQL.
6. IF dimensional data required for decomposition is missing or insufficient, THEN THE Diagnostic_Engine SHALL not produce contributions for the affected dimension, return an error indication identifying the affected dimension, and leave existing state unchanged.

### Requirement 5: Role-Based Security and Entitlement Enforcement

**User Story:** As a security owner, I want entitlements enforced in the backend data path, so that unauthorized data never reaches the language model and denied access is visible in the interface.

#### Acceptance Criteria

1. WHEN the Orchestrator begins an investigation for a persona, THE Security_Engine SHALL resolve the persona to an authorization scope consisting of the set of authorized source identifiers and, for each source, the set of authorized field names defined in `entitlements.yaml`.
2. THE Orchestrator SHALL apply the Security_Engine entitlement filter before the Evidence_Engine assembles evidence.
3. WHEN the Security_Engine filters candidate evidence, THE Security_Engine SHALL return only evidence whose source identifier belongs to the persona's authorized scope and SHALL remove any field not in the persona's authorized field set for that source.
4. THE System SHALL ensure that every evidence item reaching any LLM_Provider prompt has a source identifier within the investigating persona's authorized scope and contains only fields within the persona's authorized field set for that source.
5. WHEN a re-applied entitlement filter processes an already-filtered evidence set, THE Security_Engine SHALL return an evidence set identical to its input without adding any source identifier or field outside the persona's authorization scope.
6. IF a persona lacks entitlement to a requested source, THEN THE System SHALL exclude that source's evidence from all LLM_Provider prompts, continue the investigation using only the authorized subset of sources, and return from the API an access-denied result identifying each excluded source identifier without including any evidence content from the excluded sources.
7. WHEN the user interface receives an access-denied result, THE System SHALL display an access-denied panel listing the excluded source identifiers and SHALL NOT display or grant access to any evidence content from the excluded sources.
8. IF the Security_Engine cannot resolve a persona's authorization scope because `entitlements.yaml` is missing, unreadable, or fails schema validation, THEN THE Security_Engine SHALL resolve the authorization scope to the empty set, THE System SHALL send no evidence to any LLM_Provider prompt, and THE System SHALL return an access-denied result from the API indicating that entitlements could not be resolved.
9. WHILE the entitlement filter is applied to a candidate evidence set of up to 10,000 items, THE Security_Engine SHALL complete filtering within 2 seconds.

### Requirement 6: Freshness-Weighted Evidence Reliability

**User Story:** As an analyst, I want evidence from stale sources down-weighted, so that conclusions drawn from outdated data carry less confidence.

#### Acceptance Criteria

1. WHEN the Evidence_Engine assembles evidence, THE Evidence_Engine SHALL assign each evidence item a reliability weight that is a real number in the inclusive range [0, 1].
2. WHERE a source's staleness is within its SLA, THE Evidence_Engine SHALL set the evidence reliability weight equal to that source's data quality factor, where the data quality factor is a value in the inclusive range [0, 1].
3. IF a source's staleness exceeds its SLA, THEN THE Evidence_Engine SHALL set the reliability weight of evidence from that source to a value that is strictly less than the source's data quality factor and not less than 0.
4. WHILE a source's staleness continues to increase beyond its SLA, THE Evidence_Engine SHALL assign a reliability weight that is monotonically non-increasing as staleness increases.
5. WHEN two sources have equal data quality factors and differ only in staleness, THE Evidence_Engine SHALL assign the more stale source a reliability weight less than or equal to that of the less stale source.
6. IF a source's staleness cannot be determined or the source has no defined SLA, THEN THE Evidence_Engine SHALL assign the evidence reliability weight a value of 0 and record an indication that the weight was assigned due to missing freshness metadata.
7. WHEN the Challenge_Engine computes a hypothesis score, THE Challenge_Engine SHALL multiply each evidence item's contribution to the confidence math by that evidence item's reliability weight.

### Requirement 7: Evidence Provenance On Every Output

**User Story:** As a reviewer, I want provenance attached to every output, so that I can trace source freshness, analytical method, contribution, confidence, and lineage for any conclusion.

#### Acceptance Criteria

1. WHEN any engine emits an output, THE System SHALL attach a Method_Tag identifying the analytical method that produced the output, where the Method_Tag is one of the defined values in the Method_Tag set.
2. IF an engine emits an output whose analytical method does not correspond to a defined Method_Tag value, THEN THE System SHALL reject the output, exclude it from any presented result, and return an error indication identifying the unrecognized method.
3. WHEN the Evidence_Engine returns an evidence item, THE Evidence_Engine SHALL attach the source identifier, a reliability weight expressed as a value from 0.0 to 1.0 inclusive, a relevance score expressed as a value from 0.0 to 1.0 inclusive, and a raw reference to the underlying table row or document chunk.
4. THE Evidence_Engine SHALL tag structured evidence with the Method_Tag SQL and unstructured evidence with the Method_Tag RETRIEVAL.
5. IF an evidence item's source identifier does not resolve to a Source_Registry entry, THEN THE Evidence_Engine SHALL drop that evidence item as potential hallucination, exclude it from all downstream outputs, and record an indication that the item was dropped for an unresolved source identifier.
6. WHEN the System presents an investigation output, THE System SHALL surface the source freshness expressed as the timestamp at which the underlying source was last updated, the analytical method as the Method_Tag, the dimensional contribution, the confidence state as one of the defined values from the Confidence_State set, and the lineage identifying each source that contributed to that output.

### Requirement 8: LLM Hypothesis Generation Without Numbers

**User Story:** As a reviewer, I want the language model to propose hypotheses referencing only real evidence identifiers and no quantitative truth, so that generated reasoning cannot fabricate evidence or numbers.

#### Acceptance Criteria

1. WHEN the Hypothesis_Engine generates a hypothesis, THE Hypothesis_Engine SHALL produce a hypothesis containing exactly four fields: a statement (1 to 2000 characters, non-empty), a list of supporting evidence identifiers (0 to 500 entries), a list of contradictory evidence identifiers (0 to 500 entries), and reasoning (1 to 5000 characters, non-empty).
2. THE Hypothesis_Engine SHALL reference in the supporting and contradictory evidence identifier lists only evidence identifiers that are present in the entitlement-filtered evidence input set.
3. IF a generated hypothesis references an evidence identifier that is not present in the entitlement-filtered evidence input set, THEN THE Hypothesis_Engine SHALL reject that hypothesis, exclude it from the returned results, and record an error indication identifying the unknown evidence identifier.
4. THE Hypothesis_Engine SHALL exclude from every hypothesis statement any confidence value and any quantitative-truth value, where a quantitative-truth value is defined as any numeric digit, percentage, ratio, probability, count, score, or ranking that asserts a measured or fabricated fact.
5. IF a generated hypothesis statement contains a quantitative-truth value as defined in criterion 4, THEN THE Hypothesis_Engine SHALL reject that hypothesis, exclude it from the returned results, and record an error indication identifying the offending statement.
6. WHEN the Hypothesis_Engine returns a hypothesis, THE Hypothesis_Engine SHALL stamp it with the Method_Tag LLM.
7. THE Orchestrator SHALL provide the Hypothesis_Engine only evidence that has already passed the Security_Engine entitlement filter.

### Requirement 9: Deterministic Confidence and Abstention

**User Story:** As an evaluator, I want all confidence math and abstention owned by a deterministic engine, so that scores are reproducible across runs and defensible under evaluation.

#### Acceptance Criteria

1. WHEN the Challenge_Engine scores a hypothesis, THE Challenge_Engine SHALL evaluate each of the rules timeline, segment_alignment, kpi_corroboration, mechanism_consistency, and contradiction, and SHALL assign each rule exactly one verdict from the set {PASS, PARTIAL, FAIL}.
2. THE Challenge_Engine SHALL compute the final score as a deterministic function whose only inputs are the rule verdicts, the evidence reliability weights (each in the range [0, 1]), the evidence relevance scores (each in the range [0, 1]), and the configured thresholds, such that identical input values always yield identical output values with no dependence on wall-clock time, random values, or external state.
3. THE Challenge_Engine SHALL clamp every final score to the range [0, 1].
4. WHEN two investigations run with identical inputs, THE Challenge_Engine SHALL produce an equal multiset of (hypothesis identifier, final score, confidence state) tuples, where final scores compare as equal at the full stored numeric precision.
5. WHERE the Challenge_Engine produces an optional narrative, THE Challenge_Engine SHALL tag the narrative LLM_NARRATIVE, and the final score and confidence state fields SHALL hold identical values whether or not the narrative is produced.
6. IF the top hypothesis final score is below the configured abstain threshold (a value in [0, 1]) OR the gap between the top hypothesis final score and the runner-up final score is below the configured minimum gap (a value in [0, 1]), THEN THE Challenge_Engine SHALL set the top hypothesis confidence state to ABSTAIN.
7. IF no hypothesis is available to rank when a confidence state must be assigned, THEN THE Challenge_Engine SHALL set the confidence state to ABSTAIN and SHALL leave all final score fields unmodified.
8. WHEN the Challenge_Engine accumulates a support score, THE Challenge_Engine SHALL add only supporting evidence to the support score and SHALL add only contradictory evidence to the contradiction penalty.

### Requirement 10: Abstention Safety and Low-Confidence Handling

**User Story:** As a decision owner, I want the system to withhold recommendations when confidence is low, so that no action is proposed on ambiguous evidence.

#### Acceptance Criteria

1. WHEN the winning hypothesis confidence state resolves to ABSTAIN, THE Decision_Engine SHALL set the decision status to "abstained" and SHALL return an empty recommended-action field.
2. WHILE the confidence score of the winning hypothesis is below the configured abstention threshold (default 0.60 on a 0.00 to 1.00 scale), THE Decision_Engine SHALL classify the confidence state as ABSTAIN.
3. WHEN the Decision_Engine sets the decision status to "abstained", THE Decision_Engine SHALL return verification guidance consisting of at least one and at most ten actionable verification steps in place of a recommended action.
4. WHEN the Decision_Engine sets the decision status to "abstained", THE Decision_Engine SHALL include a machine-readable reason identifying the abstention cause (low confidence or provider unavailability).
5. IF the LLM_Provider remains unavailable after the fallback from the default model to the fallback model, THEN THE Decision_Engine SHALL set the decision status to "abstained" with a stated reason indicating provider unavailability, AND SHALL retain and return the numeric outputs produced by the deterministic engines without modification.
6. IF the LLM_Provider returns no response within the configured request timeout (default 30 seconds) for both the default model and the fallback model, THEN THE Decision_Engine SHALL treat the LLM_Provider as unavailable.

### Requirement 11: Persona-Specific Narratives With Invariant Analysis

**User Story:** As a stakeholder in a specific role, I want narratives and actions framed for my role while the underlying analysis stays identical, so that different roles receive relevant guidance without diverging conclusions.

#### Acceptance Criteria

1. THE System SHALL support at least two of the three personas CFO, Analyst, and Manager, where a persona is considered supported if the System accepts it as a valid input and produces persona-framed output for it.
2. WHEN the same scenario is investigated for two different supported personas, THE Orchestrator SHALL produce quantitative fields that are exactly equal at their full stored precision, including KPI values, deltas, dimension contributions, final scores, and the winning hypothesis identifier, such that a field-by-field comparison yields zero differences.
3. WHEN the Decision_Engine produces output for a supported persona, THE Decision_Engine SHALL apply that persona's narrative framing to the surfaced textual output while leaving every quantitative field identical to the value computed for any other persona for the same scenario.
4. WHEN the same scenario is investigated for two different supported personas, THE Decision_Engine SHALL produce persona narratives that differ in at least the persona-framed textual content while the winning hypothesis identifier and all quantitative fields remain exactly equal.
5. IF a persona lacks entitlement to a specific field, THEN THE System SHALL omit that field from the persona's surfaced output while retaining that field's computed value in the underlying analysis unchanged.
6. IF a requested persona is not among the supported personas, THEN THE System SHALL reject the request and return an error indication that the requested persona is unsupported, without producing surfaced output.

### Requirement 12: INC_001 Multi-Factor Movement With Known Drivers

**User Story:** As a demonstrator, I want the INC_001 scenario to reproduce a multi-factor KPI movement with known drivers, so that the pipeline provably identifies the true cause and refutes misleading alternatives.

#### Acceptance Criteria

1. THE System SHALL represent the INC_001 movement with the following fixed values: revenue down 8.2 percent, overall conversion down 10 percent, Android conversion down 17 percent, payment failure rate increased to 4.0 times its baseline value (a 300 percent increase), gateway latency up 240 percent, and inventory at normal levels, with the marketing source data flagged as stale (data age greater than 24 hours).
2. WHEN the Diagnostic_Engine decomposes INC_001 by device, THE Diagnostic_Engine SHALL identify the Android device segment as the dominant negative contributor, defined as the device segment with the largest-magnitude negative contribution to the conversion decline among all device segments.
3. WHEN the Challenge_Engine scores the INC_001 hypotheses, THE Challenge_Engine SHALL assign the checkout/payment degradation hypothesis a confidence state of HIGH (confidence score in the range 0.70 to 1.00 on a 0.00 to 1.00 scale) and SHALL select it as the winning hypothesis.
4. WHEN the Challenge_Engine scores the inventory-shortage hypothesis for INC_001, THE Challenge_Engine SHALL assign it a confidence state of LOW (confidence score in the range 0.00 to 0.30 on a 0.00 to 1.00 scale) driven by the fresh (data age at most 24 hours) inventory-normal contradictory evidence, and SHALL NOT select it as the winning hypothesis.
5. WHEN the Challenge_Engine scores the competitor-pricing hypothesis for INC_001, THE Challenge_Engine SHALL assign it a confidence state no higher than MEDIUM (confidence score below the 0.70 HIGH threshold) due to the device-segment mismatch and the down-weighted stale marketing evidence, and SHALL NOT select it as the winning hypothesis.
6. WHEN the Decision_Engine resolves INC_001 without abstaining, THE Decision_Engine SHALL recommend rolling back release v4.3, and SHALL set the verification metrics to payment success rate and conversion recovery.

### Requirement 13: Visible Method Separation Between LLM and Non-LLM

**User Story:** As a reviewer, I want a visible separation between language-model methods and deterministic methods, so that I can confirm the language model is never the source of quantitative truth.

#### Acceptance Criteria

1. WHEN any engine produces a numeric field, including KPI values, deltas, contributions, and final scores, THE System SHALL set the producing engine's Method_Tag to exactly one of SQL, STATS, or RULES.
2. IF an engine tagged LLM produces a numeric field, including KPI values, deltas, contributions, or final scores, THEN THE System SHALL reject the output, exclude the numeric field from the investigation result, and record an error indication identifying the offending engine.
3. THE System SHALL restrict LLM_Provider output to exactly the following content types: hypothesis statements, evidence summaries, persona narrative, and action explanation.
4. IF LLM_Provider output contains any content outside the four permitted content types, THEN THE System SHALL reject that output and record an error indication identifying the disallowed content type.
5. WHEN the Orchestrator completes an investigation, THE Orchestrator SHALL return a method-ownership map that associates each engine with its Method_Tag or tags, where every engine present in the investigation appears exactly once.
6. WHEN the user interface renders an investigation, THE System SHALL display, from the method-ownership map, each engine, its associated Method_Tag or tags, and a grouping that separates engines tagged LLM from engines tagged SQL, STATS, or RULES.

### Requirement 14: Outcome Simulation Honesty

**User Story:** As a reviewer, I want simulated outcomes clearly labeled and distinguished from observed data, so that projections are never mistaken for causal proof.

#### Acceptance Criteria

1. WHEN the Outcome_Engine produces an outcome projection, THE Outcome_Engine SHALL set the outcome type to SIMULATED and stamp it with the Method_Tag SIMULATED before the projection is returned.
2. WHEN the Outcome_Engine returns a projection, THE Outcome_Engine SHALL attach a disclaimer stating that the projection is a simulated estimate and is not causal proof.
3. THE System SHALL present every outcome projection with its SIMULATED type and disclaimer visible, and SHALL NOT present any projection using wording that asserts or implies causal proof.
4. WHEN the user interface displays outcomes, THE System SHALL render a persistent SIMULATED label on each simulated outcome that remains visible for as long as the outcome is displayed, such that simulated outcomes are visually distinguishable from observed outcomes without further user action.
5. IF an outcome projection lacks the Method_Tag SIMULATED, THEN THE System SHALL withhold the projection from display and indicate that the outcome could not be verified as a labeled simulation.
6. WHERE a simulated outcome is exported or shared outside the user interface, THE System SHALL include the SIMULATED type and the not-causal-proof disclaimer in the exported representation.

### Requirement 15: Organizational Memory

**User Story:** As an analyst, I want the system to store and retrieve precedents, so that prior investigations inform current ones.

#### Acceptance Criteria

1. WHEN an investigation completes, THE Memory_Engine SHALL store the investigation result as a precedent within 5 seconds of completion.
2. IF storing a precedent fails, THEN THE Memory_Engine SHALL retain the investigation result in a pending queue for retry up to 3 attempts and return an error indication reporting the storage failure.
3. WHEN the Orchestrator investigates a scenario, THE Memory_Engine SHALL retrieve up to 10 precedents whose relevance score to that scenario is greater than or equal to 0.7 on a 0.0 to 1.0 scale, ordered from highest to lowest relevance score.
4. IF no stored precedent has a relevance score greater than or equal to 0.7 for the investigated scenario, THEN THE Memory_Engine SHALL return an empty precedent set and an indication that no relevant precedents were found.
5. WHEN the Memory_Engine returns a retrieved precedent, THE Memory_Engine SHALL stamp it with the RETRIEVAL Method_Tag.

### Requirement 16: Runtime Telemetry

**User Story:** As an operator, I want runtime telemetry captured per investigation, so that I can measure latency, model usage, and cost avoidance.

#### Acceptance Criteria

1. WHEN the Orchestrator runs an investigation, THE Telemetry_Service SHALL record per-engine latency in milliseconds with a resolution of 1 millisecond.
2. WHEN the Orchestrator runs an investigation, THE Telemetry_Service SHALL record the count of language-model calls as a non-negative integer and record token usage as separate input-token and output-token counts.
3. THE Telemetry_Service SHALL record the external cost as exactly 0.00 United States dollars for local model execution.
4. THE Telemetry_Service SHALL record an equivalent cloud cost estimate in United States dollars, rounded to 2 decimal places, computed by multiplying the recorded token usage by the corresponding per-1000-token rate from the rate table.
5. IF the per-1000-token rate table is unavailable or does not contain a rate for a recorded model, THEN THE Telemetry_Service SHALL record the equivalent cloud cost estimate as unavailable, continue recording all remaining telemetry metrics, and provide an indication that the estimate could not be computed.
6. IF recording any individual telemetry metric fails, THEN THE Telemetry_Service SHALL record that metric as unavailable, preserve all successfully recorded metrics, and continue the investigation without aborting.
7. WHEN an investigation completes, THE Orchestrator SHALL include all recorded telemetry, comprising per-engine latency, language-model call count, input-token and output-token counts, external cost, and equivalent cloud cost estimate, in the investigation result.

### Requirement 17: Feedback Capture

**User Story:** As a user, I want to submit feedback on an investigation, so that the system can capture signals for future improvement.

#### Acceptance Criteria

1. WHEN a user submits feedback of 1 to 5000 characters on an investigation result, THE System SHALL persist the feedback content associated with that investigation.
2. WHEN feedback is persisted, THE System SHALL record the investigation identifier to which the feedback applies and the timestamp at which the feedback was received.
3. IF the submitted feedback is empty or exceeds 5000 characters, THEN THE System SHALL reject the submission without persisting it and return an error indicating the feedback content is invalid.
4. IF the investigation identifier associated with the submitted feedback does not correspond to an existing investigation, THEN THE System SHALL reject the submission without persisting it and return an error indicating the investigation was not found.
5. IF persistence of the feedback fails, THEN THE System SHALL not record a partial entry and SHALL return an error indicating the feedback could not be saved.

### Requirement 18: Ground-Truth Evaluation Across 15 Dimensions

**User Story:** As an evaluator, I want the pipeline scored against hidden ground truth across 15 dimensions, so that correctness is proven objectively rather than asserted by fluency.

#### Acceptance Criteria

1. WHEN the Evaluator scores an investigation, THE Evaluator SHALL score the run across 15 dimensions, including winning-hypothesis correctness, hypothesis ranking, contradiction handling, expected confidence state, recommended action, verification metric, hallucinated-evidence count, and authorization-violation count, and SHALL emit a per-dimension result record in which each dimension is scored as a value in the inclusive range 0 to 1.
2. WHILE the Evaluator is scoring a run, THE Evaluator SHALL read the Ground_Truth file only within the Evaluator process.
3. THE pipeline SHALL NOT import or read the Ground_Truth file.
4. IF the pipeline attempts to access the Ground_Truth file, THEN THE System SHALL fail that access and record an authorization-violation indication.
5. WHEN the Evaluator scores a run, THE Evaluator SHALL mark the run as passed only IF the hallucinated-evidence count equals 0 AND the authorization-violation count equals 0, and otherwise THE Evaluator SHALL mark the run as failed.

### Requirement 19: Domain-Agnostic Configuration and Extensibility

**User Story:** As a platform owner, I want the domain expressed as configuration, so that the same pipeline can be retargeted to another industry without engine code changes.

#### Acceptance Criteria

1. WHEN the System initializes, THE System SHALL determine the active domain exclusively from the KPI_Semantic_Contract, the entitlements configuration, and the sources configuration, without reference to any hardcoded domain value in engine code.
2. IF the KPI_Semantic_Contract, the entitlements configuration, or the sources configuration is absent or fails schema validation during initialization, THEN THE System SHALL halt initialization and return an error indicating which configuration artifact is missing or invalid, without falling back to a default domain.
3. WHERE the KPI_Semantic_Contract, entitlements configuration, and sources configuration are replaced with those of a different domain, THE System SHALL execute the same engine pipeline with zero modifications to engine source files and without recompilation of engine code.
4. THE System SHALL exclude the banking domain switch, causal inference, GraphRAG, and support for more than one external LLM provider from the MVP scope.
5. THE LLM_Provider SHALL expose a backend-agnostic interface such that replacing the language-model backend requires zero modifications to engine source files.
