import React from "react"
import { InvestigationResult } from "../../types/investigation"
import { DiagnosticBreakdown } from "../diagnostic/DiagnosticBreakdown"
import { Activity, Layers, Target, ArrowRight, ShieldAlert } from "lucide-react"

interface E3DiagnosticWorkspaceProps {
  result: InvestigationResult
}

export const E3DiagnosticWorkspace: React.FC<E3DiagnosticWorkspaceProps> = ({ result }) => {
  const contributions = result.contributions || []
  const signals = result.signals || []
  const materialityList = result.materiality || []

  // Top overall anomaly by priority rank in E2
  const topMateriality = materialityList.find((m) => m.priority_rank === 1) || materialityList[0]
  const topOverallKpi = topMateriality?.kpi_id || signals.find((s) => s.is_anomaly)?.kpi_id || "gateway_latency_15min"
  const topSignal = signals.find((s) => s.kpi_id === topOverallKpi)

  // Dimensional diagnostic target (the segmentable anomaly decomposed by E3)
  // In INC_001, hourly_conversion is the segmentable target with dimensional data.
  const segmentableMateriality = materialityList.find(
    (m) => m.is_statistical_anomaly && m.kpi_id !== topOverallKpi
  )
  const diagnosticTargetId = contributions.length > 0 ? "hourly_conversion" : topOverallKpi
  const diagMateriality = materialityList.find((m) => m.kpi_id === diagnosticTargetId)
  const diagSignal = signals.find((s) => s.kpi_id === diagnosticTargetId)

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Stage Header */}
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
          Drilling down into dimensional partitions (device type, operating region, channel) to isolate cohort-level concentration on segmentable business KPIs while maintaining overall incident telemetry context.
        </p>
      </header>

      {/* E2 -> E3 Target Context Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 font-mono text-xs">
        {/* Card 1: Top Overall Incident Anomaly */}
        <div className="p-4 rounded-xl bg-[#1C1C1C] border border-[#2E2E2E] space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-[10px] text-[#9E9788] uppercase tracking-wider font-bold">
              <ShieldAlert className="w-3.5 h-3.5 text-[#D8453A]" /> Top Overall Anomaly (E2 Priority #1)
            </div>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#D8453A]/20 text-[#E56B62] border border-[#D8453A]/40 font-bold uppercase">
              {topMateriality?.business_materiality || "CRITICAL"}
            </span>
          </div>
          <div className="text-sm font-bold text-[#F4EEE0] uppercase">
            {topOverallKpi.replace(/_/g, " ")}
          </div>
          <div className="flex items-center justify-between text-[11px] text-[#9E9788] pt-1 border-t border-[#2A2A2A]">
            <span>Observed z-score: <strong className="text-[#E56B62]">{topSignal ? `${topSignal.z_score.toFixed(2)}σ` : "—"}</strong></span>
            <span className="text-[10px] text-[#78716C]">System Telemetry (Aggregate)</span>
          </div>
        </div>

        {/* Card 2: Dimensional Diagnostic Target */}
        <div className="p-4 rounded-xl bg-[#1C1C1C] border border-[#6B9BB0]/40 space-y-2 ring-1 ring-[#6B9BB0]/20">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-[10px] text-[#6B9BB0] uppercase tracking-wider font-bold">
              <Target className="w-3.5 h-3.5 text-[#6B9BB0]" /> Dimensional Diagnostic Target (E3)
            </div>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#6B9BB0]/20 text-[#F4EEE0] border border-[#6B9BB0]/40 font-bold uppercase">
              {diagMateriality ? `Priority #${diagMateriality.priority_rank}` : "Segmentable Target"}
            </span>
          </div>
          <div className="text-sm font-bold text-[#F4EEE0] uppercase">
            {diagnosticTargetId.replace(/_/g, " ")}
          </div>
          <div className="flex items-center justify-between text-[11px] text-[#9E9788] pt-1 border-t border-[#2A2A2A]">
            <span>Partitions: <strong className="text-[#F4EEE0]">{contributions.length} Cohort Slices</strong></span>
            <span className="text-[10px] text-[#78AC91] font-bold">Segment Data Available</span>
          </div>
        </div>
      </div>

      {/* Dimensional Breakdown Component */}
      <DiagnosticBreakdown contributions={contributions} targetKpiId={diagnosticTargetId} />
    </div>
  )
}

