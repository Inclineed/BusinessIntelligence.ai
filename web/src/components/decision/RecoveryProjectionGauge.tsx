import React from "react"
import { OutcomeProjection } from "../../types/investigation"
import { TrendingUp, AlertCircle } from "lucide-react"

interface RecoveryProjectionGaugeProps {
  outcome?: OutcomeProjection
}

export const RecoveryProjectionGauge: React.FC<RecoveryProjectionGaugeProps> = ({ outcome }) => {
  if (!outcome || outcome.projected_recovery_pct === undefined) {
    return null
  }

  const recoveryPct = Math.min(100, Math.max(0, outcome.projected_recovery_pct))

  return (
    <div className="p-4 rounded-xl bg-[#222222] border border-[#333333] space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-[#4E8569]" />
          <span className="text-xs font-mono font-bold text-[#F4EEE0] uppercase tracking-wider">
            Simulated Recovery Projection
          </span>
        </div>
        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#181818] text-[#9E9788] border border-[#2E2E2E]">
          [SIMULATED]
        </span>
      </div>

      {/* Numerical display */}
      <div className="flex items-baseline justify-between gap-2">
        <div>
          <div className="text-2xl font-bold font-mono text-[#4E8569] tabular-nums">
            {recoveryPct.toFixed(1)}%
          </div>
          <div className="text-[11px] font-mono text-[#9E9788]">
            Projected Metric: <span className="text-[#D1C9B8]">{outcome.projected_metric || "Recovery Metric"}</span>
          </div>
        </div>

        {/* Progress gauge bar */}
        <div className="w-32">
          <div className="h-2 w-full bg-[#141414] rounded-full overflow-hidden border border-[#2E2E2E]">
            <div
              className="h-full rounded-full bg-[#4E8569] transition-all duration-700"
              style={{ width: `${recoveryPct}%` }}
            />
          </div>
        </div>
      </div>

      {/* Mandatory Disclaimer */}
      <div className="p-2.5 rounded-lg bg-[#181818] border border-[#2E2E2E] text-[11px] font-sans text-[#9E9788] flex items-start gap-1.5">
        <AlertCircle className="w-3.5 h-3.5 text-[#6B9BB0] shrink-0 mt-0.5" />
        <span>
          {outcome.disclaimer || "Simulated projection based on synthetic calibration parameters. Not historical causal proof."}
        </span>
      </div>
    </div>
  )
}
