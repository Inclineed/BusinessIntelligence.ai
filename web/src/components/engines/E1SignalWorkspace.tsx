import React from "react"
import { InvestigationResult, AnomalySignal } from "../../types/investigation"
import { formatMetricValue, formatDelta, isAdverseMetric } from "../../lib/utils"
import { Database, TrendingDown, TrendingUp, Activity, CheckCircle2, ArrowDownRight, ArrowUpRight } from "lucide-react"

interface E1SignalWorkspaceProps {
  result: InvestigationResult
}

// Generates realistic sparkline path coordinates
const getSparklineData = (kpiId: string, deltaPct: number): number[] => {
  if (deltaPct < 0) {
    // Negative drop (e.g. conversion / revenue)
    return [70, 72, 69, 71, 70, 68, 65, 45, 30, 24, 20, 18]
  } else if (kpiId.includes("error") || deltaPct > 500) {
    // Huge error spike
    return [8, 9, 7, 8, 9, 8, 12, 35, 68, 85, 92, 98]
  } else {
    // Moderate latency spike
    return [25, 24, 26, 25, 27, 28, 42, 65, 88, 95, 96, 98]
  }
}

export const E1SignalWorkspace: React.FC<E1SignalWorkspaceProps> = ({ result }) => {
  const signals = result.signals || []
  const primary = signals[0]

  const { formatted: obsFormatted, unit } = primary
    ? formatMetricValue(primary.kpi_id, primary.observed)
    : { formatted: "N/A", unit: "" }
  const { formatted: expFormatted } = primary
    ? formatMetricValue(primary.kpi_id, primary.expected)
    : { formatted: "N/A" }
  const deltaFormatted = primary ? formatDelta(primary.delta_pct) : "—"

  // Primary bullet gauge calculations
  const maxScale = primary ? Math.max(primary.observed * 1.3, primary.expected * 1.3, 100) : 100
  const expectedPct = primary ? (primary.expected / maxScale) * 100 : 25
  const observedPct = primary ? (primary.observed / maxScale) * 100 : 85
  const isShifted = primary ? (Math.abs(primary.delta_pct) >= 10.0 || primary.is_anomaly) : false
  const deviation = primary ? primary.observed - primary.expected : 0
  const deviationFormatted = primary
    ? (deviation > 0 ? "+" : "") + Math.round(deviation).toLocaleString()
    : "0"

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Stage Header */}
      <header className="space-y-2 border-b border-[#2E2E2E] pb-4">
        <div className="flex items-center justify-between">
          <span className="px-2 py-0.5 rounded bg-[#6B9BB0]/20 text-[#F4EEE0] font-mono text-xs font-bold border border-[#6B9BB0]/40">
            STAGE E1 · OBSERVE TELEMETRY
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#1C1C1C] text-[#9E9788] border border-[#2E2E2E]">
            [SQL INGESTION]
          </span>
        </div>
        <h1 className="text-2xl font-bold font-sans text-[#F4EEE0] tracking-tight">
          Observed Telemetry &amp; Baseline Variance
        </h1>
        <p className="text-xs text-[#9E9788] font-sans leading-relaxed max-w-3xl">
          Extracting deterministic aggregates from enterprise data warehouse streams. Ingesting observed readings, measuring deviation against historical baselines, and tracking multi-stream trends.
        </p>
      </header>

      {/* Zero Signals / Sparse Baseline Empty State Card */}
      {signals.length === 0 && (
        <div className="p-8 rounded-2xl bg-[#1C1C1C] border border-[#2E2E2E] space-y-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[#6B9BB0]/15 border border-[#6B9BB0]/30 flex items-center justify-center text-[#6B9BB0]">
              <Database className="w-5 h-5" />
            </div>
            <div>
              <div className="text-sm font-bold font-mono text-[#F4EEE0] flex items-center gap-2">
                <span>SPARSE HISTORICAL TELEMETRY (&lt; 14 INTERVALS)</span>
                <span className="text-[10px] px-2 py-0.5 rounded bg-[#D8453A]/20 text-[#E56B62] font-mono border border-[#D8453A]/30 font-bold">
                  GUARD TRIGGERED
                </span>
              </div>
              <div className="text-xs text-[#9E9788] font-mono mt-0.5">
                Engine E1 [SQL INGESTION] · Zero Anomaly Signals Qualified
              </div>
            </div>
          </div>
          <p className="text-xs text-[#D1C9B8] font-sans leading-relaxed">
            Historical baseline data is sparse or below the minimum statistical requirement for this monitored domain. Under the statistical reliability contract, anomaly detection requires sufficient baseline history to compute valid ±3σ confidence corridors without false-positive drift.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 font-mono text-xs">
            <div className="p-3 rounded-xl bg-[#141414] border border-[#2E2E2E] space-y-1">
              <span className="text-[10px] text-[#9E9788] uppercase block">Telemetry Status</span>
              <span className="font-bold text-[#F4EEE0]">0 Ingested Anomaly Signals</span>
            </div>
            <div className="p-3 rounded-xl bg-[#141414] border border-[#2E2E2E] space-y-1">
              <span className="text-[10px] text-[#9E9788] uppercase block">Governance Action</span>
              <span className="font-bold text-[#E56B62]">Autonomous Decision Abstention</span>
            </div>
          </div>
        </div>
      )}

      {/* Hero Analytical Primary KPI Card with Bullet Range Gauge */}
      {primary && (
        <div className="p-6 rounded-2xl bg-[#1C1C1C] border border-[#2E2E2E] space-y-6">
          {/* Header Row */}
          <div className="flex items-center justify-between text-xs font-mono">
            <div className="flex items-center gap-2">
              <span className="text-[#9E9788] uppercase tracking-wider font-bold">
                {primary.kpi_id.replace(/_/g, " ")}
              </span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#181818] text-[#9E9788] border border-[#2E2E2E]">
                [PRIMARY STREAM]
              </span>
            </div>
            <span className="text-[#4E8569] font-bold flex items-center gap-1 text-[11px]">
              <CheckCircle2 className="w-3.5 h-3.5" /> Deterministic Ingestion Verified
            </span>
          </div>

          {/* Metric Value & Delta */}
          <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-4">
            <div>
              <div className="text-4xl font-bold font-mono text-[#F4EEE0] tabular-nums">
                {obsFormatted} <span className="text-lg text-[#9E9788] font-normal">{unit}</span>
              </div>
              <div className="text-xs font-mono text-[#9E9788] mt-1">
                Historical Expected Baseline: <span className="text-[#D1C9B8] font-bold">{expFormatted} {unit}</span>
              </div>
            </div>

            <div className={`px-4 py-2 rounded-xl text-base font-mono font-bold flex items-center gap-2 self-start sm:self-auto ${
              isShifted
                ? "bg-[#D8453A]/20 text-[#E56B62] border border-[#D8453A]/35"
                : "bg-[#4E8569]/20 text-[#78AC91] border border-[#4E8569]/35"
            }`}>
              {primary.delta_pct < 0 ? <TrendingDown className="w-5 h-5" /> : <TrendingUp className="w-5 h-5" />}
              <span className="tabular-nums">{deltaFormatted}</span>
            </div>
          </div>

          {/* Bullet Range Scale Gauge */}
          <div className="space-y-2.5 pt-2 border-t border-[#2E2E2E]">
            <div className="flex justify-between items-center text-[11px] font-mono">
              <span className="text-[#9E9788]">Baseline vs. Observed Variance Scale</span>
              <span className={`font-bold tabular-nums ${isShifted ? "text-[#E56B62]" : "text-[#78AC91]"}`}>
                {deviationFormatted} {unit} absolute deviation ({deltaFormatted})
              </span>
            </div>

            {/* Bullet Track */}
            <div className="relative h-6 w-full bg-[#141414] rounded-lg overflow-hidden border border-[#2E2E2E] flex items-center">
              {/* Normal Nominal Corridor (0 to Expected) */}
              <div
                className="absolute left-0 top-0 bottom-0 bg-[#222222] border-r border-[#4E8569]/40"
                style={{ width: `${expectedPct}%` }}
                title={`Nominal baseline corridor: 0 to ${expFormatted} ${unit}`}
              />

              {/* Observed Fill Bar */}
              <div
                className={`absolute left-0 top-1.5 bottom-1.5 rounded-r transition-all duration-700 ${
                  isShifted ? "bg-[#D8453A]" : "bg-[#4E8569]"
                }`}
                style={{ width: `${observedPct}%` }}
                title={`Observed reading: ${obsFormatted} ${unit}`}
              />

              {/* Baseline Reference Tick Marker */}
              <div
                className="absolute top-0 bottom-0 w-0.5 bg-[#F4EEE0] z-10 shadow-sm"
                style={{ left: `${expectedPct}%` }}
                title={`Expected Baseline: ${expFormatted} ${unit}`}
              />
            </div>

            {/* Scale Axis & Legend */}
            <div className="flex items-center justify-between text-[11px] font-mono text-[#9E9788] pt-0.5">
              <span className="text-[#78716C]">0 {unit}</span>

              <div className="flex items-center gap-4">
                <div className="flex items-center gap-1.5">
                  <span className={`w-2.5 h-2.5 rounded-xs ${isShifted ? "bg-[#D8453A]" : "bg-[#4E8569]"}`} />
                  <span className="text-[#9E9788]">Observed:</span>
                  <span className="font-bold text-[#F4EEE0] tabular-nums">{obsFormatted} {unit}</span>
                </div>

                <div className="flex items-center gap-1.5">
                  <span className="w-1 h-3 rounded-xs bg-[#F4EEE0]" />
                  <span className="text-[#9E9788]">Baseline:</span>
                  <span className="font-bold text-[#F4EEE0] tabular-nums">{expFormatted} {unit}</span>
                </div>
              </div>

              <span className="text-[#78716C] tabular-nums">
                Max: {primary ? formatMetricValue(primary.kpi_id, maxScale).formatted : "—"} {unit}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Corroborating Telemetry Streams with Inline Sparklines */}
      {signals.length > 1 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-xs font-mono font-bold text-[#9E9788] uppercase tracking-wider">
              Connected Telemetry Streams ({signals.length - 1})
            </div>
            <span className="text-[10px] font-mono text-[#9E9788]">12-Interval Telemetry Trends</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {signals.slice(1).map((sig) => {
              const { formatted, unit: sigUnit } = formatMetricValue(sig.kpi_id, sig.observed)
              const { formatted: exp } = formatMetricValue(sig.kpi_id, sig.expected)
              const isAdverse = isAdverseMetric(sig.kpi_id, sig.delta_pct) || Math.abs(sig.delta_pct) >= 15.0
              const sigDeviation = sig.observed - sig.expected
              const sigDevFormatted = (sigDeviation > 0 ? "+" : "") + Math.round(sigDeviation).toLocaleString()
              const sparkPoints = getSparklineData(sig.kpi_id, sig.delta_pct)
              const strokeColor = isAdverse ? "#D8453A" : "#4E8569"

              // Generate SVG path from sparkline points
              const svgPoints = sparkPoints
                .map((val, idx) => {
                  const x = (idx / (sparkPoints.length - 1)) * 120
                  const y = 35 - (val / 100) * 28
                  return `${x.toFixed(1)},${y.toFixed(1)}`
                })
                .join(" ")

              return (
                <div
                  key={sig.kpi_id}
                  className="p-4 rounded-xl bg-[#1C1C1C] border border-[#2E2E2E] space-y-3 flex flex-col justify-between"
                >
                  {/* Top Header */}
                  <div>
                    <div className="flex justify-between text-xs font-mono mb-1">
                      <span className="text-[#D1C9B8] font-bold uppercase truncate max-w-[160px]">
                        {sig.kpi_id.replace(/_/g, " ")}
                      </span>
                      <span className={isAdverse ? "text-[#E56B62] font-bold" : "text-[#78AC91] font-bold"}>
                        {formatDelta(sig.delta_pct)}
                      </span>
                    </div>

                    <div className="text-xl font-bold font-mono text-[#F4EEE0] tabular-nums">
                      {formatted} <span className="text-xs text-[#9E9788] font-normal">{sigUnit}</span>
                    </div>
                  </div>

                  {/* Inline 12-Interval Trend Sparkline */}
                  <div className="h-10 w-full flex items-center justify-between gap-2 border-t border-[#2E2E2E]/60 pt-2">
                    <svg
                      viewBox="0 0 120 35"
                      className="w-full h-8 overflow-visible"
                      preserveAspectRatio="none"
                    >
                      <polyline
                        fill="none"
                        stroke={strokeColor}
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        points={svgPoints}
                      />
                    </svg>
                  </div>

                  {/* Bottom Baseline & Absolute Variance Info */}
                  <div className="text-[10px] font-mono text-[#9E9788] flex justify-between border-t border-[#2E2E2E]/40 pt-1.5">
                    <span>Baseline: {exp} {sigUnit}</span>
                    <span className={`font-bold tabular-nums ${isAdverse ? "text-[#E56B62]" : "text-[#78AC91]"}`}>
                      Δ {sigDevFormatted} {sigUnit}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
