import React from "react"
import { DimensionContribution } from "../../types/investigation"
import { formatDelta } from "../../lib/utils"
import { Layers, AlertTriangle, PieChart, Sparkles, Filter } from "lucide-react"

interface DiagnosticBreakdownProps {
  contributions: DimensionContribution[]
  targetKpiId?: string
}

export const DiagnosticBreakdown: React.FC<DiagnosticBreakdownProps> = ({ contributions, targetKpiId }) => {
  if (!contributions || contributions.length === 0) {
    return (
      <div className="p-6 rounded-2xl bg-[#1C1C1C] border border-[#2E2E2E] text-center text-xs font-mono text-[#9E9788]">
        No dimensional variance observed / no cohort-level partition data available for this investigation.
      </div>
    )
  }

  // Sort descending by contribution percentage
  const sorted = [...contributions].sort((a, b) => b.contribution_pct - a.contribution_pct)
  const primaryDriver = sorted[0]

  return (
    <div className="space-y-5">
      {/* 1. Analytical Summary Callout: Explains the Core Finding */}
      <div className="p-5 rounded-2xl bg-[#1C1C1C] border border-[#2E2E2E] space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-[#6B9BB0]" />
            <span className="text-xs font-mono font-bold text-[#F4EEE0] uppercase tracking-wider">
              Dimensional Concentration Analysis {targetKpiId ? `(${targetKpiId.replace(/_/g, " ")})` : ""}
            </span>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#181818] text-[#9E9788] border border-[#2E2E2E]">
            AUTOMATED SLICE &amp; ATTRIBUTE
          </span>
        </div>

        {/* 3 Summary Stats dynamically bound */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 font-mono text-xs">
          <div className="p-3.5 rounded-xl bg-[#222222] border border-[#333333] space-y-1">
            <span className="text-[10px] text-[#9E9788] uppercase block">Primary Bottleneck Slice</span>
            <div className="text-sm font-bold text-[#F4EEE0] uppercase truncate">
              {primaryDriver ? `${primaryDriver.dimension}: ${primaryDriver.segment}` : "—"}
            </div>
            <span className="text-[10px] text-[#6B9BB0] block">Highest failure density</span>
          </div>

          <div className="p-3.5 rounded-xl bg-[#222222] border border-[#333333] space-y-1">
            <span className="text-[10px] text-[#9E9788] uppercase block">Share of System Impact</span>
            <div className="text-lg font-bold text-[#D8453A] tabular-nums">
              {primaryDriver ? `${primaryDriver.contribution_pct.toFixed(1)}%` : "—"}
            </div>
            <span className="text-[10px] text-[#9E9788] block">of aggregate incident volume</span>
          </div>

          <div className="p-3.5 rounded-xl bg-[#222222] border border-[#333333] space-y-1">
            <span className="text-[10px] text-[#9E9788] uppercase block">Segment Anomaly Surge</span>
            <div className="text-lg font-bold text-[#E56B62] tabular-nums">
              {primaryDriver && primaryDriver.segment_delta_pct !== undefined
                ? formatDelta(primaryDriver.segment_delta_pct)
                : "—"}
            </div>
            <span className="text-[10px] text-[#9E9788] block">Within-slice latency increase</span>
          </div>
        </div>
      </div>

      {/* 2. Structured Decomposition Table with Distinct Dimension & Segment Columns */}
      <div className="p-5 rounded-2xl bg-[#1C1C1C] border border-[#2E2E2E] space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h4 className="font-mono text-xs font-bold text-[#F4EEE0] uppercase tracking-wider">
              Segment Attribution Breakdown {targetKpiId ? `· ${targetKpiId.replace(/_/g, " ")}` : ""}
            </h4>
            <p className="text-[11px] text-[#9E9788] font-mono mt-0.5">
              Comparing how much each slice surged locally vs. its contribution to the {targetKpiId ? `'${targetKpiId.replace(/_/g, " ")}'` : "target KPI"} anomaly.
            </p>
          </div>
        </div>

        {/* Table Header with Dedicated Dimension and Segment columns */}
        <div className="grid grid-cols-12 gap-4 px-4 py-2 text-[10px] font-mono font-bold uppercase text-[#9E9788] border-b border-[#2E2E2E]">
          <div className="col-span-2">Dimension</div>
          <div className="col-span-3">Segment Name</div>
          <div className="col-span-2">Local Surge (Δ%)</div>
          <div className="col-span-3">Share of Total Drop</div>
          <div className="col-span-2 text-right">Severity</div>
        </div>

        {/* Rows with clear separation */}
        <div className="space-y-2">
          {sorted.map((item, idx) => {
            const pct = Math.min(100, Math.max(0, item.contribution_pct))
            const isDominant = idx === 0

            return (
              <div
                key={`${item.dimension}-${item.segment}`}
                className={`grid grid-cols-12 gap-4 px-4 py-3 rounded-xl border transition-all items-center font-mono text-xs ${
                  isDominant
                    ? "bg-[#252020] border-[#D8453A]/40 shadow-sm"
                    : "bg-[#222222] border-[#333333]"
                }`}
              >
                {/* Column 1: Dimension Tag */}
                <div className="col-span-2">
                  <span className="text-[10px] text-[#9E9788] uppercase px-2 py-0.5 rounded bg-[#181818] border border-[#2E2E2E] inline-block font-medium">
                    {item.dimension}
                  </span>
                </div>

                {/* Column 2: Segment Name */}
                <div className="col-span-3">
                  <span className="font-bold text-[#F4EEE0] truncate block">
                    {item.segment}
                  </span>
                </div>

                {/* Column 3: Local Surge */}
                <div className="col-span-2">
                  {item.segment_delta_pct !== undefined ? (
                    <span className="px-2 py-0.5 rounded bg-[#D8453A]/20 text-[#E56B62] border border-[#D8453A]/30 text-[11px] font-bold inline-block">
                      {formatDelta(item.segment_delta_pct)}
                    </span>
                  ) : (
                    <span className="text-[#9E9788]">—</span>
                  )}
                </div>

                {/* Column 4: Share of Total Drop with Progress Bar */}
                <div className="col-span-3 space-y-1">
                  <div className="flex justify-between text-[11px]">
                    <span className="text-[#F4EEE0] font-bold tabular-nums">{pct.toFixed(1)}%</span>
                    <span className="text-[10px] text-[#9E9788]">of impact</span>
                  </div>
                  <div className="h-1.5 w-full bg-[#141414] rounded-full overflow-hidden border border-[#2E2E2E]">
                    <div
                      className={`h-full rounded-full ${
                        isDominant ? "bg-[#D8453A]" : "bg-[#6B9BB0]"
                      }`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>

                {/* Column 5: Severity Hotspot Tag */}
                <div className="col-span-2 text-right">
                  {isDominant ? (
                    <span className="px-2 py-0.5 rounded bg-[#D8453A]/20 text-[#E56B62] border border-[#D8453A]/40 text-[10px] font-bold">
                      CRITICAL DRIVER
                    </span>
                  ) : pct > 20 ? (
                    <span className="px-2 py-0.5 rounded bg-[#6B9BB0]/20 text-[#6B9BB0] border border-[#6B9BB0]/40 text-[10px] font-bold">
                      ELEVATED
                    </span>
                  ) : (
                    <span className="text-[10px] text-[#9E9788]">
                      SECONDARY
                    </span>
                  )}
                </div>
              </div>
            )
          })}
        </div>

        {/* 3. Fully Dynamic Data-Driven Causal Conclusion */}
        {primaryDriver && (
          <div className="p-3.5 rounded-xl bg-[#181818] border border-[#2E2E2E] flex items-start gap-2.5 text-xs text-[#D1C9B8]">
            <Sparkles className="w-4 h-4 text-[#6B9BB0] shrink-0 mt-0.5" />
            <p className="leading-relaxed font-sans">
              <strong className="text-[#F4EEE0] font-mono">Diagnostic Conclusion:</strong> Slicing the aggregate anomaly reveals that <strong className="text-[#F4EEE0]">{primaryDriver.segment.replace(/_/g, " ")}</strong> ({primaryDriver.dimension}) is the primary driver, responsible for <strong className="text-[#D8453A] font-mono">{primaryDriver.contribution_pct.toFixed(1)}%</strong> of all incident impact{primaryDriver.segment_delta_pct !== undefined ? <> with a within-segment surge of <strong className="text-[#E56B62] font-mono">{formatDelta(primaryDriver.segment_delta_pct)}</strong></> : ""}.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
