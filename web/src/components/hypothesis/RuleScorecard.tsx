import React from "react"
import { RuleResult, ScoredHypothesisItem, HypothesisItem } from "../../types/investigation"
import {
  Check,
  X,
  AlertTriangle,
  Minus,
  ShieldCheck,
  GitCommit,
  ShieldAlert,
  Layers,
  Lock,
} from "lucide-react"

interface RuleScorecardProps {
  ruleResults: RuleResult[]
  scoredHypothesis?: ScoredHypothesisItem
  hypothesis?: HypothesisItem
}

export const RuleScorecard: React.FC<RuleScorecardProps> = ({
  ruleResults,
  scoredHypothesis,
  hypothesis,
}) => {
  if (!ruleResults || ruleResults.length === 0) {
    return null
  }

  const getVerdictBadge = (verdict: string) => {
    switch (verdict.toLowerCase()) {
      case "pass":
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-mono font-bold text-[#78AC91] px-2 py-0.5 rounded bg-[#4E8569]/20 border border-[#4E8569]/40">
            <Check className="w-3 h-3" /> PASS
          </span>
        )
      case "partial":
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-mono font-bold text-[#6B9BB0] px-2 py-0.5 rounded bg-[#6B9BB0]/20 border border-[#6B9BB0]/40">
            <AlertTriangle className="w-3 h-3" /> PARTIAL
          </span>
        )
      case "fail":
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-mono font-bold text-[#E56B62] px-2 py-0.5 rounded bg-[#D8453A]/20 border border-[#D8453A]/40">
            <X className="w-3 h-3" /> FAIL
          </span>
        )
      default:
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-mono text-[#9E9788] px-2 py-0.5 rounded bg-[#222222] border border-[#333333]">
            <Minus className="w-3 h-3" /> NOMINAL
          </span>
        )
    }
  }

  // Root-cause gate evaluation
  const rootCauseType = hypothesis?.root_cause_type || "UNKNOWN"
  const gatePassed = scoredHypothesis?.root_cause_gate_passed ?? true
  const gateEvidenceIds = scoredHypothesis?.root_cause_evidence_ids || []
  const gateRationale =
    scoredHypothesis?.root_cause_rationale ||
    (gatePassed
      ? "Sufficient discriminative evidence verified for root-cause claim."
      : "Discriminative evidence missing for claimed root cause. Capped at MARGINAL.")

  const isSpecificRootCause =
    rootCauseType === "INTERNAL_RELEASE" ||
    rootCauseType === "EXTERNAL_PROVIDER" ||
    rootCauseType === "INVENTORY_SHORTAGE" ||
    rootCauseType === "RESOURCE_EXHAUSTION" ||
    rootCauseType === "MACRO_EXTERNAL"

  return (
    <div className="space-y-3 pt-2 border-t border-[#2E2E2E]">
      {/* ── Root-Cause Evidence Gate Banner ─────────────────────────────── */}
      <div
        className={`p-3.5 rounded-xl border text-xs font-mono transition-all ${
          gatePassed
            ? "bg-[#18221E] border-[#4E8569]/40 text-[#D1C9B8]"
            : "bg-[#251A1A] border-[#D8453A]/40 text-[#E56B62]"
        }`}
      >
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-white/[0.06] pb-2 mb-2">
          <div className="flex items-center gap-2">
            <ShieldCheck
              className={`w-4 h-4 ${
                gatePassed ? "text-[#4E8569]" : "text-[#D8453A]"
              }`}
            />
            <span className="font-bold text-[#F4EEE0] uppercase tracking-wider text-[11px]">
              Root-Cause Evidence Gate
            </span>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-black/40 text-[#9E9788] border border-[#333333]">
              {rootCauseType.replace(/_/g, " ").toUpperCase()}
            </span>
          </div>

          <div className="flex items-center gap-2">
            {gatePassed ? (
              <span className="inline-flex items-center gap-1 text-[10px] font-bold text-[#78AC91] px-2 py-0.5 rounded bg-[#4E8569]/20 border border-[#4E8569]/40">
                <Check className="w-3 h-3" /> GATE PASSED
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-[10px] font-bold text-[#E56B62] px-2 py-0.5 rounded bg-[#D8453A]/20 border border-[#D8453A]/40">
                <X className="w-3 h-3" /> GATE FAILED (CAPPED AT MARGINAL)
              </span>
            )}
          </div>
        </div>

        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 text-xs">
          <div className="space-y-1 flex-1">
            <div className="text-[11px] text-[#D1C9B8] font-sans leading-relaxed">
              {gateRationale}
            </div>
            {!gatePassed && (
              <div className="text-[10px] text-[#E56B62] font-mono flex items-center gap-1 mt-1">
                <ShieldAlert className="w-3.5 h-3.5" />
                <span>
                  Telemetry alone cannot satisfy INTERNAL_RELEASE or EXTERNAL_PROVIDER claims without direct release/provider evidence records.
                </span>
              </div>
            )}
          </div>

          {gateEvidenceIds.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap shrink-0">
              <span className="text-[10px] text-[#9E9788] uppercase">
                Grounded Records:
              </span>
              {gateEvidenceIds.map((id) => (
                <span
                  key={id}
                  className="px-1.5 py-0.5 rounded bg-[#181818] border border-[#333333] text-[#6B9BB0] font-bold text-[10px]"
                >
                  {id}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── 5-Rule Deterministic Matrix ─────────────────────────────────── */}
      <div className="space-y-1.5">
        {/* Column Headers */}
        <div className="grid grid-cols-12 gap-3 px-3 py-1.5 text-[10px] font-mono font-bold uppercase text-[#9E9788] border-b border-[#2E2E2E]">
          <div className="col-span-3">Deterministic Rule</div>
          <div className="col-span-2">Verdict</div>
          <div className="col-span-2">Penalty Impact</div>
          <div className="col-span-5">Verification Rationale</div>
        </div>

        {/* Structured Rule Rows */}
        <div className="space-y-1.5">
          {ruleResults.map((rule) => {
            const isFail = rule.verdict.toLowerCase() === "fail"
            const isPartial = rule.verdict.toLowerCase() === "partial"

            return (
              <div
                key={rule.rule_name}
                className={`grid grid-cols-12 gap-3 px-3 py-2.5 rounded-xl border items-center text-xs font-mono transition-colors ${
                  isFail
                    ? "bg-[#252020] border-[#D8453A]/35"
                    : isPartial
                    ? "bg-[#202528] border-[#6B9BB0]/35"
                    : "bg-[#222222] border-[#333333]"
                }`}
              >
                {/* Column 1: Rule Name (Full, unclipped) */}
                <div className="col-span-3 font-bold text-[#F4EEE0] flex items-center gap-1.5 truncate">
                  <span>{rule.rule_name.replace(/_/g, " ")}</span>
                </div>

                {/* Column 2: Verdict Badge */}
                <div className="col-span-2">
                  {getVerdictBadge(rule.verdict)}
                </div>

                {/* Column 3: Penalty Impact */}
                <div className="col-span-2 text-[11px] font-bold">
                  {isFail ? (
                    <span className="text-[#E56B62]">-25% to -35%</span>
                  ) : isPartial ? (
                    <span className="text-[#6B9BB0]">-10% penalty</span>
                  ) : (
                    <span className="text-[#78AC91]">0% (Passed)</span>
                  )}
                </div>

                {/* Column 4: Verification Rationale (Full text) */}
                <div className="col-span-5 text-xs text-[#D1C9B8] font-sans leading-relaxed">
                  {rule.rationale || "Verified against deterministic constraint engine."}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
