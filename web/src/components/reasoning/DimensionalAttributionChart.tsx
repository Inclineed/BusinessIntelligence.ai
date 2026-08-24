import React from "react"
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Cell } from "recharts"
import { DimensionContribution } from "../../types/investigation"

interface DimensionalAttributionChartProps {
  contributions: DimensionContribution[]
}

export const DimensionalAttributionChart: React.FC<DimensionalAttributionChartProps> = ({ contributions }) => {
  if (!contributions || contributions.length === 0) return null

  const sorted = [...contributions].sort((a, b) => b.contribution_pct - a.contribution_pct)
  const data = sorted.map((c, i) => ({
    segment: `${c.dimension.toUpperCase()}: ${c.segment}`,
    contribution_pct: Number(c.contribution_pct.toFixed(1)),
    segment_delta_pct: c.segment_delta_pct,
    is_dominant: i === 0,
  }))

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const d = payload[0].payload
      return (
        <div className="bg-surface-raised border border-hairline-bright p-3 rounded-md shadow-xl text-xs font-mono">
          <div className="font-bold text-white mb-1">{d.segment}</div>
          <div className="flex justify-between gap-4 text-muted-foreground">
            <span>Variance Contribution:</span>
            <span className="text-white font-bold">{d.contribution_pct}%</span>
          </div>
          {d.segment_delta_pct !== undefined && (
            <div className="flex justify-between gap-4 text-muted-foreground">
              <span>Segment Delta:</span>
              <span className="text-semantic-critical font-bold">{d.segment_delta_pct.toFixed(1)}%</span>
            </div>
          )}
        </div>
      )
    }
    return null
  }

  return (
    <div className="h-[180px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart layout="vertical" data={data} margin={{ top: 5, right: 40, left: 100, bottom: 5 }}>
          <XAxis
            type="number"
            domain={[0, 100]}
            tick={{ fill: "#64748B", fontSize: 10, fontFamily: "JetBrains Mono" }}
            axisLine={{ stroke: "#1E2B3E" }}
            tickFormatter={(v) => `${v}%`}
          />
          <YAxis
            type="category"
            dataKey="segment"
            tick={{ fill: "#94A3B8", fontSize: 11, fontFamily: "JetBrains Mono" }}
            axisLine={{ stroke: "#1E2B3E" }}
            tickLine={false}
            width={120}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
          <Bar dataKey="contribution_pct" barSize={12} radius={[0, 3, 3, 0]}>
            {data.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={entry.is_dominant ? "#F05252" : "#3B82F6"}
                opacity={entry.is_dominant ? 1 : 0.4}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
