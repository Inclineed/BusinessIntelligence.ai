import React from "react"
import { CheckCircle2, ShieldAlert, Sparkles, Award } from "lucide-react"
import { InvestigationResult } from "../../types/investigation"
import { cleanLLMTags, cn } from "../../lib/utils"
import { RuleVerdictMatrix } from "./RuleVerdictMatrix"
import { SupportPenaltyChart } from "./SupportPenaltyChart"

interface HypothesisStudioProps {
  result: InvestigationResult
  onOpenEvidenceDrawer?: (evidenceId: string) => void
}

export const HypothesisStudio: React.FC<HypothesisStudioProps> = ({ result, onOpenEvidenceDrawer }) => {
  const { hypotheses = [], scored = [], decision = {} } = result
  const winnerId = decision.winning_hypothesis_id
  const abstained = Boolean(decision.abstained)

  if (!hypotheses || hypotheses.length === 0) {
    return (
      <div className="p-8 rounded-lg bg-surface border border-hairline text-center text-muted-foreground text-xs">
        No causal hypotheses generated for this scenario.
      </div>
    )
  }

  const scoredMap = new Map(scored.map((s) => [s.hypothesis_id, s]))
  const sortedHypotheses = [...hypotheses].sort((a, b) => {
    const scoreA = scoredMap.get(a.hypothesis_id)?.final_audit_score || 0
    const scoreB = scoredMap.get(b.hypothesis_id)?.final_audit_score || 0
    return scoreB - scoreA
  })

  // Render citation chips
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
            className="inline-flex items-center gap-1 mx-1 px-1.5 py-0.5 rounded bg-surface-hover border border-hairline-bright text-semantic-neutral font-mono text-[11px] font-semibold hover:bg-blue-900/40 hover:border-semantic-neutral transition-all shadow-sm"
            title={`Inspect evidence artifact ${eid}`}
          >
            ◈ {eid}
          </button>
        )
      }
      return <span key={index}>{part}</span>
    })
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-sm font-mono font-bold uppercase tracking-wider text-white flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-semantic-neutral" />
          Hypothesis Studio & Multi-Causal Falsification
        </h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Candidate explanations synthesized from empirical evidence and rigorously evaluated by deterministic challenge rules.
        </p>
      </div>

      {/* Hypothesis Cards List */}
      <div className="space-y-3.5">
        {sortedHypotheses.map((hyp) => {
          const hid = hyp.hypothesis_id
          const sh = scoredMap.get(hid)
          const isWinner = hid === winnerId && !abstained
          const score = sh?.final_audit_score || 0
          const support = sh?.support_score || 0
          const penalty = sh?.contradiction_score || 0
          const conf = (sh?.audit_verdict || "REJECTED").toUpperCase()
          const cleanStmt = cleanLLMTags(hyp.statement)

          let confColor = "text-semantic-positive bg-semantic-positive-bg border-semantic-positive-border"
          if (conf === "MARGINAL") {
            confColor = "text-semantic-warning bg-semantic-warning-bg border-semantic-warning-border"
          } else if (conf === "REJECTED") {
            confColor = "text-semantic-critical bg-semantic-critical-bg border-semantic-critical-border"
          }

          return (
            <div
              key={hid}
              className={cn(
                "rounded-lg p-5 bg-surface border transition-all duration-150 shadow-card",
                isWinner
                  ? "border-semantic-positive-border bg-gradient-to-r from-surface to-semantic-positive-bg/20 shadow-glow-positive"
                  : "border-hairline hover:border-hairline-bright"
              )}
            >
              <div className="flex flex-wrap items-center justify-between gap-3 mb-2.5">
                <div className="flex items-center gap-2.5">
                  <span className="font-mono text-sm font-bold text-white bg-surface-raised px-2 py-0.5 rounded border border-hairline">
                    {hid}
                  </span>
                  {isWinner && (
                    <span className="px-2.5 py-0.5 rounded text-[11px] font-mono font-bold bg-semantic-positive-bg text-semantic-positive border border-semantic-positive-border flex items-center gap-1.5 shadow-sm">
                      <Award className="w-3.5 h-3.5" /> WINNING HYPOTHESIS
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-4 font-mono text-xs">
                  <span className="text-muted-foreground">
                    Support: <b className="text-semantic-positive">+{support.toFixed(2)}</b>
                  </span>
                  <span className="text-muted-foreground">
                    Penalty: <b className={penalty > 0 ? "text-semantic-critical" : "text-muted-foreground"}>-{penalty.toFixed(2)}</b>
                  </span>
                  <span className={cn("px-2.5 py-0.5 rounded font-bold border", confColor)}>
                    {conf} ({score.toFixed(2)})
                  </span>
                </div>
              </div>

              {/* Statement with interactive citations */}
              <p className="text-xs sm:text-sm font-medium text-foreground leading-relaxed mb-3">
                {renderInteractiveStatement(cleanStmt)}
              </p>

              {/* Evidence Utilization Summary */}
              <div className="flex flex-wrap items-center justify-between text-[11px] pt-3 border-t border-hairline-subtle text-muted-foreground font-mono">
                <div className="flex items-center gap-3">
                  <span>Supporting Artifacts: <b className="text-foreground">{hyp.supporting_evidence_ids?.length || 0}</b></span>
                  <span>Contradictory Artifacts: <b className="text-foreground">{hyp.contradictory_evidence_ids?.length || 0}</b></span>
                </div>
                <div className="text-[10px] text-muted-foreground">
                  RULES ENGINE · DETERMINISTIC SCORING
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Side by Side: Verdict Matrix & Support vs Penalty */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 pt-2">
        <div className="p-5 rounded-lg bg-surface border border-hairline shadow-card">
          <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-white mb-3">
            Falsification Rule Verdict Matrix
          </h3>
          <RuleVerdictMatrix scored={scored} />
        </div>

        <div className="p-5 rounded-lg bg-surface border border-hairline shadow-card">
          <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-white mb-3">
            Evidentiary Support vs Contradiction Subtraction
          </h3>
          <SupportPenaltyChart scored={scored} />
        </div>
      </div>
    </div>
  )
}
