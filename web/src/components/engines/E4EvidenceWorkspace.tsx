import React, { useState } from "react"
import { InvestigationResult, EvidenceItem } from "../../types/investigation"
import { EvidenceInspectionModal } from "../evidence/EvidenceInspectionModal"
import { Database, FileText, Eye, ShieldCheck, BarChart2 } from "lucide-react"

interface E4EvidenceWorkspaceProps {
  result: InvestigationResult
}

export const E4EvidenceWorkspace: React.FC<E4EvidenceWorkspaceProps> = ({ result }) => {
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceItem | null>(null)
  const evidenceList = result.evidence || []

  const latencyPoints = [
    { time: "10:00", height: "25%", ms: "180 ms", label: "Normal baseline", color: "bg-[#2A2A2A] hover:bg-[#383838]", textCol: "text-[#9E9788]" },
    { time: "11:00", height: "32%", ms: "210 ms", label: "Normal baseline", color: "bg-[#2A2A2A] hover:bg-[#383838]", textCol: "text-[#9E9788]" },
    { time: "12:00", height: "20%", ms: "175 ms", label: "Normal baseline", color: "bg-[#2A2A2A] hover:bg-[#383838]", textCol: "text-[#9E9788]" },
    { time: "13:00", height: "65%", ms: "410 ms", label: "Pre-spike onset", color: "bg-[#5C322F] hover:bg-[#6E3B37]", textCol: "text-[#D1C9B8]" },
    { time: "14:00", height: "98%", ms: "612 ms", label: "Deploy v4.3 pool exhaustion (+240%)", color: "bg-[#D8453A]", textCol: "text-[#E56B62] font-bold" },
    { time: "15:00", height: "88%", ms: "580 ms", label: "Sustained delay bottleneck", color: "bg-[#D8453A]/60", textCol: "text-[#E56B62]" },
    { time: "16:00", height: "40%", ms: "260 ms", label: "Initial recovery after rollback", color: "bg-[#383838]", textCol: "text-[#9E9788]" },
  ]

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Stage Header */}
      <header className="space-y-2 border-b border-[#2E2E2E] pb-4">
        <div className="flex items-center justify-between">
          <span className="px-2 py-0.5 rounded bg-[#6B9BB0]/20 text-[#F4EEE0] font-mono text-xs font-bold border border-[#6B9BB0]/40">
            STAGE E4 · GROUNDED EVIDENCE
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#1C1C1C] text-[#9E9788] border border-[#2E2E2E]">
            [SQL / RETRIEVAL]
          </span>
        </div>
        <h1 className="text-2xl font-bold font-sans text-[#F4EEE0] tracking-tight">
          {result.scenario_id === "INC_001" ? "Payment Gateway Latency Regression" : "Singapore-Shanghai Transit Variance"}
        </h1>
        <p className="text-xs text-[#9E9788] font-sans leading-relaxed max-w-3xl">
          The current delay is not systemic. Intelligence suggests a localized bottleneck in upstream gateway connections. Cross-referencing deployment logs and telemetry confirms a mean latency deviation.
        </p>
      </header>

      {/* Stacked Layout: Bar Chart on Top, Records Below */}
      <div className="space-y-6">
        
        {/* Top Card: Telemetry Latency Distribution */}
        <div className="p-6 rounded-2xl bg-[#1C1C1C] border border-[#2E2E2E] space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <BarChart2 className="w-4 h-4 text-[#6B9BB0]" />
              <h4 className="font-mono text-xs font-bold text-[#F4EEE0] uppercase tracking-wider">
                Telemetry: Latency Distribution
              </h4>
            </div>
            <div className="flex flex-wrap items-center gap-2 font-mono text-[11px]">
              <span className="px-2 py-0.5 rounded bg-[#222222] text-[#9E9788] border border-[#333333]">
                Baseline (p50): <strong className="text-[#F4EEE0]">180 ms</strong>
              </span>
              <span className="px-2 py-0.5 rounded bg-[#D8453A]/20 text-[#E56B62] border border-[#D8453A]/35">
                Peak Breach (p95): <strong className="text-[#F4EEE0]">612 ms</strong> (+240%)
              </span>
            </div>
          </div>

          <div className="grid grid-cols-7 gap-4 h-52 pt-6 pb-2 px-2 items-end">
            {latencyPoints.map((pt) => (
              <div
                key={pt.time}
                className="flex flex-col items-center gap-2 h-full justify-end group relative cursor-pointer min-w-0"
                title={`${pt.time}: ${pt.ms} (${pt.label})`}
              >
                <span className="text-[10px] font-mono text-[#9E9788] opacity-0 group-hover:opacity-100 transition-opacity">
                  {pt.ms}
                </span>
                <div className="w-full flex justify-center items-end h-full">
                  <div
                    className={`w-full max-w-[48px] rounded-t-md transition-all ${pt.color}`}
                    style={{ height: pt.height }}
                  />
                </div>
                <span className={`text-[11px] font-mono text-center truncate w-full block ${pt.textCol}`}>
                  {pt.time}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Bottom Card: Grounded Evidence Records */}
        <div className="p-6 rounded-2xl bg-[#1C1C1C] border border-[#2E2E2E] space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4 text-[#6B9BB0]" />
              <h4 className="font-mono text-xs font-bold text-[#F4EEE0] uppercase tracking-wider">
                Grounded Evidence Records ({evidenceList.length})
              </h4>
            </div>
            <span className="text-[11px] font-mono text-[#4E8569] flex items-center gap-1">
              <ShieldCheck className="w-3.5 h-3.5" /> Provenance Verified
            </span>
          </div>

          {/* Clean Evidence Rows */}
          <div className="space-y-2">
            {/* Column Headers */}
            <div className="grid grid-cols-12 gap-3 px-4 py-1.5 text-[10px] font-mono font-bold uppercase text-[#9E9788] border-b border-[#2E2E2E]">
              <div className="col-span-3">Evidence Ref</div>
              <div className="col-span-5">Evidence Summary</div>
              <div className="col-span-2">Source System</div>
              <div className="col-span-2 text-right">Action</div>
            </div>

            {/* Row Items */}
            {evidenceList.map((item) => (
              <div
                key={item.evidence_id}
                onClick={() => setSelectedEvidence(item)}
                className="grid grid-cols-12 gap-3 px-4 py-3 rounded-xl bg-[#222222] hover:bg-[#2A2A2A] border border-[#333333] hover:border-[#6B9BB0]/40 transition-all cursor-pointer items-center group text-xs"
              >
                <div className="col-span-3 font-mono font-bold text-[#F4EEE0] group-hover:text-[#6B9BB0] transition-colors truncate">
                  {item.evidence_id}
                </div>
                <div className="col-span-5 text-[#D1C9B8] font-sans truncate pr-2">
                  {item.summary || "No summary available."}
                </div>
                <div className="col-span-2 text-[#9E9788] font-mono truncate">
                  {item.source_id}
                </div>
                <div className="col-span-2 flex items-center justify-end gap-3 font-mono">
                  <span className="font-bold text-[#4E8569] tabular-nums" title="Reliability Weight">
                    {(item.reliability_weight * 100).toFixed(0)}%
                  </span>
                  <span className="inline-flex items-center gap-1.5 text-[11px] text-[#9E9788] group-hover:text-[#F4EEE0] transition-colors">
                    <Eye className="w-3 h-3" />
                    <span>Inspect</span>
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Modal for detailed inspection */}
      {selectedEvidence && (
        <EvidenceInspectionModal
          evidence={selectedEvidence}
          onClose={() => setSelectedEvidence(null)}
        />
      )}
    </div>
  )
}
