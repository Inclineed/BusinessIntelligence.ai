import React, { useState } from "react"
import { InvestigationResult, EvidenceItem } from "../../types/investigation"
import { SCENARIO_CATALOG } from "../../lib/api"
import { EvidenceInspectionModal } from "../evidence/EvidenceInspectionModal"
import { formatMetricValue, formatDelta, isAdverseMetric, formatZScore } from "../../lib/utils"
import { Database, FileText, Eye, ShieldCheck, BarChart2 } from "lucide-react"

interface E4EvidenceWorkspaceProps {
  result: InvestigationResult
}

export const E4EvidenceWorkspace: React.FC<E4EvidenceWorkspaceProps> = ({ result }) => {
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceItem | null>(null)
  const evidenceList = result.evidence || []
  const signals = result.signals || []

  // Dynamic scenario metadata
  const currentScenario =
    SCENARIO_CATALOG.find((s) => s.id === result.scenario_id) || SCENARIO_CATALOG[0]
  const primarySignal = signals[0]

  return (
    <div className="space-y-6 animate-fade-in select-text">
      {/* Dynamic Stage Header */}
      <header className="space-y-2 border-b border-[#2E2E2E] pb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 rounded bg-[#6B9BB0]/20 text-[#F4EEE0] font-mono text-xs font-bold border border-[#6B9BB0]/40">
              STAGE E4 · GROUNDED EVIDENCE
            </span>
            <span className="text-xs font-mono text-[#9E9788] font-bold">
              {result.scenario_id}
            </span>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#1C1C1C] text-[#9E9788] border border-[#2E2E2E]">
            [SQL / RETRIEVAL]
          </span>
        </div>

        <h1 className="text-2xl font-bold font-sans text-[#F4EEE0] tracking-tight">
          {currentScenario.title}
        </h1>

        <p className="text-xs text-[#9E9788] font-sans leading-relaxed max-w-3xl">
          {currentScenario.description ||
            "Cross-referencing verified deployment logs, operational telemetry, and structured database metrics to establish factual ground truth."}
        </p>
      </header>

      <div className="space-y-6">
        {/* Dynamic Telemetry & Metric Distribution Corroboration */}
        <div className="p-6 rounded-2xl bg-[#1C1C1C] border border-[#2E2E2E] space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <BarChart2 className="w-4 h-4 text-[#6B9BB0]" />
              <h4 className="font-mono text-xs font-bold text-[#F4EEE0] uppercase tracking-wider">
                Telemetry &amp; Observed Signal Corroboration ({signals.length} Streams)
              </h4>
            </div>

            {primarySignal && (
              <div className="flex flex-wrap items-center gap-2 font-mono text-[11px]">
                <span className="px-2 py-0.5 rounded bg-[#222222] text-[#9E9788] border border-[#333333]">
                  Primary Baseline:{" "}
                  <strong className="text-[#F4EEE0]">
                    {formatMetricValue(primarySignal.kpi_id, primarySignal.expected).formatted}
                    {formatMetricValue(primarySignal.kpi_id, primarySignal.expected).unit}
                  </strong>
                </span>
                <span
                  className={`px-2 py-0.5 rounded border ${
                    primarySignal.is_anomaly
                      ? "bg-[#D8453A]/20 text-[#E56B62] border-[#D8453A]/35"
                      : "bg-[#4E8569]/20 text-[#78AC91] border-[#4E8569]/35"
                  }`}
                >
                  Observed:{" "}
                  <strong className="text-[#F4EEE0]">
                    {formatMetricValue(primarySignal.kpi_id, primarySignal.observed).formatted}
                    {formatMetricValue(primarySignal.kpi_id, primarySignal.observed).unit}
                  </strong>{" "}
                  ({formatDelta(primarySignal.delta_pct)})
                </span>
              </div>
            )}
          </div>

          {/* Dynamic Metric Comparison Bars */}
          <div className="space-y-3 pt-2">
            {signals.map((sig) => {
              const { formatted: obsVal, unit } = formatMetricValue(sig.kpi_id, sig.observed)
              const { formatted: baseVal } = formatMetricValue(sig.kpi_id, sig.expected)
              const isAdverse = isAdverseMetric(sig.kpi_id, sig.delta_pct) || sig.is_anomaly
              const zVal = formatZScore(sig.z_score)
              const delta = formatDelta(sig.delta_pct)

              // Normalized bar width proportional to delta magnitude capped at 100%
              const barWidth = Math.min(100, Math.max(12, Math.abs(sig.delta_pct)))

              return (
                <div
                  key={sig.kpi_id}
                  className="p-3.5 rounded-xl bg-[#222222] border border-[#333333] space-y-2 hover:border-[#6B9BB0]/40 transition-colors"
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 text-xs font-mono">
                    <div className="flex items-center gap-2">
                      <span
                        className={`w-2 h-2 rounded-full shrink-0 ${
                          isAdverse ? "bg-[#D8453A]" : "bg-[#4E8569]"
                        }`}
                      />
                      <span className="font-bold text-[#F4EEE0] uppercase">
                        {sig.kpi_id.replace(/_/g, " ")}
                      </span>
                      {sig.is_anomaly && (
                        <span className="px-1.5 py-0.2 rounded text-[10px] bg-[#D8453A]/20 text-[#E56B62] font-bold">
                          ANOMALY
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-3 text-[11px] text-[#9E9788]">
                      <span>
                        Baseline: <strong className="text-[#D1C9B8]">{baseVal}{unit}</strong>
                      </span>
                      <span>
                        Observed: <strong className="text-[#F4EEE0]">{obsVal}{unit}</strong>
                      </span>
                      <span className={isAdverse ? "text-[#E56B62] font-bold" : "text-[#78AC91] font-bold"}>
                        {delta} ({zVal})
                      </span>
                    </div>
                  </div>

                  {/* Relative Deviation Bar */}
                  <div className="w-full bg-[#181818] h-2 rounded-full overflow-hidden flex">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${
                        isAdverse ? "bg-[#D8453A]" : "bg-[#4E8569]"
                      }`}
                      style={{ width: `${barWidth}%` }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Grounded Evidence Records Table */}
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
                {/* Evidence ID / Ref */}
                <div className="col-span-3 font-mono font-bold text-[#6B9BB0] group-hover:underline flex items-center gap-1.5 truncate">
                  <Database className="w-3.5 h-3.5 shrink-0 text-[#9E9788]" />
                  <span className="truncate">{item.raw_ref || item.evidence_id}</span>
                </div>

                {/* Evidence Summary */}
                <div className="col-span-5 text-[#D1C9B8] font-sans truncate pr-2">
                  {item.summary}
                </div>

                {/* Source System */}
                <div className="col-span-2 font-mono text-[11px] text-[#9E9788] truncate capitalize">
                  {item.source_id.replace(/_/g, " ")}
                </div>

                {/* Inspect Action */}
                <div className="col-span-2 text-right flex items-center justify-end gap-1.5 font-mono text-[11px] text-[#9E9788] group-hover:text-[#F4EEE0]">
                  <span>{Math.round((item.reliability_weight ?? 1.0) * 100)}%</span>
                  <Eye className="w-3.5 h-3.5 text-[#6B9BB0]" />
                  <span className="hidden sm:inline">Inspect</span>
                </div>
              </div>
            ))}

            {evidenceList.length === 0 && (
              <div className="p-8 text-center text-xs font-mono text-[#9E9788] border border-dashed border-[#333333] rounded-xl">
                No grounded evidence records assembled for this configuration.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Modal for Raw Evidence Inspection */}
      {selectedEvidence && (
        <EvidenceInspectionModal
          evidence={selectedEvidence}
          onClose={() => setSelectedEvidence(null)}
        />
      )}
    </div>
  )
}
