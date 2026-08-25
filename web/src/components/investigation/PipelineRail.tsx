import React from "react"
import { InvestigationResult, TelemetryData } from "../../types/investigation"
import { 
  Database, 
  Activity, 
  Layers, 
  FileText, 
  Sparkles, 
  Scale, 
  Zap, 
  TrendingUp, 
  History,
  CheckCircle2,
  AlertTriangle
} from "lucide-react"

interface PipelineRailProps {
  result: InvestigationResult
  telemetry?: TelemetryData
  activeStage?: string
  onSelectStage?: (stageId: string) => void
}

interface StageDefinition {
  id: string
  label: string
  name: string
  method: string
  engineKey: string
  icon: React.ComponentType<{ className?: string }>
}

const STAGES: StageDefinition[] = [
  { id: "e1", label: "E1", name: "KPI Store", method: "SQL", engineKey: "kpi_store", icon: Database },
  { id: "e2", label: "E2", name: "Signal", method: "STATS", engineKey: "signal", icon: Activity },
  { id: "e3", label: "E3", name: "Diagnostic", method: "SQL/STATS", engineKey: "diagnostic", icon: Layers },
  { id: "e4", label: "E4", name: "Evidence", method: "SQL/RETRIEVAL", engineKey: "evidence", icon: FileText },
  { id: "e5", label: "E5", name: "Hypothesis", method: "LLM", engineKey: "hypothesis", icon: Sparkles },
  { id: "e6", label: "E6", name: "Challenge", method: "RULES", engineKey: "challenge", icon: Scale },
  { id: "e7", label: "E7", name: "Decision", method: "LLM", engineKey: "decision", icon: Zap },
  { id: "e8", label: "E8", name: "Outcome", method: "SIMULATED", engineKey: "outcome", icon: TrendingUp },
  { id: "e9", label: "E9", name: "Memory", method: "RETRIEVAL", engineKey: "memory", icon: History },
]

export const PipelineRail: React.FC<PipelineRailProps> = ({
  result,
  telemetry,
  activeStage,
  onSelectStage,
}) => {
  const isAbstained = result.decision?.abstained ?? false

  const getStageStatus = (stage: StageDefinition) => {
    if (stage.id === "e7" && isAbstained) return "ABSTAINED"
    if (stage.id === "e6" && isAbstained) return "CHALLENGED"
    return "COMPLETED"
  }

  return (
    <div className="w-full rounded-xl p-2.5 bg-[#1C1C1C] border border-[#2E2E2E] mb-4">
      <div className="flex items-center justify-between gap-2 overflow-x-auto pb-1 scrollbar-none">
        {STAGES.map((stage, idx) => {
          const Icon = stage.icon
          const status = getStageStatus(stage)
          const latency = telemetry?.latency_ms_by_engine?.[stage.engineKey]
          const isSelected = activeStage === stage.id

          return (
            <button
              key={stage.id}
              onClick={() => onSelectStage?.(stage.id)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-mono transition-all cursor-pointer whitespace-nowrap ${
                isSelected
                  ? "bg-[#6B9BB0]/25 border border-[#6B9BB0]/50 text-[#F4EEE0] shadow-sm"
                  : "bg-[#222222] hover:bg-[#2A2A2A] border border-[#333333] text-[#D1C9B8]"
              }`}
            >
              <div className="flex items-center gap-1.5">
                <Icon className={`w-3.5 h-3.5 ${
                  status === "ABSTAINED" ? "text-[#D8453A]" : "text-[#4E8569]"
                }`} />
                <span className="font-bold text-[#F4EEE0]">{stage.label}</span>
                <span className="text-[#9E9788] hidden sm:inline">{stage.name}</span>
              </div>

              <span className="text-[10px] px-1 py-0.2 rounded bg-[#181818] text-[#9E9788] font-mono border border-[#2E2E2E]">
                [{stage.method}]
              </span>

              {latency !== undefined && (
                <span className="text-[10px] text-[#9E9788] font-mono">
                  {Math.round(latency)}ms
                </span>
              )}

              {idx < STAGES.length - 1 && (
                <span className="text-[#555555] ml-1 select-none">→</span>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}
