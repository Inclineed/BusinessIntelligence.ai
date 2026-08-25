import React from "react"
import { InvestigationResult } from "../../types/investigation"
import { DiagnosticBreakdown } from "../diagnostic/DiagnosticBreakdown"

interface E3DiagnosticWorkspaceProps {
  result: InvestigationResult
}

export const E3DiagnosticWorkspace: React.FC<E3DiagnosticWorkspaceProps> = ({ result }) => {
  const contributions = result.contributions || []

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Clean Single Stage Header */}
      <header className="space-y-2 border-b border-[#2E2E2E] pb-4">
        <div className="flex items-center justify-between">
          <span className="px-2 py-0.5 rounded bg-[#6B9BB0]/20 text-[#F4EEE0] font-mono text-xs font-bold border border-[#6B9BB0]/40">
            STAGE E3 · DIAGNOSTIC ATTRIBUTION
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#1C1C1C] text-[#9E9788] border border-[#2E2E2E]">
            [SQL + STATS]
          </span>
        </div>
        <h1 className="text-2xl font-bold font-sans text-[#F4EEE0] tracking-tight">
          Dimensional Slice Attribution &amp; Segment Isolation
        </h1>
        <p className="text-xs text-[#9E9788] font-sans leading-relaxed max-w-3xl">
          Drilling down into dimensional partitions (device type, operating region, customer tier, payment gateway) to isolate segment concentration.
        </p>
      </header>

      {/* Dimensional Breakdown Component */}
      <DiagnosticBreakdown contributions={contributions} />
    </div>
  )
}
