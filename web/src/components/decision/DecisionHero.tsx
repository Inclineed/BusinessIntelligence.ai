import React from "react"
import { DecisionPayload, OutcomeProjection, InvestigationResult } from "../../types/investigation"
import { cleanLLMTags } from "../../lib/utils"
import { AbstentionCard } from "./AbstentionCard"
import { RecoveryProjectionGauge } from "./RecoveryProjectionGauge"
import { Zap, CheckCircle2, ShieldCheck, ArrowRight, Activity, CheckSquare, Target, User, BarChart2 } from "lucide-react"

interface DecisionHeroProps {
  decision?: DecisionPayload
  outcome?: OutcomeProjection
  result?: InvestigationResult
}

export const DecisionHero: React.FC<DecisionHeroProps> = ({ decision, outcome, result }) => {
  if (!decision) {
    return null
  }

  if (decision.abstained) {
    return <AbstentionCard decision={decision} result={result} />
  }

  const sr = decision.structured_recommendation

  if (!sr) {
    // Fallback if no structured recommendation is available
    return (
      <div className="p-6 rounded-2xl bg-[#1C1C1C] border border-[#2E2E2E] space-y-5">
        <div className="flex items-center justify-between border-b border-[#2E2E2E] pb-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[#6B9BB0]/15 border border-[#6B9BB0]/30 flex items-center justify-center">
              <Zap className="w-5 h-5 text-[#6B9BB0]" />
            </div>
            <div>
              <div className="text-base font-bold text-[#F4EEE0] font-mono flex items-center gap-2">
                <span>GOVERNED ACTION DIRECTIVE</span>
              </div>
              <div className="text-xs text-[#9E9788] font-mono">
                Winning Hypothesis: <span className="text-[#6B9BB0] font-bold">{decision.winning_hypothesis_id || "H1"}</span>
              </div>
            </div>
          </div>
        </div>
        <div className="space-y-1.5">
          <div className="text-xs font-mono font-bold text-[#6B9BB0] uppercase tracking-wider">
            Action Directive
          </div>
          <div className="p-4 rounded-xl bg-[#141414] border border-[#2E2E2E] text-base font-bold text-[#F4EEE0] font-sans leading-snug">
            {decision.recommended_action || "Implement operational mitigation for identified root cause."}
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
          {decision.persona_narrative && (
            <div className="p-3.5 rounded-xl bg-[#222222] border border-[#333333] space-y-1.5">
              <div className="text-xs font-mono font-bold text-[#D1C9B8] flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5 text-[#4E8569]" />
                <span>Executive Briefing</span>
              </div>
              <p className="text-xs text-[#D1C9B8] font-sans leading-relaxed">
                {cleanLLMTags(decision.persona_narrative)}
              </p>
            </div>
          )}
        </div>
        <RecoveryProjectionGauge outcome={outcome} />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-5 lg:flex-row">
      {/* Primary Governed Action Record */}
      <div className="flex-1 p-6 rounded-2xl bg-[#1C1C1C] border border-[#2E2E2E] flex flex-col gap-5 shadow-sm relative overflow-hidden">
        {/* subtle background glow */}
        <div className="absolute top-0 right-0 w-64 h-64 bg-gradient-to-bl from-[#6B9BB0]/5 to-transparent rounded-bl-full pointer-events-none" />

        <div className="flex items-center justify-between border-b border-[#2E2E2E] pb-3 relative z-10">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[#6B9BB0]/15 border border-[#6B9BB0]/30 flex items-center justify-center">
              <Zap className="w-5 h-5 text-[#6B9BB0]" />
            </div>
            <div>
              <div className="text-base font-bold text-[#F4EEE0] font-mono flex items-center gap-2">
                <span>GOVERNED ACTION RECORD</span>
                <span className="text-[10px] px-2 py-0.5 rounded bg-[#4E8569]/20 text-[#78AC91] font-mono border border-[#4E8569]/30">
                  AUTHORIZED
                </span>
              </div>
              <div className="text-xs text-[#9E9788] font-mono">
                Engine E7 Output <span className="text-[#6B9BB0] font-bold">| {decision.winning_hypothesis_id || "H1"}</span>
              </div>
            </div>
          </div>
          <span className="text-[10px] font-mono px-2 py-1 rounded bg-[#181818] text-[#9E9788] border border-[#2E2E2E]">
            [STRUCTURED]
          </span>
        </div>

        {/* Structured Field Grid */}
        <div className="relative z-10 flex flex-col gap-[1px] bg-[#2E2E2E] rounded-xl overflow-hidden border border-[#2E2E2E]">
          {/* Driver */}
          <div className="flex flex-col sm:flex-row bg-[#1C1C1C]">
            <div className="sm:w-1/3 p-3 bg-[#181818] text-[11px] font-mono font-bold text-[#9E9788] uppercase tracking-wider border-b sm:border-b-0 sm:border-r border-[#2E2E2E] flex items-center gap-2">
              <Target className="w-3.5 h-3.5 text-[#A56868]" /> Causal Driver
            </div>
            <div className="sm:w-2/3 p-3 text-sm text-[#F4EEE0] font-sans leading-relaxed">
              {sr.driver}
            </div>
          </div>

          {/* Lever */}
          <div className="flex flex-col sm:flex-row bg-[#1C1C1C]">
            <div className="sm:w-1/3 p-3 bg-[#181818] text-[11px] font-mono font-bold text-[#9E9788] uppercase tracking-wider border-b sm:border-b-0 sm:border-r border-[#2E2E2E] flex items-center gap-2">
              <Activity className="w-3.5 h-3.5 text-[#D19B5E]" /> Controllable Lever
            </div>
            <div className="sm:w-2/3 p-3 text-sm font-mono text-[#D19B5E] font-bold">
              {sr.controllable_lever}
            </div>
          </div>

          {/* Action */}
          <div className="flex flex-col sm:flex-row bg-[#1C1C1C]">
            <div className="sm:w-1/3 p-3 bg-[#181818] text-[11px] font-mono font-bold text-[#9E9788] uppercase tracking-wider border-b sm:border-b-0 sm:border-r border-[#2E2E2E] flex items-center gap-2">
              <CheckSquare className="w-3.5 h-3.5 text-[#6B9BB0]" /> Executable Action
            </div>
            <div className="sm:w-2/3 p-3 text-base text-[#F4EEE0] font-bold font-sans leading-snug">
              {sr.action}
            </div>
          </div>

          {/* Impact */}
          <div className="flex flex-col sm:flex-row bg-[#1C1C1C]">
            <div className="sm:w-1/3 p-3 bg-[#181818] text-[11px] font-mono font-bold text-[#9E9788] uppercase tracking-wider border-b sm:border-b-0 sm:border-r border-[#2E2E2E] flex items-center gap-2">
              <BarChart2 className="w-3.5 h-3.5 text-[#4E8569]" /> Expected Impact
            </div>
            <div className="sm:w-2/3 p-3 text-sm text-[#4E8569] font-mono font-bold">
              {sr.expected_impact}
            </div>
          </div>

          {/* Monitoring */}
          <div className="flex flex-col sm:flex-row bg-[#1C1C1C]">
            <div className="sm:w-1/3 p-3 bg-[#181818] text-[11px] font-mono font-bold text-[#9E9788] uppercase tracking-wider border-b sm:border-b-0 sm:border-r border-[#2E2E2E] flex items-center gap-2">
              <Activity className="w-3.5 h-3.5 text-[#9E9788]" /> Monitoring Plan
            </div>
            <div className="sm:w-2/3 p-3 text-xs text-[#D1C9B8] font-sans">
              {sr.monitoring_plan}
            </div>
          </div>

          {/* Governance / RBAC */}
          <div className="flex flex-col sm:flex-row bg-[#1C1C1C]">
            <div className="sm:w-1/3 p-3 bg-[#181818] text-[11px] font-mono font-bold text-[#9E9788] uppercase tracking-wider border-b sm:border-b-0 sm:border-r border-[#2E2E2E] flex items-center gap-2">
              <User className="w-3.5 h-3.5 text-[#735A88]" /> Governance Auth
            </div>
            <div className="sm:w-2/3 p-3 text-xs font-mono text-[#D1C9B8] flex flex-wrap items-center gap-2">
              <span className="text-[#9E9788]">Owner:</span> 
              <span className="font-bold text-[#E0D8C8]">{sr.owner}</span>
              <span className="px-1 text-[#444]">•</span>
              <span className="text-[#9E9788]">Personas:</span> 
              <div className="flex gap-1.5">
                {sr.authorized_personas.map(p => (
                  <span key={p} className="px-1.5 py-0.5 rounded-sm bg-[#735A88]/20 text-[#A287B8] text-[10px] border border-[#735A88]/30">
                    {p.toUpperCase()}
                  </span>
                ))}
              </div>
              <span className="px-1 text-[#444]">•</span>
              <span className="text-[#9E9788]">Audit Score:</span> 
              <span className="font-bold text-[#6B9BB0]">{(sr.confidence * 100).toFixed(0)}%</span>
            </div>
          </div>
        </div>
      </div>

      {/* Secondary Panel: Narrative & Simulated Outcomes */}
      <div className="flex flex-col w-full lg:w-[320px] xl:w-[380px] gap-5 shrink-0">
        {/* Executive Briefing */}
        {decision.persona_narrative && (
          <div className="p-4 rounded-xl bg-[#222222] border border-[#333333] space-y-2 flex-1">
            <div className="text-xs font-mono font-bold text-[#D1C9B8] flex items-center gap-1.5 pb-2 border-b border-[#333333]">
              <ShieldCheck className="w-4 h-4 text-[#4E8569]" />
              <span>Executive Briefing</span>
            </div>
            <p className="text-sm text-[#D1C9B8] font-sans leading-relaxed pt-1">
              {cleanLLMTags(decision.persona_narrative)}
            </p>
          </div>
        )}

        {/* E8 Projection */}
        <RecoveryProjectionGauge outcome={outcome} />
      </div>
    </div>
  )
}
