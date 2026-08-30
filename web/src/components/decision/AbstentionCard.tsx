import React from "react"
import { DecisionPayload, InvestigationResult } from "../../types/investigation"
import { getInvestigationStory } from "../../lib/narrativeHelpers"
import { AlertTriangle, ShieldCheck, HelpCircle, CheckCircle2, ArrowRight } from "lucide-react"

interface AbstentionCardProps {
  decision: DecisionPayload
  result?: InvestigationResult
}

export const AbstentionCard: React.FC<AbstentionCardProps> = ({ decision, result }) => {
  const story = result ? getInvestigationStory(result) : null
  const isNominal = story?.isNominal ?? false

  return (
    <div
      className={`p-6 sm:p-8 rounded-2xl bg-[#1C1C1C] shadow-2xl space-y-5 animate-fade-in select-text border ${
        isNominal
          ? "border-[#4E8569]/40 ring-1 ring-[#4E8569]/20"
          : "border-[#D8453A]/40"
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[#2E2E2E] pb-4">
        <div className="flex items-center gap-3">
          <div
            className={`w-10 h-10 rounded-xl flex items-center justify-center border ${
              isNominal
                ? "bg-[#4E8569]/15 border-[#4E8569]/30 text-[#78AC91]"
                : "bg-[#D8453A]/15 border-[#D8453A]/30 text-[#E56B62]"
            }`}
          >
            {isNominal ? (
              <ShieldCheck className="w-5 h-5 text-[#4E8569]" />
            ) : (
              <AlertTriangle className="w-5 h-5 text-[#D8453A]" />
            )}
          </div>
          <div>
            <div className="text-base font-bold text-[#F4EEE0] font-mono flex items-center gap-2">
              <span>{isNominal ? "SYSTEM NOMINAL" : "SYSTEM ABSTAINED"}</span>
              <span
                className={`text-[10px] px-2 py-0.5 rounded font-mono border font-bold uppercase ${
                  isNominal
                    ? "bg-[#4E8569]/20 text-[#78AC91] border-[#4E8569]/30"
                    : "bg-[#D8453A]/20 text-[#E56B62] border-[#D8453A]/30"
                }`}
              >
                {isNominal ? "ALL STREAMS HEALTHY" : "SAFETY GUARD ACTIVE"}
              </span>
            </div>
            <div className="text-xs text-[#9E9788] font-mono mt-0.5">
              {story
                ? story.headline
                : "Action recommendations suppressed due to causal uncertainty or data quality constraints."}
            </div>
          </div>
        </div>

        <span className="text-[10px] font-mono px-2 py-1 rounded bg-[#181818] text-[#9E9788] border border-[#2E2E2E]">
          {isNominal ? "[NOMINAL STATE]" : "[SAFETY GUARD]"}
        </span>
      </div>

      {/* Incident Diagnosis Details */}
      <div className="space-y-1.5">
        <div className="text-xs font-mono font-bold text-[#6B9BB0] uppercase tracking-wider">
          Incident Diagnosis &amp; Telemetry Assessment
        </div>
        <div className="p-4 rounded-xl bg-[#141414] border border-[#2E2E2E] text-sm text-[#D1C9B8] leading-relaxed font-sans">
          {story
            ? story.story
            : decision.abstention_reason ||
              decision.persona_narrative ||
              "Causal evidence does not satisfy strict confidence threshold for automated action recommendation."}
        </div>
      </div>

      {/* Grounded Evidence & Operator Guidance Grid */}
      {story && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 font-mono text-xs">
          <div className="p-3.5 rounded-xl bg-[#181818] border border-[#2A2A2A] space-y-1.5">
            <div className="text-[10px] text-[#78AC91] uppercase font-bold flex items-center gap-1">
              <CheckCircle2 className="w-3.5 h-3.5" /> Grounded Evidence Finding
            </div>
            <p className="text-[11px] text-[#D1C9B8] font-sans leading-relaxed">
              {story.keyEvidenceHighlight}
            </p>
          </div>

          <div className="p-3.5 rounded-xl bg-[#181818] border border-[#2A2A2A] space-y-1.5">
            <div
              className={`text-[10px] uppercase font-bold flex items-center gap-1 ${
                isNominal ? "text-[#78AC91]" : "text-[#E56B62]"
              }`}
            >
              {isNominal ? (
                <CheckCircle2 className="w-3.5 h-3.5 text-[#4E8569]" />
              ) : (
                <AlertTriangle className="w-3.5 h-3.5 text-[#D8453A]" />
              )}
              <span>Governed Operator Directive</span>
            </div>
            <p className="text-[11px] text-[#D1C9B8] font-sans leading-relaxed">
              {story.operatorAction}
            </p>
          </div>
        </div>
      )}

      {/* Recommended Next Steps */}
      <div className="p-4 rounded-xl bg-[#222222] border border-[#333333] space-y-2">
        <div className="text-xs font-mono font-bold text-[#D1C9B8] flex items-center gap-1.5">
          <HelpCircle className="w-3.5 h-3.5 text-[#6B9BB0]" />
          <span>Recommended Analyst Next Steps:</span>
        </div>
        <ul className="text-xs text-[#9E9788] space-y-1.5 pl-5 list-disc font-sans">
          {story?.operatorAction && (
            <li className="text-[#F4EEE0] font-medium">{story.operatorAction}</li>
          )}
          <li>Inspect multi-source telemetry in Stage E4 Grounded Evidence Dossier.</li>
          <li>Record verified ground truth or operator override using the Feedback bar below.</li>
        </ul>
      </div>
    </div>
  )
}
