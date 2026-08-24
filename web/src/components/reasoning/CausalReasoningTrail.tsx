import React from "react"
import { InvestigationResult } from "../../types/investigation"
import { DimensionalAttributionChart } from "./DimensionalAttributionChart"

interface CausalReasoningTrailProps {
  result: InvestigationResult
}

export const CausalReasoningTrail: React.FC<CausalReasoningTrailProps> = ({ result }) => {
  const { signals = [], contributions = [], evidence = [], scored = [], decision = {} } = result

  const anomalies = signals.filter((s) => s.is_anomaly)
  const primarySignal = anomalies[0] || signals[0] || {}
  const kpiName = (primarySignal.kpi_id || "KPI").replace(/_/g, " ").toUpperCase()
  const delta = primarySignal.delta_pct || 0

  const winnerId = decision.winning_hypothesis_id
  const winningScored = scored.find((s) => s.hypothesis_id === winnerId)
  const confState = (winningScored?.confidence_state || (decision.abstained ? "ABSTAIN" : "LOW")).toUpperCase()
  const finalScore = winningScored?.final_score || 0

  const steps = [
    {
      num: "01",
      title: "ANOMALY ISOLATION",
      tag: "E2 SIGNAL ENGINE",
      summary: `Detected abnormal variance in ${kpiName} (${delta > 0 ? "+" : ""}${delta.toFixed(1)}% shock).`,
      status: anomalies.length > 0 ? "CONFIRMED" : "NOMINAL",
      statusColor: anomalies.length > 0 ? "text-semantic-critical border-semantic-critical-border bg-semantic-critical-bg" : "text-muted-foreground border-hairline bg-surface-raised",
    },
    {
      num: "02",
      title: "DIMENSIONAL LOCALIZATION",
      tag: "E3 DIAGNOSTIC ENGINE",
      summary: contributions.length > 0 
        ? `Identified ${contributions.length} contributing segments across device and channel dimensions.`
        : "Variance is uniformly distributed across platform segments.",
      status: contributions.length > 0 ? "LOCALIZED" : "UNIFORM",
      statusColor: "text-semantic-neutral border-semantic-neutral-border bg-semantic-neutral-bg",
    },
    {
      num: "03",
      title: "EVIDENCE RETRIEVAL",
      tag: "E4 EVIDENCE ASSEMBLY",
      summary: `Assembled ${evidence.length} authorized telemetry records under strict pre-retrieval boundary.`,
      status: "AUTHENTICATED",
      statusColor: "text-semantic-warning border-semantic-warning-border bg-semantic-warning-bg",
    },
    {
      num: "04",
      title: "HYPOTHESIS CHALLENGE",
      tag: "E6 CHALLENGE RULES",
      summary: "Tested candidate mechanisms against 5 deterministic falsification criteria.",
      status: "VERIFIED",
      statusColor: "text-semantic-positive border-semantic-positive-border bg-semantic-positive-bg",
    },
    {
      num: "05",
      title: "PRESCRIPTIVE ACTION",
      tag: "E7 DECISION ENGINE",
      summary: `Prescribed operational action with ${confState} confidence (${finalScore.toFixed(2)}).`,
      status: decision.abstained ? "ABSTAINED" : "RESOLVED",
      statusColor: decision.abstained 
        ? "text-semantic-warning border-semantic-warning-border bg-semantic-warning-bg" 
        : "text-semantic-positive border-semantic-positive-border bg-semantic-positive-bg",
    },
  ]

  return (
    <div className="space-y-6">
      {/* 5-Step Storyboard Flow */}
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-3.5">
        {steps.map((step) => (
          <div
            key={step.num}
            className="p-4 rounded-lg bg-surface border border-hairline shadow-card flex flex-col justify-between"
          >
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="font-mono text-xs font-bold text-muted-foreground">{step.num}</span>
                <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border ${step.statusColor}`}>
                  {step.status}
                </span>
              </div>
              <div className="font-mono text-[11px] font-bold tracking-wider text-white mb-0.5">
                {step.title}
              </div>
              <div className="text-[10px] font-mono text-muted-foreground mb-2">{step.tag}</div>
              <p className="text-xs text-muted-foreground leading-relaxed">{step.summary}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Dimensional Attribution Section */}
      {contributions.length > 0 && (
        <div className="p-5 rounded-lg bg-surface border border-hairline shadow-card">
          <div className="flex justify-between items-center mb-2">
            <div>
              <h2 className="text-xs font-mono font-bold uppercase tracking-wider text-white">
                Dimensional Variance Attribution
              </h2>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                Apportionment of total KPI shock across breakdown dimensions.
              </p>
            </div>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-surface-raised border border-hairline text-muted-foreground">
              SQL + STATS
            </span>
          </div>

          <DimensionalAttributionChart contributions={contributions} />
        </div>
      )}
    </div>
  )
}
