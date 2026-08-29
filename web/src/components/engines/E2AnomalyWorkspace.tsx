import React, { useState, useEffect } from "react"
import { InvestigationResult } from "../../types/investigation"
import { AnomalyCorridorChart } from "../kpi/AnomalyCorridorChart"
import { formatZScore, formatDelta } from "../../lib/utils"
import {
  AlertTriangle,
  CheckCircle2,
  DollarSign,
  Layers,
  ShieldAlert,
  ArrowDownRight,
  ArrowUpRight,
  Activity,
  Filter,
  Target,
  ChevronDown,
  ChevronUp,
} from "lucide-react"

interface E2AnomalyWorkspaceProps {
  result: InvestigationResult
}

export const E2AnomalyWorkspace: React.FC<E2AnomalyWorkspaceProps> = ({ result }) => {
  const signals = result.signals || []
  const materialityList = result.materiality || []
  const anomalousCount = signals.filter((s) => s.is_anomaly).length

  // Find top priority ranked stream
  const topMateriality = materialityList.find((m) => m.priority_rank === 1) || materialityList[0]
  const defaultSelectedId = topMateriality?.kpi_id || signals[0]?.kpi_id || ""

  const [selectedKpiId, setSelectedKpiId] = useState<string>(defaultSelectedId)

  // Update selected KPI if the scenario changes
  useEffect(() => {
    if (defaultSelectedId) {
      setSelectedKpiId(defaultSelectedId)
    }
  }, [result.scenario_id, defaultSelectedId])

  const formatBusinessImpact = (financialImpact?: number | null, volumeImpact?: number | null) => {
    if (financialImpact != null) {
      return `$${financialImpact.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
    }
    if (volumeImpact != null) {
      return `${volumeImpact.toLocaleString()} units`
    }
    return "—"
  }

  const getTierBadge = (tier: string) => {
    switch (tier) {
      case "CRITICAL":
        return "bg-[#D8453A]/20 text-[#E56B62] border-[#D8453A]/40"
      case "VERIFIED":
        return "bg-[#C46830]/20 text-[#E88E52] border-[#C46830]/40"
      case "MARGINAL":
        return "bg-[#A88232]/20 text-[#DEC06A] border-[#A88232]/40"
      case "REJECTED":
        return "bg-[#4E8569]/20 text-[#78AC91] border-[#4E8569]/40"
      default:
        return "bg-[#222222] text-[#9E9788] border-[#333333]"
    }
  }

  // Sorted materiality streams
  const sortedMateriality = materialityList
    .slice()
    .sort((a, b) => (a.priority_rank || 99) - (b.priority_rank || 99))

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Stage Header */}
      <header className="space-y-2 border-b border-[#2E2E2E] pb-4">
        <div className="flex items-center justify-between">
          <span className="px-2 py-0.5 rounded bg-[#D8453A]/20 text-[#F4EEE0] font-mono text-xs font-bold border border-[#D8453A]/40">
            STAGE E2 · QUALIFY &amp; PRIORITIZE
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#1C1C1C] text-[#9E9788] border border-[#2E2E2E]">
            [STATS + RULES]
          </span>
        </div>
        <h1 className="text-2xl font-bold font-sans text-[#F4EEE0] tracking-tight">
          Statistical Qualification &amp; Materiality Prioritization
        </h1>
        <p className="text-xs text-[#9E9788] font-sans leading-relaxed max-w-3xl">
          Disentangles raw statistical variance (±3σ thresholds) from domain economic impact. Select any ranked stream to inspect its statistical significance, converted business loss, and anomaly corridor.
        </p>
      </header>

      {/* 1. Qualification Funnel Pipeline Overview */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 font-mono">
        <div className="p-4 rounded-xl bg-[#1C1C1C] border border-[#2E2E2E] space-y-1">
          <div className="flex items-center gap-1.5 text-[10px] text-[#9E9788] uppercase tracking-wider">
            <Activity className="w-3.5 h-3.5 text-[#6B9BB0]" /> Ingested Streams
          </div>
          <div className="text-2xl font-bold text-[#F4EEE0] tabular-nums">
            {signals.length} <span className="text-xs text-[#9E9788] font-normal">streams</span>
          </div>
          <div className="text-[10px] text-[#78716C]">Monitored telemetry feeds</div>
        </div>

        <div className="p-4 rounded-xl bg-[#1C1C1C] border border-[#2E2E2E] space-y-1">
          <div className="flex items-center gap-1.5 text-[10px] text-[#9E9788] uppercase tracking-wider">
            <Filter className="w-3.5 h-3.5 text-[#D8453A]" /> Statistical Filter
          </div>
          <div className="text-2xl font-bold text-[#E56B62] tabular-nums">
            {anomalousCount} <span className="text-xs text-[#9E9788] font-normal">anomalies</span>
          </div>
          <div className="text-[10px] text-[#78716C]">Breached |z| &gt; 3.0σ gate</div>
        </div>

        <div className="p-4 rounded-xl bg-[#1C1C1C] border border-[#2E2E2E] space-y-1">
          <div className="flex items-center gap-1.5 text-[10px] text-[#9E9788] uppercase tracking-wider">
            <Target className="w-3.5 h-3.5 text-[#4E8569]" /> Primary Target
          </div>
          <div className="text-sm font-bold text-[#F4EEE0] uppercase truncate">
            {topMateriality ? topMateriality.kpi_id.replace(/_/g, " ") : "None"}
          </div>
          <div className="text-[10px] text-[#78AC91] font-bold">
            {topMateriality?.business_materiality || "CRITICAL"} Tier · Rank #1
          </div>
        </div>
      </div>

      {/* 2. Unified Expandable Prioritization Table with Inline Qualification & Corridor */}
      <div className="p-5 rounded-2xl bg-[#1C1C1C] border border-[#2E2E2E] space-y-4 font-mono">
        <div className="flex items-center justify-between text-xs border-b border-[#2A2A2A] pb-3">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-[#6B9BB0]" />
            <span className="font-bold text-[#F4EEE0]">Materiality &amp; Investigation Prioritization Table</span>
          </div>
          <span className="text-[10px] text-[#9E9788]">
            {sortedMateriality.filter((m) => m.is_statistical_anomaly).length} Qualified Stream(s) · Click row to inspect
          </span>
        </div>

        {/* Table Rows Container */}
        <div className="space-y-3">
          {sortedMateriality.map((m) => {
            const isSelected = m.kpi_id === selectedKpiId
            const isPrimary = m.priority_rank === 1
            const matchingSignal = signals.find((s) => s.kpi_id === m.kpi_id)
            const isAnomaly = matchingSignal?.is_anomaly ?? m.is_statistical_anomaly

            return (
              <div
                key={m.kpi_id}
                className={`rounded-xl border transition-all overflow-hidden ${
                  isSelected
                    ? "bg-[#222222]/90 border-[#6B9BB0]/40 shadow-xl ring-1 ring-[#6B9BB0]/20"
                    : "bg-[#181818] border-[#2A2A2A] hover:border-[#383838] hover:bg-[#1E1E1E]"
                }`}
              >
                {/* Clickable Header Row */}
                <button
                  type="button"
                  onClick={() => setSelectedKpiId(isSelected ? "" : m.kpi_id)}
                  className="w-full p-4 flex flex-col md:flex-row md:items-center justify-between gap-3 text-left cursor-pointer transition-colors"
                >
                  {/* Left: Rank & Stream Title */}
                  <div className="flex items-center gap-3 min-w-[240px]">
                    <div className="flex items-center gap-1.5">
                      <span className={`text-sm font-bold ${isPrimary ? "text-[#E56B62]" : "text-[#6B9BB0]"}`}>
                        {m.priority_rank > 0 ? `#${m.priority_rank}` : "—"}
                      </span>
                      {isPrimary && (
                        <span className="px-1.5 py-0.2 rounded bg-[#D8453A]/20 text-[#E56B62] border border-[#D8453A]/30 text-[9px] font-bold">
                          PRIMARY
                        </span>
                      )}
                    </div>

                    <span className="text-xs font-bold text-[#F4EEE0] uppercase truncate">
                      {m.kpi_id.replace(/_/g, " ")}
                    </span>
                  </div>

                  {/* Center-Right: Metrics Columns */}
                  <div className="grid grid-cols-3 md:grid-cols-4 gap-4 items-center text-xs flex-1 max-w-xl">
                    <div className="text-right">
                      <div className="text-[9px] text-[#78716C] uppercase">Movement</div>
                      <div className="font-bold tabular-nums text-[#D1C9B8]">
                        {formatDelta(m.delta_pct)}
                      </div>
                    </div>

                    <div className="text-right">
                      <div className="text-[9px] text-[#78716C] uppercase">Z-Score</div>
                      <div className="font-bold tabular-nums text-[#D8453A]">
                        {formatZScore(m.z_score)}
                      </div>
                    </div>

                    <div className="text-right">
                      <div className="text-[9px] text-[#78716C] uppercase">Business Loss</div>
                      <div className="font-bold tabular-nums text-[#F4EEE0]">
                        {formatBusinessImpact(m.financial_impact, m.volume_impact)}
                      </div>
                    </div>

                    <div className="text-center hidden md:block">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold border inline-block ${getTierBadge(
                          m.business_materiality
                        )}`}
                      >
                        {m.business_materiality}
                      </span>
                    </div>
                  </div>

                  {/* Right Expand Chevron */}
                  <div className="flex items-center justify-end pl-2 text-[#9E9788]">
                    {isSelected ? <ChevronUp className="w-4 h-4 text-[#F4EEE0]" /> : <ChevronDown className="w-4 h-4" />}
                  </div>
                </button>

                {/* Expanded Detail Workspace (Dual-Lens Cards + Interactive Corridor Chart) */}
                {isSelected && (
                  <div className="p-5 border-t border-[#2E2E2E] bg-[#171717] space-y-5 animate-fade-in">
                    {/* Dual-Lens Metric Summary Grid */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                      <div className="p-3 rounded-lg bg-[#1F1F1F] border border-[#2A2A2A] space-y-0.5">
                        <div className="text-[9px] text-[#9E9788] uppercase">KPI Movement</div>
                        <div className="text-lg font-bold text-[#F4EEE0] tabular-nums flex items-center gap-1">
                          {m.delta_pct < 0 ? (
                            <ArrowDownRight className="w-3.5 h-3.5 text-[#D8453A]" />
                          ) : (
                            <ArrowUpRight className="w-3.5 h-3.5 text-[#4E8569]" />
                          )}
                          {formatDelta(m.delta_pct)}
                        </div>
                        <div className="text-[9px] text-[#666666]">Baseline variance</div>
                      </div>

                      <div className="p-3 rounded-lg bg-[#1F1F1F] border border-[#2A2A2A] space-y-0.5">
                        <div className="text-[9px] text-[#9E9788] uppercase">Statistical Signif.</div>
                        <div className="text-lg font-bold text-[#D8453A] tabular-nums">
                          {formatZScore(m.z_score)}
                        </div>
                        <div className="text-[9px] text-[#666666]">Threshold: |z| &gt; 3.0σ</div>
                      </div>

                      <div className="p-3 rounded-lg bg-[#1F1F1F] border border-[#2A2A2A] space-y-0.5">
                        <div className="text-[9px] text-[#9E9788] uppercase">Est. Business Loss</div>
                        <div className="text-lg font-bold text-[#F4EEE0] tabular-nums">
                          {formatBusinessImpact(m.financial_impact, m.volume_impact)}
                        </div>
                        <div className="text-[9px] text-[#666666]">Domain converted impact</div>
                      </div>

                      <div className="p-3 rounded-lg bg-[#1F1F1F] border border-[#2A2A2A] space-y-0.5">
                        <div className="text-[9px] text-[#9E9788] uppercase">Materiality Tier</div>
                        <div className="pt-0.5">
                          <span
                            className={`px-2 py-0.5 rounded text-[11px] font-bold border inline-flex items-center gap-1 ${getTierBadge(
                              m.business_materiality
                            )}`}
                          >
                            <ShieldAlert className="w-3 h-3" />
                            {m.business_materiality}
                          </span>
                        </div>
                        <div className="text-[9px] text-[#666666]">
                          {isPrimary ? "Primary Investigation Gate" : "Secondary Corroboration"}
                        </div>
                      </div>
                    </div>

                    {/* Integrated Time-Series Anomaly Corridor Chart (±3σ) */}
                    <div className="border border-[#2A2A2A] rounded-xl overflow-hidden">
                      <AnomalyCorridorChart
                        scenarioId={result.scenario_id}
                        signal={matchingSignal}
                        kpiLabel={`${m.kpi_id.replace(/_/g, " ").toUpperCase()} ANOMALY CORRIDOR (±3Σ)`}
                      />
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
