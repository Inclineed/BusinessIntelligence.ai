import React from "react"
import { InvestigationResult } from "../../types/investigation"
import { AnomalyCorridorChart } from "../kpi/AnomalyCorridorChart"
import { formatZScore, formatDelta } from "../../lib/utils"
import { Activity, AlertTriangle, CheckCircle2 } from "lucide-react"

interface E2AnomalyWorkspaceProps {
  result: InvestigationResult
}

export const E2AnomalyWorkspace: React.FC<E2AnomalyWorkspaceProps> = ({ result }) => {
  const primarySignal = result.signals?.[0]
  const isAnomaly = primarySignal?.is_anomaly ?? false

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Stage Header */}
      <header className="space-y-2 border-b border-[#2E2E2E] pb-4">
        <div className="flex items-center justify-between">
          <span className="px-2 py-0.5 rounded bg-[#D8453A]/20 text-[#F4EEE0] font-mono text-xs font-bold border border-[#D8453A]/40">
            STAGE E2 · ANOMALY CORRIDOR
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#1C1C1C] text-[#9E9788] border border-[#2E2E2E]">
            [STATS]
          </span>
        </div>
        <h1 className="text-2xl font-bold font-sans text-[#F4EEE0] tracking-tight">
          Anomaly Detection &amp; Corridor Verification
        </h1>
        <p className="text-xs text-[#9E9788] font-sans leading-relaxed max-w-3xl">
          Statistical anomaly detection evaluating standard deviation thresholds (±3σ), moving averages, and seasonality guards.
        </p>
      </header>

      {/* Anomaly Severity Card */}
      {primarySignal && (
        <div className="p-5 rounded-2xl bg-[#1C1C1C] border border-[#2E2E2E] grid grid-cols-1 sm:grid-cols-3 gap-4 font-mono">
          <div className="space-y-1">
            <div className="text-[10px] text-[#9E9788] uppercase">Statistical Z-Score</div>
            <div className="text-2xl font-bold text-[#D8453A] tabular-nums">
              {formatZScore(primarySignal.z_score)}
            </div>
            <div className="text-[10px] text-[#666666]">Threshold: |z| &gt; 3.00σ</div>
          </div>

          <div className="space-y-1">
            <div className="text-[10px] text-[#9E9788] uppercase">Deviation Magnitude</div>
            <div className="text-2xl font-bold text-[#F4EEE0] tabular-nums">
              {formatDelta(primarySignal.delta_pct)}
            </div>
            <div className="text-[10px] text-[#666666]">Relative to expected baseline</div>
          </div>

          <div className="space-y-1">
            <div className="text-[10px] text-[#9E9788] uppercase">Anomaly Status</div>
            <div className="flex items-center gap-1.5 pt-1">
              {isAnomaly ? (
                <span className="px-2.5 py-1 rounded bg-[#D8453A]/20 text-[#E56B62] border border-[#D8453A]/40 text-xs font-bold flex items-center gap-1">
                  <AlertTriangle className="w-3.5 h-3.5" /> CRITICAL BREACH
                </span>
              ) : (
                <span className="px-2.5 py-1 rounded bg-[#4E8569]/20 text-[#78AC91] border border-[#4E8569]/40 text-xs font-bold flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5" /> NOMINAL STREAM
                </span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Interactive Time-Series Corridor Chart */}
      <AnomalyCorridorChart scenarioId={result.scenario_id} />
    </div>
  )
}
