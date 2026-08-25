import React from "react"
import { RuleResult } from "../../types/investigation"
import { Check, X, AlertTriangle, Minus, ShieldCheck } from "lucide-react"

interface RuleScorecardProps {
  ruleResults: RuleResult[]
}

const CANONICAL_RULES = [
  { key: "timeline", name: "Timeline Precedence" },
  { key: "segment_alignment", name: "Segment Alignment" },
  { key: "kpi_corroboration", name: "KPI Corroboration" },
  { key: "mechanism_consistency", name: "Mechanism Consistency" },
  { key: "contradiction", name: "Contradiction Guard" },
]

export const RuleScorecard: React.FC<RuleScorecardProps> = ({ ruleResults }) => {
  if (!ruleResults || ruleResults.length === 0) {
    return null
  }

  // Create a map from results for easy canonical rule lookup
  const resultMap = new Map<string, RuleResult>()
  ruleResults.forEach((r) => {
    const normKey = r.rule_name.toLowerCase().replace(/\s+/g, "_")
    resultMap.set(normKey, r)
  })

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

  return (
    <div className="space-y-2 pt-2 border-t border-[#2E2E2E]">
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
  )
}
