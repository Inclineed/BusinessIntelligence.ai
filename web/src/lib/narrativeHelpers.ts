import { InvestigationResult, HypothesisItem } from "../types/investigation"
import { cleanLLMTags } from "./utils"

export interface ScenarioNarrative {
  headline: string
  story: string
  guardName: string
  operatorAction: string
  keyEvidenceHighlight?: string
  isNominal?: boolean
  isAbstained?: boolean
}

/**
 * Derives a human-grounded executive narrative for investigations 100% dynamically
 * from backend telemetry signals, deterministic audit rules, LLM reasoning,
 * and evidence observations.
 * 
 * Works dynamically across any scenario (INC_001 to INC_006+) or custom user inputs.
 */
export function getInvestigationStory(result: InvestigationResult): ScenarioNarrative {
  const isAbstained = result.decision?.abstained ?? false
  const evidence = result.evidence || []
  const signals = result.signals || []
  const hypotheses: HypothesisItem[] = result.hypotheses || []
  const scored = result.scored || []
  const primarySignal = signals[0]

  // Extract dynamic backend payload fields
  const backendNarrative = result.decision?.persona_narrative
    ? cleanLLMTags(result.decision.persona_narrative).trim()
    : ""
  const backendAction = result.decision?.recommended_action
    ? cleanLLMTags(result.decision.recommended_action).trim()
    : ""
  const backendAbstentionReason = result.decision?.abstention_reason
    ? cleanLLMTags(result.decision.abstention_reason).trim()
    : ""
  const structuredRec = result.decision?.structured_recommendation

  const winningId = result.decision?.winning_hypothesis_id || "H1"
  const topHypothesis = hypotheses.find((h) => h.hypothesis_id === winningId) || hypotheses[0]
  const topScored = scored.find((s) => s.hypothesis_id === (topHypothesis?.hypothesis_id || winningId)) || scored[0]

  // Dynamically find most relevant evidence observation
  const rootCauseEvidence = topScored?.root_cause_evidence_ids?.length
    ? evidence.find((e) => {
        const eid = e.id || e.evidence_id
        return eid && topScored.root_cause_evidence_ids?.includes(eid)
      })
    : undefined

  const topEvidence = rootCauseEvidence || evidence[0]
  const evidenceHighlight =
    topEvidence?.observation ||
    topEvidence?.summary ||
    (signals.length > 0 && signals.some((s) => s.is_anomaly)
      ? `Observed ${signals.filter((s) => s.is_anomaly).length} anomalous signal(s) across telemetry feeds.`
      : "All telemetry signals within expected historical variance bounds.")

  // 1. Nominal Healthy State (No KPI breached ±3σ corridors)
  const isNominal = signals.length > 0 && signals.every((s) => !s.is_anomaly)
  if (isNominal) {
    return {
      headline: "Nominal System Telemetry · Within Baseline Bounds",
      story:
        backendNarrative ||
        "All monitored KPI streams are fluctuating within normal statistical corridors (|z| < 3.0σ). Observed fluctuations represent standard operational variance without degradation.",
      guardName: "Corridor Bounds Check",
      operatorAction:
        backendAction ||
        structuredRec?.action ||
        "No mitigation required. Telemetry is healthy and operating within calibrated tolerance.",
      keyEvidenceHighlight: evidenceHighlight,
      isNominal: true,
      isAbstained: false,
    }
  }

  // 2. Abstention States (Safety guards or mathematical uncertainty)
  if (isAbstained) {
    const reasonLower = backendAbstentionReason.toLowerCase()

    // 2a. Governance / Unrecognized Action Lever Guard (e.g. compound or unapproved lever)
    if (
      reasonLower.includes("unrecognized lever") ||
      reasonLower.includes("lever") ||
      reasonLower.includes("governance") ||
      reasonLower.includes("policy")
    ) {
      return {
        headline: "Governance Guard Triggered · Unrecognized Action Lever",
        story:
          backendNarrative ||
          backendAbstentionReason ||
          "The system formulated an action using an unrecognized or unauthorized operational lever. Automated execution is blocked pending governance review.",
        guardName: "Governance Lever Policy Guard",
        operatorAction:
          backendAction ||
          "Submit proposed operational lever for architecture review and governance validation before manual dispatch.",
        keyEvidenceHighlight: evidenceHighlight,
        isAbstained: true,
      }
    }

    // 2b. Entitlement Scope Restriction (e.g. Manager/CFO persona restricted from infra/gateway logs)
    if (
      (result.persona === "manager" || result.persona === "cfo") &&
      evidence.length === 0 &&
      signals.some((s) => s.is_anomaly)
    ) {
      return {
        headline: `Autonomous Action Suppressed · Restricted Persona Scope (${result.persona.toUpperCase()})`,
        story:
          backendNarrative ||
          backendAbstentionReason ||
          `The ${result.persona === "manager" ? "Regional Manager" : "CFO"} persona has scoped access limited to business telemetry. Underlying payment gateway and infrastructure logs are restricted by enterprise entitlement policy, preventing causal verification from this scope.`,
        guardName: "Role Entitlement Scope Guard",
        operatorAction:
          backendAction ||
          "Switch persona to Lead Analyst (Full System Scope) to inspect restricted deployment and payment gateway evidence.",
        keyEvidenceHighlight:
          "Zero authorized evidence records available under current persona scope (restricted to inventory and order telemetry).",
        isAbstained: true,
      }
    }

    // 2c. Data Quality / Ingestion Pipeline Lag
    if (
      primarySignal?.data_quality_suspect ||
      reasonLower.includes("data quality") ||
      reasonLower.includes("etl") ||
      reasonLower.includes("ingestion")
    ) {
      return {
        headline: "Data Quality Guard Triggered · Ingestion Pipeline Delay",
        story:
          backendNarrative ||
          backendAbstentionReason ||
          "Real-world operations are proceeding normally. The observed KPI anomaly is a telemetry artifact caused by an upstream data ingestion lag, resulting in delayed batch records.",
        guardName: "Data Quality Guard (Req 3.3)",
        operatorAction:
          backendAction ||
          "Inspect ETL ingestion pipeline and message queues (Airflow/Kafka). Do not page on-call SRE or alter production software.",
        keyEvidenceHighlight: evidenceHighlight,
        isAbstained: true,
      }
    }

    // 2c. Statistical Cold-Start (Sparse History < 14 Days)
    if (
      primarySignal?.sparse_history ||
      signals.length === 0 ||
      reasonLower.includes("sparse") ||
      reasonLower.includes("cold_start")
    ) {
      return {
        headline: "Cold-Start Guard Triggered · Sparse Baseline History (< 14 Days)",
        story:
          backendNarrative ||
          backendAbstentionReason ||
          "The monitored domain has fewer than 14 intervals of historical telemetry. To prevent false-positive anomaly spikes from cold-start variance, automated corridors and hypothesis generation are suppressed.",
        guardName: "Statistical Cold-Start Guard",
        operatorAction:
          backendAction ||
          "Allow the data warehouse to accumulate at least 14 days of baseline telemetry before enabling automated ±3σ anomaly detection.",
        keyEvidenceHighlight: evidenceHighlight,
        isAbstained: true,
      }
    }

    // 2d. Multi-Causal Ambiguity / Competing Hypotheses with Narrow Margin
    if (hypotheses.length >= 2) {
      const h1Cause = hypotheses[0]?.root_cause_type
        ? hypotheses[0].root_cause_type.replace(/_/g, " ")
        : hypotheses[0]?.hypothesis_id || "H1"
      const h2Cause = hypotheses[1]?.root_cause_type
        ? hypotheses[1].root_cause_type.replace(/_/g, " ")
        : hypotheses[1]?.hypothesis_id || "H2"

      return {
        headline: `Multi-Causal Ambiguity · Competing Drivers (${h1Cause} vs ${h2Cause})`,
        story:
          backendNarrative ||
          backendAbstentionReason ||
          `Two competing explanations (${h1Cause} and ${h2Cause}) scored within a narrow margin without a dominant verified root cause. Automated dispatch is suppressed to prevent incorrect remediation.`,
        guardName: "Multi-Causal Conflict Guard",
        operatorAction:
          backendAction ||
          `Collect additional discriminative telemetry to mathematically isolate ${h1Cause} from ${h2Cause}.`,
        keyEvidenceHighlight: evidenceHighlight,
        isAbstained: true,
      }
    }

    // 2e. Single Hypothesis with Low Confidence / General Safety Guard Fallback
    const h1Cause = hypotheses[0]?.root_cause_type
      ? hypotheses[0].root_cause_type.replace(/_/g, " ")
      : hypotheses[0]?.hypothesis_id || "Candidate Explanation"
    const h1Stmt = hypotheses[0]?.statement || "proposed explanation"

    const isLowConf = reasonLower.includes("low_confidence") || reasonLower.includes("confidence")

    return {
      headline: isLowConf
        ? `Audit Guard Triggered · Insufficient Causal Confidence (${h1Cause})`
        : "Safety Guard Active · Autonomous Directive Suppressed",
      story:
        backendNarrative ||
        (isLowConf
          ? `The candidate explanation ("${h1Stmt}") did not satisfy strict deterministic verification thresholds. Grounded evidence was insufficient to mathematically corroborate the causal chain.`
          : backendAbstentionReason) ||
        "Causal evidence does not satisfy strict confidence threshold for automated action recommendation.",
      guardName: isLowConf ? "Causal Confidence Guard" : "Safety Guard Active",
      operatorAction:
        backendAction ||
        "Inspect detailed rule penalties in Stage E6 scorecard and await additional telemetry corroboration before manual intervention.",
      keyEvidenceHighlight: evidenceHighlight,
      isAbstained: true,
    }
  }

  // 3. Deterministic Operational Incident (Verified Causal Chain)
  const causeLabel = topHypothesis?.root_cause_type
    ? topHypothesis.root_cause_type.replace(/_/g, " ")
    : "Operational Defect"
  const mechanismLabel = topHypothesis?.proximal_mechanism
    ? topHypothesis.proximal_mechanism.replace(/_/g, " ")
    : topHypothesis?.statement || "System Latency"

  return {
    headline: backendAction
      ? `Verified Directive · ${backendAction}`
      : `Verified Incident · ${causeLabel} (${mechanismLabel})`,
    story:
      backendNarrative ||
      topScored?.narrative ||
      topHypothesis?.statement ||
      `A deterministic causal chain has been audited: ${causeLabel} in ${topHypothesis?.affected_subsystem || "subsystem"} induced observed ${mechanismLabel}.`,
    guardName: "Root-Cause Gate Verified",
    operatorAction:
      backendAction ||
      structuredRec?.action ||
      `Dispatch governed mitigation to resolve ${mechanismLabel} in ${topHypothesis?.affected_subsystem || "impacted system"}.`,
    keyEvidenceHighlight: evidenceHighlight,
    isAbstained: false,
  }
}
