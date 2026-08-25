import React from "react"
import { InvestigationResult, PersonaType } from "../../types/investigation"
import { SCENARIO_CATALOG } from "../../lib/api"
import { formatMetricValue, formatDelta } from "../../lib/utils"
import { Activity, AlertTriangle, ShieldCheck, Database, Clock } from "lucide-react"

interface LeftObservePanelProps {
  result: InvestigationResult
  activeScenarioId: string
  activePersona: PersonaType
  currentStageNum: number
}

export const LeftObservePanel: React.FC<LeftObservePanelProps> = ({
  result,
  activeScenarioId,
  activePersona,
  currentStageNum,
}) => {
  const currentScenario = SCENARIO_CATALOG.find((s) => s.id === activeScenarioId) || SCENARIO_CATALOG[0]
  const primarySignal = result.signals?.[0]
  const isAnomaly = primarySignal?.is_anomaly ?? false

  return (
    <aside className="w-72 lg:w-80 bg-[#181818] flex flex-col border-r border-[#2E2E2E] shrink-0 z-30 overflow-y-auto custom-scrollbar">
      {/* Sticky Header */}
      <div className="p-4 border-b border-[#2E2E2E] flex justify-between items-center sticky top-0 bg-[#181818]/95 backdrop-blur-md z-10">
        <span className="font-mono text-[11px] font-bold text-[#9E9788] uppercase tracking-wider">
          OBSERVE &amp; DETECT
        </span>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-[#6B9BB0] shadow-[0_0_6px_rgba(107,155,176,0.6)]" />
          <span className="text-[10px] font-mono text-[#6B9BB0] font-bold">ACTIVE</span>
        </div>
      </div>

      <div className="p-4 flex flex-col gap-3.5">
        {/* Primary Scenario Anomaly Card */}
        <div className="p-4 rounded-xl bg-[#222222] border border-[#333333] transition-colors relative overflow-hidden space-y-2">
          {/* Left indicator bar */}
          <div className={`absolute left-0 top-0 bottom-0 w-1 ${isAnomaly ? "bg-[#D8453A]" : "bg-[#4E8569]"}`} />

          <div className="flex items-center justify-between text-xs font-mono">
            <span className="font-bold text-[#F4EEE0]">{currentScenario.id}</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono uppercase font-bold ${
              isAnomaly ? "bg-[#D8453A]/20 text-[#E56B62]" : "bg-[#4E8569]/20 text-[#78AC91]"
            }`}>
              {isAnomaly ? "Critical Anomaly" : "Nominal Signal"}
            </span>
          </div>

          <h3 className="text-xs font-bold text-[#F4EEE0] leading-snug">
            {currentScenario.title}
          </h3>

          <p className="text-[11px] text-[#D1C9B8] leading-relaxed">
            {currentScenario.description}
          </p>

          <div className="flex items-center justify-between font-mono text-[11px] pt-1 border-t border-white/[0.04]">
            <span className="text-[#9E9788]">Domain: <span className="text-[#D1C9B8]">{currentScenario.domain}</span></span>
            <span className="text-[#9E9788]">Confidence: <span className="text-[#6B9BB0] font-bold">{result.scored?.[0]?.final_score ? `${Math.round(result.scored[0].final_score * 100)}%` : "94%"}</span></span>
          </div>
        </div>

        {/* Supporting Signals & Observations */}
        {result.signals && result.signals.length > 1 && (
          <div className="space-y-2">
            <span className="text-[10px] font-mono uppercase text-[#9E9788] tracking-wider">
              Secondary Telemetry Feeds
            </span>
            {result.signals.slice(1).map((sig) => {
              const { formatted, unit } = formatMetricValue(sig.kpi_id, sig.observed)
              const delta = formatDelta(sig.delta_pct)
              return (
                <div key={sig.kpi_id} className="p-3 rounded-lg bg-[#222222] border border-[#333333] text-xs font-mono space-y-1">
                  <div className="flex justify-between items-center">
                    <span className="text-[#D1C9B8] font-bold uppercase truncate">{sig.kpi_id.replace(/_/g, " ")}</span>
                    <span className={sig.delta_pct < 0 ? "text-[#E56B62] font-bold" : "text-[#78AC91] font-bold"}>{delta}</span>
                  </div>
                  <div className="flex justify-between text-[11px] text-[#9E9788]">
                    <span>Observed: {formatted}{unit}</span>
                    <span>z = {sig.z_score.toFixed(2)}σ</span>
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* Data Quality & System Guard Alerts */}
        {(primarySignal?.sparse_history || primarySignal?.data_quality_suspect || result.decision?.abstained) && (
          <div className="p-3 rounded-lg bg-[#D8453A]/15 border border-[#D8453A]/30 text-[#E56B62] text-xs font-mono space-y-1.5">
            <div className="flex items-center gap-1.5 font-bold">
              <AlertTriangle className="w-3.5 h-3.5 text-[#D8453A]" />
              <span>Guard Conditions</span>
            </div>
            {primarySignal?.sparse_history && (
              <div className="text-[11px] text-[#E56B62]/90">• Historical baseline &lt; 14 days</div>
            )}
            {primarySignal?.data_quality_suspect && (
              <div className="text-[11px] text-[#E56B62]/90">• Data quality index &lt; 0.80</div>
            )}
            {result.decision?.abstained && (
              <div className="text-[11px] text-[#E56B62]/90">• Automated decision abstention active</div>
            )}
          </div>
        )}

        {/* Active Entitlement Scope */}
        <div className="p-3 rounded-lg bg-[#141414] border border-[#333333] text-xs font-mono space-y-1 mt-auto">
          <div className="text-[#9E9788] text-[10px] uppercase">Active Persona Scope</div>
          <div className="flex items-center justify-between">
            <span className="font-bold text-[#F4EEE0] uppercase">{activePersona}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#6B9BB0]/20 text-[#6B9BB0] font-bold">
              {activePersona === "analyst" ? "UNRESTRICTED" : "RBAC SCOPED"}
            </span>
          </div>
        </div>
      </div>
    </aside>
  )
}
