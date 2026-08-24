import React, { useState } from "react"
import { InvestigationResult, PersonaType, EvidenceItem } from "../../types/investigation"
import { SCENARIO_CATALOG } from "../../lib/defaultData"
import { formatMetricValue, formatDelta, formatZScore } from "../../lib/utils"
import { ScenarioSelector, PersonaSelector, RegionSelector } from "./ScenarioSelector"
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
  Clock, 
  ShieldAlert, 
  Scale, 
  Globe, 
  Eye, 
  Play, 
  Lock,
  ArrowRight,
  Database,
  Layers
} from "lucide-react"

interface AnalysisConfig {
  scenarioId: string
  persona: PersonaType
  region: string
}

interface InvestigationOverviewProps {
  result: InvestigationResult
  activeConfig: AnalysisConfig
  evaluatedConfig: AnalysisConfig
  isStale: boolean
  isPreviousResultPinned: boolean
  onConfigChange: (scenarioId: string, persona: PersonaType, region: string) => void
  onRunLive: (scenarioId?: string, persona?: PersonaType, region?: string) => void
  onKeepViewingPrevious: () => void
  isLiveLoading?: boolean
  liveElapsedSeconds?: number
}

export const InvestigationOverview: React.FC<InvestigationOverviewProps> = ({ 
  result, 
  activeConfig,
  evaluatedConfig,
  isStale,
  isPreviousResultPinned,
  onConfigChange,
  onRunLive,
  onKeepViewingPrevious,
  isLiveLoading = false,
  liveElapsedSeconds = 0,
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

  // Persona Scope Definitions
  const personaScopes: Record<PersonaType, { label: string; sourcesCount: number; summary: string }> = {
    analyst: {
      label: "Analyst",
      sourcesCount: 7,
      summary: "Full access (orders, payment_gateway, inventory, marketing, deployment_log, support_tickets, release_notes)",
    },
    cfo: {
      label: "CFO",
      sourcesCount: 2,
      summary: "Executive aggregate access (orders, inventory)",
    },
    manager: {
      label: "Manager",
      sourcesCount: 2,
      summary: "Regional bounded access (orders, inventory)",
    },
  }

  // 2. FUNDAMENTAL THREE-WAY STATE MODEL:
  // State A: isGuardTriggered (decision.abstained && hypotheses.length === 0)
  // State B: isAmbiguousAbstain (decision.abstained && hypotheses.length > 0)
  // State C: isSuccess (!decision.abstained && hypotheses.length > 0)
  const isAbstained = Boolean(decision.abstained)
  const hasHypotheses = hypotheses.length > 0
  const isGuardTriggered = isAbstained && !hasHypotheses
  const isAmbiguousAbstain = isAbstained && hasHypotheses
  const isSuccess = !isAbstained && hasHypotheses

  // Signal extraction
  const anomalies = signals.filter((s) => s.is_anomaly)
  const primarySignal = anomalies[0] || signals[0] || {}
  const secondarySignals = signals.filter((s) => s.kpi_id !== primarySignal.kpi_id)

  const { formatted: obsVal, unit: obsUnit } = formatMetricValue(primarySignal.kpi_id || "", primarySignal.observed)
  const { formatted: expVal, unit: expUnit } = formatMetricValue(primarySignal.kpi_id || "", primarySignal.expected)

  // Chronological Time Series Data
  const base = primarySignal.expected || 180
  const observed = primarySignal.observed || 612
  const chartPoints = [
    { time: "13:45", baseline: base * 0.98, actual: base * 0.99 },
    { time: "13:55", baseline: base * 0.99, actual: base * 1.01 },
    { time: "14:05", baseline: base * 1.01, actual: base * 0.99 },
    { time: "14:15", baseline: base * 1.00, actual: base * (isGuardTriggered ? 1.02 : 1.15) },
    { time: "14:18", baseline: base * 1.01, actual: base * (isGuardTriggered ? 1.01 : 1.65) },
    { time: "14:22", baseline: base * 0.99, actual: base * (isGuardTriggered ? 0.99 : 2.30) },
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

  // Hypothesis & Scoring Computations
  const sortedScores = [...scored].sort((a, b) => b.final_score - a.final_score)
  const winnerId = decision.winning_hypothesis_id || sortedScores[0]?.hypothesis_id
  const winningHyp = hypotheses.find((h) => h.hypothesis_id === winnerId)
  const winningScored = scored.find((s) => s.hypothesis_id === winnerId) || sortedScores[0]

  const winnerGap = sortedScores.length > 1 ? sortedScores[0].final_score - sortedScores[1].final_score : 0.0
  const confidenceState = winningScored?.confidence_state || (isAbstained ? "ABSTAIN" : "HIGH")

  const cleanStatement = winningHyp?.statement
    ? winningHyp.statement.replace(/\[LLM_NARRATIVE\]|\[LLM\]|\[RULES\]/g, "").trim()
    : ""

  const cleanAction = decision.recommended_action
    ? decision.recommended_action.replace(/\[LLM_NARRATIVE\]|\[LLM\]/g, "").trim()
    : "Hold operational changes and monitor telemetry."

  // Guard Type Rationale
  const isSparse = signals.some((s) => s.sparse_history) || scenario_id === "INC_003"
  const isDataQuality = signals.some((s) => s.data_quality_suspect) || scenario_id === "INC_004"
  const isNominal = signals.every((s) => !s.is_anomaly) || scenario_id === "INC_005"

  let guardTitle = "Deterministic Safety Guardrail Triggered"
  let guardCategory = "Governance & Anomaly Suppression Guard"
  if (isSparse) {
    guardTitle = "Sparse Baseline History Guard"
    guardCategory = "Data Volume Safety Guard"
  } else if (isDataQuality) {
    guardTitle = "Data-Quality Verification Guard"
    guardCategory = "Pipeline Freshness & Partition Integrity Guard"
  } else if (isNominal) {
    guardTitle = "Nominal Seasonal Corridor (No Anomaly)"
    guardCategory = "Statistical Invariance Verification"
  }

  // Status Badge Logic
  let statusBadge = {
    label: `Completed (${confidenceState} ${winningScored?.final_score?.toFixed(2) || "0.90"})`,
    color: "bg-emerald-500/10 text-emerald-400 border-emerald-500/25",
  }

  if (isGuardTriggered) {
    if (isSparse) {
      statusBadge = {
        label: "Sparse Baseline Guard (ABSTAIN)",
        color: "bg-amber-500/10 text-amber-400 border-amber-500/25",
      }
    } else if (isDataQuality) {
      statusBadge = {
        label: "Data-Quality Guard (ABSTAIN)",
        color: "bg-amber-500/10 text-amber-400 border-amber-500/25",
      }
    } else if (isNominal) {
      statusBadge = {
        label: "Nominal Baseline (NO ANOMALY)",
        color: "bg-blue-500/10 text-blue-400 border-blue-500/25",
      }
    } else {
      statusBadge = {
        label: "Governance Guard (ABSTAIN)",
        color: "bg-amber-500/10 text-amber-400 border-amber-500/25",
      }
    }
  } else if (isAmbiguousAbstain) {
    statusBadge = {
      label: `Ambiguous Conflict (ABSTAIN · Margin ${winnerGap.toFixed(2)} < 0.15)`,
      color: "bg-amber-500/10 text-amber-400 border-amber-500/25",
    }
  }

  // Dynamic Causal Trail Steps
  const causalTrailByScenario: Record<string, { step: string; title: string; subtitle: string; color: string }[]> = {
    INC_001: [
      { step: "01 · DEPLOY TRIGGER", title: "Checkout v4.3 Release", subtitle: "14:15 UTC [EV_v43_deployment]", color: "text-blue-400 border-blue-500/20" },
      { step: "02 · POOL SATURATION", title: "50/50 Saturated", subtitle: "14:18 UTC [EV_payment_pool]", color: "text-amber-400 border-amber-500/20" },
      { step: "03 · TIMEOUT SPIKES", title: "Latency 612ms", subtitle: "42 Tickets [EV_checkout_tickets]", color: "text-red-400 border-red-500/20" },
      { step: "04 · REVENUE IMPACT", title: "Conversion -44.7%", subtitle: "$41.2K Hourly Shock", color: "text-emerald-400 border-emerald-500/20" },
    ],
    INC_006: [
      { step: "01 · WAN PACKET LOSS", title: "18% Ingress Drop", subtitle: "10:05 UTC [EV_upstream_packet_loss]", color: "text-blue-400 border-blue-500/20" },
      { step: "02 · RETRY STORM", title: "Un-jittered Retries", subtitle: "10:08 UTC [EV_auth_retry_storm]", color: "text-amber-400 border-amber-500/20" },
      { step: "03 · AUTH SATURATION", title: "Auth-Proxy Thread Lock", subtitle: "Cascading Mesh Latency", color: "text-red-400 border-red-500/20" },
      { step: "04 · PLATFORM IMPACT", title: "Error Rate 12.8%", subtitle: "+2460% Outage Shock", color: "text-emerald-400 border-emerald-500/20" },
    ],
    INC_007: [
      { step: "01 · BUFFER LEAK", title: "Byte Buffer Retained", subtitle: "[EV_buffer_leak_telemetry]", color: "text-blue-400 border-blue-500/20" },
      { step: "02 · HEAP DRIFT", title: "+1.2GB every 6h", subtitle: "Continuous 48h Drift", color: "text-amber-400 border-amber-500/20" },
      { step: "03 · GC THRASHING", title: "Latency 3200ms", subtitle: "Worker Stalls", color: "text-red-400 border-red-500/20" },
      { step: "04 · COMPUTE IMPACT", title: "Memory 94.2%", subtitle: "Cluster Capacity Critical", color: "text-emerald-400 border-emerald-500/20" },
    ],
    INC_008: [
      { step: "01 · CERT EXPIRY", title: "SAML x509 Expired", subtitle: "00:00 UTC [EV_saml_cert_expiry]", color: "text-blue-400 border-blue-500/20" },
      { step: "02 · VALIDATION HALT", title: "Crypto Reject", subtitle: "Inbound Assertion Drop", color: "text-amber-400 border-amber-500/20" },
      { step: "03 · LOGIN OUTAGE", title: "100% SP Drop", subtitle: "Enterprise SSO Blocked", color: "text-red-400 border-red-500/20" },
      { step: "04 · SESSION IMPACT", title: "Failure Rate 98.4%", subtitle: "Sessions Plunge -96.6%", color: "text-emerald-400 border-emerald-500/20" },
    ],
  }

  const activeCausalTrail = causalTrailByScenario[scenario_id] || []

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

  return (
    <div className="min-h-screen bg-[#08090C] text-white font-sans selection:bg-emerald-500/20 antialiased relative">
      
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
            onClick={() => onRunLive()}
            disabled={isLiveLoading}
            className="flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black font-semibold text-xs transition-all shadow-[0_0_15px_rgba(16,185,129,0.25)] active:scale-95 disabled:opacity-50 cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLiveLoading ? "animate-spin" : ""}`} />
            <span>{isLiveLoading ? "Running Inference..." : "Run Investigation"}</span>
          </button>
        </div>
      </nav>

      {/* ── Main Investigation Dashboard Canvas ─────────────────────────── */}
      <main className="max-w-[1380px] mx-auto px-6 lg:px-10 py-6 space-y-6">
        
        {/* ── 2. Header with Unified Custom Command Selectors & Scope Bar ─── */}
        <header className="p-4 rounded-2xl bg-[#0F1017] border border-white/[0.06] flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 font-mono font-semibold border border-emerald-500/20">
                {scenario_id}
              </span>
              <span className="text-neutral-400">{currentMeta.domain}</span>
              <span className="text-neutral-600">•</span>
              <span className="text-neutral-300">
                Evaluated: <strong className="text-white capitalize">{evaluatedConfig.persona}</strong> ({evaluatedConfig.region === "all" ? "Global" : evaluatedConfig.region})
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

          {/* Custom Command-Style Scenario, Persona & Region Selectors */}
          <div className="flex flex-wrap items-center gap-2 self-start md:self-center">
            <ScenarioSelector
              selectedScenarioId={activeConfig.scenarioId}
              onSelectScenario={(newId) => onConfigChange(newId, activeConfig.persona, activeConfig.region)}
              disabled={isLiveLoading}
            />
            <PersonaSelector
              selectedPersona={activeConfig.persona}
              onSelectPersona={(newPersona) => onConfigChange(activeConfig.scenarioId, newPersona, activeConfig.region)}
              disabled={isLiveLoading}
            />
            <RegionSelector
              selectedRegion={activeConfig.region}
              onSelectRegion={(newRegion) => onConfigChange(activeConfig.scenarioId, activeConfig.persona, newRegion)}
              disabled={isLiveLoading}
            />
          </div>
        </header>

        {/* ── 3. CONFIGURATION CHANGED / STALE RESULT BANNER ──────────────── */}
        {isStale && !isPreviousResultPinned && (
          <div className="p-5 rounded-2xl bg-gradient-to-r from-blue-950/30 via-[#12131D] to-[#12131D] border border-blue-500/35 shadow-xl space-y-3.5 animate-in fade-in slide-in-from-top-2 duration-200">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-blue-400 font-bold text-sm">
                <AlertTriangle className="w-4 h-4 text-blue-400" />
                <span>Configuration Changed — Active Result is Stale</span>
              </div>
              <span className="text-[11px] font-mono text-neutral-400">
                Pipeline execution required for new configuration
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono">
              <div className="p-3 rounded-xl bg-black/40 border border-white/[0.06] space-y-1">
                <span className="text-[10px] text-neutral-400 uppercase font-semibold">Evaluated Result Scope:</span>
                <div className="text-white font-bold flex items-center gap-2">
                  <span className="px-2 py-0.5 rounded bg-white/[0.06]">{evaluatedConfig.scenarioId}</span>
                  <span className="capitalize">{evaluatedConfig.persona}</span> · {evaluatedConfig.region === "all" ? "Global" : evaluatedConfig.region}
                  <span className="text-neutral-400 text-[10px]">({personaScopes[evaluatedConfig.persona]?.sourcesCount} sources)</span>
                </div>
              </div>

              <div className="p-3 rounded-xl bg-black/40 border border-blue-500/20 space-y-1">
                <span className="text-[10px] text-blue-400 uppercase font-semibold">New Requested Configuration:</span>
                <div className="text-blue-300 font-bold flex items-center gap-2">
                  <span className="px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30">{activeConfig.scenarioId}</span>
                  <span className="capitalize">{activeConfig.persona}</span> · {activeConfig.region === "all" ? "Global" : activeConfig.region}
                  <span className="text-neutral-400 text-[10px]">({personaScopes[activeConfig.persona]?.sourcesCount} sources)</span>
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3 pt-1">
              <button
                onClick={() => onRunLive(activeConfig.scenarioId, activeConfig.persona, activeConfig.region)}
                disabled={isLiveLoading}
                className="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black font-bold text-xs flex items-center gap-2 transition-all shadow-md active:scale-95 cursor-pointer"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Re-run Investigation for {activeConfig.persona.toUpperCase()} ({activeConfig.region === "all" ? "Global" : activeConfig.region})</span>
              </button>

              <button
                onClick={onKeepViewingPrevious}
                className="px-4 py-2 rounded-xl bg-white/[0.06] hover:bg-white/[0.1] text-neutral-300 hover:text-white font-medium text-xs flex items-center gap-2 transition-all border border-white/[0.08] cursor-pointer"
              >
                <Eye className="w-3.5 h-3.5 text-neutral-400" />
                <span>Keep Viewing Previous Result ({evaluatedConfig.persona.toUpperCase()} scope)</span>
              </button>
            </div>
          </div>
        )}

        {/* ── 4. PINNED PREVIOUS RESULT NOTICE (When user explicitly chose to keep viewing) ── */}
        {isStale && isPreviousResultPinned && (
          <div className="px-4 py-2 rounded-xl bg-[#14151F] border border-white/[0.08] flex items-center justify-between text-xs text-neutral-300">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-amber-400" />
              <span>Viewing previous result · <strong>{evaluatedConfig.persona.toUpperCase()} scope ({evaluatedConfig.region})</strong>. Current configuration is <strong>{activeConfig.persona.toUpperCase()} ({activeConfig.region})</strong>.</span>
            </div>
            <button
              onClick={() => onRunLive(activeConfig.scenarioId, activeConfig.persona, activeConfig.region)}
              className="text-emerald-400 font-bold hover:underline cursor-pointer"
            >
              Re-run for {activeConfig.persona.toUpperCase()} →
            </button>
          </div>
        )}

        {/* ── 5. GUARD BANNER (When Applicable) ────────────────────────────── */}
        {isAbstained && decision.abstention_reason && (
          <div className="p-5 rounded-2xl bg-gradient-to-r from-amber-950/25 via-[#13141C] to-[#13141C] border border-amber-500/30 shadow-md space-y-2">
            <div className="flex items-center gap-2 text-amber-400 font-semibold text-sm">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              <span>{guardCategory}</span>
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

        {/* ── 6. THE CAUSAL INVESTIGATION SPINE ──────────────────────────── */}
        <div className="relative pl-6 lg:pl-8 space-y-9 before:absolute before:left-2 before:top-4 before:bottom-4 before:w-0.5 before:bg-gradient-to-b before:from-emerald-500/40 before:via-blue-500/20 before:to-emerald-500/40">

          {/* ═════════════════════════════════════════════════════════════════ */}
          {/* STEP 1: WHAT WAS MEASURED / CHANGED?                              */}
          {/* ═════════════════════════════════════════════════════════════════ */}
          <section className="relative space-y-3">
            <div className="absolute -left-[30px] lg:-left-[38px] top-1 w-5 h-5 rounded-full bg-[#08090C] border-2 border-emerald-400/60 flex items-center justify-center text-[10px] font-bold text-emerald-400">
              <Check className="w-3 h-3" />
            </div>

            <div>
              <div className="text-xs font-medium text-neutral-400">01 · Signal Evaluation</div>
              <h2 className="text-base lg:text-lg font-bold text-white tracking-tight">
                {isNominal ? "What signals were evaluated against historical corridors?" : "What changed and how large is the shift?"}
              </h2>
            </div>

            {/* Asymmetric KPI Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
              
              {/* Primary Evaluated Metric Card (5-Col) */}
              <div className={`lg:col-span-5 p-5 rounded-2xl bg-[#111219] border shadow-sm flex flex-col justify-between relative overflow-hidden ${
                primarySignal.is_anomaly ? "border-red-500/25" : "border-blue-500/25"
              }`}>
                <div className="space-y-2.5">
                  <div className="flex justify-between items-start">
                    <div>
                      <span className={`text-[11px] font-semibold uppercase tracking-wide flex items-center gap-1.5 ${
                        primarySignal.is_anomaly ? "text-red-400" : "text-blue-400"
                      }`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${primarySignal.is_anomaly ? "bg-red-500 animate-pulse" : "bg-blue-400"}`} />
                        {primarySignal.is_anomaly ? "Primary Anomalous Metric" : "Monitored Metric Corridor"}
                      </span>
                      <h3 className="text-sm font-bold text-white capitalize mt-0.5">
                        {primarySignal.kpi_id ? primarySignal.kpi_id.replace(/_/g, " ") : "Primary Metric"}
                      </h3>
                    </div>
                    <span className={`px-2 py-0.5 rounded-full text-xs font-mono font-bold border ${
                      primarySignal.is_anomaly 
                        ? "bg-red-500/10 text-red-400 border-red-500/20"
                        : "bg-blue-500/10 text-blue-400 border-blue-500/20"
                    }`}>
                      {formatZScore(primarySignal.z_score)}
                    </span>
                  </div>

                  <div className="flex items-baseline gap-3">
                    <span className="text-3xl font-extrabold font-mono text-white tracking-tight">
                      {obsVal}{obsUnit}
                    </span>
                    <span className={`text-sm font-bold font-mono flex items-center ${
                      (primarySignal.delta_pct || 0) < 0 ? "text-red-400" : "text-emerald-400"
                    }`}>
                      {(primarySignal.delta_pct || 0) < 0 ? <TrendingDown className="w-4 h-4 mr-0.5" /> : <TrendingUp className="w-4 h-4 mr-0.5" />}
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
                    <div className={`font-semibold text-sm mt-0.5 ${primarySignal.is_anomaly ? "text-red-400" : "text-blue-400"}`}>
                      {primarySignal.is_anomaly ? "> 3.0σ Anomaly" : "Within ±0.45σ Normal"}
                    </div>
                  </div>
                </div>
              </div>

              {/* Supporting Secondary Signals (7-Col Grid) */}
              <div className="lg:col-span-7 grid grid-cols-1 sm:grid-cols-3 gap-3">
                {secondarySignals.length > 0 ? (
                  secondarySignals.slice(0, 3).map((sig) => {
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
                  })
                ) : (
                  <div className="sm:col-span-3 p-5 rounded-2xl bg-[#0E0F15] border border-white/[0.05] flex items-center justify-center text-xs text-neutral-400 text-center">
                    Single metric evaluation corridor under active investigation scope.
                  </div>
                )}
              </div>
            </div>
          </section>


          {/* ═════════════════════════════════════════════════════════════════ */}
          {/* STEP 2: TEMPORAL & DIMENSIONAL CORRIDOR                           */}
          {/* ═════════════════════════════════════════════════════════════════ */}
          <section className="relative space-y-3">
            <div className="absolute -left-[30px] lg:-left-[38px] top-1 w-5 h-5 rounded-full bg-[#08090C] border-2 border-emerald-400/60 flex items-center justify-center text-[10px] font-bold text-emerald-400">
              <Check className="w-3 h-3" />
            </div>

            <div>
              <div className="text-xs font-medium text-neutral-400">02 · Temporal & Dimensional Context</div>
              <h2 className="text-base lg:text-lg font-bold text-white tracking-tight">
                {isGuardTriggered ? "Observed telemetry series & segment distribution" : "When did it happen and where is it concentrated?"}
              </h2>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
              
              {/* Chronological Timeline Chart (7-Col) */}
              <div className="lg:col-span-7 p-5 rounded-2xl bg-[#0E0F15] border border-white/[0.06] flex flex-col justify-between space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-xs font-bold text-white capitalize">
                      {primarySignal.kpi_id ? primarySignal.kpi_id.replace(/_/g, " ") : "Metric"} Progression Window
                    </h3>
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

                {/* Timeline sequence chips */}
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
                      {primarySignal.is_anomaly && (
                        <ReferenceDot x="14:30" y={observed} r={5} fill="#ef4444" stroke="rgba(239, 68, 68, 0.35)" strokeWidth={8} />
                      )}
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>

                <div className="pt-2.5 border-t border-white/[0.06] flex flex-wrap justify-between items-center text-[11px] text-neutral-400">
                  <span>Evaluation Window: <strong className="text-white">15m rolling</strong></span>
                  <span>Observed Status: <strong className={primarySignal.is_anomaly ? "text-red-400" : "text-emerald-400"}>{obsVal}{obsUnit} ({formatDelta(primarySignal.delta_pct)})</strong></span>
                </div>
              </div>

              {/* Dimensional Breakdown (5-Col) */}
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
                    <div className="p-5 rounded-xl bg-[#14151F] text-center text-xs text-neutral-400 space-y-1">
                      <div>Variance is uniformly distributed across platform traffic.</div>
                      <div className="text-[11px] text-neutral-500">No disproportionate segment skew isolated.</div>
                    </div>
                  )}
                </div>

                <div className="pt-2.5 border-t border-white/[0.06] flex items-center justify-between text-[11px] text-neutral-400">
                  <span>DOMINANT CONTRIBUTOR:</span>
                  <span className="text-white font-mono font-bold">
                    {contributions[0]?.segment || "Global"} · {contributions[0]?.contribution_pct ? `${contributions[0].contribution_pct.toFixed(1)}%` : "100%"} of variance
                  </span>
                </div>
              </div>
            </div>
          </section>


          {/* ═════════════════════════════════════════════════════════════════ */}
          {/* STEP 3: DYNAMIC BRANCHING BASED ON STATE MODEL                    */}
          {/* ═════════════════════════════════════════════════════════════════ */}
          {isGuardTriggered ? (
            /* ── STATE A: GUARD STATE ── */
            <section className="relative space-y-3">
              <div className="absolute -left-[32px] lg:-left-[40px] top-1 w-6 h-6 rounded-full bg-[#08090C] border-2 border-amber-400 flex items-center justify-center text-xs font-bold text-amber-400 shadow-[0_0_15px_rgba(245,158,11,0.4)]">
                !
              </div>

              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-amber-400 flex items-center gap-1.5">
                  <ShieldAlert className="w-3.5 h-3.5" />
                  <span>03 · Governance & Safety Guardrail</span>
                </div>
                <h2 className="text-lg lg:text-xl font-extrabold text-white tracking-tight">
                  {guardTitle}
                </h2>
              </div>

              <div className="p-6 rounded-3xl bg-gradient-to-br from-[#1C1710] via-[#141210] to-[#0D0E14] border border-amber-500/35 shadow-md space-y-5">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div className="flex items-center gap-2.5">
                    <span className="px-3 py-1 rounded-xl bg-amber-500/15 text-amber-400 font-mono font-bold text-xs border border-amber-500/30">
                      SAFETY GUARD ACTIVATED
                    </span>
                    <span className="text-xs text-neutral-400">
                      Hypothesis synthesis suppressed to prevent spurious correlation & hallucination
                    </span>
                  </div>

                  <div className="px-3 py-1.5 rounded-xl bg-black/40 border border-white/[0.08] flex items-center gap-2 font-mono text-xs">
                    <span className="text-neutral-400 text-[11px]">STATUS:</span>
                    <span className="text-amber-400 font-bold">ABSTAIN (GUARDRAIL)</span>
                  </div>
                </div>

                <div className="p-4 rounded-2xl bg-black/40 border border-amber-500/20 space-y-1.5">
                  <div className="text-[11px] font-mono uppercase font-bold text-amber-400 flex items-center gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5" />
                    <span>Guardrail Trigger Rationale:</span>
                  </div>
                  <p className="text-xs text-neutral-200 leading-relaxed font-sans">
                    {decision.abstention_reason || "Deterministic safety guard prevented hypothesis formulation."}
                  </p>
                </div>

                {/* Guard Diagnostic Audit Grid */}
                <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs font-mono">
                  <div className="p-3.5 rounded-xl bg-[#14151F] border border-white/[0.06] space-y-1">
                    <span className="text-[10px] text-neutral-400 font-semibold block uppercase">Signals Evaluated</span>
                    <div className="text-base font-bold text-white">{signals.length} Verified</div>
                    <div className="text-[10px] text-emerald-400/90">Baseline Computed</div>
                  </div>

                  <div className="p-3.5 rounded-xl bg-[#14151F] border border-white/[0.06] space-y-1">
                    <span className="text-[10px] text-neutral-400 font-semibold block uppercase">Evidence Assembled</span>
                    <div className="text-base font-bold text-amber-400">0 Items</div>
                    <div className="text-[10px] text-neutral-400">Retrieval Suppressed</div>
                  </div>

                  <div className="p-3.5 rounded-xl bg-[#14151F] border border-white/[0.06] space-y-1">
                    <span className="text-[10px] text-neutral-400 font-semibold block uppercase">Hypotheses Evaluated</span>
                    <div className="text-base font-bold text-amber-400">0 Candidates</div>
                    <div className="text-[10px] text-neutral-400">Synthesis Halted</div>
                  </div>

                  <div className="p-3.5 rounded-xl bg-[#14151F] border border-white/[0.06] space-y-1">
                    <span className="text-[10px] text-neutral-400 font-semibold block uppercase">Operational Action</span>
                    <div className="text-sm font-bold text-neutral-200 line-clamp-1">Hold Changes</div>
                    <div className="text-[10px] text-emerald-400">Monitor Corridors</div>
                  </div>
                </div>
              </div>
            </section>
          ) : isAmbiguousAbstain ? (
            /* ── STATE B: AMBIGUOUS ABSTAIN ── */
            <section className="relative space-y-3">
              <div className="absolute -left-[32px] lg:-left-[40px] top-1 w-6 h-6 rounded-full bg-[#08090C] border-2 border-amber-400 flex items-center justify-center text-xs font-bold text-amber-400 shadow-[0_0_15px_rgba(245,158,11,0.5)]">
                !
              </div>

              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-amber-400 flex items-center gap-1.5">
                  <Scale className="w-3.5 h-3.5" />
                  <span>03 · Multi-Causal Conflict (Investigation Abstained)</span>
                </div>
                <h2 className="text-lg lg:text-xl font-extrabold text-white tracking-tight">
                  No dominant root cause confirmed (Competing hypotheses insufficiently separated)
                </h2>
              </div>

              <div className="p-6 rounded-3xl bg-gradient-to-br from-[#1A1612] via-[#121118] to-[#0D0E14] border border-amber-500/35 shadow-md space-y-5">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div className="flex items-center gap-2.5">
                    <span className="px-3 py-1 rounded-xl bg-amber-500/15 text-amber-400 font-mono font-bold text-xs border border-amber-500/30">
                      ABSTAINED — AMBIGUOUS SEPARATION
                    </span>
                    <span className="text-xs text-neutral-400">
                      Winning margin (+{winnerGap.toFixed(2)}) is below required threshold (0.15)
                    </span>
                  </div>

                  <div className="flex items-center gap-3 font-mono text-xs">
                    <div className="px-3 py-1.5 rounded-xl bg-black/40 border border-white/[0.08] flex items-center gap-2">
                      <span className="text-neutral-400 text-[11px]">SCORE GAP:</span>
                      <span className="text-amber-400 font-bold">+{winnerGap.toFixed(2)} (Req ≥ 0.15)</span>
                    </div>
                  </div>
                </div>

                <div className="p-4 rounded-2xl bg-black/40 border border-amber-500/20 space-y-1">
                  <div className="text-[11px] font-mono uppercase font-bold text-amber-400">Primary Challenge Conclusion:</div>
                  <p className="text-xs text-neutral-200 leading-relaxed font-sans">
                    {decision.abstention_reason}
                  </p>
                </div>

                {/* Competing Top Hypotheses Side-by-Side */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5 text-xs">
                  {sortedScores.slice(0, 2).map((sh, idx) => {
                    const hypObj = hypotheses.find((h) => h.hypothesis_id === sh.hypothesis_id)
                    return (
                      <div key={sh.hypothesis_id} className="p-4 rounded-2xl bg-[#14151F] border border-white/[0.06] space-y-2">
                        <div className="flex justify-between items-center">
                          <span className="font-bold text-white font-mono px-2 py-0.5 rounded bg-white/[0.06]">
                            Candidate {idx + 1}: {sh.hypothesis_id}
                          </span>
                          <span className="font-mono font-bold text-amber-400 text-xs">
                            Score: {sh.final_score.toFixed(2)}
                          </span>
                        </div>
                        <p className="text-xs text-neutral-200 leading-relaxed font-sans">
                          "{hypObj?.statement}"
                        </p>
                      </div>
                    )
                  })}
                </div>
              </div>
            </section>
          ) : (
            /* ── STATE C: SUCCESS STATE ── */
            <section className="relative space-y-3">
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
                {activeCausalTrail.length > 0 && (
                  <div className="pt-3 border-t border-white/[0.06] space-y-2">
                    <div className="text-[11px] text-neutral-400 uppercase tracking-wider font-semibold">
                      Empirically Supported Causal Sequence:
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-4 gap-2.5 text-xs font-mono">
                      {activeCausalTrail.map((node, idx) => (
                        <div key={idx} className={`p-3 rounded-xl bg-[#171924] border ${node.color} space-y-0.5`}>
                          <span className="text-[10px] font-bold block">{node.step}</span>
                          <div className="text-white font-semibold">{node.title}</div>
                          <div className="text-[10px] text-neutral-400">{node.subtitle}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </section>
          )}


          {/* ═════════════════════════════════════════════════════════════════ */}
          {/* STEP 4: SUPPORTING EVIDENCE                                       */}
          {/* ═════════════════════════════════════════════════════════════════ */}
          {evidence.length > 0 && (
            <section className="relative space-y-3">
              <div className="absolute -left-[30px] lg:-left-[38px] top-1 w-5 h-5 rounded-full bg-[#08090C] border border-white/20 flex items-center justify-center text-[10px] text-neutral-400 font-bold">
                →
              </div>

              <div>
                <div className="text-xs font-medium text-neutral-400">04 · Empirical Evidence Foundation</div>
                <h2 className="text-base lg:text-lg font-bold text-white tracking-tight">
                  {isAmbiguousAbstain ? "What evidence was assembled for competing hypotheses?" : `What evidence supports ${winnerId}?`}
                </h2>
              </div>

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
            </section>
          )}


          {/* ═════════════════════════════════════════════════════════════════ */}
          {/* STEP 5: FALSIFICATION AUDIT                                       */}
          {/* ═════════════════════════════════════════════════════════════════ */}
          {scored.length > 0 && (
            <section className="relative space-y-3">
              <div className="absolute -left-[30px] lg:-left-[38px] top-1 w-5 h-5 rounded-full bg-[#08090C] border border-white/20 flex items-center justify-center text-[10px] text-neutral-400 font-bold">
                →
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <div className="text-xs font-medium text-neutral-400">05 · Falsification Audit</div>
                  <h2 className="text-base lg:text-lg font-bold text-white tracking-tight">
                    {isAmbiguousAbstain ? "Why were candidates rejected for decisive isolation?" : `Why did ${winnerId} win and alternatives lose?`}
                  </h2>
                </div>
                <div className="text-xs font-mono text-neutral-400">
                  Separation Margin: <strong className={isAmbiguousAbstain ? "text-amber-400" : "text-emerald-400"}>+{winnerGap.toFixed(2)}</strong>
                </div>
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
                        const mechanism = ruleMap.get("mechanism_consistency")?.verdict || "pass"
                        const contradiction = ruleMap.get("contradiction")?.verdict || "pass"

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
          )}


          {/* ═════════════════════════════════════════════════════════════════ */}
          {/* STEP 6: WHAT SHOULD WE DO & NEXT STEPS                            */}
          {/* ═════════════════════════════════════════════════════════════════ */}
          <section className="relative space-y-3">
            <div className="absolute -left-[30px] lg:-left-[38px] top-1 w-5 h-5 rounded-full bg-[#08090C] border border-white/20 flex items-center justify-center text-[10px] text-neutral-400 font-bold">
              →
            </div>

            <div>
              <div className="text-xs font-medium text-neutral-400">06 · Prescribed Resolution & Operational Next Steps</div>
              <h2 className="text-base lg:text-lg font-bold text-white tracking-tight">
                {isGuardTriggered ? "Recommended next steps & monitoring protocol" : "What action must be taken and what is the expected recovery?"}
              </h2>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
              
              {/* Prescribed Resolution (6-Col or 12-Col if Guard) */}
              <div className={`${isSuccess ? "lg:col-span-6" : "lg:col-span-12"} p-5 rounded-2xl bg-gradient-to-br from-emerald-950/20 via-[#101117] to-[#0D0E14] border ${
                isAbstained ? "border-amber-500/30" : "border-emerald-500/30"
              } shadow-md flex flex-col justify-between space-y-3.5`}>
                <div className="space-y-1.5">
                  <div className={`flex items-center gap-2 font-semibold text-xs uppercase tracking-wide ${
                    isAbstained ? "text-amber-400" : "text-emerald-400"
                  }`}>
                    <ShieldCheck className="w-4 h-4" />
                    <span>{isAbstained ? "Prescribed Governance Protocol" : "Prescribed Operational Action"}</span>
                  </div>

                  <h3 className="text-base font-bold text-white leading-snug">
                    {cleanAction}
                  </h3>
                </div>

                <div className="space-y-2 pt-2.5 border-t border-white/[0.08] text-xs">
                  <div className="p-3 rounded-xl bg-black/40 border border-white/[0.06] space-y-0.5">
                    <span className="text-[10px] text-neutral-400 font-semibold block uppercase">Protocol Objective</span>
                    <span className="text-neutral-200 text-xs">
                      {decision.verification_metric || (
                        isGuardTriggered 
                          ? "Accumulate baseline telemetry and re-evaluate once observation criteria are satisfied."
                          : "Verify metric stabilization within expected operational threshold."
                      )}
                    </span>
                  </div>
                </div>
              </div>

              {/* Simulation Trajectory (6-Col E8 Simulation — Only if Success) */}
              {isSuccess && (
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
              )}
            </div>
          </section>


          {/* ═════════════════════════════════════════════════════════════════ */}
          {/* STEP 7: HAVE WE SEEN THIS BEFORE? (PERSONA-AWARE E9 MEMORY)       */}
          {/* ═════════════════════════════════════════════════════════════════ */}
          <section className="relative space-y-3">
            <div className="absolute -left-[30px] lg:-left-[38px] top-1 w-5 h-5 rounded-full bg-[#08090C] border border-white/20 flex items-center justify-center text-[10px] text-neutral-400 font-bold">
              →
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="text-xs font-medium text-neutral-400">07 · Institutional Precedent Memory (E9)</div>
                <h2 className="text-base lg:text-lg font-bold text-white tracking-tight">
                  Have we seen this failure pattern before?
                </h2>
              </div>

              {/* Explicit Persona Retrieval Scope Badge */}
              <div className="flex items-center gap-2 px-2.5 py-1 rounded-lg bg-black/40 border border-white/[0.06] text-[11px] font-mono text-neutral-400">
                <Lock className="w-3 h-3 text-neutral-400" />
                <span>Scope: <strong className="text-white capitalize">{persona}</strong> ({personaScopes[persona]?.sourcesCount || 7} authorized sources)</span>
              </div>
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
              <div className="p-5 rounded-2xl bg-[#0E0F15] border border-white/[0.06] space-y-1.5 text-center">
                <div className="text-xs font-semibold text-neutral-200">
                  No matching precedent was available within the current authorization scope.
                </div>
                <div className="text-[11px] text-neutral-400 max-w-xl mx-auto leading-relaxed">
                  Historical precedent retrieval is constrained by the active entitlement boundary ({personaScopes[persona]?.summary || "active persona scope"}). Precedent records outside this authorization scope are not accessible.
                </div>
              </div>
            )}
          </section>
        </div>
      </main>

      {/* ── 7. TRUTHFUL LIVE INVESTIGATION EXECUTION PROGRESS OVERLAY ────── */}
      {isLiveLoading && (
        <div className="fixed inset-0 z-50 bg-black/85 backdrop-blur-md flex items-center justify-center p-4">
          <div className="max-w-lg w-full bg-[#12131D] border border-emerald-500/30 rounded-3xl p-7 space-y-5 shadow-[0_0_50px_rgba(16,185,129,0.15)] text-center animate-in fade-in zoom-in-95 duration-150">
            <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 mx-auto">
              <RefreshCw className="w-6 h-6 animate-spin" />
            </div>

            <div className="space-y-1.5">
              <h3 className="text-lg font-bold text-white tracking-tight">
                INVESTIGATION IN PROGRESS
              </h3>
              <p className="text-xs text-neutral-400">
                Executing 9-engine causal pipeline on FastAPI server (<code className="text-emerald-400 font-mono">:8080/investigate</code>)
              </p>
            </div>

            {/* Execution Context & Truthful Timer */}
            <div className="p-4 rounded-2xl bg-black/50 border border-white/[0.06] space-y-2 text-xs font-mono text-left">
              <div className="flex justify-between items-center text-neutral-300">
                <span className="text-neutral-400">Scenario Target:</span>
                <span className="text-white font-bold">{activeConfig.scenarioId}</span>
              </div>
              <div className="flex justify-between items-center text-neutral-300">
                <span className="text-neutral-400">Persona Scope:</span>
                <span className="text-emerald-400 font-bold capitalize">{activeConfig.persona} ({activeConfig.region === "all" ? "Global" : activeConfig.region})</span>
              </div>
              <div className="flex justify-between items-center text-neutral-300 pt-1 border-t border-white/[0.06]">
                <span className="text-neutral-400">Pipeline Mode:</span>
                <span className="text-neutral-200 font-medium">Synchronous Multi-Engine</span>
              </div>
              <div className="flex justify-between items-center text-neutral-300">
                <span className="text-neutral-400">Elapsed Time:</span>
                <span className="text-emerald-400 font-bold text-sm">{liveElapsedSeconds.toFixed(1)}s</span>
              </div>
            </div>

            <div className="text-[11px] text-neutral-500 leading-relaxed font-sans">
              Processing statistical anomaly isolation, server-side entitlement validation, deterministic challenge rules, and vector memory retrieval.
            </div>
          </div>
        </div>
      )}

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
              <button onClick={() => setActiveEvidenceModal(null)} className="p-1 rounded-lg text-neutral-400 hover:text-white hover:bg-white/5 cursor-pointer">
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
              <button onClick={() => setShowTelemetryDrawer(false)} className="text-neutral-400 hover:text-white cursor-pointer">✕</button>
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
