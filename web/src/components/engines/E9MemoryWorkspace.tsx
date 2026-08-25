import React from "react"
import { InvestigationResult, PersonaType } from "../../types/investigation"
import { PrecedentCarousel } from "../memory/PrecedentCarousel"
import { FeedbackReviewBar } from "../investigation/FeedbackReviewBar"
import { History, Database, CheckCircle2 } from "lucide-react"

interface E9MemoryWorkspaceProps {
  result: InvestigationResult
  persona: PersonaType
}

export const E9MemoryWorkspace: React.FC<E9MemoryWorkspaceProps> = ({ result, persona }) => {
  return (
    <div className="space-y-6 animate-fade-in">
      {/* Stage Header */}
      <header className="space-y-2 border-b border-[#2E2E2E] pb-4">
        <div className="flex items-center justify-between">
          <span className="px-2 py-0.5 rounded bg-[#6B9BB0]/20 text-[#F4EEE0] font-mono text-xs font-bold border border-[#6B9BB0]/40">
            STAGE E9 · INSTITUTIONAL MEMORY
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#1C1C1C] text-[#9E9788] border border-[#2E2E2E]">
            [RETRIEVAL]
          </span>
        </div>
        <h1 className="text-2xl font-bold font-sans text-[#F4EEE0] tracking-tight">
          Vector Precedents &amp; Institutional Memory Bank
        </h1>
        <p className="text-xs text-[#9E9788] font-sans leading-relaxed max-w-3xl">
          Logging scenario parameters, updating causal priors, and retrieving verified historical resolutions via ChromaDB institutional memory.
        </p>
      </header>

      {/* Institutional Precedent Carousel */}
      <PrecedentCarousel precedents={result.precedents} />

      {/* Inline Structured Review Bar */}
      <div className="pt-2">
        <FeedbackReviewBar result={result} persona={persona} />
      </div>
    </div>
  )
}
