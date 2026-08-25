import React from "react"
import { InvestigationResult } from "../../types/investigation"
import { RecoveryProjectionGauge } from "../decision/RecoveryProjectionGauge"
import { TrendingUp, AlertCircle, Clock, DollarSign } from "lucide-react"

interface E8OutcomeWorkspaceProps {
  result: InvestigationResult
}

export const E8OutcomeWorkspace: React.FC<E8OutcomeWorkspaceProps> = ({ result }) => {
  const outcome = result.outcome
  const recoveryPct = outcome?.projected_recovery_pct ?? 88.0

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Stage Header */}
      <header className="space-y-2 border-b border-[#2E2E2E] pb-4">
        <div className="flex items-center justify-between">
          <span className="px-2 py-0.5 rounded bg-[#6B9BB0]/20 text-[#F4EEE0] font-mono text-xs font-bold border border-[#6B9BB0]/40">
            STAGE E8 · PROJECTED OUTCOME
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#1C1C1C] text-[#9E9788] border border-[#2E2E2E]">
            [SIMULATED]
          </span>
        </div>
        <h1 className="text-2xl font-bold font-sans text-[#F4EEE0] tracking-tight">
          Recovery Trajectory &amp; Projected Impact
        </h1>
        <p className="text-xs text-[#9E9788] font-sans leading-relaxed max-w-3xl">
          Forecasting the operational and financial impact of executing the recommended intervention against baseline recovery corridors.
        </p>
      </header>

      {/* 2-Card Projection Metric Summary */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 font-mono">
        <div className="p-6 rounded-2xl bg-[#1C1C1C] border border-[#2E2E2E] text-center space-y-2">
          <div className="text-[11px] text-[#9E9788] uppercase tracking-wider">Projected Recovery</div>
          <div className="text-4xl font-bold text-[#4E8569] tabular-nums">
            {recoveryPct.toFixed(1)}%
          </div>
          <div className="text-xs text-[#9E9788]">Target metric: {outcome?.projected_metric || "order_conversion_rate"}</div>
        </div>

        <div className="p-6 rounded-2xl bg-[#1C1C1C] border border-[#2E2E2E] text-center space-y-2">
          <div className="text-[11px] text-[#9E9788] uppercase tracking-wider">Mean Time to Normalcy</div>
          <div className="text-4xl font-bold text-[#6B9BB0] tabular-nums">
            5.0m
          </div>
          <div className="text-xs text-[#9E9788]">Post-rollback reload &amp; latency stabilization</div>
        </div>
      </div>

      {/* Recovery Projection Component with Disclaimer */}
      <RecoveryProjectionGauge outcome={outcome} />
    </div>
  )
}
