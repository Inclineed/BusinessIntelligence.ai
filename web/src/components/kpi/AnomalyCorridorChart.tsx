import React from "react"
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  CartesianGrid,
} from "recharts"

interface AnomalyCorridorChartProps {
  scenarioId: string
  kpiLabel?: string
  data?: Array<{
    period: string
    observed: number
    baseline: number
    upperCorridor: number
    lowerCorridor: number
  }>
}

const DEFAULT_CHART_DATA = [
  { period: "10:00", observed: 5.62, baseline: 5.60, upperCorridor: 5.85, lowerCorridor: 5.35 },
  { period: "11:00", observed: 5.58, baseline: 5.61, upperCorridor: 5.86, lowerCorridor: 5.36 },
  { period: "12:00", observed: 5.65, baseline: 5.63, upperCorridor: 5.88, lowerCorridor: 5.38 },
  { period: "13:00", observed: 5.50, baseline: 5.60, upperCorridor: 5.85, lowerCorridor: 5.35 },
  { period: "14:00", observed: 4.82, baseline: 5.62, upperCorridor: 5.87, lowerCorridor: 5.37 }, // Anomaly onset
  { period: "15:00", observed: 4.75, baseline: 5.64, upperCorridor: 5.89, lowerCorridor: 5.39 },
  { period: "16:00", observed: 4.80, baseline: 5.65, upperCorridor: 5.90, lowerCorridor: 5.40 },
]

export const AnomalyCorridorChart: React.FC<AnomalyCorridorChartProps> = ({
  scenarioId,
  kpiLabel = "Hourly Metric Anomaly Corridor (±3σ)",
  data = DEFAULT_CHART_DATA,
}) => {
  return (
    <div className="p-5 rounded-2xl bg-[#1C1C1C] border border-[#2E2E2E] space-y-3">
      <div className="flex items-center justify-between gap-2 mb-1">
        <div>
          <div className="text-xs font-mono font-bold text-[#F4EEE0] uppercase tracking-wider">
            {kpiLabel}
          </div>
          <div className="text-[11px] font-mono text-[#9E9788]">
            Historical Baseline Window (μ ± 3σ) vs Observed Incident Trajectory
          </div>
        </div>
        <div className="flex items-center gap-3 text-[11px] font-mono">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-0.5 bg-[#9E9788]" />
            <span className="text-[#9E9788]">Baseline Corridor</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-0.5 bg-[#D8453A]" />
            <span className="text-[#E56B62] font-bold">Observed Anomaly</span>
          </div>
        </div>
      </div>

      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 25, right: 15, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="corridorGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#6B9BB0" stopOpacity={0.18} />
                <stop offset="95%" stopColor="#6B9BB0" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255, 255, 255, 0.05)" />
            <XAxis dataKey="period" stroke="#888888" fontSize={10} tickLine={false} />
            <YAxis stroke="#888888" fontSize={10} tickLine={false} domain={["dataMin - 0.5", "dataMax + 0.5"]} />
            <Tooltip
              contentStyle={{
                backgroundColor: "#181818",
                borderColor: "#333333",
                borderRadius: "10px",
                fontSize: "11px",
                fontFamily: "monospace",
                color: "#F4EEE0",
                boxShadow: "0 8px 24px rgba(0,0,0,0.6)",
              }}
            />
            {/* Shaded Corridor Range without hover dot */}
            <Area
              type="monotone"
              dataKey="upperCorridor"
              stroke="transparent"
              fill="url(#corridorGradient)"
              name="Upper 3σ Corridor"
              activeDot={false}
              isAnimationActive={false}
            />
            {/* Baseline Reference Line */}
            <Line
              type="monotone"
              dataKey="baseline"
              stroke="#9E9788"
              strokeWidth={1.5}
              strokeDasharray="4 4"
              dot={false}
              name="Expected Normal (μ)"
            />
            {/* Actual Observed Line */}
            <Line
              type="monotone"
              dataKey="observed"
              stroke="#D8453A"
              strokeWidth={2.5}
              dot={{ r: 3.5, fill: "#D8453A", strokeWidth: 1, stroke: "#F4EEE0" }}
              name="Observed Value"
            />
            {/* Anomaly Onset Reference Line with insideTop placement so it is never clipped */}
            <ReferenceLine
              x="14:00"
              stroke="#D8453A"
              strokeDasharray="3 3"
              label={{
                value: "ANOMALY ONSET (14:00)",
                fill: "#E56B62",
                fontSize: 10,
                position: "insideTop",
                dy: -18,
                fontFamily: "monospace",
                fontWeight: 600,
              }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
