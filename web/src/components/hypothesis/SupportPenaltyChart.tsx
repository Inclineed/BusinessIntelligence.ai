import React from "react"
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, ReferenceLine, Legend } from "recharts"
import { ScoredHypothesisItem } from "../../types/investigation"

interface SupportPenaltyChartProps {
  scored: ScoredHypothesisItem[]
}

export const SupportPenaltyChart: React.FC<SupportPenaltyChartProps> = ({ scored }) => {
  if (!scored || scored.length === 0) return null

  const data = scored.map((s) => ({
    hid: s.hypothesis_id,
    Support: Number(s.support_score.toFixed(2)),
    Penalty: -Number(Math.abs(s.contradiction_penalty).toFixed(2)),
    final: Number(s.final_score.toFixed(2)),
  }))

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const d = payload[0].payload
      return (
        <div className="bg-surface-raised border border-hairline-bright p-3 rounded-md shadow-xl text-xs font-mono">
          <div className="font-bold text-white mb-1.5">{d.hid} Scoring Balance</div>
          <div className="space-y-1 text-muted-foreground">
            <div className="flex justify-between gap-4">
              <span className="text-semantic-positive">Support Score:</span>
              <span className="text-white font-bold">+{d.Support}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-semantic-critical">Penalty Subtraction:</span>
              <span className="text-white font-bold">{d.Penalty}</span>
            </div>
            <div className="flex justify-between gap-4 pt-1 border-t border-hairline">
              <span>Final Net Score:</span>
              <span className="text-semantic-neutral font-bold">{d.final}</span>
            </div>
          </div>
        </div>
      )
    }
    return null
  }

  return (
    <div className="h-[180px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart layout="vertical" data={data} margin={{ top: 5, right: 30, left: 30, bottom: 5 }}>
          <XAxis
            type="number"
            domain={[-1.0, 1.0]}
            tick={{ fill: "#64748B", fontSize: 10, fontFamily: "JetBrains Mono" }}
            axisLine={{ stroke: "#1E2B3E" }}
            tickFormatter={(v) => `${v}`}
          />
          <YAxis
            type="category"
            dataKey="hid"
            tick={{ fill: "#94A3B8", fontSize: 11, fontFamily: "JetBrains Mono", fontWeight: 600 }}
            axisLine={{ stroke: "#1E2B3E" }}
            tickLine={false}
            width={40}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
          <Legend wrapperStyle={{ fontSize: "11px", fontFamily: "JetBrains Mono", paddingTop: "6px" }} />
          <ReferenceLine x={0} stroke="#2A3D58" strokeWidth={1.5} />
          <Bar dataKey="Support" fill="#31C48D" barSize={10} radius={[0, 2, 2, 0]} />
          <Bar dataKey="Penalty" fill="#F05252" barSize={10} radius={[2, 0, 0, 2]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
