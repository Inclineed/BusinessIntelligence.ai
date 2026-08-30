export type PersonaType = "analyst" | "cfo" | "manager"
export type AuditVerdict = "VERIFIED" | "MARGINAL" | "REJECTED" | "ABSTAIN"
export type EvidenceSufficiencyLevel = "STRONG" | "SUFFICIENT" | "LIMITED" | "INSUFFICIENT"
export type RuleVerdict = "pass" | "partial" | "fail" | "n/a"
export type BusinessMateriality = "NEGLIGIBLE" | "REJECTED" | "MARGINAL" | "VERIFIED" | "CRITICAL"

export interface AnomalySignal {
  kpi_id: string
  observed: number
  expected: number
  delta_pct: number
  z_score: number
  is_anomaly: boolean
  method?: string
  corroborated_by?: string[]
  sparse_history?: boolean
  data_quality_suspect?: boolean
}

export interface MaterialityAssessment {
  kpi_id: string
  observed_value: number
  baseline_mean: number
  z_score: number
  delta_pct: number
  is_statistical_anomaly: boolean
  financial_impact?: number | null
  volume_impact?: number | null
  business_materiality: BusinessMateriality
  priority_rank: number
}

export interface DimensionContribution {
  dimension: string
  segment: string
  contribution_pct: number
  segment_delta_pct?: number
  method?: string
}

export interface EvidenceItem {
  id?: string
  evidence_id?: string
  source_id: string
  source_name?: string
  entity?: string
  kind?: string
  method: string
  relevance?: number
  reliability_weight?: number
  source_reliability?: number
  confidence?: number
  summary?: string
  observation?: string
  raw_ref?: string
  timestamp?: string
  freshness_minutes?: number
  lineage?: string[]
}

export interface HypothesisItem {
  hypothesis_id: string
  mechanism_tag: string
  statement: string
  reasoning?: string
  supporting_evidence_ids: string[]
  contradictory_evidence_ids: string[]
}

export interface RuleResult {
  rule_name: string
  verdict: RuleVerdict
  rationale: string
}

export interface ScoredHypothesisItem {
  hypothesis_id: string
  support_score: number
  contradiction_score: number
  rule_score: number
  final_audit_score: number
  audit_verdict: AuditVerdict
  evidence_sufficiency_score: number
  evidence_sufficiency_level: EvidenceSufficiencyLevel
  rule_results: RuleResult[]
  narrative?: string
}

export interface StructuredActionRecommendation {
  driver: string
  controllable_lever: string
  action: string
  expected_impact: string
  owner: string
  confidence: number
  monitoring_plan: string
  authorized_personas: string[]
}

export interface DecisionPayload {
  winning_hypothesis_id?: string
  recommended_action?: string
  abstained?: boolean
  abstention_reason?: string
  verification_metric?: string
  persona_narrative?: string
  overall_verdict?: AuditVerdict
  structured_recommendation?: StructuredActionRecommendation
}

export interface OutcomeProjection {
  method?: string
  outcome_type?: string
  projected_recovery_pct?: number
  projected_metric?: string
  recovery_window_hours?: number
  mean_time_to_normalcy?: string
  assumptions?: string[]
  disclaimer?: string
}

export interface PrecedentItem {
  scenario_id: string
  summary?: string
  relevance?: number
  retrieval_score?: number
  retrieval_weight?: number
  validation_state?: "UNVALIDATED" | "VALIDATED" | "PARTIALLY_VALIDATED" | "DISPUTED" | "SUPPRESSED"
  audit_verdict?: string
  original_audit_verdict?: string
  outcome_type?: string
  winning_hypothesis?: string
  recommendation?: string
  timestamp?: string
  created_at?: string
  evidence_ids?: string
  source_ids?: string[]
  human_validated?: boolean
  validated_at?: string
  disputed_at?: string
  dispute_notes?: string
  method?: string
  similarity?: number
}

export interface TelemetryData {
  latency_ms_by_engine: Record<string, number>
  llm_calls: number
  llm_tokens_in: number
  llm_tokens_out: number
  external_cost_usd?: number
  equivalent_cloud_cost_usd?: number
  llm_provider?: string
  llm_model?: string
  rate_limit_events?: number
  retry_count?: number
}

export interface InvestigationResult {
  scenario_id: string
  persona: PersonaType
  signals: AnomalySignal[]
  materiality?: MaterialityAssessment[]
  contributions: DimensionContribution[]
  evidence: EvidenceItem[]
  hypotheses: HypothesisItem[]
  scored: ScoredHypothesisItem[]
  decision: DecisionPayload
  outcome?: OutcomeProjection
  precedents?: (PrecedentItem | string)[]
  telemetry?: TelemetryData
  method_ownership?: Record<string, string | string[]>
  investigation_id?: string
  access_denied?: boolean
  excluded_sources?: string[]
  denied_sources?: string[]
  reason?: string
}

export interface ScenarioMeta {
  id: string
  status: "live" | "evaluation_only"
  title: string
  domain: string
  type: string
  description: string
}

// ---------------------------------------------------------------------------
// Round 2 — Structured Feedback Types
// ---------------------------------------------------------------------------

export type FeedbackVerdict = "CORRECT" | "INCORRECT" | "PARTIALLY_CORRECT" | "UNSURE"

export interface StructuredFeedbackSubmission {
  investigation_id: string
  scenario_id: string
  persona?: string
  verdict: FeedbackVerdict
  corrected_hypothesis_id?: string
  corrected_audit_verdict?: string
  corrected_action?: string
  evidence_grounding_correct?: boolean
  analyst_notes?: string
}

export interface FeedbackResponse {
  success: boolean
  feedback_id?: number
  validated_precedent?: boolean
  error?: string
}

export interface FeedbackRecord {
  feedback_id: number
  investigation_id: string
  scenario_id: string
  persona: string
  verdict: FeedbackVerdict
  corrected_hypothesis_id?: string
  corrected_audit_verdict?: string
  corrected_action?: string
  evidence_grounding_correct?: boolean
  analyst_notes?: string
  validated_precedent: boolean
  validation_precedent_id?: string
  received_at: string
}

// ---------------------------------------------------------------------------
// Round 2 — Continuous Evaluation & Drift Monitoring Types
// ---------------------------------------------------------------------------

export type HealthStatusType = "HEALTHY" | "WATCH" | "DEGRADED" | "INSUFFICIENT_DATA"
export type SampleStateType = "INSUFFICIENT_DATA" | "RECENT_ONLY" | "PARTIAL_BASELINE" | "FULL_COMPARISON"

export interface MetricEvaluationItem {
  name: string
  recent_value: number | null
  baseline_value: number | null
  delta: number | null
  relative_change: number | null
  status: "HEALTHY" | "WATCH" | "DEGRADED" | "NOT_ENOUGH_FEEDBACK" | "INSUFFICIENT_E9_SAMPLE" | "NOT_EVALUABLE"
  watch_threshold: number
  degraded_threshold: number
  reason: string
}

export interface SystemHealthData {
  status: HealthStatusType
  sample_state: SampleStateType
  total_investigations: number
  recent_window_size: number
  baseline_window_size: number
  generated_at: string
  summary_reason: string
  metrics: Record<string, MetricEvaluationItem>
}

