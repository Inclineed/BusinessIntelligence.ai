import React from "react"
import { HypothesisItem, ScoredHypothesisItem, AuditVerdict } from "../../types/investigation"
import { RuleScorecard } from "./RuleScorecard"
import { Sparkles, Scale, CheckCircle2, AlertTriangle, ShieldAlert, Award } from "lucide-react"

interface HypothesisMatrixProps {
  hypotheses: HypothesisItem[]
  scoredHypotheses: ScoredHypothesisItem[]
  winningHypothesisId?: string
}

export const HypothesisMatrix: React.FC<HypothesisMatrixProps> = ({
  hypotheses,
  scoredHypotheses,
  winningHypothesisId,
}) => {
  if (!scoredHypotheses || scoredHypotheses.length === 0) {
    return (
      <div className="glass-panel p-6 rounded-xl border border-white/[0.08] text-center">
        <Sparkles className="w-8 h-8 text-neutral-500 mx-auto mb-2" />
        <div className="text-sm font-medium text-neutral-300">No Hypotheses Evaluated</div>
        <div className="text-xs text-neutral-400">Zero candidate hypotheses were generated or evaluated for this scenario slice.</div>
      </div>
    )
  }

  // Build lookup map of raw statement by hypothesis_id
  const statementMap = new Map(hypotheses.map((h) => [h.hypothesis_id, h]))

  const getConfidenceBadge = (confidence: AuditVerdict) => {
    switch (confidence) {
      case "VERIFIED":
        return (
          <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
            HIGH CONFIDENCE
          </span>
        )
      case "MARGINAL":
        return (
          <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30">
            MEDIUM CONFIDENCE
          </span>
        )
      case "REJECTED":
        return (
          <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-red-500/15 text-red-400 border border-red-500/30">
            LOW CONFIDENCE
          </span>
        )
      case "ABSTAIN":
        return (
          <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-neutral-800 text-neutral-400 border border-neutral-700">
            ABSTAIN
          </span>
        )
    }
  }

  return (
    <div className="glass-panel p-4 rounded-xl border border-white/[0.08] space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center">
            <Scale className="w-3.5 h-3.5 text-emerald-400" />
          </div>
          <div>
            <div className="text-xs font-mono font-bold text-neutral-200 uppercase tracking-wider">
              [E5 + E6] Competing Hypotheses & 5-Rule Challenge Scorecard
            </div>
            <div className="text-[11px] font-mono text-neutral-400">
              Deterministic 5-Rule Verification (Timeline, Mechanism, Segment, Corroboration, Contradiction)
            </div>
          </div>
        </div>
        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-black/40 text-neutral-400 border border-white/[0.06]">
          [LLM + RULES]
        </span>
      </div>

      {/* Hypothesis Cards */}
      <div className="space-y-3">
        {scoredHypotheses.map((sh, idx) => {
          const raw = statementMap.get(sh.hypothesis_id)
          const isWinning = sh.hypothesis_id === winningHypothesisId
          const finalScorePct = Math.round(sh.final_audit_score * 100)

          return (
            <div
              key={sh.hypothesis_id}
              className={`p-4 rounded-xl border transition-all ${
                isWinning
                  ? "bg-emerald-500/[0.04] border-emerald-500/30 shadow-card"
                  : "bg-surface border-border"
              }`}
            >
              {/* Card Header */}
              <div className="flex items-center justify-between gap-2 mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-mono font-bold text-white px-2 py-0.5 rounded bg-black/50 border border-white/10">
                    {sh.hypothesis_id}
                  </span>
                  {isWinning && (
                    <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 flex items-center gap-1">
                      <Award className="w-3 h-3 text-emerald-400" />
                      WINNING HYPOTHESIS
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  {getConfidenceBadge(sh.audit_verdict)}
                  <div className="text-right">
                    <span className="text-xs font-mono font-bold text-neutral-200 tabular-nums">
                      {finalScorePct}%
                    </span>
                    <span className="text-[10px] font-mono text-neutral-400 ml-1">Score</span>
                  </div>
                </div>
              </div>

              {/* Qualitative Statement (LLM) */}
              <div className="text-sm font-medium text-neutral-200 mb-2 leading-relaxed font-sans">
                {raw?.statement || "Hypothesis statement under evaluation."}
              </div>

              {/* Rationale narrative */}
              {sh.narrative && (
                <div className="p-2.5 rounded-lg bg-black/40 border border-white/[0.04] text-xs text-neutral-300 font-sans leading-relaxed mb-3">
                  <span className="text-[10px] font-mono text-neutral-400 uppercase font-bold mr-1.5">
                    Evaluator Rationale:
                  </span>
                  {sh.narrative}
                </div>
              )}

              {/* Scores breakdown: Support vs Contradiction */}
              <div className="flex items-center gap-4 text-xs font-mono text-neutral-400 mb-2">
                <div>
                  <span>Support Score: </span>
                  <span className="font-bold text-emerald-400 tabular-nums">
                    {Math.min(100, Math.round(sh.support_score * 100))}%
                  </span>
                </div>
                {sh.contradiction_score > 0 && (
                  <div>
                    <span>Contradiction Penalty: </span>
                    <span className="font-bold text-red-400 tabular-nums">
                      -{Math.min(100, Math.round(sh.contradiction_score * 100))}%
                    </span>
                  </div>
                )}
              </div>

              {/* 5-Rule Verdict Matrix */}
              <RuleScorecard ruleResults={sh.rule_results} />
            </div>
          )
        })}
      </div>
    </div>
  )
}
