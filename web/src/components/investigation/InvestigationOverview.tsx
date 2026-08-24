import React, { useState } from "react"
import { InvestigationResult, PersonaType } from "../../types/investigation"
import { formatMetricValue, formatDelta } from "../../lib/utils"
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceDot,
  CartesianGrid,
} from "recharts"
import { 
  TrendingUp, 
  TrendingDown, 
  CheckCircle2, 
  ChevronRight, 
  FileText, 
  Sparkles, 
  Activity, 
  RefreshCw,
  ShieldCheck,
  AlertCircle,
  Database,
  ArrowRight
} from "lucide-react"

interface InvestigationOverviewProps {
  result: InvestigationResult
  onRunLive?: (scenarioId: string, persona: PersonaType) => void
  isLiveLoading?: boolean
}

export const InvestigationOverview: React.FC<InvestigationOverviewProps> = ({ 
  result, 
  onRunLive,
  isLiveLoading = false 
}) => {
  const [selectedScenario, setSelectedScenario] = useState(result.scenario_id || "INC_001")
  const [selectedPersona, setSelectedPersona] = useState<PersonaType>(result.persona || "analyst")
  const [activeEvidenceModal, setActiveEvidenceModal] = useState<any | null>(null)

  const { scenario_id, persona, signals = [], evidence = [], hypotheses = [], scored = [], decision = {} } = result

  // Titles dictionary for scenarios
  const scenarioTitles: Record<string, string> = {
    INC_001: "Payment Gateway Latency Regression",
    INC_002: "Simultaneous Conflicting Causes",
    INC_004: "ETL Ingestion Pipeline Delay",
    INC_006: "Compound Network & Deploy Failure",
    INC_008: "Enterprise SAML SSO Outage",
  }

  const title = scenarioTitles[scenario_id] || "Payment Gateway Latency Regression"

  // Primary KPI and supporting signals
  const anomalies = signals.filter((s) => s.is_anomaly)
  const primarySignal = anomalies[0] || signals[0] || {}
  const kpiTitle = (primarySignal.kpi_id || "gateway_latency_15min").replace(/_/g, " ")

  // Construct smooth time-series chart data
  const base = primarySignal.expected || 180
  const observed = primarySignal.observed || 612
  const chartPoints = [
    { time: "13:45", baseline: base * 0.98, actual: base * 0.99, isAnomaly: false },
    { time: "13:50", baseline: base * 1.01, actual: base * 1.00, isAnomaly: false },
    { time: "13:55", baseline: base * 0.99, actual: base * 1.02, isAnomaly: false },
    { time: "14:00", baseline: base * 1.00, actual: base * 0.98, isAnomaly: false },
    { time: "14:05", baseline: base * 1.02, actual: base * 1.01, isAnomaly: false },
    { time: "14:10", baseline: base * 0.99, actual: base * 1.03, isAnomaly: false },
    { time: "14:15", baseline: base * 1.00, actual: base * 1.15, isAnomaly: false },
    { time: "14:20", baseline: base * 1.01, actual: base * 1.85, isAnomaly: false },
    { time: "14:25", baseline: base * 0.98, actual: base * 2.45, isAnomaly: false },
    { time: "14:30", baseline: base * 1.00, actual: observed, isAnomaly: true },
  ]

  // Primary Hypothesis & Decision
  const winnerId = decision.winning_hypothesis_id || "H1"
  const winningHyp = hypotheses.find((h) => h.hypothesis_id === winnerId) || hypotheses[0]
  const winningScored = scored.find((s) => s.hypothesis_id === winnerId) || scored[0]

  const cleanStatement = winningHyp?.statement
    ? winningHyp.statement.replace(/\[LLM_NARRATIVE\]|\[LLM\]|\[RULES\]/g, "").trim()
    : "Payment gateway latency spike is driven by connection pool exhaustion introduced in the Checkout Service v4.3 release."

  const cleanAction = decision.recommended_action
    ? decision.recommended_action.replace(/\[LLM_NARRATIVE\]|\[LLM\]/g, "").trim()
    : "Roll back Checkout Service from v4.3 to v4.2 immediately to restore database connection pool capacity."

  const sortedScores = [...scored].sort((a, b) => b.final_score - a.final_score)
  const winnerGap = sortedScores.length > 1 ? sortedScores[0].final_score - sortedScores[1].final_score : 0.41
  const confidenceState = winningScored?.confidence_state || "HIGH"

  const handleTriggerRun = () => {
    if (onRunLive) {
      onRunLive(selectedScenario, selectedPersona)
    }
  }

  return (
    <div className="min-h-screen bg-[#0A0A0A] text-white font-sans selection:bg-emerald-500/20">
      {/* ── 1. Compact Professional Top Navigation ───────────────────────── */}
      <nav className="h-16 border-b border-white/5 bg-[#0F0F12]/80 backdrop-blur-xl sticky top-0 z-40 flex items-center justify-between px-6 lg:px-10">
        <div className="flex items-center gap-8">
          <div className="font-semibold text-base tracking-tight flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
              <Activity className="w-4 h-4" />
            </div>
            <span className="text-white">BusinessIntelligence</span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-white/5 text-neutral-400 border border-white/5 font-normal">
              AI Analytics
            </span>
          </div>

          <div className="hidden md:flex items-center gap-6 text-sm font-medium text-neutral-400">
            <span className="text-white font-semibold">Overview</span>
            <span className="hover:text-white cursor-pointer transition-colors">Incidents</span>
            <span className="hover:text-white cursor-pointer transition-colors">Signals</span>
            <span className="hover:text-white cursor-pointer transition-colors">Memory</span>
            <span className="hover:text-white cursor-pointer transition-colors">Audit</span>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="hidden sm:flex items-center gap-2 text-xs text-neutral-400 bg-white/5 px-3 py-1.5 rounded-full border border-white/5">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>Telemetry Pipeline Live</span>
          </div>

          <button
            onClick={handleTriggerRun}
            disabled={isLiveLoading}
            className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-black font-semibold text-xs transition-all shadow-[0_0_20px_rgba(34,197,94,0.25)] active:scale-95 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLiveLoading ? "animate-spin" : ""}`} />
            <span>{isLiveLoading ? "Analyzing..." : "Run Live Pipeline"}</span>
          </button>
        </div>
      </nav>

      {/* ── Main Dashboard Canvas ────────────────────────────────────────── */}
      <main className="max-w-[1400px] mx-auto px-6 lg:px-10 py-8 space-y-8">
        
        {/* ── 2. Investigation Header ─────────────────────────────────────── */}
        <header className="flex flex-col lg:flex-row lg:items-end justify-between gap-4 pb-2 border-b border-white/5">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-3 text-xs text-neutral-400 font-medium">
              <span className="px-2.5 py-1 rounded-full bg-white/5 text-white font-semibold border border-white/10">
                {scenario_id}
              </span>
              <span className="flex items-center gap-1.5 text-neutral-300">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                Scope: <strong className="text-white capitalize">{persona}</strong>
              </span>
              <span>•</span>
              <span>Global Region</span>
              <span>•</span>
              <span className="text-emerald-400 font-medium">Automated Attribution Complete</span>
            </div>

            <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight text-white">
              {title}
            </h1>
          </div>

          {/* Scenario & Persona Controls */}
          <div className="flex items-center gap-2.5 bg-[#141418] p-1.5 rounded-xl border border-white/5">
            <select
              value={selectedScenario}
              onChange={(e) => {
                setSelectedScenario(e.target.value)
                if (onRunLive) onRunLive(e.target.value, selectedPersona)
              }}
              className="bg-transparent text-xs text-white font-medium px-2.5 py-1.5 rounded-lg outline-none cursor-pointer hover:bg-white/5 transition-colors"
            >
              <option value="INC_001" className="bg-[#141418] text-white">INC_001 — Payment Latency</option>
              <option value="INC_002" className="bg-[#141418] text-white">INC_002 — Conflicting Causes</option>
              <option value="INC_004" className="bg-[#141418] text-white">INC_004 — ETL Delay</option>
              <option value="INC_006" className="bg-[#141418] text-white">INC_006 — Compound Failure</option>
              <option value="INC_008" className="bg-[#141418] text-white">INC_008 — SSO Outage</option>
            </select>

            <div className="w-px h-4 bg-white/10" />

            <select
              value={selectedPersona}
              onChange={(e) => {
                const p = e.target.value as PersonaType
                setSelectedPersona(p)
                if (onRunLive) onRunLive(selectedScenario, p)
              }}
              className="bg-transparent text-xs text-neutral-300 font-medium px-2.5 py-1.5 rounded-lg outline-none cursor-pointer hover:bg-white/5 transition-colors"
            >
              <option value="analyst" className="bg-[#141418] text-white">Analyst (Full)</option>
              <option value="cfo" className="bg-[#141418] text-white">CFO (Executive)</option>
              <option value="manager" className="bg-[#141418] text-white">Manager (Regional)</option>
            </select>
          </div>
        </header>

        {/* ── 3. KPI Cards ───────────────────────────────────────────────── */}
        <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {signals.slice(0, 4).map((sig) => {
            const isAnomaly = sig.is_anomaly
            const { formatted, unit } = formatMetricValue(sig.kpi_id, sig.observed)
            const { formatted: baseFormatted, unit: baseUnit } = formatMetricValue(sig.kpi_id, sig.expected)
            const delta = sig.delta_pct || 0
            const isHigher = delta > 0

            return (
              <div
                key={sig.kpi_id}
                className={`p-5 rounded-2xl bg-[#121216] border transition-all duration-200 flex flex-col justify-between ${
                  isAnomaly 
                    ? "border-red-500/20 bg-gradient-to-b from-[#161316] to-[#121216] shadow-[0_4px_25px_rgba(239,68,68,0.06)]" 
                    : "border-white/5 hover:border-white/10"
                }`}
              >
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-neutral-400 capitalize tracking-wide">
                      {sig.kpi_id.replace(/_/g, " ")}
                    </span>
                    {isAnomaly ? (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-red-500/10 text-red-400 border border-red-500/20">
                        Anomaly
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-white/5 text-neutral-400 border border-white/5">
                        Nominal
                      </span>
                    )}
                  </div>

                  <div className="flex items-baseline gap-2">
                    <span className="text-3xl font-semibold tracking-tight text-white">
                      {formatted}{unit}
                    </span>
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-white/5 flex items-center justify-between text-xs text-neutral-400">
                  <span>
                    Baseline: <strong className="text-neutral-200 font-medium">{baseFormatted}{baseUnit}</strong>
                  </span>
                  <span
                    className={`font-semibold flex items-center gap-0.5 ${
                      isAnomaly ? "text-red-400" : isHigher ? "text-emerald-400" : "text-neutral-300"
                    }`}
                  >
                    {isHigher ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
                    {formatDelta(delta)}
                  </span>
                </div>
              </div>
            )
          })}
        </section>

        {/* ── 4. Large Analytical Chart & Causal Panels (Grid) ────────────── */}
        <section className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          
          {/* Chart Component (7 cols) */}
          <div className="lg:col-span-7 p-6 rounded-3xl bg-[#121216] border border-white/5 flex flex-col justify-between">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-base font-semibold text-white capitalize">{kpiTitle} Trajectory</h2>
                <p className="text-xs text-neutral-400 mt-0.5">Observed shock vs statistical baseline corridor</p>
              </div>

              <div className="flex items-center gap-4 text-xs">
                <div className="flex items-center gap-1.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/40 border border-emerald-500" />
                  <span className="text-neutral-400">Baseline Target</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-white" />
                  <span className="text-neutral-200">Observed</span>
                </div>
              </div>
            </div>

            <div className="w-full h-[280px]">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartPoints} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="emeraldGlow" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.18} />
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" vertical={false} />
                  <XAxis 
                    dataKey="time" 
                    axisLine={false} 
                    tickLine={false} 
                    tick={{ fill: "#737373", fontSize: 11 }} 
                    dy={8}
                  />
                  <YAxis 
                    axisLine={false} 
                    tickLine={false} 
                    tick={{ fill: "#737373", fontSize: 11 }} 
                  />
                  <Tooltip
                    contentStyle={{ 
                      backgroundColor: "#17171C", 
                      border: "1px solid rgba(255,255,255,0.08)", 
                      borderRadius: "12px", 
                      color: "#fff",
                      fontSize: "12px"
                    }}
                  />
                  <Area 
                    type="monotone" 
                    dataKey="baseline" 
                    stroke="rgba(16, 185, 129, 0.5)" 
                    fill="url(#emeraldGlow)" 
                    strokeWidth={1.5} 
                  />
                  <Line 
                    type="monotone" 
                    dataKey="actual" 
                    stroke="#ffffff" 
                    strokeWidth={2.5} 
                    dot={false}
                  />
                  <ReferenceDot
                    x={chartPoints[chartPoints.length - 1].time}
                    y={chartPoints[chartPoints.length - 1].actual}
                    r={6}
                    fill="#ef4444"
                    stroke="rgba(239, 68, 68, 0.35)"
                    strokeWidth={10}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* ── 5 & 6. Primary Hypothesis & Recommendation Panels (5 cols) ── */}
          <div className="lg:col-span-5 flex flex-col gap-4 justify-between">
            
            {/* 5. Primary Hypothesis Panel */}
            <div className="p-6 rounded-3xl bg-[#121216] border border-white/5 flex-1 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-emerald-400" />
                    <span className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
                      Primary Causal Hypothesis
                    </span>
                  </div>
                  <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    {winnerId}
                  </span>
                </div>

                <p className="text-sm text-neutral-100 font-medium leading-relaxed">
                  {cleanStatement}
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3 mt-4 pt-4 border-t border-white/5">
                <div className="p-3 rounded-xl bg-white/[0.02] border border-white/5">
                  <div className="text-[11px] text-neutral-400 mb-0.5">Confidence State</div>
                  <div className="text-base font-semibold text-white flex items-center gap-1.5">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <span>{confidenceState}</span>
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-white/[0.02] border border-white/5">
                  <div className="text-[11px] text-neutral-400 mb-0.5">Winner Separation</div>
                  <div className="text-base font-semibold text-emerald-400">
                    +{winnerGap.toFixed(2)}
                  </div>
                </div>
              </div>
            </div>

            {/* 6. Recommendation Panel */}
            <div className="p-6 rounded-3xl bg-gradient-to-br from-emerald-950/30 to-[#121216] border border-emerald-500/20 shadow-[0_4px_30px_rgba(16,185,129,0.05)]">
              <div className="flex items-center gap-2 mb-2 text-emerald-400">
                <ShieldCheck className="w-4 h-4" />
                <h3 className="text-xs font-semibold uppercase tracking-wider">
                  Prescribed Operational Action
                </h3>
              </div>

              <p className="text-sm font-medium text-neutral-100 leading-relaxed">
                {cleanAction}
              </p>

              {decision.verification_metric && (
                <div className="mt-3 text-[11px] text-neutral-400 flex items-center gap-1.5">
                  <span className="text-neutral-500">Verification:</span>
                  <span className="text-emerald-400/90 font-medium">{decision.verification_metric}</span>
                </div>
              )}
            </div>
          </div>
        </section>

        {/* ── 7. Evidence / Supporting Factors Section ────────────────────── */}
        <section className="space-y-4 pt-2">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-white">Empirical Evidence & Telemetry Linkage</h2>
            <span className="text-xs text-neutral-400">{evidence.length} authorized factors retrieved</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {evidence.slice(0, 3).map((ev) => (
              <div
                key={ev.evidence_id}
                onClick={() => setActiveEvidenceModal(ev)}
                className="p-5 rounded-2xl bg-[#121216] border border-white/5 hover:border-emerald-500/30 transition-all duration-150 cursor-pointer group flex flex-col justify-between min-h-[140px]"
              >
                <div>
                  <div className="flex items-center justify-between mb-2.5">
                    <span className="px-2.5 py-0.5 rounded-full bg-white/5 text-[11px] font-medium text-neutral-300 capitalize border border-white/5">
                      {ev.source_id.replace(/_/g, " ")}
                    </span>
                    <span className="text-[10px] text-neutral-500 font-mono">
                      Weight: {(ev.reliability_weight * 100).toFixed(0)}%
                    </span>
                  </div>

                  <p className="text-xs text-neutral-300 leading-relaxed line-clamp-3">
                    {ev.summary}
                  </p>
                </div>

                <div className="mt-4 flex items-center justify-between text-xs text-neutral-400 pt-3 border-t border-white/5">
                  <span className="text-[11px] font-mono text-neutral-500">{ev.evidence_id}</span>
                  <span className="text-emerald-400 group-hover:translate-x-0.5 transition-transform flex items-center font-medium">
                    Inspect <ChevronRight className="w-3.5 h-3.5 ml-0.5" />
                  </span>
                </div>
              </div>
            ))}
          </div>
        </section>
      </main>

      {/* Detail Modal for Evidence Inspection */}
      {activeEvidenceModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4" onClick={() => setActiveEvidenceModal(null)}>
          <div className="max-w-lg w-full bg-[#16161B] border border-white/10 rounded-2xl p-6 space-y-4 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between pb-3 border-b border-white/5">
              <span className="text-xs font-semibold text-emerald-400 px-2.5 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20">
                {activeEvidenceModal.evidence_id}
              </span>
              <button onClick={() => setActiveEvidenceModal(null)} className="text-neutral-400 hover:text-white text-sm">✕</button>
            </div>
            <div>
              <div className="text-xs text-neutral-400 uppercase font-semibold mb-1">Source: {activeEvidenceModal.source_id}</div>
              <p className="text-sm text-neutral-100 leading-relaxed font-sans">{activeEvidenceModal.summary}</p>
            </div>
            {activeEvidenceModal.raw_ref && (
              <div className="p-3 rounded-lg bg-black/40 border border-white/5 text-xs font-mono text-neutral-400">
                Ref: {activeEvidenceModal.raw_ref}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
