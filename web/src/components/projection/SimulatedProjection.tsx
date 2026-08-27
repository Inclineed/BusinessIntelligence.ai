import React from "react"
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  Legend,
} from "recharts"
import { AlertCircle, TrendingUp } from "lucide-react"
import { OutcomeProjection, AnomalySignal } from "../../types/investigation"

interface SimulatedProjectionProps {
  outcome?: OutcomeProjection
  signals?: AnomalySignal[]
}

export const SimulatedProjection: React.FC<SimulatedProjectionProps> = ({ outcome, signals = [] }) => {
  const primarySignal = signals.find((s) => s.is_anomaly) || signals[0] || {}
  const delta = primarySignal.delta_pct || -12.0
  const recoveryPct = outcome?.projected_recovery_pct ?? 0
  const metricName = outcome?.projected_metric || primarySignal.kpi_id || "Revenue / Conversion"
  const disclaimer =
    outcome?.disclaimer ||
    "Model-generated projection based on historical anomaly rebound profiles — not empirical historical evidence."

  const drop = -Math.abs(delta)
  const target = drop * (1.0 - recoveryPct / 100.0)

  interface TrajectoryPoint {
    period: string
    observed: number | null
    simulated: number | null
    uncertainty_low: number | null
    uncertainty_high: number | null
    band: [number, number] | null
  }

  // Construct trajectory data
  const data: TrajectoryPoint[] = []
  for (let t = -6; t <= 0; t++) {
    const frac = t < -2 ? 0.0 : (t + 2) / 2.0
    data.push({
      period: `t${t < 0 ? t : "+0"}`,
      observed: Number((100.0 + drop * frac).toFixed(2)),
      simulated: null,
      uncertainty_low: null,
      uncertainty_high: null,
      band: null,
    })
  }

  for (let t = 1; t <= 7; t++) {
    const k = t / 7.0
    const ease = 1 - Math.pow(1 - k, 2.2)
    const val = 100.0 + drop + (target - drop) * ease
    const spread = Math.abs(target - drop) * 0.35 * k + 0.6
    data.push({
      period: `t+${t}`,
      observed: null,
      simulated: Number(val.toFixed(2)),
      uncertainty_low: Number((val - spread).toFixed(2)),
      uncertainty_high: Number((val + spread).toFixed(2)),
      band: [Number((val - spread).toFixed(2)), Number((val + spread).toFixed(2))],
    })
  }

  // Add bridge point at t=0 for smooth transition
  const obsT0 = data[6].observed ?? 100.0
  data[6].simulated = obsT0
  data[6].uncertainty_low = obsT0
  data[6].uncertainty_high = obsT0
  data[6].band = [obsT0, obsT0]

  const residual = Math.abs(delta) * (1 - recoveryPct / 100.0)

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-surface-raised border border-hairline-bright p-3 rounded-md shadow-xl text-xs font-mono">
          <div className="font-bold text-white mb-1">Timeline Period: {label}</div>
          {payload.map((entry: any, index: number) => {
            if (entry.value === null || entry.dataKey === "band") return null
            return (
              <div key={index} className="flex justify-between gap-4 text-muted-foreground">
                <span style={{ color: entry.color }}>{entry.name}:</span>
                <span className="text-white font-bold">{entry.value}</span>
              </div>
            )
          })}
        </div>
      )
    }
    return null
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-sm font-mono font-bold uppercase tracking-wider text-white flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-semantic-neutral" />
          Simulated Recovery Trajectory & Impact Projection
        </h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Forward-looking projection modeling the expected recovery trajectory following the execution of the recommended operational action.
        </p>
      </div>

      {/* Watermark Banner */}
      <div className="p-3.5 rounded-lg bg-surface-raised border border-hairline-bright flex items-center gap-3">
        <span className="px-2.5 py-0.5 rounded text-[10px] font-mono font-bold bg-surface-hover text-semantic-simulated border border-hairline">
          SIMULATED DATA
        </span>
        <span className="text-xs text-muted-foreground leading-relaxed">{disclaimer}</span>
      </div>

      {/* Grid: Chart (8 cols) + Key Stats (4 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-8 p-5 rounded-lg bg-surface border border-hairline shadow-card">
          <div className="flex justify-between items-center mb-3">
            <span className="text-xs font-mono font-bold uppercase tracking-wider text-white">
              Recovery Performance Curve (Indexed to 100)
            </span>
            <div className="flex items-center gap-4 text-[10px] font-mono text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <span className="w-3 h-0.5 bg-semantic-critical"></span> Observed Shock
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-3 h-0.5 bg-semantic-neutral border-b border-dashed"></span> Simulated Recovery
              </span>
            </div>
          </div>

          <div className="h-[250px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={data} margin={{ top: 10, right: 20, left: 10, bottom: 5 }}>
                <XAxis
                  dataKey="period"
                  tick={{ fill: "#64748B", fontSize: 10, fontFamily: "JetBrains Mono" }}
                  axisLine={{ stroke: "#1E2B3E" }}
                />
                <YAxis
                  domain={["dataMin - 3", "dataMax + 3"]}
                  tick={{ fill: "#64748B", fontSize: 10, fontFamily: "JetBrains Mono" }}
                  axisLine={{ stroke: "#1E2B3E" }}
                />
                <Tooltip content={<CustomTooltip />} />
                <ReferenceLine y={100} stroke="#2A3D58" strokeDasharray="3 3" />
                <ReferenceLine x="t+0" stroke="#3F83F8" strokeDasharray="2 2" />

                {/* Uncertainty Band Area */}
                <Area
                  type="monotone"
                  dataKey="band"
                  name="Uncertainty Envelope"
                  stroke="none"
                  fill="#3F83F8"
                  fillOpacity={0.12}
                />

                {/* Observed Line */}
                <Line
                  type="monotone"
                  dataKey="observed"
                  name="Observed History"
                  stroke="#F05252"
                  strokeWidth={2.5}
                  dot={{ fill: "#F05252", r: 3 }}
                />

                {/* Simulated Line */}
                <Line
                  type="monotone"
                  dataKey="simulated"
                  name="Simulated Recovery"
                  stroke="#3F83F8"
                  strokeWidth={2}
                  strokeDasharray="4 4"
                  dot={{ fill: "#3F83F8", r: 3 }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Key Recovery Metrics */}
        <div className="lg:col-span-4 p-5 rounded-lg bg-surface border border-hairline shadow-card flex flex-col justify-between">
          <div>
            <div className="text-[11px] font-mono font-bold tracking-wider text-muted-foreground uppercase mb-1">
              PROJECTED RECOVERY RATE
            </div>
            <div className="text-3xl font-bold font-mono text-semantic-positive mb-3">
              {recoveryPct.toFixed(0)}%
            </div>

            <div className="w-full bg-surface-raised rounded-full h-2 overflow-hidden border border-hairline mb-4">
              <div
                className="bg-semantic-positive h-full rounded-full transition-all"
                style={{ width: `${recoveryPct}%` }}
              ></div>
            </div>
          </div>

          <div className="pt-4 border-t border-hairline-subtle space-y-2.5 font-mono text-xs">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Observed Shock:</span>
              <span className="text-semantic-critical font-bold">{delta > 0 ? "+" : ""}{delta.toFixed(1)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Residual Deficit:</span>
              <span className="text-semantic-warning font-bold">-{residual.toFixed(1)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Target KPI:</span>
              <span className="text-white font-semibold">{metricName}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
