import React from "react"
import { ScoredHypothesisItem, RuleResult } from "../../types/investigation"

interface RuleVerdictMatrixProps {
  scored: ScoredHypothesisItem[]
}

const RULES = [
  { key: "timeline", name: "Timeline", short: "TIM" },
  { key: "segment_alignment", name: "Segment Alignment", short: "SEG" },
  { key: "kpi_corroboration", name: "KPI Corroboration", short: "COR" },
  { key: "mechanism_consistency", name: "Mechanism Consistency", short: "MEC" },
  { key: "contradiction", name: "Contradiction Check", short: "CON" },
]

export const RuleVerdictMatrix: React.FC<RuleVerdictMatrixProps> = ({ scored }) => {
  if (!scored || scored.length === 0) return null

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs font-mono text-left">
        <thead>
          <tr className="border-b border-hairline text-muted-foreground text-[10px] uppercase">
            <th className="py-2.5 px-3">Hypothesis</th>
            {RULES.map((r) => (
              <th key={r.key} className="py-2.5 px-3 text-center" title={r.name}>
                {r.short}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline-subtle">
          {scored.map((sh) => {
            const ruleMap = new Map<string, RuleResult>()
            sh.rule_results?.forEach((r) => ruleMap.set(r.rule_name, r))

            return (
              <tr key={sh.hypothesis_id} className="hover:bg-surface-raised/40 transition-colors">
                <td className="py-3 px-3 font-bold text-white flex items-center gap-2">
                  <span>{sh.hypothesis_id}</span>
                  <span className="text-[10px] text-muted-foreground font-normal">
                    ({sh.final_audit_score.toFixed(2)})
                  </span>
                </td>
                {RULES.map((r) => {
                  const res = ruleMap.get(r.key)
                  const verdict = (res?.verdict || "n/a").toLowerCase()

                  let badge = "text-muted-foreground bg-surface-raised border-hairline"
                  let label = "— N/A"
                  if (verdict === "pass") {
                    badge = "text-semantic-positive bg-semantic-positive-bg border-semantic-positive-border"
                    label = "✓ PASS"
                  } else if (verdict === "partial") {
                    badge = "text-semantic-warning bg-semantic-warning-bg border-semantic-warning-border"
                    label = "◐ PART"
                  } else if (verdict === "fail") {
                    badge = "text-semantic-critical bg-semantic-critical-bg border-semantic-critical-border"
                    label = "✕ FAIL"
                  }

                  return (
                    <td key={r.key} className="py-3 px-3 text-center">
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold border ${badge}`}
                        title={`${r.name}: ${res?.rationale || "No rationale provided"}`}
                      >
                        {label}
                      </span>
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
