import React from "react"
import { DecisionPayload, OutcomeProjection } from "../../types/investigation"
import { AbstentionCard } from "./AbstentionCard"
import { RecoveryProjectionGauge } from "./RecoveryProjectionGauge"
import { Zap, CheckCircle2, ShieldCheck, ArrowRight, Activity } from "lucide-react"

interface DecisionHeroProps {
  decision?: DecisionPayload
  outcome?: OutcomeProjection
}

export const DecisionHero: React.FC<DecisionHeroProps> = ({ decision, outcome }) => {
  if (!decision) {
    return null
  }

  if (decision.abstained) {
    return <AbstentionCard decision={decision} />
  }

  return (
    <div className="p-6 rounded-2xl bg-[#1C1C1C] border border-[#2E2E2E] space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[#2E2E2E] pb-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[#6B9BB0]/15 border border-[#6B9BB0]/30 flex items-center justify-center">
            <Zap className="w-5 h-5 text-[#6B9BB0]" />
          </div>
          <div>
            <div className="text-base font-bold text-[#F4EEE0] font-mono flex items-center gap-2">
              <span>RECOMMENDED EXECUTIVE ACTION</span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-[#4E8569]/20 text-[#78AC91] font-mono border border-[#4E8569]/30">
                EVALUATED &amp; GROUNDED
              </span>
            </div>
            <div className="text-xs text-[#9E9788] font-mono">
              Winning Hypothesis: <span className="text-[#6B9BB0] font-bold">{decision.winning_hypothesis_id || "H1"}</span>
            </div>
          </div>
        </div>

        <span className="text-[10px] font-mono px-2 py-1 rounded bg-[#181818] text-[#9E9788] border border-[#2E2E2E]">
          [LLM + SIMULATED]
        </span>
      </div>

      {/* Primary Action Directive */}
      <div className="space-y-1.5">
        <div className="text-xs font-mono font-bold text-[#6B9BB0] uppercase tracking-wider">
          Action Directive
        </div>
        <div className="p-4 rounded-xl bg-[#141414] border border-[#2E2E2E] text-base font-bold text-[#F4EEE0] font-sans leading-snug">
          {decision.recommended_action || "Implement operational mitigation for identified root cause."}
        </div>
      </div>

      {/* Verification Metric & Persona Narrative Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Verification Metric */}
        {decision.verification_metric && (
          <div className="p-3.5 rounded-xl bg-[#222222] border border-[#333333] space-y-1.5">
            <div className="text-xs font-mono font-bold text-[#6B9BB0] flex items-center gap-1.5">
              <Activity className="w-3.5 h-3.5" />
              <span>Verification Metric</span>
            </div>
            <p className="text-xs text-[#D1C9B8] font-sans leading-relaxed">
              {decision.verification_metric}
            </p>
          </div>
        )}

        {/* Persona Executive Narrative */}
        {decision.persona_narrative && (
          <div className="p-3.5 rounded-xl bg-[#222222] border border-[#333333] space-y-1.5">
            <div className="text-xs font-mono font-bold text-[#D1C9B8] flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-[#4E8569]" />
              <span>Executive Briefing</span>
            </div>
            <p className="text-xs text-[#D1C9B8] font-sans leading-relaxed">
              {decision.persona_narrative}
            </p>
          </div>
        )}
      </div>

      {/* Simulated Recovery Outcome */}
      <RecoveryProjectionGauge outcome={outcome} />
    </div>
  )
}
