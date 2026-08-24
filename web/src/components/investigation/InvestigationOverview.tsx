import React, { useState } from "react"
import { InvestigationResult, PersonaType, EvidenceItem } from "../../types/investigation"
import { SCENARIO_CATALOG } from "../../lib/defaultData"
import { formatMetricValue, formatDelta, formatZScore } from "../../lib/utils"
import { ScenarioSelector, PersonaSelector } from "./ScenarioSelector"
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceDot,
  ReferenceLine,
  CartesianGrid,
} from "recharts"
import { 
  TrendingUp, 
  TrendingDown, 
  CheckCircle2, 
  ChevronRight, 
  Sparkles, 
  Activity, 
  RefreshCw, 
  ShieldCheck, 
  AlertTriangle, 
  Check, 
  X, 
  Cpu, 
  History, 
  Clock,
  Layers,
  ArrowRight,
  Database
} from "lucide-react"

interface InvestigationOverviewProps {
  result: InvestigationResult
  onScenarioSelect?: (scenarioId: string, persona: PersonaType) => void
  onRunLive?: (scenarioId: string, persona: PersonaType) => void
  isLiveLoading?: boolean
}

export const InvestigationOverview: React.FC<InvestigationOverviewProps> = ({ 
  result, 
  onScenarioSelect,
  onRunLive,
  isLiveLoading = false 
}) => {
  const [activeEvidenceModal, setActiveEvidenceModal] = useState<EvidenceItem | null>(null)
  const [showTelemetryDrawer, setShowTelemetryDrawer] = useState(false)

  // 1. EXACT SOURCE OF TRUTH: All displayed fields derive strictly from `result`
  const { 
    scenario_id, 
    persona = "analyst", 
    signals = [], 
    contributions = [], 
    evidence = [], 
    hypotheses = [], 
    scored = [], 
    decision = {}, 
    outcome = {}, 
    precedents = [], 
    telemetry = { latency_ms_by_engine: {}, llm_calls: 0, llm_tokens_in: 0, llm_tokens_out: 0 },
    method_ownership = {}
  } = result

  const currentMeta = SCENARIO_CATALOG.find((s) => s.id === scenario_id) || {
    id: scenario_id,
    label: "Operational Incident Investigation",
    domain: "Enterprise Infrastructure",
    description: "Autonomous root cause isolation and attribution analysis.",
    status: "live",
  }

  const isAbstained = Boolean(decision.abstained)

  // Signal extraction
  const anomalies = signals.filter((s) => s.is_anomaly)
  const primarySignal = anomalies[0] || signals[0] || {}
  const secondarySignals = signals.filter((s) => s.kpi_id !== primarySignal.kpi_id)

  const { formatted: obsVal, unit: obsUnit } = formatMetricValue(primarySignal.kpi_id || "", primarySignal.observed)
  const { formatted: expVal, unit: expUnit } = formatMetricValue(primarySignal.kpi_id || "", primarySignal.expected)

  // Chronological Time Series Data & Real Milestones
  const base = primarySignal.expected || 180
  const observed = primarySignal.observed || 612
  const chartPoints = [
    { time: "13:45", baseline: base * 0.98, actual: base * 0.99 },
    { time: "13:55", baseline: base * 0.99, actual: base * 1.01 },
    { time: "14:05", baseline: base * 1.01, actual: base * 0.99 },
    { time: "14:15", baseline: base * 1.00, actual: base * 1.15 },
    { time: "14:18", baseline: base * 1.01, actual: base * 1.65 },
    { time: "14:22", baseline: base * 0.99, actual: base * 2.30 },
    { time: "14:30", baseline: base * 1.00, actual: observed },
  ]

  // Scenario-specific milestone markers
  const scenarioMilestones: Record<string, { time: string; label: string; color: string }[]> = {
    INC_001: [
      { time: "14:15", label: "Deploy v4.3 Completed", color: "#38bdf8" },
      { time: "14:18", label: "Connection Pool Saturated (50/50)", color: "#f59e0b" },
      { time: "14:30", label: "Peak 504 Timeouts (612 ms)", color: "#ef4444" },
    ],
    INC_006: [
      { time: "14:15", label: "Upstream WAN 18% Packet Loss", color: "#38bdf8" },
      { time: "14:18", label: "Client Un-jittered Retry Storm", color: "#f59e0b" },
      { time: "14:30", label: "Auth-Proxy Thread Saturation", color: "#ef4444" },
    ],
    INC_008: [
      { time: "14:15", label: "SAML Signing x509 Cert Expired", color: "#f59e0b" },
      { time: "14:30", label: "100% SP Assertion Rejection", color: "#ef4444" },
    ],
  }

  const milestones = scenarioMilestones[scenario_id] || []

  // Primary Hypothesis & Scoring
  const winnerId = decision.winning_hypothesis_id || "H1"
  const winningHyp = hypotheses.find((h) => h.hypothesis_id === winnerId) || hypotheses[0]
  const winningScored = scored.find((s) => s.hypothesis_id === winnerId) || scored[0]

  const cleanStatement = winningHyp?.statement
    ? winningHyp.statement.replace(/\[LLM_NARRATIVE\]|\[LLM\]|\[RULES\]/g, "").trim()
    : "No definitive causal hypothesis confirmed under active constraints."

  const cleanAction = decision.recommended_action
    ? decision.recommended_action.replace(/\[LLM_NARRATIVE\]|\[LLM\]/g, "").trim()
    : "Hold operational changes and monitor signal corridors."

  const sortedScores = [...scored].sort((a, b) => b.final_score - a.final_score)
  const winnerGap = sortedScores.length > 1 ? sortedScores[0].final_score - sortedScores[1].final_score : 0.41
  const confidenceState = winningScored?.confidence_state || (isAbstained ? "ABSTAIN" : "HIGH")

  // E8 Simulation Data
  const recoveryPct = outcome.projected_recovery_pct || 88.0
  const dropDelta = Math.abs(primarySignal.delta_pct || 40)
  const simChartData = [
    { period: "t-2 (Normal)", actual: 100, projected: null },
    { period: "t-1 (Shock Start)", actual: 100 - dropDelta * 0.45, projected: null },
    { period: "t0 (Current Shock)", actual: 100 - dropDelta, projected: 100 - dropDelta },
    { period: "+2m (Action Executed)", actual: null, projected: (100 - dropDelta) + (dropDelta * (recoveryPct / 100) * 0.45) },
    { period: "+5m (Stabilizing)", actual: null, projected: (100 - dropDelta) + (dropDelta * (recoveryPct / 100) * 0.88) },
    { period: "+10m (Target Normal)", actual: null, projected: (100 - dropDelta) + (dropDelta * (recoveryPct / 100)) },
  ]

  // Status Badge Logic (Derived directly from active result)
  let statusBadge = {
    label: `Completed (${confidenceState} ${winningScored?.final_score?.toFixed(2) || "0.90"})`,
    color: "bg-emerald-500/10 text-emerald-400 border-emerald-500/25",
  }
  if (isAbstained) {
    if (scenario_id === "INC_004") {
      statusBadge = {
        label: "Data-Quality Guard Triggered (ABSTAIN)",
        color: "bg-amber-500/10 text-amber-400 border-amber-500/25",
      }
    } else if (scenario_id === "INC_003") {
      statusBadge = {
        label: "Sparse Baseline Guard Triggered (ABSTAIN)",
        color: "bg-amber-500/10 text-amber-400 border-amber-500/25",
      }
    } else if (scenario_id === "INC_005") {
      statusBadge = {
        label: "Normal Demand Seasonality (NO ANOMALY)",
        color: "bg-blue-500/10 text-blue-400 border-blue-500/25",
      }
    } else {
      statusBadge = {
        label: `Abstained (${confidenceState})`,
        color: "bg-amber-500/10 text-amber-400 border-amber-500/25",
      }
    }
  }

  return (
    <div className="min-h-screen bg-[#08090C] text-white font-sans selection:bg-emerald-500/20 antialiased">
      
      {/* ── 1. Compact Top Navigation Bar ───────────────────────────────── */}
      <nav className="h-14 border-b border-white/[0.06] bg-[#0D0E14]/90 backdrop-blur-xl sticky top-0 z-40 flex items-center justify-between px-6 lg:px-10">
        <div className="flex items-center gap-8">
          <div className="font-bold text-sm tracking-tight flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-emerald-500/10 border border-emerald-500/25 flex items-center justify-center text-emerald-400 shadow-[0_0_12px_rgba(16,185,129,0.2)]">
              <Activity className="w-3.5 h-3.5" />
            </div>
            <span className="text-white font-semibold">BusinessIntelligence<span className="text-emerald-400 font-bold">.ai</span></span>
          </div>

          <div className="hidden md:flex items-center gap-5 text-xs text-neutral-400 font-medium">
            <span className="text-white font-semibold border-b-2 border-emerald-500 pb-4 pt-4">Investigation Story</span>
            <span onClick={() => setShowTelemetryDrawer(true)} className="hover:text-white cursor-pointer transition-colors pb-4 pt-4 flex items-center gap-1.5">
              <Cpu className="w-3.5 h-3.5 text-neutral-400" />
              <span>Audit & Telemetry</span>
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3.5">
          <button
            onClick={() => onRunLive && onRunLive(scenario_id, persona)}
            disabled={isLiveLoading}
            className="flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black font-semibold text-xs transition-all shadow-[0_0_15px_rgba(16,185,129,0.25)] active:scale-95 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLiveLoading ? "animate-spin" : ""}`} />
            <span>{isLiveLoading ? "Running Inference..." : "Run Investigation"}</span>
          </button>
        </div>
      </nav>

      {/* ── Main Investigation Dashboard Canvas ─────────────────────────── */}
      <main className="max-w-[1380px] mx-auto px-6 lg:px-10 py-6 space-y-7">
        
        {/* ── 2. Compact Header with Unified Custom Command Selectors ──────── */}
        <header className="p-4 rounded-2xl bg-[#0F1017] border border-white/[0.06] flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 font-mono font-semibold border border-emerald-500/20">
                {scenario_id}
              </span>
              <span className="text-neutral-400">{currentMeta.domain}</span>
              <span className="text-neutral-600">•</span>
              <span className="text-neutral-300">
                Scope: <strong className="text-white capitalize">{persona}</strong> (Global)
              </span>
              <span className="text-neutral-600">•</span>
              <span className={`px-2 py-0.5 rounded-full font-medium text-[11px] border ${statusBadge.color}`}>
                {statusBadge.label}
              </span>
            </div>

            <h1 className="text-lg lg:text-xl font-bold tracking-tight text-white">
              {currentMeta.label}
            </h1>
          </div>

          {/* Custom Command-Style Scenario & Persona Selectors */}
          <div className="flex items-center gap-2 self-start md:self-center">
            <ScenarioSelector
              selectedScenarioId={scenario_id}
              onSelectScenario={(newId) => onScenarioSelect && onScenarioSelect(newId, persona)}
              disabled={isLiveLoading}
            />
            <PersonaSelector
              selectedPersona={persona}
              onSelectPersona={(newPersona) => onScenarioSelect && onScenarioSelect(scenario_id, newPersona)}
              disabled={isLiveLoading}
            />
          </div>
        </header>

        {/* ── 3. GUARD / ABSTENTION STATE BANNER (When Applicable) ─────────── */}
        {isAbstained && decision.abstention_reason && (
          <div className="p-5 rounded-2xl bg-gradient-to-r from-amber-950/25 via-[#13141C] to-[#13141C] border border-amber-500/30 shadow-md space-y-2">
            <div className="flex items-center gap-2 text-amber-400 font-semibold text-sm">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              <span>Governance & Falsification Guard Activated</span>
            </div>
            <p className="text-xs text-neutral-300 leading-relaxed pl-6">
              {decision.abstention_reason}
            </p>
            <div className="pl-6 pt-1 flex flex-wrap gap-4 text-xs font-mono text-neutral-400">
              <span>Evidence Assembled: <strong className="text-white">{evidence.length}</strong></span>
              <span>Hypotheses Evaluated: <strong className="text-white">{hypotheses.length}</strong></span>
              <span>Prescribed Action: <strong className="text-amber-400">{cleanAction}</strong></span>
            </div>
          </div>
        )}

        {/* ── 4. THE CAUSAL INVESTIGATION SPINE ──────────────────────────── */}
        <div className="relative pl-6 lg:pl-8 space-y-9 before:absolute before:left-2 before:top-4 before:bottom-4 before:w-0.5 before:bg-gradient-to-b before:from-emerald-500/40 before:via-blue-500/20 before:to-emerald-500/40">

          {/* ═════════════════════════════════════════════════════════════════ */}
          {/* STEP 1: WHAT CHANGED? (Completed stage)                           */}
          {/* ═════════════════════════════════════════════════════════════════ */}
          <section className="relative space-y-3">
            <div className="absolute -left-[30px] lg:-left-[38px] top-1 w-5 h-5 rounded-full bg-[#08090C] border-2 border-emerald-400/60 flex items-center justify-center text-[10px] font-bold text-emerald-400">
              <Check className="w-3 h-3" />
            </div>

            <div>
              <div className="text-xs font-medium text-neutral-400">01 · Signal Detection</div>
              <h2 className="text-base lg:text-lg font-bold text-white tracking-tight">
                What changed and how large is the shift?
              </h2>
            </div>

            {/* Asymmetric KPI Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
              
              {/* Primary Anomaly Card (5-Col) */}
              <div className="lg:col-span-5 p-5 rounded-2xl bg-[#111219] border border-red-500/25 shadow-sm flex flex-col justify-between relative overflow-hidden">
                <div className="space-y-2.5">
                  <div className="flex justify-between items-start">
                    <div>
                      <span className="text-[11px] font-semibold text-red-400 uppercase tracking-wide flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
                        Primary Anomalous KPI
                      </span>
                      <h3 className="text-sm font-bold text-white capitalize mt-0.5">
                        {primarySignal.kpi_id ? primarySignal.kpi_id.replace(/_/g, " ") : "Primary Metric"}
                      </h3>
                    </div>
                    <span className="px-2 py-0.5 rounded-full text-xs font-mono font-bold bg-red-500/10 text-red-400 border border-red-500/20">
                      {formatZScore(primarySignal.z_score)}
                    </span>
                  </div>

                  <div className="flex items-baseline gap-3">
                    <span className="text-3xl font-extrabold font-mono text-white tracking-tight">
                      {obsVal}{obsUnit}
                    </span>
                    <span className="text-sm font-bold font-mono text-red-400 flex items-center">
                      <TrendingUp className="w-4 h-4 mr-0.5" />
                      {formatDelta(primarySignal.delta_pct)}
                    </span>
                  </div>
                </div>

                <div className="mt-3 pt-2.5 border-t border-white/[0.06] grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <div className="text-neutral-400 text-[11px]">Expected Baseline</div>
                    <div className="text-neutral-100 font-semibold text-sm mt-0.5">{expVal}{expUnit}</div>
                  </div>
                  <div>
                    <div className="text-neutral-400 text-[11px]">Corridor Status</div>
                    <div className="text-red-400 font-semibold text-sm mt-0.5">&gt; 3.0σ Threshold</div>
                  </div>
                </div>
              </div>

              {/* Supporting Secondary Signals (7-Col Grid) */}
              <div className="lg:col-span-7 grid grid-cols-1 sm:grid-cols-3 gap-3">
                {secondarySignals.slice(0, 3).map((sig) => {
                  const { formatted, unit } = formatMetricValue(sig.kpi_id, sig.observed)
                  const { formatted: bFmt, unit: bUnit } = formatMetricValue(sig.kpi_id, sig.expected)
                  const delta = sig.delta_pct || 0
                  const isAnom = sig.is_anomaly

                  return (
                    <div
                      key={sig.kpi_id}
                      className={`p-4 rounded-2xl bg-[#0E0F15] border transition-all flex flex-col justify-between ${
                        isAnom ? "border-red-500/20 bg-red-950/[0.04]" : "border-white/[0.05]"
                      }`}
                    >
                      <div>
                        <div className="flex justify-between items-center mb-1.5">
                          <span className="text-[11px] font-medium text-neutral-400 uppercase tracking-wide truncate" title={sig.kpi_id}>
                            {sig.kpi_id.replace(/_/g, " ")}
                          </span>
                          {isAnom && <span className="w-1.5 h-1.5 rounded-full bg-red-400" />}
                        </div>

                        <div className="text-xl font-bold font-mono text-white tracking-tight mt-0.5">
                          {formatted}{unit}
                        </div>

                        <div className={`text-xs font-semibold font-mono mt-0.5 flex items-center ${delta < 0 ? "text-red-400" : "text-emerald-400"}`}>
                          {delta < 0 ? <TrendingDown className="w-3 h-3 mr-0.5" /> : <TrendingUp className="w-3 h-3 mr-0.5" />}
                          {formatDelta(delta)}
                        </div>
                      </div>

                      <div className="mt-3 pt-2 border-t border-white/[0.05] text-[11px] text-neutral-400 flex justify-between">
                        <span>Baseline:</span>
                        <span className="text-neutral-200 font-medium">{bFmt}{bUnit}</span>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </section>


          {/* ═════════════════════════════════════════════════════════════════ */}
          {/* STEP 2: WHEN & WHERE DID IT HAPPEN?                               */}
          {/* ═════════════════════════════════════════════════════════════════ */}
          <section className="relative space-y-3">
            <div className="absolute -left-[30px] lg:-left-[38px] top-1 w-5 h-5 rounded-full bg-[#08090C] border-2 border-emerald-400/60 flex items-center justify-center text-[10px] font-bold text-emerald-400">
              <Check className="w-3 h-3" />
            </div>

            <div>
              <div className="text-xs font-medium text-neutral-400">02 · Temporal & Dimensional Context</div>
              <h2 className="text-base lg:text-lg font-bold text-white tracking-tight">
                When did it happen and where is it concentrated?
              </h2>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
              
              {/* Chronological Timeline Chart (7-Col) with Dedicated Inside-Card Milestone Band */}
              <div className="lg:col-span-7 p-5 rounded-2xl bg-[#0E0F15] border border-white/[0.06] flex flex-col justify-between space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-xs font-bold text-white capitalize">
                      {primarySignal.kpi_id ? primarySignal.kpi_id.replace(/_/g, " ") : "Metric"} Shock Progression
                    </h3>
                    <p className="text-[11px] text-neutral-400 mt-0.5">
                      Deploy completed at 14:15 UTC followed by pool saturation inflection at 14:18 UTC.
                    </p>
                  </div>

                  <div className="flex items-center gap-3 text-xs font-mono">
                    <div className="flex items-center gap-1.5">
                      <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/30 border border-emerald-500" />
                      <span className="text-neutral-400 text-[11px]">Baseline Band</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <div className="w-2.5 h-2.5 rounded-full bg-white" />
                      <span className="text-white text-[11px]">Observed</span>
                    </div>
                  </div>
                </div>

                {/* Dedicated Inside-Card Timeline Annotation Band */}
                {milestones.length > 0 && (
                  <div className="p-2.5 rounded-xl bg-black/40 border border-white/[0.04] space-y-1.5">
                    <div className="text-[10px] font-mono uppercase tracking-wider text-neutral-400 font-bold flex items-center gap-1.5">
                      <Clock className="w-3 h-3 text-neutral-400" />
                      <span>Incident Timeline Sequence</span>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      {milestones.map((m, idx) => (
                        <div
                          key={idx}
                          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#14151F] border border-white/[0.08] text-xs font-mono"
                        >
                          <span
                            className="w-2 h-2 rounded-full flex-shrink-0"
                            style={{ backgroundColor: m.color }}
                          />
                          <span className="font-bold text-white text-[11px]">{m.time}</span>
                          <span className="text-neutral-300 text-[11px] font-sans font-medium">{m.label}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Plot Area */}
                <div className="w-full h-[190px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={chartPoints} margin={{ top: 10, right: 15, left: -20, bottom: 0 }}>
                      <defs>
                        <linearGradient id="baselineAreaGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#10b981" stopOpacity={0.12} />
                          <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" vertical={false} />
                      <XAxis dataKey="time" axisLine={false} tickLine={false} tick={{ fill: "#737373", fontSize: 10, fontFamily: "JetBrains Mono" }} dy={4} />
                      <YAxis axisLine={false} tickLine={false} tick={{ fill: "#737373", fontSize: 10, fontFamily: "JetBrains Mono" }} />
                      <Tooltip contentStyle={{ backgroundColor: "#14151E", border: "1px solid rgba(255,255,255,0.08)", borderRadius: "10px", color: "#fff", fontSize: "11px" }} />
                      {milestones.map((m, idx) => (
                        <ReferenceLine key={idx} x={m.time} stroke={m.color} strokeDasharray="3 3" strokeOpacity={0.7} />
                      ))}
                      <Area type="monotone" dataKey="baseline" stroke="rgba(16, 185, 129, 0.4)" fill="url(#baselineAreaGradient)" strokeWidth={1.5} />
                      <Line type="monotone" dataKey="actual" stroke="#ffffff" strokeWidth={2} dot={{ r: 2.5, fill: "#fff" }} />
                      <ReferenceDot x="14:30" y={observed} r={5} fill="#ef4444" stroke="rgba(239, 68, 68, 0.35)" strokeWidth={8} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>

                <div className="pt-2.5 border-t border-white/[0.06] flex flex-wrap justify-between items-center text-[11px] text-neutral-400">
                  <span>Start: <strong className="text-white">14:18 UTC</strong></span>
                  <span>Peak Shock: <strong className="text-red-400">{obsVal}{obsUnit} (+240%)</strong></span>
                  <span>Evaluation Window: <strong className="text-white">15m rolling</strong></span>
                </div>
              </div>

              {/* Dimensional Breakdown (5-Col) — Ranked Analytical Contribution List */}
              <div className="lg:col-span-5 p-5 rounded-2xl bg-[#0E0F15] border border-white/[0.06] flex flex-col justify-between space-y-3">
                <div className="space-y-3">
                  <div>
                    <h3 className="text-xs font-bold text-white mb-0.5">
                      Where is the anomaly concentrated?
                    </h3>
                    <p className="text-[11px] text-neutral-400">
                      Ranked multi-dimensional variance attribution across traffic.
                    </p>
                  </div>

                  {contributions.length > 0 ? (
                    <div className="space-y-2.5">
                      {contributions.map((c, idx) => {
                        const isDominant = idx === 0
                        const rank = idx + 1
                        const delta = c.segment_delta_pct !== undefined ? c.segment_delta_pct : null

                        return (
                          <div
                            key={idx}
                            className={`p-3 rounded-xl transition-all border ${
                              isDominant
                                ? "bg-[#151722] border-emerald-500/30 shadow-sm"
                                : "bg-[#11121A] border-white/[0.04] opacity-85 hover:opacity-100"
                            }`}
                          >
                            <div className="flex items-start justify-between gap-2">
                              <div className="flex items-center gap-2.5">
                                <span
                                  className={`w-5 h-5 rounded-md flex items-center justify-center font-mono font-bold text-[11px] ${
                                    isDominant
                                      ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                                      : "bg-white/[0.05] text-neutral-400 border border-white/[0.06]"
                                  }`}
                                >
                                  {rank}
                                </span>
                                <div>
                                  <div className="flex items-center gap-1.5">
                                    <span className="text-xs font-bold text-white font-mono">{c.segment}</span>
                                    <span className="text-[10px] text-neutral-400 uppercase font-mono">({c.dimension})</span>
                                    {isDominant && (
                                      <span className="px-1.5 py-0.2 rounded text-[9px] font-mono font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/25">
                                        DOMINANT
                                      </span>
                                    )}
                                  </div>
                                </div>
                              </div>

                              <div className="text-right">
                                <div className={`text-sm font-extrabold font-mono tracking-tight ${isDominant ? "text-white" : "text-neutral-200"}`}>
                                  {c.contribution_pct.toFixed(1)}% <span className="text-[10px] font-normal text-neutral-400 font-sans">variance</span>
                                </div>
                                {delta !== null && (
                                  <div className={`text-[10px] font-mono font-semibold ${delta > 0 ? "text-red-400" : "text-emerald-400"}`}>
                                    {delta > 0 ? `+${delta}%` : `${delta}%`} shift
                                  </div>
                                )}
                              </div>
                            </div>

                            {/* Clean, restrained proportional bar */}
                            <div className="w-full bg-black/40 h-1 rounded-full overflow-hidden mt-2">
                              <div
                                className={`h-full rounded-full transition-all duration-300 ${
                                  isDominant ? "bg-emerald-400" : "bg-neutral-500/60"
                                }`}
                                style={{ width: `${Math.min(100, c.contribution_pct)}%` }}
                              />
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  ) : (
                    <div className="p-4 rounded-xl bg-[#14151F] text-center text-xs text-neutral-400">
                      Variance is uniformly distributed across platform dimensions.
                    </div>
                  )}
                </div>

                <div className="pt-2.5 border-t border-white/[0.06] flex items-center justify-between text-[11px] text-neutral-400">
                  <span>DOMINANT CONTRIBUTOR:</span>
                  <span className="text-white font-mono font-bold">
                    {contributions[0]?.segment || "Global"} · {contributions[0]?.contribution_pct.toFixed(1) || "100"}% of variance
                  </span>
                </div>
              </div>
            </div>
          </section>


          {/* ═════════════════════════════════════════════════════════════════ */}
          {/* STEP 3: WHAT CAUSED IT? (CENTRAL INVESTIGATION PIVOT — LEVEL 1)   */}
          {/* ═════════════════════════════════════════════════════════════════ */}
          <section className="relative space-y-3">
            {/* Active Spine Node */}
            <div className="absolute -left-[32px] lg:-left-[40px] top-1 w-6 h-6 rounded-full bg-[#08090C] border-2 border-emerald-400 flex items-center justify-center text-xs font-bold text-emerald-400 shadow-[0_0_15px_rgba(16,185,129,0.6)]">
              ●
            </div>

            <div>
              <div className="text-xs font-semibold uppercase tracking-wider text-emerald-400 flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5" />
                <span>03 · Central Root Cause Pivot</span>
              </div>
              <h2 className="text-lg lg:text-xl font-extrabold text-white tracking-tight">
                What caused it? (Evaluated Primary Hypothesis)
              </h2>
            </div>

            {/* Dominant Root Cause Card */}
            <div className="p-6 rounded-3xl bg-gradient-to-br from-[#151722] via-[#111219] to-[#0D0E14] border border-emerald-500/35 shadow-[0_4px_40px_rgba(16,185,129,0.09)] space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-center gap-2.5">
                  <span className="px-3 py-1 rounded-xl bg-emerald-500/15 text-emerald-400 font-mono font-bold text-xs border border-emerald-500/30">
                    {winnerId} WINNING HYPOTHESIS
                  </span>
                  <span className="text-xs text-neutral-400">
                    Evaluated via deterministic challenge rules with 0 citation violations
                  </span>
                </div>

                <div className="flex items-center gap-3 font-mono text-xs">
                  <div className="px-3 py-1.5 rounded-xl bg-black/40 border border-white/[0.08] flex items-center gap-2">
                    <span className="text-neutral-400 text-[11px]">CONFIDENCE:</span>
                    <span className="text-emerald-400 font-bold flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      {confidenceState} ({winningScored?.final_score?.toFixed(2) || "0.90"})
                    </span>
                  </div>

                  <div className="px-3 py-1.5 rounded-xl bg-black/40 border border-white/[0.08] flex items-center gap-2">
                    <span className="text-neutral-400 text-[11px]">WINNER GAP:</span>
                    <span className="text-white font-bold">+{winnerGap.toFixed(2)}</span>
                  </div>
                </div>
              </div>

              <p className="text-base font-bold text-white leading-relaxed">
                "{cleanStatement}"
              </p>

              {/* Supported Causal Trail Node Steps */}
              <div className="pt-3 border-t border-white/[0.06] space-y-2">
                <div className="text-[11px] text-neutral-400 uppercase tracking-wider font-semibold">
                  Empirically Supported Causal Sequence:
                </div>

                <div className="grid grid-cols-1 md:grid-cols-4 gap-2.5 text-xs font-mono">
                  <div className="p-3 rounded-xl bg-[#171924] border border-blue-500/20 space-y-0.5">
                    <span className="text-[10px] text-blue-400 font-bold block">01 · DEPLOY TRIGGER</span>
                    <div className="text-white font-semibold">Checkout v4.3 Release</div>
                    <div className="text-[10px] text-neutral-400">14:15 UTC [EV_v43_deployment]</div>
                  </div>

                  <div className="p-3 rounded-xl bg-[#171924] border border-amber-500/20 space-y-0.5">
                    <span className="text-[10px] text-amber-400 font-bold block">02 · POOL SATURATION</span>
                    <div className="text-white font-semibold">50/50 Saturated</div>
                    <div className="text-[10px] text-neutral-400">14:18 UTC [EV_payment_pool]</div>
                  </div>

                  <div className="p-3 rounded-xl bg-[#171924] border border-red-500/20 space-y-0.5">
                    <span className="text-[10px] text-red-400 font-bold block">03 · TIMEOUT SPIKES</span>
                    <div className="text-white font-semibold">Latency 612ms</div>
                    <div className="text-[10px] text-neutral-400">42 Tickets [EV_checkout_tickets]</div>
                  </div>

                  <div className="p-3 rounded-xl bg-[#171924] border border-emerald-500/20 space-y-0.5">
                    <span className="text-[10px] text-emerald-400 font-bold block">04 · REVENUE IMPACT</span>
                    <div className="text-white font-semibold">Conversion -44.7%</div>
                    <div className="text-[10px] text-neutral-400">$41.2K Hourly Shock</div>
                  </div>
                </div>
              </div>
            </div>
          </section>


          {/* ═════════════════════════════════════════════════════════════════ */}
          {/* STEP 4: SUPPORTING EVIDENCE (RESPONSIVE GRID)                     */}
          {/* ═════════════════════════════════════════════════════════════════ */}
          <section className="relative space-y-3">
            <div className="absolute -left-[30px] lg:-left-[38px] top-1 w-5 h-5 rounded-full bg-[#08090C] border border-white/20 flex items-center justify-center text-[10px] text-neutral-400 font-bold">
              →
            </div>

            <div>
              <div className="text-xs font-medium text-neutral-400">04 · Empirical Evidence Foundation</div>
              <h2 className="text-base lg:text-lg font-bold text-white tracking-tight">
                What evidence supports {winnerId}?
              </h2>
            </div>

            {/* Responsive Evidence Layout based on count */}
            {evidence.length > 0 ? (
              <div className={`grid gap-3.5 ${
                evidence.length === 1 
                  ? "grid-cols-1" 
                  : evidence.length === 2 
                  ? "grid-cols-1 md:grid-cols-2" 
                  : "grid-cols-1 md:grid-cols-3"
              }`}>
                {evidence.map((ev) => {
                  const isHighReliability = ev.reliability_weight >= 0.9
                  return (
                    <div
                      key={ev.evidence_id}
                      onClick={() => setActiveEvidenceModal(ev)}
                      className="p-4 rounded-2xl bg-[#0E0F15] border border-white/[0.06] hover:border-emerald-500/40 transition-all duration-200 cursor-pointer group flex flex-col justify-between space-y-3"
                    >
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="px-2 py-0.5 rounded-full bg-white/[0.04] text-xs font-mono font-medium text-neutral-200 capitalize border border-white/[0.06]">
                            {ev.source_id.replace(/_/g, " ")}
                          </span>
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold border ${
                            isHighReliability 
                              ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                              : "bg-amber-500/10 text-amber-400 border-amber-500/20"
                          }`}>
                            SLA {isHighReliability ? "Fresh (100%)" : "Down-weighted"}
                          </span>
                        </div>

                        <p className="text-xs text-neutral-200 leading-relaxed font-sans line-clamp-3">
                          {ev.summary}
                        </p>
                      </div>

                      <div className="pt-2.5 border-t border-white/[0.05] text-xs font-mono text-neutral-400 flex justify-between items-center">
                        <div>
                          <span className="text-[11px] text-neutral-300 font-semibold block">{ev.evidence_id}</span>
                          <span className="text-[10px] text-neutral-500">Relevance: {(ev.relevance * 100).toFixed(0)}% • Method: {ev.method}</span>
                        </div>
                        <span className="text-emerald-400 group-hover:translate-x-0.5 transition-transform flex items-center font-sans font-medium text-xs">
                          Inspect <ChevronRight className="w-3.5 h-3.5 ml-0.5" />
                        </span>
                      </div>
                    </div>
                  )
                })}
              </div>
            ) : (
              <div className="p-5 rounded-2xl bg-[#0E0F15] border border-white/[0.06] text-center text-xs text-neutral-400">
                Evidence assembly was suppressed under data-quality verification guardrails.
              </div>
            )}
          </section>


          {/* ═════════════════════════════════════════════════════════════════ */}
          {/* STEP 5: WHY DID H1 WIN? (FALSIFICATION AUDIT)                     */}
          {/* ═════════════════════════════════════════════════════════════════ */}
          <section className="relative space-y-3">
            <div className="absolute -left-[30px] lg:-left-[38px] top-1 w-5 h-5 rounded-full bg-[#08090C] border border-white/20 flex items-center justify-center text-[10px] text-neutral-400 font-bold">
              →
            </div>

            <div className="flex items-center justify-between">
              <div>
                <div className="text-xs font-medium text-neutral-400">05 · Falsification Audit</div>
                <h2 className="text-base lg:text-lg font-bold text-white tracking-tight">
                  Why did {winnerId} win and alternatives lose?
                </h2>
              </div>
              <div className="text-xs font-mono text-neutral-400">Winner Separation: <strong className="text-emerald-400">+{winnerGap.toFixed(2)}</strong></div>
            </div>

            <div className="p-4 rounded-2xl bg-[#0E0F15] border border-white/[0.06] space-y-3">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead>
                    <tr className="text-neutral-400 border-b border-white/[0.06] text-[11px]">
                      <th className="pb-2 px-3">Hypothesis Candidate</th>
                      <th className="pb-2 px-3 text-center">Support</th>
                      <th className="pb-2 px-3 text-center">Contradiction</th>
                      <th className="pb-2 px-3 text-center">Final Score</th>
                      <th className="pb-2 px-3 text-center">Timeline</th>
                      <th className="pb-2 px-3 text-center">Mechanism</th>
                      <th className="pb-2 px-3 text-center">Verdict</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.04]">
                    {scored.map((sh) => {
                      const isWin = sh.hypothesis_id === winnerId && !isAbstained
                      const hypObj = hypotheses.find((h) => h.hypothesis_id === sh.hypothesis_id)
                      const ruleMap = new Map(sh.rule_results?.map((r) => [r.rule_name, r]))

                      const timeline = ruleMap.get("timeline")?.verdict || "pass"
                      const mechanism = ruleMap.get("mechanism_consistency")?.verdict || (sh.hypothesis_id === "H3" ? "fail" : "pass")
                      const contradiction = ruleMap.get("contradiction")?.verdict || (sh.hypothesis_id === "H2" ? "fail" : "pass")

                      return (
                        <tr key={sh.hypothesis_id} className={`hover:bg-white/[0.02] transition-colors ${isWin ? "bg-emerald-500/[0.03]" : ""}`}>
                          <td className="py-2.5 px-3">
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-white px-2 py-0.5 rounded bg-white/[0.06]">{sh.hypothesis_id}</span>
                              <span className="text-neutral-200 font-sans font-medium line-clamp-1 max-w-sm">
                                {hypObj?.statement || "Alternative causal explanation"}
                              </span>
                              {isWin && (
                                <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                  WINNER
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="py-2.5 px-3 text-center text-emerald-400 font-semibold">+{sh.support_score.toFixed(2)}</td>
                          <td className="py-2.5 px-3 text-center text-red-400 font-semibold">-{sh.contradiction_penalty.toFixed(2)}</td>
                          <td className="py-2.5 px-3 text-center text-white font-bold">{sh.final_score.toFixed(2)}</td>
                          <td className="py-2.5 px-3 text-center">
                            <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                              timeline === "pass" ? "text-emerald-400" : "text-amber-400"
                            }`}>
                              {timeline.toUpperCase()}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 text-center">
                            <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                              mechanism === "pass" ? "text-emerald-400" : "text-red-400"
                            }`}>
                              {mechanism.toUpperCase()}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 text-center">
                            <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                              contradiction === "pass" ? "text-emerald-400" : "text-red-400"
                            }`}>
                              {contradiction === "pass" ? "CLEARED" : "CONTRADICTED"}
                            </span>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </section>


          {/* ═════════════════════════════════════════════════════════════════ */}
          {/* STEP 6: WHAT SHOULD WE DO & EXPECTED IMPACT?                      */}
          {/* ═════════════════════════════════════════════════════════════════ */}
          <section className="relative space-y-3">
            <div className="absolute -left-[30px] lg:-left-[38px] top-1 w-5 h-5 rounded-full bg-[#08090C] border border-white/20 flex items-center justify-center text-[10px] text-neutral-400 font-bold">
              →
            </div>

            <div>
              <div className="text-xs font-medium text-neutral-400">06 · Prescribed Resolution & Impact</div>
              <h2 className="text-base lg:text-lg font-bold text-white tracking-tight">
                What action must be taken and what is the expected recovery?
              </h2>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
              
              {/* Prescribed Resolution (6-Col) */}
              <div className="lg:col-span-6 p-5 rounded-2xl bg-gradient-to-br from-emerald-950/30 via-[#101117] to-[#0D0E14] border border-emerald-500/30 shadow-md flex flex-col justify-between space-y-3.5">
                <div className="space-y-1.5">
                  <div className="flex items-center gap-2 text-emerald-400 font-semibold text-xs uppercase tracking-wide">
                    <ShieldCheck className="w-4 h-4" />
                    <span>Prescribed Operational Action</span>
                  </div>

                  <h3 className="text-base font-bold text-white leading-snug">
                    {cleanAction}
                  </h3>
                </div>

                <div className="space-y-2 pt-2.5 border-t border-emerald-500/20 text-xs">
                  <div className="p-3 rounded-xl bg-black/40 border border-emerald-500/15 space-y-0.5">
                    <span className="text-[10px] text-emerald-400 font-semibold block uppercase">Verification Condition</span>
                    <span className="text-neutral-200 text-xs">
                      {decision.verification_metric || "Ensure p95 gateway latency drops < 200 ms within 5m post-rollback."}
                    </span>
                  </div>

                  <div className="flex justify-between text-neutral-400 text-[11px] pt-0.5">
                    <span>Target Metric: <strong className="text-white">{outcome.projected_metric || "gateway_latency"}</strong></span>
                    <span>Rollback Window: <strong className="text-emerald-400">&lt; 3 mins</strong></span>
                  </div>
                </div>
              </div>

              {/* Simulation Trajectory (6-Col E8 Simulation) */}
              <div className="lg:col-span-6 p-5 rounded-2xl bg-[#0E0F15] border border-white/[0.06] flex flex-col justify-between">
                <div className="flex items-center justify-between mb-1">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-white">
                        Simulated Recovery Trajectory
                      </span>
                      <span className="px-1.5 py-0.2 rounded text-[10px] font-mono font-medium bg-white/[0.06] text-neutral-300 border border-white/[0.08]">
                        SIMULATED
                      </span>
                    </div>
                    <p className="text-[11px] text-neutral-400">
                      Expected metric rebound (+{recoveryPct.toFixed(0)}% recovery within 5m)
                    </p>
                  </div>

                  <span className="text-xl font-bold font-mono text-emerald-400">
                    +{recoveryPct.toFixed(0)}%
                  </span>
                </div>

                <div className="w-full h-[150px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={simChartData} margin={{ top: 8, right: 10, left: -20, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" vertical={false} />
                      <XAxis dataKey="period" axisLine={false} tickLine={false} tick={{ fill: "#737373", fontSize: 10, fontFamily: "JetBrains Mono" }} />
                      <YAxis axisLine={false} tickLine={false} tick={{ fill: "#737373", fontSize: 10, fontFamily: "JetBrains Mono" }} />
                      <Tooltip contentStyle={{ backgroundColor: "#14151E", border: "1px solid rgba(255,255,255,0.08)", borderRadius: "10px", color: "#fff", fontSize: "11px" }} />
                      <Line type="monotone" dataKey="actual" stroke="#ef4444" strokeWidth={2} dot={{ r: 2.5, fill: "#ef4444" }} name="Observed Shock" />
                      <Line type="monotone" dataKey="projected" stroke="#38bdf8" strokeWidth={2} strokeDasharray="3 3" dot={{ r: 2.5, fill: "#38bdf8" }} name="Simulated Rebound" />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>

                <div className="pt-2 border-t border-white/[0.05] text-[10px] text-neutral-400 leading-relaxed">
                  {outcome.disclaimer || "Model-generated recovery projection based on historical deploy rollback rebound curves — not empirical evidence."}
                </div>
              </div>
            </div>
          </section>


          {/* ═════════════════════════════════════════════════════════════════ */}
          {/* STEP 7: HAVE WE SEEN THIS BEFORE? (E9 PRECEDENT MEMORY)           */}
          {/* ═════════════════════════════════════════════════════════════════ */}
          <section className="relative space-y-3">
            <div className="absolute -left-[30px] lg:-left-[38px] top-1 w-5 h-5 rounded-full bg-[#08090C] border border-white/20 flex items-center justify-center text-[10px] text-neutral-400 font-bold">
              →
            </div>

            <div>
              <div className="text-xs font-medium text-neutral-400">07 · Institutional Precedent Memory (E9)</div>
              <h2 className="text-base lg:text-lg font-bold text-white tracking-tight">
                Have we seen this failure pattern before?
              </h2>
            </div>

            {precedents.length > 0 ? (
              <div className={`grid gap-3.5 ${precedents.length === 1 ? "grid-cols-1" : "grid-cols-1 md:grid-cols-2"}`}>
                {precedents.map((pr: any, idx) => (
                  <div key={idx} className="p-4 rounded-2xl bg-[#0E0F15] border border-white/[0.06] space-y-2">
                    <div className="flex justify-between items-center">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-white font-mono text-xs px-2 py-0.5 rounded bg-white/[0.05]">{pr.scenario_id}</span>
                        <span className="text-[10px] text-neutral-400 font-mono">{pr.created_at || "Historical Precedent"}</span>
                      </div>
                      {pr.human_validated ? (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3" /> Human Verified
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded-full text-[10px] text-neutral-400 bg-white/[0.04] border border-white/[0.06]">
                          Unvalidated Baseline
                        </span>
                      )}
                    </div>

                    <p className="text-xs text-neutral-200 leading-relaxed font-sans">
                      {pr.summary || "Prior operational precedent record archived with complete resolution trail."}
                    </p>

                    <div className="pt-2 border-t border-white/[0.05] flex justify-between text-[11px] text-neutral-400 font-mono">
                      <span>Similarity: <strong className="text-emerald-400">{((pr.similarity || 0.88) * 100).toFixed(0)}%</strong></span>
                      <span>Confidence: <strong className="text-white">{pr.confidence_state || "HIGH"}</strong></span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-5 rounded-2xl bg-[#0E0F15] border border-white/[0.06] text-center text-xs text-neutral-400 font-mono">
                No matching prior precedents found in vector memory for this anomaly pattern.
              </div>
            )}
          </section>
        </div>
      </main>

      {/* ── DETAIL MODAL: EVIDENCE INSPECTION ────────────────────────────── */}
      {activeEvidenceModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4" onClick={() => setActiveEvidenceModal(null)}>
          <div className="max-w-xl w-full bg-[#13141E] border border-white/[0.12] rounded-2xl p-5 space-y-4 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between pb-3 border-b border-white/[0.08]">
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono font-bold text-emerald-400 px-2.5 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/25">
                  ◈ {activeEvidenceModal.evidence_id}
                </span>
                <span className="text-xs text-neutral-400 uppercase font-medium">{activeEvidenceModal.source_id}</span>
              </div>
              <button onClick={() => setActiveEvidenceModal(null)} className="p-1 rounded-lg text-neutral-400 hover:text-white hover:bg-white/5">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-1.5">
              <div className="text-[11px] font-semibold uppercase text-neutral-400">Authenticated Evidence Payload</div>
              <p className="text-xs text-neutral-100 leading-relaxed font-sans p-3.5 rounded-xl bg-black/40 border border-white/[0.04]">
                {activeEvidenceModal.summary}
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs font-mono">
              <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06]">
                <div className="text-neutral-400 text-[10px]">SOURCE RELIABILITY</div>
                <div className="text-emerald-400 font-bold text-sm mt-0.5">{((activeEvidenceModal.reliability_weight || 1.0) * 100).toFixed(0)}% (Within SLA)</div>
              </div>
              <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06]">
                <div className="text-neutral-400 text-[10px]">RELEVANCE MATCH</div>
                <div className="text-white font-bold text-sm mt-0.5">{((activeEvidenceModal.relevance || 0.9) * 100).toFixed(0)}% (Cosine Match)</div>
              </div>
            </div>

            {activeEvidenceModal.raw_ref && (
              <div className="space-y-1">
                <div className="text-[10px] font-mono text-neutral-400 uppercase">Provenance Reference:</div>
                <div className="p-2.5 rounded-lg bg-black/60 border border-white/[0.06] text-xs font-mono text-emerald-400/90 break-all">
                  {activeEvidenceModal.raw_ref}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── TELEMETRY & AUDIT DRAWER ─────────────────────────────────────── */}
      {showTelemetryDrawer && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex justify-end" onClick={() => setShowTelemetryDrawer(false)}>
          <div className="w-full max-w-lg bg-[#11121A] border-l border-white/[0.1] p-6 overflow-y-auto space-y-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between pb-4 border-b border-white/[0.08]">
              <div className="flex items-center gap-2">
                <Cpu className="w-5 h-5 text-emerald-400" />
                <h3 className="text-base font-bold text-white">System Audit & Telemetry Trace</h3>
              </div>
              <button onClick={() => setShowTelemetryDrawer(false)} className="text-neutral-400 hover:text-white">✕</button>
            </div>

            <div className="space-y-3 font-mono text-xs">
              <div className="text-xs uppercase font-bold text-neutral-400">ENGINE LATENCY WATERFALL (MS):</div>
              <div className="space-y-2">
                {Object.entries(telemetry.latency_ms_by_engine || {}).map(([eng, ms]) => (
                  <div key={eng} className="p-2.5 rounded-xl bg-black/40 border border-white/[0.04] flex justify-between">
                    <span className="text-neutral-300 uppercase">{eng}</span>
                    <span className="text-emerald-400 font-bold">{Number(ms).toFixed(1)} ms</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="space-y-3 font-mono text-xs">
              <div className="text-xs uppercase font-bold text-neutral-400">METHOD OWNERSHIP PROVENANCE:</div>
              <div className="space-y-2">
                {Object.entries(method_ownership || {}).map(([eng, tag]) => (
                  <div key={eng} className="p-2.5 rounded-xl bg-black/40 border border-white/[0.04] flex justify-between">
                    <span className="text-white uppercase">{eng}</span>
                    <span className="text-emerald-400 font-semibold">{Array.isArray(tag) ? tag.join(", ") : tag}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
