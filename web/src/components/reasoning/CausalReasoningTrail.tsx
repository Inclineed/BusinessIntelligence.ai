import React, { useState } from "react"
import { InvestigationResult, HypothesisItem } from "../../types/investigation"
import {
  ArrowRight,
  GitCommit,
  Server,
  Zap,
  TrendingDown,
  ShieldAlert,
  Layers,
  Award,
  Activity,
  Cpu,
  Globe,
  Database,
  Smartphone,
  Flame,
  AlertTriangle,
} from "lucide-react"

interface CausalReasoningTrailProps {
  result: InvestigationResult
  selectedHypothesisId?: string
  onSelectHypothesis?: (id: string) => void
}

export const CausalReasoningTrail: React.FC<CausalReasoningTrailProps> = ({
  result,
  selectedHypothesisId,
  onSelectHypothesis,
}) => {
  const hypotheses = result.hypotheses || []
  const scored = result.scored || []
  const winningId = result.decision?.winning_hypothesis_id || hypotheses[0]?.hypothesis_id || "H1"

  const [activeId, setActiveId] = useState<string>(
    selectedHypothesisId || winningId
  )

  // Keep internal state in sync if parent passes selectedHypothesisId
  const currentId = selectedHypothesisId || activeId
  const currentHyp =
    hypotheses.find((h) => h.hypothesis_id === currentId) || hypotheses[0]
  const currentScored = scored.find((s) => s.hypothesis_id === currentId)

  if (!currentHyp && hypotheses.length === 0) {
    return null
  }

  const handleSelect = (id: string) => {
    setActiveId(id)
    if (onSelectHypothesis) {
      onSelectHypothesis(id)
    }
  }

  const rootCause = currentHyp?.root_cause_type || "UNKNOWN"
  const subsystem = currentHyp?.affected_subsystem || "UNKNOWN"
  const mechanism =
    currentHyp?.proximal_mechanism || currentHyp?.mechanism_tag || "UNKNOWN"
  const symptomKpis = currentHyp?.symptom_kpis || []

  // Helper icons and styles
  const getRootCauseBadgeStyle = (rc: string) => {
    switch (rc.toUpperCase()) {
      case "INTERNAL_RELEASE":
        return {
          bg: "bg-[#D8453A]/20 border-[#D8453A]/40 text-[#E56B62]",
          icon: <GitCommit className="w-4 h-4 text-[#E56B62]" />,
          label: "INTERNAL RELEASE",
        }
      case "EXTERNAL_PROVIDER":
        return {
          bg: "bg-[#6B9BB0]/20 border-[#6B9BB0]/40 text-[#6B9BB0]",
          icon: <Globe className="w-4 h-4 text-[#6B9BB0]" />,
          label: "EXTERNAL PROVIDER",
        }
      case "RESOURCE_EXHAUSTION":
        return {
          bg: "bg-[#D19B5E]/20 border-[#D19B5E]/40 text-[#E0B070]",
          icon: <Cpu className="w-4 h-4 text-[#E0B070]" />,
          label: "RESOURCE EXHAUSTION",
        }
      case "INVENTORY_SHORTAGE":
        return {
          bg: "bg-[#A88232]/20 border-[#A88232]/40 text-[#DEC06A]",
          icon: <Database className="w-4 h-4 text-[#DEC06A]" />,
          label: "INVENTORY SHORTAGE",
        }
      case "MACRO_EXTERNAL":
        return {
          bg: "bg-[#735A88]/20 border-[#735A88]/40 text-[#A287B8]",
          icon: <Flame className="w-4 h-4 text-[#A287B8]" />,
          label: "MACRO EXTERNAL",
        }
      default:
        return {
          bg: "bg-[#222222] border-[#333333] text-[#9E9788]",
          icon: <AlertTriangle className="w-4 h-4 text-[#9E9788]" />,
          label: rc.replace(/_/g, " "),
        }
    }
  }

  const getSubsystemIcon = (sub: string) => {
    switch (sub.toLowerCase()) {
      case "payment_gateway":
        return <Server className="w-4 h-4 text-[#6B9BB0]" />
      case "device_client":
        return <Smartphone className="w-4 h-4 text-[#6B9BB0]" />
      case "inventory_system":
      case "compute_backend":
        return <Database className="w-4 h-4 text-[#6B9BB0]" />
      case "marketing_channel":
        return <Globe className="w-4 h-4 text-[#6B9BB0]" />
      default:
        return <Cpu className="w-4 h-4 text-[#6B9BB0]" />
    }
  }

  const rootBadge = getRootCauseBadgeStyle(rootCause)
  const isWinning = currentHyp?.hypothesis_id === winningId
  const auditScorePct = currentScored
    ? Math.round(currentScored.final_audit_score * 100)
    : null

  return (
    <div className="p-5 rounded-2xl bg-[#1C1C1C] border border-[#2E2E2E] space-y-4 font-mono select-text shadow-sm">
      {/* Header & Hypothesis Selector */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#2E2E2E] pb-3">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-[#6B9BB0]" />
          <div>
            <h3 className="text-xs font-bold text-[#F4EEE0] uppercase tracking-wider">
              4-Layer Causal Ontology Trail
            </h3>
            <span className="text-[10px] text-[#9E9788] block">
              Directed causal propagation: Root Cause → Subsystem → Mechanism → Symptoms
            </span>
          </div>
        </div>

        {/* Candidate Switcher Tabs */}
        {hypotheses.length > 1 && (
          <div className="flex items-center gap-1.5 self-start sm:self-auto">
            {hypotheses.map((h) => {
              const isHWinning = h.hypothesis_id === winningId
              const isSelected = h.hypothesis_id === currentId
              return (
                <button
                  key={h.hypothesis_id}
                  onClick={() => handleSelect(h.hypothesis_id)}
                  className={`px-2.5 py-1 rounded-lg text-xs transition-all cursor-pointer flex items-center gap-1.5 ${
                    isSelected
                      ? "bg-[#6B9BB0]/25 text-[#F4EEE0] border border-[#6B9BB0]/50 font-bold shadow-sm"
                      : "bg-[#181818] text-[#9E9788] border border-[#2E2E2E] hover:border-[#444444]"
                  }`}
                >
                  {isHWinning && <Award className="w-3 h-3 text-[#4E8569]" />}
                  <span>{h.hypothesis_id}</span>
                </button>
              )
            })}
          </div>
        )}
      </div>

      {/* 4-Stage Horizontal DAG Chain */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-stretch">
        {/* Layer 1: ROOT CAUSE */}
        <div className="p-3.5 rounded-xl bg-[#171717] border border-[#2E2E2E] flex flex-col justify-between space-y-2 relative group hover:border-[#6B9BB0]/40 transition-colors">
          <div>
            <div className="flex items-center justify-between text-[10px] text-[#9E9788] uppercase tracking-wider mb-1.5">
              <span>01 · Root Cause</span>
              <span className="text-[9px] px-1 py-0.2 rounded bg-black/40 text-[#78716C]">
                INITIATOR
              </span>
            </div>
            <div className={`p-2 rounded-lg border flex items-center gap-2 text-xs font-bold ${rootBadge.bg}`}>
              {rootBadge.icon}
              <span className="truncate">{rootBadge.label}</span>
            </div>
          </div>
          <div className="text-[10px] text-[#78716C] leading-snug">
            Primary causal trigger initiating system-level state change.
          </div>
          {/* Connector Arrow for Desktop */}
          <div className="hidden md:flex absolute -right-3.5 top-1/2 -translate-y-1/2 z-10 w-5 h-5 rounded-full bg-[#222222] border border-[#333333] items-center justify-center text-[#9E9788]">
            <ArrowRight className="w-3 h-3" />
          </div>
        </div>

        {/* Layer 2: AFFECTED SUBSYSTEM */}
        <div className="p-3.5 rounded-xl bg-[#171717] border border-[#2E2E2E] flex flex-col justify-between space-y-2 relative group hover:border-[#6B9BB0]/40 transition-colors">
          <div>
            <div className="flex items-center justify-between text-[10px] text-[#9E9788] uppercase tracking-wider mb-1.5">
              <span>02 · Affected Subsystem</span>
              <span className="text-[9px] px-1 py-0.2 rounded bg-black/40 text-[#78716C]">
                TARGET
              </span>
            </div>
            <div className="p-2 rounded-lg bg-[#222222] border border-[#333333] flex items-center gap-2 text-xs font-bold text-[#F4EEE0]">
              {getSubsystemIcon(subsystem)}
              <span className="truncate">{subsystem.replace(/_/g, " ").toUpperCase()}</span>
            </div>
          </div>
          <div className="text-[10px] text-[#78716C] leading-snug">
            Specific infrastructure or service component experiencing fault.
          </div>
          {/* Connector Arrow for Desktop */}
          <div className="hidden md:flex absolute -right-3.5 top-1/2 -translate-y-1/2 z-10 w-5 h-5 rounded-full bg-[#222222] border border-[#333333] items-center justify-center text-[#9E9788]">
            <ArrowRight className="w-3 h-3" />
          </div>
        </div>

        {/* Layer 3: PROXIMAL MECHANISM */}
        <div className="p-3.5 rounded-xl bg-[#171717] border border-[#2E2E2E] flex flex-col justify-between space-y-2 relative group hover:border-[#6B9BB0]/40 transition-colors">
          <div>
            <div className="flex items-center justify-between text-[10px] text-[#9E9788] uppercase tracking-wider mb-1.5">
              <span>03 · Proximal Mechanism</span>
              <span className="text-[9px] px-1 py-0.2 rounded bg-black/40 text-[#78716C]">
                FAILURE MODE
              </span>
            </div>
            <div className="p-2 rounded-lg bg-[#222222] border border-[#D19B5E]/30 flex items-center gap-2 text-xs font-bold text-[#D19B5E]">
              <Zap className="w-4 h-4 text-[#D19B5E]" />
              <span className="truncate">{mechanism.replace(/_/g, " ").toUpperCase()}</span>
            </div>
          </div>
          <div className="text-[10px] text-[#78716C] leading-snug">
            Direct operational physics (e.g. pool exhaustion, timeout surge).
          </div>
          {/* Connector Arrow for Desktop */}
          <div className="hidden md:flex absolute -right-3.5 top-1/2 -translate-y-1/2 z-10 w-5 h-5 rounded-full bg-[#222222] border border-[#333333] items-center justify-center text-[#9E9788]">
            <ArrowRight className="w-3 h-3" />
          </div>
        </div>

        {/* Layer 4: SYMPTOM KPIS */}
        <div className="p-3.5 rounded-xl bg-[#171717] border border-[#2E2E2E] flex flex-col justify-between space-y-2 group hover:border-[#6B9BB0]/40 transition-colors">
          <div>
            <div className="flex items-center justify-between text-[10px] text-[#9E9788] uppercase tracking-wider mb-1.5">
              <span>04 · Symptom KPIs</span>
              <span className="text-[9px] px-1 py-0.2 rounded bg-black/40 text-[#78716C]">
                OBSERVED
              </span>
            </div>
            <div className="flex flex-col gap-1.5">
              {symptomKpis.length > 0 ? (
                symptomKpis.map((kpi) => (
                  <div
                    key={kpi}
                    className="p-1.5 rounded-lg bg-[#1F1818] border border-[#D8453A]/30 text-[11px] font-bold text-[#E56B62] flex items-center gap-1.5 truncate"
                  >
                    <TrendingDown className="w-3.5 h-3.5 text-[#D8453A] shrink-0" />
                    <span className="truncate">{kpi.replace(/_/g, " ")}</span>
                  </div>
                ))
              ) : (
                <div className="p-1.5 rounded-lg bg-[#222222] border border-[#333333] text-[11px] text-[#9E9788]">
                  {result.signals?.[0]?.kpi_id.replace(/_/g, " ") || "Observed KPI shock"}
                </div>
              )}
            </div>
          </div>
          <div className="text-[10px] text-[#78716C] leading-snug">
            Measurable business and telemetry impact produced by mechanism.
          </div>
        </div>
      </div>
    </div>
  )
}
