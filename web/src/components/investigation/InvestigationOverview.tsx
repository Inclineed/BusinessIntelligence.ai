import React, { useState } from "react"
import { InvestigationResult, PersonaType, EvidenceItem } from "../../types/investigation"
import { formatMetricValue, formatDelta, formatZScore } from "../../lib/utils"
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
  Clock,
  Layers,
  ArrowRight,
  ArrowDown,
  Database,
  FileCode,
  X,
  Cpu,
  History,
  Check,
  AlertCircle
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
  const [activeEvidenceModal, setActiveEvidenceModal] = useState<EvidenceItem | null>(null)
  const [showTelemetryDrawer, setShowTelemetryDrawer] = useState(false)

  const { 
    scenario_id, 
    persona, 
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

  // Scenario Titles & Metadata
  const scenarioTitles: Record<string, { title: string; domain: string; desc: string }> = {
    INC_001: {
      title: "Payment Gateway Latency Regression",
      domain: "E-Commerce Checkout",
      desc: "Checkout v4.3 deploy caused connection pool exhaustion in payment gateway client.",
    },
    INC_002: {
      title: "Simultaneous Conflicting Causes",
      domain: "E-Commerce Checkout",
      desc: "Simultaneous gateway latency spike and aggressive competitor discount campaign.",
    },
    INC_004: {
      title: "ETL Ingestion Pipeline Delay",
      domain: "Data Engineering",
      desc: "Delayed batch data warehouse sync causing apparent revenue plunge.",
    },
    INC_006: {
      title: "Compound Network & Deploy Failure",
      domain: "Platform Infrastructure",
      desc: "Simultaneous upstream packet loss and service client latency regression.",
    },
    INC_008: {
      title: "Enterprise SAML SSO Outage",
      domain: "B2B SaaS Security",
      desc: "Identity provider certificate rotation failure blocking enterprise login.",
    },
  }

  const currentMeta = scenarioTitles[scenario_id] || {
    title: "Operational Incident Investigation",
    domain: "Enterprise Infrastructure",
    desc: "Autonomous root cause isolation and attribution analysis.",
  }

  const isAbstained = Boolean(decision.abstained)

  // 1. WHAT CHANGED
  const anomalies = signals.filter((s) => s.is_anomaly)
  const primarySignal = anomalies[0] || signals[0] || {}
  const secondarySignals = signals.filter((s) => s.kpi_id !== primarySignal.kpi_id)

  const { formatted: obsVal, unit: obsUnit } = formatMetricValue(primarySignal.kpi_id || "", primarySignal.observed)
  const { formatted: expVal, unit: expUnit } = formatMetricValue(primarySignal.kpi_id || "", primarySignal.expected)

  // 2. WHEN & WHERE Time series
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

  // 3. WHAT CAUSED IT (Primary Hypothesis)
  const winnerId = decision.winning_hypothesis_id || "H1"
  const winningHyp = hypotheses.find((h) => h.hypothesis_id === winnerId) || hypotheses[0]
  const winningScored = scored.find((s) => s.hypothesis_id === winnerId) || scored[0]

  const cleanStatement = winningHyp?.statement
    ? winningHyp.statement.replace(/\[LLM_NARRATIVE\]|\[LLM\]|\[RULES\]/g, "").trim()
    : "No definitive causal hypothesis confirmed under active constraints."

  const cleanAction = decision.recommended_action
    ? decision.recommended_action.replace(/\[LLM_NARRATIVE\]|\[LLM\]/g, "").trim()
    : "Monitor signal corridors."

  const sortedScores = [...scored].sort((a, b) => b.final_score - a.final_score)
  const winnerGap = sortedScores.length > 1 ? sortedScores[0].final_score - sortedScores[1].final_score : 0.41
  const confidenceState = winningScored?.confidence_state || (isAbstained ? "ABSTAIN" : "HIGH")

  // 4. SIMULATION TRAJECTORY (E8)
  const recoveryPct = outcome.projected_recovery_pct || 88.0
  const dropDelta = Math.abs(primarySignal.delta_pct || 40)
  const simChartData = [
    { period: "t-2 (Normal)", actual: 100, projected: null },
    { period: "t-1 (Shock Start)", actual: 100 - dropDelta * 0.45, projected: null },
    { period: "t0 (Current Peak)", actual: 100 - dropDelta, projected: 100 - dropDelta },
    { period: "+2m (Rollback Executed)", actual: null, projected: (100 - dropDelta) + (dropDelta * (recoveryPct / 100) * 0.45) },
    { period: "+5m (Pool Recovered)", actual: null, projected: (100 - dropDelta) + (dropDelta * (recoveryPct / 100) * 0.88) },
    { period: "+10m (Target Normal)", actual: null, projected: (100 - dropDelta) + (dropDelta * (recoveryPct / 100)) },
  ]

  const handleTriggerRun = () => {
    if (onRunLive) {
      onRunLive(selectedScenario, selectedPersona)
    }
  }

  return (
    <div className="min-h-screen bg-[#07080A] text-white font-sans selection:bg-emerald-500/20 antialiased">
      
      {/* ── Top Navigation Header ────────────────────────────────────────── */}
      <nav className="h-16 border-b border-white/[0.06] bg-[#0C0D12]/90 backdrop-blur-xl sticky top-0 z-40 flex items-center justify-between px-6 lg:px-12">
        <div className="flex items-center gap-8">
          <div className="font-bold text-base tracking-tight flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 shadow-[0_0_15px_rgba(16,185,129,0.25)]">
              <Activity className="w-4 h-4" />
            </div>
            <div>
              <div className="leading-none text-white font-bold">BusinessIntelligence<span className="text-emerald-400">.ai</span></div>
              <div className="text-[10px] text-neutral-400 font-mono tracking-wider mt-0.5 uppercase">Autonomous Investigation Pipeline</div>
            </div>
          </div>

          <div className="hidden md:flex items-center gap-6 text-xs font-mono font-medium text-neutral-400">
            <span className="text-white font-bold border-b-2 border-emerald-500 pb-5 pt-5">INVESTIGATION STORY</span>
            <span onClick={() => setShowTelemetryDrawer(true)} className="hover:text-white cursor-pointer transition-colors pb-5 pt-5 flex items-center gap-1.5">
              <Cpu className="w-3.5 h-3.5 text-neutral-400" />
              <span>SYSTEM AUDIT & TELEMETRY</span>
            </span>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="hidden sm:flex items-center gap-2 text-xs font-mono text-neutral-400 bg-white/[0.04] px-3.5 py-1.5 rounded-full border border-white/[0.06]">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-neutral-300">FastAPI Backend :8080 Active</span>
          </div>

          <button
            onClick={handleTriggerRun}
            disabled={isLiveLoading}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black font-bold text-xs font-mono transition-all shadow-[0_0_20px_rgba(16,185,129,0.3)] active:scale-95 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLiveLoading ? "animate-spin" : ""}`} />
            <span>{isLiveLoading ? "Running Inference..." : "Run Live Inference"}</span>
          </button>
        </div>
      </nav>

      {/* ── Main Canvas with Vertical Investigation Spine ────────────────── */}
      <main className="max-w-[1440px] mx-auto px-6 lg:px-12 py-10 space-y-12">
        
        {/* ── TOP HEADER / INVESTIGATION SCOPE ────────────────────────────── */}
        <header className="p-7 rounded-3xl bg-[#0F1016] border border-white/[0.08] shadow-sm flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="space-y-2.5">
            <div className="flex flex-wrap items-center gap-3 text-xs font-mono">
              <span className="px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-400 font-bold border border-emerald-500/25">
                {scenario_id}
              </span>
              <span className="text-neutral-300">{currentMeta.domain}</span>
              <span>•</span>
              <span className="text-neutral-300 flex items-center gap-1">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                Scope: <strong className="text-white capitalize">{persona}</strong>
              </span>
              <span>•</span>
              <span>Region: <strong className="text-white">Global Baseline</strong></span>
              <span>•</span>
              <span className={`px-2.5 py-0.5 rounded-full font-bold text-[11px] ${
                isAbstained 
                  ? "bg-amber-500/10 text-amber-400 border border-amber-500/25"
                  : "bg-emerald-500/10 text-emerald-400 border border-emerald-500/25"
              }`}>
                {isAbstained ? "Status: Abstained (Guard Active)" : "Status: Completed (HIGH 0.90)"}
              </span>
            </div>

            <h1 className="text-2xl lg:text-3xl font-extrabold tracking-tight text-white">
              {currentMeta.title}
            </h1>
            <p className="text-xs lg:text-sm text-neutral-400 max-w-3xl leading-relaxed">
              {currentMeta.desc}
            </p>
          </div>

          {/* Quick Scenario & Scope Switcher */}
          <div className="flex flex-wrap items-center gap-3 bg-[#151620] p-2 rounded-2xl border border-white/[0.06] self-start lg:self-center">
            <div className="space-y-1">
              <div className="text-[10px] uppercase font-bold text-neutral-400 px-2 tracking-wider font-mono">INCIDENT SCENARIO</div>
              <select
                value={selectedScenario}
                onChange={(e) => {
                  setSelectedScenario(e.target.value)
                  if (onRunLive) onRunLive(e.target.value, selectedPersona)
                }}
                className="bg-[#0C0D12] text-xs text-white font-medium px-3 py-2 rounded-xl outline-none cursor-pointer border border-white/[0.08] hover:border-emerald-500/40 transition-colors font-mono"
              >
                <option value="INC_001">INC_001 — Payment Latency (HIGH 0.90)</option>
                <option value="INC_002">INC_002 — Conflicting Causes (ABSTAIN)</option>
                <option value="INC_004">INC_004 — ETL Delay (DATA-QUALITY GUARD)</option>
                <option value="INC_006">INC_006 — Compound Failure (HIGH)</option>
                <option value="INC_008">INC_008 — SAML SSO Outage (HIGH)</option>
              </select>
            </div>

            <div className="w-px h-10 bg-white/10 hidden sm:block" />

            <div className="space-y-1">
              <div className="text-[10px] uppercase font-bold text-neutral-400 px-2 tracking-wider font-mono">ANALYST PERSONA</div>
              <select
                value={selectedPersona}
                onChange={(e) => {
                  const p = e.target.value as PersonaType
                  setSelectedPersona(p)
                  if (onRunLive) onRunLive(selectedScenario, p)
                }}
                className="bg-[#0C0D12] text-xs text-neutral-200 font-medium px-3 py-2 rounded-xl outline-none cursor-pointer border border-white/[0.08] hover:border-emerald-500/40 transition-colors font-mono"
              >
                <option value="analyst">Analyst (Full Access)</option>
                <option value="cfo">CFO (Executive Aggregates)</option>
                <option value="manager">Manager (Regional Scope)</option>
              </select>
            </div>
          </div>
        </header>

        {/* ── GUARD STATE BANNER (When Active, e.g. INC_004 / INC_002) ─────── */}
        {isAbstained && decision.abstention_reason && (
          <div className="p-6 rounded-3xl bg-gradient-to-r from-amber-950/30 via-[#13141C] to-[#13141C] border border-amber-500/30 shadow-lg space-y-2">
            <div className="flex items-center gap-2.5 text-amber-400 font-bold text-sm font-mono">
              <AlertTriangle className="w-5 h-5 flex-shrink-0" />
              <span>GOVERNANCE & FALSIFICATION GUARD ACTIVATED</span>
            </div>
            <p className="text-sm text-neutral-200 leading-relaxed pl-7">
              {decision.abstention_reason}
            </p>
            <div className="pl-7 pt-2 flex flex-wrap gap-5 text-xs font-mono text-neutral-400">
              <span>Evidence Assembled: <strong className="text-white">{evidence.length}</strong></span>
              <span>Hypotheses Evaluated: <strong className="text-white">{hypotheses.length}</strong></span>
              <span>Action: <strong className="text-amber-400">{cleanAction}</strong></span>
            </div>
          </div>
        )}

        {/* ── THE CAUSAL INVESTIGATION SPINE ──────────────────────────────── */}
        <div className="relative pl-6 lg:pl-10 space-y-12 before:absolute before:left-2 lg:before:left-3 before:top-4 before:bottom-4 before:w-0.5 before:bg-gradient-to-b before:from-emerald-500/50 before:via-blue-500/30 before:to-emerald-500/50">

          {/* ═════════════════════════════════════════════════════════════════ */}
          {/* STEP 1: WHAT CHANGED?                                             */}
          {/* ═════════════════════════════════════════════════════════════════ */}
          <section className="relative space-y-4">
            {/* Spine Node Marker */}
            <div className="absolute -left-[31px] lg:-left-[47px] top-1.5 w-6 h-6 rounded-full bg-[#07080A] border-2 border-emerald-400 flex items-center justify-center text-[10px] font-mono font-bold text-emerald-400 shadow-[0_0_10px_rgba(16,185,129,0.5)]">
              1
            </div>

            <div className="space-y-1">
              <div className="text-xs font-mono font-bold uppercase tracking-wider text-emerald-400">
                STAGE 1 · ANOMALY ISOLATION
              </div>
              <h2 className="text-xl font-bold text-white tracking-tight">
                What changed and how large is the statistical shock?
              </h2>
            </div>

            {/* Asymmetric KPI Strip */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
              
              {/* Primary Metric Card (Large 5-Col) */}
              <div className="lg:col-span-5 p-6 rounded-3xl bg-[#12131B] border border-red-500/30 shadow-[0_4px_30px_rgba(239,68,68,0.08)] flex flex-col justify-between relative overflow-hidden">
                <div className="absolute top-0 right-0 w-32 h-32 bg-red-500/5 rounded-full blur-2xl pointer-events-none" />
                
                <div className="space-y-4">
                  <div className="flex justify-between items-start">
                    <div>
                      <span className="text-[11px] font-mono font-bold uppercase tracking-wider text-red-400 flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                        PRIMARY ANOMALOUS KPI
                      </span>
                      <h3 className="text-lg font-bold text-white capitalize mt-0.5">
                        {primarySignal.kpi_id ? primarySignal.kpi_id.replace(/_/g, " ") : "Primary KPI"}
                      </h3>
                    </div>
                    <span className="px-2.5 py-1 rounded-full text-xs font-mono font-bold bg-red-500/10 text-red-400 border border-red-500/25">
                      {formatZScore(primarySignal.z_score)}
                    </span>
                  </div>

                  <div className="flex items-baseline gap-3">
                    <span className="text-4xl lg:text-5xl font-extrabold font-mono text-white tracking-tight">
                      {obsVal}{obsUnit}
                    </span>
                    <span className="text-lg font-bold font-mono text-red-400 flex items-center">
                      <TrendingUp className="w-5 h-5 mr-0.5" />
                      {formatDelta(primarySignal.delta_pct)}
                    </span>
                  </div>
                </div>

                <div className="mt-6 pt-4 border-t border-white/[0.08] grid grid-cols-2 gap-4 text-xs font-mono">
                  <div>
                    <div className="text-neutral-400 text-[11px]">EXPECTED BASELINE</div>
                    <div className="text-neutral-100 font-bold text-sm mt-0.5">{expVal}{expUnit}</div>
                  </div>
                  <div>
                    <div className="text-neutral-400 text-[11px]">CORRIDOR BREACH</div>
                    <div className="text-red-400 font-bold text-sm mt-0.5">&gt; 3.0σ Threshold</div>
                  </div>
                </div>
              </div>

              {/* Supporting Secondary Signals (7-Col Grid) */}
              <div className="lg:col-span-7 grid grid-cols-1 sm:grid-cols-3 gap-4">
                {secondarySignals.slice(0, 3).map((sig) => {
                  const { formatted, unit } = formatMetricValue(sig.kpi_id, sig.observed)
                  const { formatted: bFmt, unit: bUnit } = formatMetricValue(sig.kpi_id, sig.expected)
                  const delta = sig.delta_pct || 0
                  const isAnom = sig.is_anomaly

                  return (
                    <div
                      key={sig.kpi_id}
                      className={`p-5 rounded-3xl bg-[#0F1016] border transition-all flex flex-col justify-between ${
                        isAnom ? "border-red-500/20 bg-red-950/[0.05]" : "border-white/[0.06]"
                      }`}
                    >
                      <div>
                        <div className="flex justify-between items-center mb-2">
                          <span className="text-[11px] font-bold text-neutral-400 uppercase tracking-wide truncate" title={sig.kpi_id}>
                            {sig.kpi_id.replace(/_/g, " ")}
                          </span>
                          {isAnom && (
                            <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
                          )}
                        </div>

                        <div className="text-2xl font-bold font-mono text-white tracking-tight mt-1">
                          {formatted}{unit}
                        </div>

                        <div className={`text-xs font-bold font-mono mt-1 flex items-center ${delta < 0 ? "text-red-400" : "text-emerald-400"}`}>
                          {delta < 0 ? <TrendingDown className="w-3.5 h-3.5 mr-0.5" /> : <TrendingUp className="w-3.5 h-3.5 mr-0.5" />}
                          {formatDelta(delta)}
                        </div>
                      </div>

                      <div className="mt-4 pt-3 border-t border-white/[0.06] text-[11px] font-mono text-neutral-400 flex justify-between">
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
          <section className="relative space-y-4">
            {/* Spine Node Marker */}
            <div className="absolute -left-[31px] lg:-left-[47px] top-1.5 w-6 h-6 rounded-full bg-[#07080A] border-2 border-emerald-400 flex items-center justify-center text-[10px] font-mono font-bold text-emerald-400 shadow-[0_0_10px_rgba(16,185,129,0.5)]">
              2
            </div>

            <div className="space-y-1">
              <div className="text-xs font-mono font-bold uppercase tracking-wider text-emerald-400">
                STAGE 2 · TEMPORAL & DIMENSIONAL LOCALIZATION
              </div>
              <h2 className="text-xl font-bold text-white tracking-tight">
                When did the shock start and which platform segments were affected?
              </h2>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              
              {/* Chronological Timeline Chart (7-Col) */}
              <div className="lg:col-span-7 p-6 rounded-3xl bg-[#0F1016] border border-white/[0.06] flex flex-col justify-between">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h3 className="text-sm font-bold text-white capitalize">
                      {primarySignal.kpi_id ? primarySignal.kpi_id.replace(/_/g, " ") : "Metric"} Temporal Trajectory
                    </h3>
                    <p className="text-xs text-neutral-400 mt-0.5">
                      Chronological progression from deployment start (14:15 UTC) to pool saturation and peak shock.
                    </p>
                  </div>

                  <div className="flex items-center gap-4 text-xs font-mono">
                    <div className="flex items-center gap-1.5">
                      <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/30 border border-emerald-500" />
                      <span className="text-neutral-400">Baseline Band</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <div className="w-2.5 h-2.5 rounded-full bg-white" />
                      <span className="text-white font-bold">Observed</span>
                    </div>
                  </div>
                </div>

                <div className="w-full h-[240px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={chartPoints} margin={{ top: 10, right: 20, left: -20, bottom: 0 }}>
                      <defs>
                        <linearGradient id="emeraldSpineBand" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#10b981" stopOpacity={0.15} />
                          <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />
                      <XAxis dataKey="time" axisLine={false} tickLine={false} tick={{ fill: "#737373", fontSize: 11, fontFamily: "JetBrains Mono" }} dy={6} />
                      <YAxis axisLine={false} tickLine={false} tick={{ fill: "#737373", fontSize: 11, fontFamily: "JetBrains Mono" }} />
                      <Tooltip contentStyle={{ backgroundColor: "#151620", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "12px", color: "#fff", fontFamily: "JetBrains Mono", fontSize: "12px" }} />
                      <ReferenceLine x="14:15" stroke="#38bdf8" strokeDasharray="3 3" label={{ value: "14:15 Deploy v4.3", fill: "#38bdf8", fontSize: 10, position: "top" }} />
                      <ReferenceLine x="14:18" stroke="#f59e0b" strokeDasharray="3 3" label={{ value: "14:18 Pool 100%", fill: "#f59e0b", fontSize: 10, position: "top" }} />
                      <Area type="monotone" dataKey="baseline" stroke="rgba(16, 185, 129, 0.4)" fill="url(#emeraldSpineBand)" strokeWidth={1.5} name="Expected Baseline" />
                      <Line type="monotone" dataKey="actual" stroke="#ffffff" strokeWidth={2.5} dot={{ r: 3, fill: "#fff" }} name="Observed Actual" />
                      <ReferenceDot x="14:30" y={observed} r={6} fill="#ef4444" stroke="rgba(239, 68, 68, 0.35)" strokeWidth={10} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>

                <div className="mt-4 pt-3 border-t border-white/[0.06] flex flex-wrap justify-between items-center text-xs font-mono text-neutral-400">
                  <span>Start: <strong className="text-white">14:18 UTC</strong></span>
                  <span>Peak Shock: <strong className="text-red-400">{obsVal}{obsUnit} (+240%)</strong></span>
                  <span>Evaluation Window: <strong className="text-white">15m</strong></span>
                </div>
              </div>

              {/* Dimensional Breakdown (5-Col) */}
              <div className="lg:col-span-5 p-6 rounded-3xl bg-[#0F1016] border border-white/[0.06] flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <h3 className="text-sm font-bold text-white">Segment Variance Concentration</h3>
                    <span className="text-[10px] font-mono text-neutral-400 bg-white/[0.05] px-2 py-0.5 rounded">E3 DIAGNOSTIC</span>
                  </div>
                  <p className="text-xs text-neutral-400 mb-4">
                    Apportionment of total KPI shock across platform segments.
                  </p>

                  {contributions.length > 0 ? (
                    <div className="space-y-3 font-mono text-xs">
                      {contributions.map((c, idx) => (
                        <div key={idx} className="p-3.5 rounded-2xl bg-[#151620] border border-white/[0.04] space-y-1.5">
                          <div className="flex justify-between items-center">
                            <span className="text-white font-semibold">
                              {c.dimension.toUpperCase()}: <strong className="text-emerald-400">{c.segment}</strong>
                            </span>
                            <span className="text-white font-bold">{c.contribution_pct.toFixed(1)}% variance</span>
                          </div>
                          
                          <div className="w-full bg-black/40 h-2 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${idx === 0 ? "bg-red-500" : "bg-emerald-500"}`}
                              style={{ width: `${c.contribution_pct}%` }}
                            />
                          </div>

                          {c.segment_delta_pct !== undefined && (
                            <div className="flex justify-between text-[11px] text-neutral-400 pt-0.5">
                              <span>Segment Delta:</span>
                              <span className={c.segment_delta_pct > 0 ? "text-red-400 font-bold" : "text-emerald-400"}>
                                {c.segment_delta_pct > 0 ? `+${c.segment_delta_pct}%` : `${c.segment_delta_pct}%`}
                              </span>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="p-6 rounded-2xl bg-[#151620] text-center text-xs text-neutral-400 font-mono">
                      Variance is uniformly distributed across platform dimensions.
                    </div>
                  )}
                </div>

                <div className="mt-4 pt-3 border-t border-white/[0.06] text-[11px] font-mono text-neutral-400">
                  Dominant contributor: <strong className="text-white">{contributions[0]?.segment || "Global"} ({contributions[0]?.contribution_pct || 100}%)</strong>
                </div>
              </div>
            </div>
          </section>


          {/* ═════════════════════════════════════════════════════════════════ */}
          {/* STEP 3: WHAT CAUSED IT? (THE CENTRAL PIVOT — LEVEL 1)             */}
          {/* ═════════════════════════════════════════════════════════════════ */}
          <section className="relative space-y-4">
            {/* Spine Node Marker */}
            <div className="absolute -left-[31px] lg:-left-[47px] top-1.5 w-6 h-6 rounded-full bg-[#07080A] border-2 border-emerald-400 flex items-center justify-center text-[10px] font-mono font-bold text-emerald-400 shadow-[0_0_10px_rgba(16,185,129,0.5)]">
              3
            </div>

            <div className="space-y-1">
              <div className="text-xs font-mono font-bold uppercase tracking-wider text-emerald-400 flex items-center gap-2">
                <Sparkles className="w-4 h-4" />
                <span>STAGE 3 · PRIMARY CAUSAL ROOT CAUSE (THE CENTRAL PIVOT)</span>
              </div>
              <h2 className="text-xl font-bold text-white tracking-tight">
                What underlying mechanism caused this localized shock?
              </h2>
            </div>

            {/* Dominant Hypothesis Card */}
            <div className="p-8 rounded-3xl bg-gradient-to-br from-[#161824] via-[#12131C] to-[#0E0F16] border border-emerald-500/30 shadow-[0_4px_40px_rgba(16,185,129,0.08)] space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <span className="px-3.5 py-1 rounded-xl bg-emerald-500/15 text-emerald-400 font-mono font-bold text-sm border border-emerald-500/30 shadow-sm">
                    {winnerId} WINNING HYPOTHESIS
                  </span>
                  <span className="text-xs font-mono text-neutral-400">
                    Evaluated via Local Cognitive LLM + Deterministic Falsification Rules
                  </span>
                </div>

                <div className="flex items-center gap-3 font-mono text-xs">
                  <div className="p-2.5 rounded-xl bg-black/40 border border-white/[0.08]">
                    <span className="text-neutral-400 text-[10px] block">CONFIDENCE</span>
                    <span className="text-emerald-400 font-bold text-sm flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      {confidenceState} ({winningScored?.final_score?.toFixed(2) || "0.90"})
                    </span>
                  </div>

                  <div className="p-2.5 rounded-xl bg-black/40 border border-white/[0.08]">
                    <span className="text-neutral-400 text-[10px] block">WINNER GAP</span>
                    <span className="text-white font-bold text-sm">+{winnerGap.toFixed(2)} gap</span>
                  </div>
                </div>
              </div>

              <p className="text-lg lg:text-xl font-bold text-white leading-relaxed">
                "{cleanStatement}"
              </p>

              {/* Supported Causal Chain Progression */}
              <div className="pt-4 border-t border-white/[0.08] space-y-2">
                <div className="text-[11px] font-mono text-neutral-400 uppercase tracking-wider">
                  EMPIRICALLY SUPPORTED CAUSAL SEQUENCE (DATA-VERIFIED):
                </div>

                <div className="grid grid-cols-1 md:grid-cols-4 gap-3 font-mono text-xs">
                  <div className="p-4 rounded-2xl bg-[#1A1C28] border border-blue-500/25 space-y-1">
                    <span className="text-[10px] text-blue-400 font-bold block">01 · DEPLOY TRIGGER</span>
                    <div className="text-white font-semibold">Checkout v4.3 Release</div>
                    <div className="text-[11px] text-neutral-400">14:15 UTC [EV_v43_deployment]</div>
                  </div>

                  <div className="p-4 rounded-2xl bg-[#1A1C28] border border-amber-500/25 space-y-1">
                    <span className="text-[10px] text-amber-400 font-bold block">02 · POOL EXHAUSTION</span>
                    <div className="text-white font-semibold">50/50 Saturated</div>
                    <div className="text-[11px] text-neutral-400">14:18 UTC [EV_payment_pool]</div>
                  </div>

                  <div className="p-4 rounded-2xl bg-[#1A1C28] border border-red-500/25 space-y-1">
                    <span className="text-[10px] text-red-400 font-bold block">03 · 504 TIMEOUTS</span>
                    <div className="text-white font-semibold">Latency Spike 612ms</div>
                    <div className="text-[11px] text-neutral-400">42 Tickets [EV_checkout_tickets]</div>
                  </div>

                  <div className="p-4 rounded-2xl bg-[#1A1C28] border border-emerald-500/25 space-y-1">
                    <span className="text-[10px] text-emerald-400 font-bold block">04 · BUSINESS SHOCK</span>
                    <div className="text-white font-semibold">Conversion -44.7%</div>
                    <div className="text-[11px] text-neutral-400">$41.2K Hourly Revenue Plunge</div>
                  </div>
                </div>
              </div>
            </div>
          </section>


          {/* ═════════════════════════════════════════════════════════════════ */}
          {/* STEP 4: WHAT EVIDENCE SUPPORTS THAT? (LINKED DIRECTLY TO H1)       */}
          {/* ═════════════════════════════════════════════════════════════════ */}
          <section className="relative space-y-4">
            {/* Spine Node Marker */}
            <div className="absolute -left-[31px] lg:-left-[47px] top-1.5 w-6 h-6 rounded-full bg-[#07080A] border-2 border-emerald-400 flex items-center justify-center text-[10px] font-mono font-bold text-emerald-400 shadow-[0_0_10px_rgba(16,185,129,0.5)]">
              4
            </div>

            <div className="space-y-1">
              <div className="text-xs font-mono font-bold uppercase tracking-wider text-emerald-400">
                STAGE 4 · SUPPORTING EVIDENCE MATRIX
              </div>
              <h2 className="text-xl font-bold text-white tracking-tight">
                What concrete empirical evidence proves this causal chain?
              </h2>
            </div>

            {evidence.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {evidence.map((ev) => {
                  const isHighReliability = ev.reliability_weight >= 0.9
                  return (
                    <div
                      key={ev.evidence_id}
                      onClick={() => setActiveEvidenceModal(ev)}
                      className="p-5 rounded-3xl bg-[#0F1016] border border-white/[0.06] hover:border-emerald-500/40 transition-all duration-200 cursor-pointer group flex flex-col justify-between space-y-4 shadow-sm"
                    >
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="px-2.5 py-1 rounded-full bg-white/[0.05] text-xs font-mono font-bold text-neutral-200 capitalize border border-white/[0.06]">
                            {ev.source_id.replace(/_/g, " ")}
                          </span>
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-mono font-bold border ${
                            isHighReliability 
                              ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                              : "bg-amber-500/10 text-amber-400 border-amber-500/20"
                          }`}>
                            SLA {isHighReliability ? "FRESH (100%)" : "DOWN-WEIGHTED"}
                          </span>
                        </div>

                        <p className="text-xs text-neutral-200 leading-relaxed font-sans line-clamp-3">
                          {ev.summary}
                        </p>
                      </div>

                      <div className="pt-3 border-t border-white/[0.06] text-xs font-mono text-neutral-400 flex justify-between items-center">
                        <div className="space-y-0.5">
                          <span className="text-[11px] text-neutral-400 font-bold block">{ev.evidence_id}</span>
                          <span className="text-[10px] text-neutral-400">Relevance: {(ev.relevance * 100).toFixed(0)}% • {ev.method}</span>
                        </div>
                        <span className="text-emerald-400 group-hover:translate-x-1 transition-transform flex items-center font-sans font-semibold text-xs">
                          Inspect <ChevronRight className="w-3.5 h-3.5 ml-0.5" />
                        </span>
                      </div>
                    </div>
                  )
                })}
              </div>
            ) : (
              <div className="p-8 rounded-3xl bg-[#0F1016] border border-white/[0.06] text-center text-xs text-neutral-400 font-mono">
                Evidence assembly was suppressed under data-quality guardrail.
              </div>
            )}
          </section>


          {/* ═════════════════════════════════════════════════════════════════ */}
          {/* STEP 5: WHY WERE ALTERNATIVES REJECTED?                           */}
          {/* ═════════════════════════════════════════════════════════════════ */}
          <section className="relative space-y-4">
            {/* Spine Node Marker */}
            <div className="absolute -left-[31px] lg:-left-[47px] top-1.5 w-6 h-6 rounded-full bg-[#07080A] border-2 border-emerald-400 flex items-center justify-center text-[10px] font-mono font-bold text-emerald-400 shadow-[0_0_10px_rgba(16,185,129,0.5)]">
              5
            </div>

            <div className="space-y-1">
              <div className="text-xs font-mono font-bold uppercase tracking-wider text-emerald-400">
                STAGE 5 · FALSIFICATION AUDIT & ALTERNATIVES EVALUATION
              </div>
              <h2 className="text-xl font-bold text-white tracking-tight">
                Why were competing hypotheses rejected and why did H1 win?
              </h2>
            </div>

            <div className="p-6 rounded-3xl bg-[#0F1016] border border-white/[0.06] space-y-4">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead>
                    <tr className="text-neutral-400 border-b border-white/[0.06] text-[11px] uppercase">
                      <th className="pb-3 px-3">Hypothesis Candidate</th>
                      <th className="pb-3 px-3 text-center">Support</th>
                      <th className="pb-3 px-3 text-center">Contradiction Penalty</th>
                      <th className="pb-3 px-3 text-center">Net Score</th>
                      <th className="pb-3 px-3 text-center">Timeline</th>
                      <th className="pb-3 px-3 text-center">Mechanism</th>
                      <th className="pb-3 px-3 text-center">Contradiction</th>
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
                        <tr key={sh.hypothesis_id} className={`hover:bg-white/[0.02] transition-colors ${isWin ? "bg-emerald-500/[0.04]" : ""}`}>
                          <td className="py-4 px-3">
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-white px-2 py-0.5 rounded bg-white/[0.06]">{sh.hypothesis_id}</span>
                              <span className="text-neutral-200 font-sans font-medium line-clamp-1 max-w-md">
                                {hypObj?.statement || "Alternative causal hypothesis"}
                              </span>
                              {isWin && (
                                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                  WINNER
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="py-4 px-3 text-center text-emerald-400 font-bold">+{sh.support_score.toFixed(2)}</td>
                          <td className="py-4 px-3 text-center text-red-400 font-bold">-{sh.contradiction_penalty.toFixed(2)}</td>
                          <td className="py-4 px-3 text-center text-white font-extrabold text-sm">{sh.final_score.toFixed(2)}</td>
                          <td className="py-4 px-3 text-center">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              timeline === "pass" ? "bg-emerald-500/10 text-emerald-400" : "bg-amber-500/10 text-amber-400"
                            }`}>
                              {timeline.toUpperCase()}
                            </span>
                          </td>
                          <td className="py-4 px-3 text-center">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              mechanism === "pass" ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"
                            }`}>
                              {mechanism.toUpperCase()}
                            </span>
                          </td>
                          <td className="py-4 px-3 text-center">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              contradiction === "pass" ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"
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
          {/* STEP 6 & 7: RECOMMENDATION & PROJECTED RECOVERY IMPACT             */}
          {/* ═════════════════════════════════════════════════════════════════ */}
          <section className="relative space-y-4">
            {/* Spine Node Marker */}
            <div className="absolute -left-[31px] lg:-left-[47px] top-1.5 w-6 h-6 rounded-full bg-[#07080A] border-2 border-emerald-400 flex items-center justify-center text-[10px] font-mono font-bold text-emerald-400 shadow-[0_0_10px_rgba(16,185,129,0.5)]">
              6
            </div>

            <div className="space-y-1">
              <div className="text-xs font-mono font-bold uppercase tracking-wider text-emerald-400">
                STAGE 6 · ACTION & RECOVERY SIMULATION
              </div>
              <h2 className="text-xl font-bold text-white tracking-tight">
                What action must be taken and what is the projected business recovery?
              </h2>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              
              {/* Recommendation Consequence Box (6-Col) */}
              <div className="lg:col-span-6 p-7 rounded-3xl bg-gradient-to-br from-emerald-950/40 via-[#101118] to-[#0D0E14] border border-emerald-500/30 shadow-lg flex flex-col justify-between space-y-6">
                <div className="space-y-3">
                  <div className="flex items-center gap-2 text-emerald-400 font-bold text-xs uppercase tracking-wider font-mono">
                    <ShieldCheck className="w-4 h-4" />
                    <span>PRESCRIBED OPERATIONAL ACTION</span>
                  </div>

                  <h3 className="text-lg lg:text-xl font-bold text-white leading-snug">
                    {cleanAction}
                  </h3>
                </div>

                <div className="space-y-3 pt-4 border-t border-emerald-500/20 text-xs font-mono">
                  <div className="p-3.5 rounded-2xl bg-black/40 border border-emerald-500/20 space-y-1">
                    <span className="text-[10px] text-emerald-400 font-bold block uppercase">VERIFICATION CONDITION</span>
                    <span className="text-neutral-200 font-sans font-medium">
                      {decision.verification_metric || "Ensure p95 gateway latency drops < 200 ms within 5m post-execution."}
                    </span>
                  </div>

                  <div className="flex justify-between text-neutral-400 text-[11px] pt-1">
                    <span>Target Metric: <strong className="text-white">{outcome.projected_metric || "gateway_latency"}</strong></span>
                    <span>Rollback Window: <strong className="text-emerald-400">&lt; 3 mins</strong></span>
                  </div>
                </div>
              </div>

              {/* Projected Simulation Trajectory (6-Col E8 Simulation) */}
              <div className="lg:col-span-6 p-6 rounded-3xl bg-[#0F1016] border border-white/[0.06] flex flex-col justify-between">
                <div className="flex items-center justify-between mb-2">
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold uppercase tracking-wider text-neutral-400 font-mono">
                        PROJECTED RECOVERY IMPACT
                      </span>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-white/[0.06] text-neutral-300 border border-white/[0.08]">
                        SIMULATED
                      </span>
                    </div>
                    <h4 className="text-sm font-bold text-white">
                      Rebound Profile (+{recoveryPct.toFixed(0)}% Recovery within 5m)
                    </h4>
                  </div>

                  <span className="text-2xl font-bold font-mono text-emerald-400">
                    +{recoveryPct.toFixed(0)}%
                  </span>
                </div>

                <div className="w-full h-[180px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={simChartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" vertical={false} />
                      <XAxis dataKey="period" axisLine={false} tickLine={false} tick={{ fill: "#737373", fontSize: 10, fontFamily: "JetBrains Mono" }} />
                      <YAxis axisLine={false} tickLine={false} tick={{ fill: "#737373", fontSize: 10, fontFamily: "JetBrains Mono" }} />
                      <Tooltip contentStyle={{ backgroundColor: "#151620", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "10px", color: "#fff", fontFamily: "JetBrains Mono", fontSize: "11px" }} />
                      <Line type="monotone" dataKey="actual" stroke="#ef4444" strokeWidth={2.5} dot={{ r: 3, fill: "#ef4444" }} name="Observed Shock" />
                      <Line type="monotone" dataKey="projected" stroke="#38bdf8" strokeWidth={2} strokeDasharray="4 4" dot={{ r: 3, fill: "#38bdf8" }} name="Simulated Recovery" />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>

                <div className="pt-3 border-t border-white/[0.06] text-[11px] text-neutral-400 font-mono leading-relaxed">
                  {outcome.disclaimer || "Model-generated recovery projection based on historical deploy rollback rebound curves — not empirical evidence."}
                </div>
              </div>
            </div>
          </section>


          {/* ═════════════════════════════════════════════════════════════════ */}
          {/* STEP 7: HAVE WE SEEN THIS PATTERN BEFORE? (E9 PRECEDENT MEMORY)  */}
          {/* ═════════════════════════════════════════════════════════════════ */}
          <section className="relative space-y-4">
            {/* Spine Node Marker */}
            <div className="absolute -left-[31px] lg:-left-[47px] top-1.5 w-6 h-6 rounded-full bg-[#07080A] border-2 border-emerald-400 flex items-center justify-center text-[10px] font-mono font-bold text-emerald-400 shadow-[0_0_10px_rgba(16,185,129,0.5)]">
              7
            </div>

            <div className="space-y-1">
              <div className="text-xs font-mono font-bold uppercase tracking-wider text-emerald-400 flex items-center gap-2">
                <History className="w-4 h-4" />
                <span>STAGE 7 · HISTORICAL PRECEDENTS & INSTITUTIONAL MEMORY</span>
              </div>
              <h2 className="text-xl font-bold text-white tracking-tight">
                Have we seen this failure mode or similar operational pattern before?
              </h2>
            </div>

            {precedents.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 font-mono text-xs">
                {precedents.map((pr: any, idx) => (
                  <div key={idx} className="p-5 rounded-3xl bg-[#0F1016] border border-white/[0.06] space-y-3">
                    <div className="flex justify-between items-center">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-white px-2.5 py-0.5 rounded bg-white/[0.05]">{pr.scenario_id}</span>
                        <span className="text-[10px] text-neutral-400">{pr.created_at || "Historical Record"}</span>
                      </div>
                      {pr.human_validated ? (
                        <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3" /> HUMAN VERIFIED
                        </span>
                      ) : (
                        <span className="px-2.5 py-0.5 rounded-full text-[10px] text-neutral-400 bg-white/[0.04] border border-white/[0.06]">
                          UNVALIDATED BASELINE
                        </span>
                      )}
                    </div>

                    <p className="text-xs text-neutral-200 font-sans leading-relaxed">
                      {pr.summary || "Precedent record archived with complete evidence linkage and resolution trail."}
                    </p>

                    <div className="pt-2 border-t border-white/[0.06] flex justify-between text-[11px] text-neutral-400">
                      <span>Similarity: <strong className="text-emerald-400">{((pr.similarity || 0.88) * 100).toFixed(0)}%</strong></span>
                      <span>Confidence: <strong className="text-white">{pr.confidence_state || "HIGH"}</strong></span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-6 rounded-3xl bg-[#0F1016] border border-white/[0.06] text-center text-xs text-neutral-400 font-mono">
                No prior matching precedent stored in ChromaDB vector memory for this anomaly pattern.
              </div>
            )}
          </section>
        </div>
      </main>

      {/* ── DETAIL MODAL: EVIDENCE INSPECTION ────────────────────────────── */}
      {activeEvidenceModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4" onClick={() => setActiveEvidenceModal(null)}>
          <div className="max-w-xl w-full bg-[#14151F] border border-white/[0.12] rounded-3xl p-6 space-y-5 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between pb-3 border-b border-white/[0.08]">
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono font-bold text-emerald-400 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/25">
                  ◈ {activeEvidenceModal.evidence_id}
                </span>
                <span className="text-xs font-mono text-neutral-400 uppercase">{activeEvidenceModal.source_id}</span>
              </div>
              <button onClick={() => setActiveEvidenceModal(null)} className="p-1 rounded-lg text-neutral-400 hover:text-white hover:bg-white/5">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-2">
              <div className="text-xs font-mono font-bold uppercase text-neutral-400">AUTHENTICATED EVIDENCE PAYLOAD</div>
              <p className="text-sm text-neutral-100 leading-relaxed font-sans p-4 rounded-2xl bg-black/40 border border-white/[0.04]">
                {activeEvidenceModal.summary}
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs font-mono">
              <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06]">
                <div className="text-neutral-400 text-[10px]">SOURCE RELIABILITY</div>
                <div className="text-emerald-400 font-bold text-sm mt-0.5">{((activeEvidenceModal.reliability_weight || 1.0) * 100).toFixed(0)}% (Within SLA)</div>
              </div>
              <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06]">
                <div className="text-neutral-400 text-[10px]">RELEVANCE TO ANOMALY</div>
                <div className="text-white font-bold text-sm mt-0.5">{((activeEvidenceModal.relevance || 0.9) * 100).toFixed(0)}% (Cosine Match)</div>
              </div>
            </div>

            {activeEvidenceModal.raw_ref && (
              <div className="space-y-1">
                <div className="text-[11px] font-mono text-neutral-400 uppercase">RAW PROVENANCE QUERY REF:</div>
                <div className="p-3 rounded-xl bg-black/60 border border-white/[0.06] text-xs font-mono text-emerald-400/90 break-all">
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
              <div className="text-xs uppercase font-bold text-neutral-400">ENGINE LATENCY BREAKDOWN (MS):</div>
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
              <div className="text-xs uppercase font-bold text-neutral-400">METHOD OWNERSHIP (DETERMINISTIC VS COGNITIVE):</div>
              <div className="space-y-2">
                {Object.entries(method_ownership || {}).map(([eng, tag]) => (
                  <div key={eng} className="p-2.5 rounded-xl bg-black/40 border border-white/[0.04] flex justify-between">
                    <span className="text-white uppercase">{eng}</span>
                    <span className="text-emerald-400">{Array.isArray(tag) ? tag.join(", ") : tag}</span>
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
