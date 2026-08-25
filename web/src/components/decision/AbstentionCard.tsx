import React from "react"
import { DecisionPayload } from "../../types/investigation"
import { AlertTriangle, ShieldCheck, HelpCircle, ArrowRight } from "lucide-react"

interface AbstentionCardProps {
  decision: DecisionPayload
}

export const AbstentionCard: React.FC<AbstentionCardProps> = ({ decision }) => {
  return (
    <div className="p-6 rounded-2xl bg-[#1C1C1C] border border-[#D8453A]/40 shadow-2xl space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[#2E2E2E] pb-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[#D8453A]/15 border border-[#D8453A]/30 flex items-center justify-center">
            <AlertTriangle className="w-5 h-5 text-[#D8453A]" />
          </div>
          <div>
            <div className="text-base font-bold text-[#F4EEE0] font-mono flex items-center gap-2">
              <span>SYSTEM ABSTAINED</span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-[#D8453A]/20 text-[#E56B62] font-mono border border-[#D8453A]/30">
                SAFETY GUARD ACTIVE
              </span>
            </div>
            <div className="text-xs text-[#9E9788] font-mono">
              Action recommendations suppressed due to high causal uncertainty or data quality constraints.
            </div>
          </div>
        </div>

        <span className="text-[10px] font-mono px-2 py-1 rounded bg-[#181818] text-[#9E9788] border border-[#2E2E2E]">
          [RULES / LLM]
        </span>
      </div>

      {/* Abstention Reason Details */}
      <div className="space-y-1.5">
        <div className="text-xs font-mono font-bold text-[#E56B62] uppercase tracking-wider">
          Abstention Trigger Rationale
        </div>
        <div className="p-4 rounded-xl bg-[#141414] border border-[#D8453A]/25 text-sm text-[#D1C9B8] leading-relaxed font-sans">
          {decision.abstention_reason || decision.persona_narrative || "Causal evidence does not satisfy strict confidence threshold for automated action recommendation."}
        </div>
      </div>

      {/* Recommended Next Steps */}
      <div className="p-3.5 rounded-xl bg-[#222222] border border-[#333333] space-y-2">
        <div className="text-xs font-mono font-bold text-[#D1C9B8] flex items-center gap-1.5">
          <HelpCircle className="w-3.5 h-3.5 text-[#6B9BB0]" />
          <span>Recommended Analyst Next Steps:</span>
        </div>
        <ul className="text-xs text-[#9E9788] space-y-1 pl-5 list-disc font-sans">
          <li>Review competing hypotheses and contradictory evidence in the challenge scorecard above.</li>
          <li>Await additional time-series data or verify ETL batch ingestion status.</li>
          <li>Use the structured feedback review bar below to record human domain insight.</li>
        </ul>
      </div>
    </div>
  )
}
