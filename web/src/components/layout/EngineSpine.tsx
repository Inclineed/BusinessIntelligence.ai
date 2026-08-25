import React from "react"

export interface EngineStageMeta {
  id: string
  num: number
  label: string
  name: string
  method: string
  tabCategory: string
}

export const ENGINE_STAGES: EngineStageMeta[] = [
  { id: "e1", num: 1, label: "E1", name: "KPI Discovery", method: "SQL", tabCategory: "Signal" },
  { id: "e2", num: 2, label: "E2", name: "Anomaly Detection", method: "STATS", tabCategory: "Understand" },
  { id: "e3", num: 3, label: "E3", name: "Diagnostic Attribution", method: "SQL/STATS", tabCategory: "Understand" },
  { id: "e4", num: 4, label: "E4", name: "Grounded Evidence", method: "SQL/RETRIEVAL", tabCategory: "Investigate" },
  { id: "e5", num: 5, label: "E5", name: "Competing Hypotheses", method: "LLM", tabCategory: "Investigate" },
  { id: "e6", num: 6, label: "E6", name: "Rule Challenge", method: "RULES", tabCategory: "Validate" },
  { id: "e7", num: 7, label: "E7", name: "Decision Formulation", method: "LLM", tabCategory: "Validate" },
  { id: "e8", num: 8, label: "E8", name: "Projected Outcome", method: "SIMULATED", tabCategory: "Project" },
  { id: "e9", num: 9, label: "E9", name: "Institutional Memory", method: "RETRIEVAL", tabCategory: "Resolution / Act" },
]

interface EngineSpineProps {
  currentStageNum: number
  onSelectStageNum: (num: number) => void
  isAbstained?: boolean
}

export const EngineSpine: React.FC<EngineSpineProps> = ({
  currentStageNum,
  onSelectStageNum,
  isAbstained = false,
}) => {
  return (
    <div className="w-full max-w-4xl mx-auto mb-8 relative flex items-center justify-between font-mono text-xs px-4 select-none">
      {/* Background connecting track */}
      <div className="absolute left-6 right-6 top-1/2 -translate-y-1/2 h-[1px] bg-gradient-to-r from-[#2B2B2B] via-[#444444] to-[#2B2B2B] -z-10" />

      {ENGINE_STAGES.map((stage) => {
        const isCompleted = stage.num < currentStageNum
        const isActive = stage.num === currentStageNum
        const isFuture = stage.num > currentStageNum

        let nodeClasses = "bg-[#1C1C1C] border transition-all duration-300 rounded-full w-8 h-8 flex items-center justify-center cursor-pointer text-xs font-bold font-mono "

        if (isActive) {
          nodeClasses += isAbstained && stage.num >= 6
            ? "border-[#D8453A] text-[#F4EEE0] bg-[#D8453A]/20 shadow-[0_0_8px_rgba(216,69,58,0.35)] scale-105"
            : "border-[#6B9BB0] text-[#F4EEE0] bg-[#6B9BB0]/25 shadow-[0_0_8px_rgba(107,155,176,0.35)] scale-105"
        } else if (isCompleted) {
          nodeClasses += "border-[#444444] text-[#9E9788] hover:text-[#D1C9B8] hover:border-[#6B9BB0]/40"
        } else {
          nodeClasses += "border-[#2E2E2E] text-[#666666] hover:text-[#9E9788]"
        }

        return (
          <button
            key={stage.id}
            onClick={() => onSelectStageNum(stage.num)}
            className={nodeClasses}
            title={`${stage.label}: ${stage.name} [${stage.method}]`}
            aria-label={`Jump to ${stage.label} ${stage.name}`}
            aria-current={isActive ? "step" : undefined}
          >
            {stage.label}
          </button>
        )
      })}
    </div>
  )
}
