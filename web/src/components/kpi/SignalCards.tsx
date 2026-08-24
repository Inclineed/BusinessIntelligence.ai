import React from "react"
import { ArrowDownRight, ArrowUpRight, AlertTriangle, CheckCircle2 } from "lucide-react"
import { AnomalySignal } from "../../types/investigation"
import { formatMetricValue, formatDelta, formatZScore, cn } from "../../lib/utils"

interface SignalCardsProps {
  signals: AnomalySignal[]
}

export const SignalCards: React.FC<SignalCardsProps> = ({ signals }) => {
  if (!signals || signals.length === 0) {
    return (
      <div className="p-6 rounded-lg bg-surface border border-hairline text-center text-muted-foreground text-xs">
        No KPI signals monitored for this scenario.
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {signals.map((sig) => {
        const isAnomaly = Boolean(sig.is_anomaly)
        const cleanName = sig.kpi_id.replace(/_/g, " ").toUpperCase()
        const { formatted: obsVal, unit } = formatMetricValue(sig.kpi_id, sig.observed)
        const { formatted: expVal } = formatMetricValue(sig.kpi_id, sig.expected)
        const deltaStr = formatDelta(sig.delta_pct)
        const zStr = formatZScore(sig.z_score)

        return (
          <div
            key={sig.kpi_id}
            className={cn(
              "rounded-lg p-4 bg-surface border transition-all duration-200 shadow-card flex flex-col justify-between",
              isAnomaly
                ? "border-semantic-critical-border bg-gradient-to-b from-surface to-semantic-critical-bg/20 shadow-glow-critical"
                : "border-hairline hover:border-hairline-bright"
            )}
          >
            {/* Header: Title & Status Badge */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-[11px] font-mono font-bold tracking-wider text-muted-foreground truncate" title={cleanName}>
                  {cleanName}
                </span>
                {isAnomaly ? (
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-semantic-critical-bg text-semantic-critical border border-semantic-critical-border flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3" /> ANOMALY
                  </span>
                ) : (
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-surface-raised text-muted-foreground border border-hairline flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3 text-semantic-positive" /> NOMINAL
                  </span>
                )}
              </div>

              {/* Observed Value & Delta */}
              <div className="flex items-baseline gap-2.5 my-2">
                <span className="text-2xl font-bold font-mono text-white tracking-tight">
                  {obsVal}{unit}
                </span>
                <span
                  className={cn(
                    "text-xs font-bold font-mono flex items-center",
                    isAnomaly ? "text-semantic-critical" : "text-white"
                  )}
                >
                  {sig.delta_pct < 0 ? (
                    <ArrowDownRight className="w-3.5 h-3.5 mr-0.5" />
                  ) : (
                    <ArrowUpRight className="w-3.5 h-3.5 mr-0.5" />
                  )}
                  {deltaStr}
                </span>
              </div>
            </div>

            {/* Baseline & Z-Score Footer */}
            <div className="pt-3 border-t border-hairline-subtle flex justify-between items-center text-[11px] font-mono text-muted-foreground mt-2">
              <span>
                Baseline: <span className="text-foreground">{expVal}{unit}</span>
              </span>
              <span className={cn(isAnomaly ? "text-semantic-critical font-bold" : "text-muted-foreground")}>
                {zStr}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
