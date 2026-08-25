import React from "react"
import { AnomalySignal } from "../../types/investigation"
import { formatMetricValue, formatDelta, formatZScore } from "../../lib/utils"
import { TrendingDown, TrendingUp, AlertTriangle, CheckCircle2, Activity } from "lucide-react"

interface KPISignalGridProps {
  signals: AnomalySignal[]
}

export const KPISignalGrid: React.FC<KPISignalGridProps> = ({ signals }) => {
  if (!signals || signals.length === 0) {
    return (
      <div className="p-6 rounded-2xl bg-[#1C1C1C] border border-[#2E2E2E] text-center">
        <Activity className="w-8 h-8 text-[#9E9788] mx-auto mb-2" />
        <div className="text-sm font-medium text-[#D1C9B8]">No Signal Telemetry Available</div>
        <div className="text-xs text-[#9E9788]">The current persona scope or scenario returned zero active signals.</div>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
      {signals.map((sig) => {
        const { formatted: obsFormatted, unit } = formatMetricValue(sig.kpi_id, sig.observed)
        const { formatted: expFormatted } = formatMetricValue(sig.kpi_id, sig.expected)
        const deltaFormatted = formatDelta(sig.delta_pct)
        const isNegative = sig.delta_pct < 0
        const isAnomaly = sig.is_anomaly

        return (
          <div
            key={sig.kpi_id}
            className={`p-4 rounded-xl border transition-all ${
              isAnomaly
                ? "border-[#D8453A]/40 bg-[#D8453A]/[0.04] shadow-card"
                : "border-[#2E2E2E] bg-[#1C1C1C]"
            }`}
          >
            {/* Header: Title & Provenance Method Tag */}
            <div className="flex items-center justify-between gap-2 mb-2">
              <span className="text-xs font-mono font-bold text-[#F4EEE0] uppercase tracking-wider truncate">
                {sig.kpi_id.replace(/_/g, " ")}
              </span>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#181818] text-[#9E9788] border border-[#2E2E2E]">
                [STATS]
              </span>
            </div>

            {/* Observed Value & Directional Delta */}
            <div className="flex items-baseline justify-between gap-2 mb-3">
              <div className="flex items-baseline gap-1">
                <span className="text-2xl font-bold font-mono tracking-tight text-[#F4EEE0] tabular-nums">
                  {obsFormatted}
                </span>
                {unit && <span className="text-xs font-mono text-[#9E9788]">{unit}</span>}
              </div>

              <div
                className={`flex items-center gap-1 text-xs font-mono font-bold px-2 py-0.5 rounded ${
                  isAnomaly
                    ? "bg-[#D8453A]/20 text-[#E56B62] border border-[#D8453A]/30"
                    : isNegative
                    ? "bg-[#D8453A]/15 text-[#E56B62] border border-[#D8453A]/25"
                    : "bg-[#4E8569]/20 text-[#78AC91] border border-[#4E8569]/30"
                }`}
              >
                {isNegative ? <TrendingDown className="w-3.5 h-3.5" /> : <TrendingUp className="w-3.5 h-3.5" />}
                <span className="tabular-nums">{deltaFormatted}</span>
              </div>
            </div>

            {/* Expected Baseline & Statistical Z-Score */}
            <div className="flex items-center justify-between text-xs font-mono text-[#9E9788] border-t border-[#2E2E2E] pt-2.5">
              <div>
                <span className="text-[#9E9788] text-[11px]">EXPECTED: </span>
                <span className="text-[#D1C9B8] tabular-nums">{expFormatted}{unit}</span>
              </div>
              <div className="font-bold text-[#D1C9B8]">
                {formatZScore(sig.z_score)}
              </div>
            </div>

            {/* Anomaly & Quality Guards */}
            <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
              {isAnomaly ? (
                <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-[#D8453A]/20 text-[#E56B62] border border-[#D8453A]/30 flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3 text-[#D8453A]" />
                  ANOMALY BREACH
                </span>
              ) : (
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#4E8569]/15 text-[#78AC91] border border-[#4E8569]/25 flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3 text-[#4E8569]" />
                  NOMINAL CORRIDOR
                </span>
              )}

              {sig.sparse_history && (
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#D8453A]/15 text-[#E56B62] border border-[#D8453A]/25">
                  SPARSE HISTORY (&lt;14d)
                </span>
              )}

              {sig.data_quality_suspect && (
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#D8453A]/15 text-[#E56B62] border border-[#D8453A]/25">
                  DQ SUSPECT (&lt;0.80)
                </span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
