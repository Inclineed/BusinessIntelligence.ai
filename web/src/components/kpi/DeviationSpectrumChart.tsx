import React from "react"
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ReferenceArea,
  Cell,
} from "recharts"
import { AnomalySignal } from "../../types/investigation"

interface DeviationSpectrumChartProps {
  signals: AnomalySignal[]
}

export const DeviationSpectrumChart: React.FC<DeviationSpectrumChartProps> = ({ signals }) => {
  if (!signals || signals.length === 0) return null

  const data = signals.map((s) => ({
    kpi: s.kpi_id.replace(/_/g, " ").toUpperCase(),
    z_score: Number(s.z_score.toFixed(2)),
    delta_pct: s.delta_pct,
    observed: s.observed,
    expected: s.expected,
    is_anomaly: s.is_anomaly,
  }))

  const maxZInSignals = data.length > 0 ? Math.max(...data.map((d) => Math.abs(d.z_score))) : 3.0
  const maxAbsZ = Math.max(4.0, maxZInSignals * 1.25)

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const d = payload[0].payload
      return (
        <div className="bg-surface-raised border border-hairline-bright p-3 rounded-md shadow-xl text-xs font-mono">
          <div className="font-bold text-white mb-1.5">{d.kpi}</div>
          <div className="space-y-1 text-muted-foreground">
            <div className="flex justify-between gap-4">
              <span>Z-Score Deviation:</span>
              <span className={d.is_anomaly ? "text-semantic-critical font-bold" : "text-white"}>
                {d.z_score > 0 ? `+${d.z_score}` : d.z_score}σ
              </span>
            </div>
            <div className="flex justify-between gap-4">
              <span>Delta Shift:</span>
              <span className="text-white">{d.delta_pct > 0 ? `+${d.delta_pct.toFixed(1)}` : d.delta_pct.toFixed(1)}%</span>
            </div>
            <div className="flex justify-between gap-4">
              <span>Status:</span>
              <span className={d.is_anomaly ? "text-semantic-critical font-bold" : "text-semantic-positive"}>
                {d.is_anomaly ? "CONFIRMED ANOMALY" : "NOMINAL"}
              </span>
            </div>
          </div>
        </div>
      )
    }
    return null
  }

  return (
    <div className="p-5 rounded-lg bg-surface border border-hairline shadow-card">
      <div className="flex justify-between items-center mb-4">
        <div>
          <h2 className="text-xs font-mono font-bold uppercase tracking-wider text-white">
            Statistical Deviation Spectrum (Z-Score σ)
          </h2>
          <p className="text-[11px] text-muted-foreground mt-0.5">
            Metrics outside the shaded ±3.0σ decision corridor trigger formal anomaly attribution.
          </p>
        </div>
        <div className="flex items-center gap-3 font-mono text-[10px] text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-semantic-critical"></span> Anomaly (&gt;3σ)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-surface-hover border border-hairline"></span> Nominal Band
          </span>
        </div>
      </div>

      <div className="h-[220px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            layout="vertical"
            data={data}
            margin={{ top: 10, right: 30, left: 120, bottom: 10 }}
          >
            {/* Shaded ±3.0σ Decision Corridor */}
            <ReferenceArea x1={-3.0} x2={3.0} fill="#161F2E" fillOpacity={0.6} />
            <ReferenceLine x={-3.0} stroke="#1E2B3E" strokeDasharray="3 3" />
            <ReferenceLine x={3.0} stroke="#1E2B3E" strokeDasharray="3 3" />
            <ReferenceLine x={0} stroke="#2A3D58" strokeWidth={1.5} />

            <XAxis
              type="number"
              domain={[-maxAbsZ, maxAbsZ]}
              tick={{ fill: "#64748B", fontSize: 10, fontFamily: "JetBrains Mono" }}
              axisLine={{ stroke: "#1E2B3E" }}
              tickLine={{ stroke: "#1E2B3E" }}
              tickFormatter={(v) => `${v > 0 ? "+" : ""}${v}σ`}
            />
            <YAxis
              type="category"
              dataKey="kpi"
              tick={{ fill: "#94A3B8", fontSize: 11, fontFamily: "JetBrains Mono", fontWeight: 500 }}
              axisLine={{ stroke: "#1E2B3E" }}
              tickLine={false}
              width={140}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
            <Bar dataKey="z_score" barSize={12} radius={[3, 3, 3, 3]}>
              {data.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={entry.is_anomaly ? "#F05252" : "#3B82F6"}
                  opacity={entry.is_anomaly ? 1 : 0.45}
                />
              ))}
            </Bar>
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
