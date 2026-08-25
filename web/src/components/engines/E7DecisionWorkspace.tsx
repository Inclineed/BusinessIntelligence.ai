import React from "react"
import { InvestigationResult } from "../../types/investigation"
import { DecisionHero } from "../decision/DecisionHero"
import { Zap, ShieldCheck } from "lucide-react"

interface E7DecisionWorkspaceProps {
  result: InvestigationResult
}

export const E7DecisionWorkspace: React.FC<E7DecisionWorkspaceProps> = ({ result }) => {
  return (
    <div className="space-y-6 animate-fade-in">
      {/* Stage Header */}
      <header className="space-y-2 border-b border-[#2E2E2E] pb-4">
        <div className="flex items-center justify-between">
          <span className="px-2 py-0.5 rounded bg-[#6B9BB0]/20 text-[#F4EEE0] font-mono text-xs font-bold border border-[#6B9BB0]/40">
            STAGE E7 · DECISION FORMULATION
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#1C1C1C] text-[#9E9788] border border-[#2E2E2E]">
            [LLM]
          </span>
        </div>
        <h1 className="text-2xl font-bold font-sans text-[#F4EEE0] tracking-tight">
          Synthesized Decision &amp; Grounded Action Directive
        </h1>
        <p className="text-xs text-[#9E9788] font-sans leading-relaxed max-w-3xl">
          Synthesizing validated intelligence into a definitive, grounded operational action directive with observable verification metrics.
        </p>
      </header>

      {/* Decision Hero */}
      <DecisionHero decision={result.decision} outcome={result.outcome} />
    </div>
  )
}
