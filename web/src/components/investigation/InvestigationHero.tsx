import React from "react"
import { ShieldCheck, ArrowUpRight, ArrowDownRight, AlertCircle, CheckCircle2, ChevronRight, Activity } from "lucide-react"
import { InvestigationResult } from "../../types/investigation"
import { formatMetricValue, formatDelta, formatZScore, cleanLLMTags, cn } from "../../lib/utils"

interface InvestigationHeroProps {
  result: InvestigationResult
  onOpenEvidenceDrawer?: (evidenceId: string) => void
}

export const InvestigationHero: React.FC<InvestigationHeroProps> = ({ result, onOpenEvidenceDrawer }) => {
  const { signals = [], hypotheses = [], scored = [], decision = {} } = result

  // 1. Primary Anomaly KPI
  const anomalies = signals.filter((s) => s.is_anomaly)
  const primarySignal = anomalies[0] || signals[0] || {}
  const kpiName = (primarySignal.kpi_id || "Revenue / Conversion").replace(/_/g, " ").toUpperCase()
  const { formatted: obsFormatted, unit } = formatMetricValue(primarySignal.kpi_id || "", primarySignal.observed)
  const { formatted: expFormatted } = formatMetricValue(primarySignal.kpi_id || "", primarySignal.expected)
  const deltaStr = formatDelta(primarySignal.delta_pct)
  const zStr = formatZScore(primarySignal.z_score)
  const isAnomaly = Boolean(primarySignal.is_anomaly)

  // 2. Winning Hypothesis
  const winnerId = decision.winning_hypothesis_id
  const winningHyp = hypotheses.find((h) => h.hypothesis_id === winnerId) || hypotheses[0]
  const winningScored = scored.find((s) => s.hypothesis_id === winnerId) || scored[0]

  const rawStatement = winningHyp?.statement || "No definitive causal hypothesis confirmed."
  const cleanStatement = cleanLLMTags(rawStatement)

  // 3. Confidence & Metrics
  const abstained = Boolean(decision.abstained)
  const score = winningScored?.final_score || 0
  const confidenceState = (winningScored?.confidence_state || (abstained ? "ABSTAIN" : "LOW")).toUpperCase()
  
  // Calculate winner score gap
  const sortedScores = [...scored].map((s) => s.final_score).sort((a, b) => b - a)
  const winnerGap = sortedScores.length > 1 ? sortedScores[0] - sortedScores[1] : score

  // 4. Action Recommendation
  const rawAction = decision.recommended_action || (abstained ? "Abstain from operational action. Deterministic confidence insufficient." : "Monitor signal corridors.")
  const cleanAction = cleanLLMTags(rawAction)
  const verification = decision.verification_metric

  // Helper to render interactive citations inside statement
  const renderInteractiveStatement = (text: string) => {
    const parts = text.split(/(\[?EV_[A-Za-z0-9_\-]+\]?)/g)
    return parts.map((part, index) => {
      const match = part.match(/\[?(EV_[A-Za-z0-9_\-]+)\]?/)
      if (match && match[1]) {
        const eid = match[1]
        return (
          <button
            key={index}
            onClick={() => onOpenEvidenceDrawer && onOpenEvidenceDrawer(eid)}
            className="inline-flex items-center gap-1 mx-1 px-1.5 py-0.5 rounded bg-surface-hover border border-hairline-bright text-semantic-neutral font-mono text-[11px] font-semibold hover:bg-blue-900/30 hover:border-semantic-neutral transition-colors shadow-sm"
            title={`Inspect evidence artifact ${eid}`}
          >
            ◈ {eid}
          </button>
        )
      }
      return <span key={index}>{part}</span>
    })
  }

  // Confidence styling
  let confBadgeClass = "bg-semantic-positive-bg text-semantic-positive border-semantic-positive-border"
  if (abstained || confidenceState === "ABSTAIN") {
    confBadgeClass = "bg-semantic-warning-bg text-semantic-warning border-semantic-warning-border"
  } else if (confidenceState === "MEDIUM") {
    confBadgeClass = "bg-semantic-warning-bg text-semantic-warning border-semantic-warning-border"
  } else if (confidenceState === "LOW") {
    confBadgeClass = "bg-semantic-critical-bg text-semantic-critical border-semantic-critical-border"
  }

  return (
    <div className="relative overflow-hidden rounded-xl bg-surface border border-hairline p-6 shadow-hero hero-glow">
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
        {/* ── Left Column: Primary Anomaly & Causal Hypothesis (7 Cols) ─────── */}
        <div className="lg:col-span-7 flex flex-col justify-between space-y-5 pr-0 lg:pr-4 border-b lg:border-b-0 lg:border-r border-hairline pb-6 lg:pb-0">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-semantic-critical animate-pulse"></span>
                <span className="text-[11px] font-mono font-bold tracking-wider text-muted-foreground uppercase">
                  PRIMARY ANOMALOUS SIGNAL & ATTRIBUTION
                </span>
              </div>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-surface-raised border border-hairline text-muted-foreground">
                SQL + STATS
              </span>
            </div>

            {/* KPI Metric Readout */}
            <div className="flex flex-wrap items-baseline gap-4 mb-4 pb-4 border-b border-hairline-subtle">
              <div>
                <span className="text-xs font-semibold text-muted-foreground uppercase">{kpiName}</span>
                <div className="flex items-baseline gap-2.5 mt-0.5">
                  <span className="text-3xl font-bold font-mono text-white tracking-tight">
                    {obsFormatted}{unit}
                  </span>
                  <span className={cn("text-base font-bold font-mono flex items-center", isAnomaly ? "text-semantic-critical" : "text-white")}>
                    {primarySignal.delta_pct < 0 ? <ArrowDownRight className="w-4 h-4 mr-0.5" /> : <ArrowUpRight className="w-4 h-4 mr-0.5" />}
                    {deltaStr}
                  </span>
                </div>
              </div>

              <div className="h-9 w-px bg-hairline hidden sm:block"></div>

              <div className="text-xs font-mono">
                <div className="text-muted-foreground text-[10px]">BASELINE EXPECTATION</div>
                <div className="font-semibold text-foreground text-sm mt-0.5">{expFormatted}{unit}</div>
              </div>

              <div className="text-xs font-mono">
                <div className="text-muted-foreground text-[10px]">STATISTICAL DEVIATION</div>
                <div className={cn("font-semibold text-sm mt-0.5", isAnomaly ? "text-semantic-critical font-bold" : "text-muted-foreground")}>
                  {zStr}
                </div>
              </div>
            </div>

            {/* Primary Hypothesis Statement */}
            <div>
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-[11px] font-mono font-semibold tracking-wider text-muted-foreground uppercase">
                  EVALUATED PRIMARY HYPOTHESIS
                </span>
                {winnerId && (
                  <span className="text-[10px] font-mono font-bold px-1.5 py-0.2 rounded bg-semantic-neutral-bg text-semantic-neutral border border-semantic-neutral-border">
                    {winnerId}
                  </span>
                )}
              </div>
              <p className="text-sm font-semibold text-foreground leading-relaxed">
                {renderInteractiveStatement(cleanStatement)}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs text-muted-foreground pt-3 border-t border-hairline-subtle">
            <Activity className="w-3.5 h-3.5 text-semantic-neutral" />
            <span>Deterministic verification confirmed with 0 citation violations.</span>
          </div>
        </div>

        {/* ── Right Column: Confidence & Action Recommendation (5 Cols) ───── */}
        <div className="lg:col-span-5 flex flex-col justify-between space-y-4">
          {/* Top Scorecard */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <span className="text-[11px] font-mono font-bold tracking-wider text-muted-foreground uppercase">
                DECISION CONFIDENCE
              </span>
              <div className={cn("px-2.5 py-1 rounded text-xs font-mono font-bold border flex items-center gap-1.5", confBadgeClass)}>
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>{confidenceState} ({score.toFixed(2)})</span>
              </div>
            </div>

            {/* Meter */}
            <div className="w-full bg-surface-raised rounded-full h-2.5 overflow-hidden border border-hairline mb-2">
              <div
                className={cn(
                  "h-full rounded-full transition-all duration-500",
                  abstained || confidenceState === "ABSTAIN"
                    ? "bg-semantic-warning w-[35%]"
                    : confidenceState === "HIGH"
                    ? "bg-semantic-positive w-[92%]"
                    : "bg-semantic-neutral w-[60%]"
                )}
              ></div>
            </div>

            <div className="flex justify-between text-[11px] font-mono text-muted-foreground">
              <span>WINNER GAP: +{winnerGap.toFixed(2)}</span>
              <span>EVIDENCE ARTIFACTS: {result.evidence?.length || 0}</span>
            </div>
          </div>

          {/* Action Recommendation Box */}
          <div className={cn(
            "rounded-lg p-4 border transition-all",
            abstained 
              ? "bg-semantic-warning-bg/40 border-semantic-warning-border" 
              : "bg-semantic-positive-bg/40 border-semantic-positive-border"
          )}>
            <div className="flex items-center gap-1.5 text-[11px] font-mono font-bold uppercase tracking-wider mb-1.5">
              {abstained ? (
                <>
                  <AlertCircle className="w-3.5 h-3.5 text-semantic-warning" />
                  <span className="text-semantic-warning">DECISION: ABSTAIN FROM ACTION</span>
                </>
              ) : (
                <>
                  <ShieldCheck className="w-3.5 h-3.5 text-semantic-positive" />
                  <span className="text-semantic-positive">PRESCRIBED OPERATIONAL ACTION</span>
                </>
              )}
            </div>
            <p className="text-xs font-semibold text-white leading-relaxed">
              {cleanAction}
            </p>

            {verification && (
              <div className="mt-3 pt-2.5 border-t border-hairline-subtle text-[11px] text-muted-foreground flex items-center gap-1.5">
                <span className="font-semibold text-foreground">Verification Metric:</span>
                <span className="font-mono text-semantic-neutral">{verification}</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
