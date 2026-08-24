export type PersonaType = "analyst" | "cfo" | "manager"
export type ConfidenceState = "HIGH" | "MEDIUM" | "LOW" | "ABSTAIN"
export type RuleVerdict = "pass" | "partial" | "fail" | "n/a"

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

export interface DimensionContribution {
  dimension: string
  segment: string
  contribution_pct: number
  segment_delta_pct?: number
  method?: string
}

export interface EvidenceItem {
  evidence_id: string
  source_id: string
  kind?: string
  method: string
  relevance: number
  reliability_weight: number
  summary: string
  raw_ref?: string
  timestamp?: string
}

export interface HypothesisItem {
  hypothesis_id: string
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
  contradiction_penalty: number
  final_score: number
  confidence_state: ConfidenceState
  rule_results: RuleResult[]
  narrative?: string
}

export interface DecisionPayload {
  winning_hypothesis_id?: string
  recommended_action?: string
  abstained?: boolean
  abstention_reason?: string
  verification_metric?: string
  persona_narrative?: string
}

export interface OutcomeProjection {
  method?: string
  outcome_type?: string
  projected_recovery_pct?: number
  projected_metric?: string
  disclaimer?: string
}

export interface PrecedentItem {
  scenario_id: string
  summary?: string
  relevance?: number
  retrieval_score?: number
  retrieval_weight?: number
  confidence_state?: string
  original_confidence_state?: string
  outcome_type?: string
  winning_hypothesis?: string
  recommendation?: string
  timestamp?: string
  created_at?: string
  evidence_ids?: string
  source_ids?: string[]
  human_validated?: boolean
  validated_at?: string
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
}

export interface InvestigationResult {
  scenario_id: string
  persona: PersonaType
  signals: AnomalySignal[]
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
  corrected_confidence_state?: string
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
  corrected_confidence_state?: string
  corrected_action?: string
  evidence_grounding_correct?: boolean
  analyst_notes?: string
  validated_precedent: boolean
  validation_precedent_id?: string
  received_at: string
}
