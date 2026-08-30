import React from "react"
import { PersonaType, TelemetryData } from "../../types/investigation"
import { Play, Zap } from "lucide-react"

interface TopBarProps {
  activeScenarioId: string
  activePersona: PersonaType
  activeRegion: string
  currentStageNum: number
  isStale: boolean
  isLiveLoading: boolean
  liveElapsedSeconds: number
  telemetry?: TelemetryData
  confidenceScore?: number // backwards compatible alias for auditScore
  auditScore?: number
  auditVerdict?: string
  isAbstained?: boolean
  isNominal?: boolean
  onConfigChange: (scenarioId: string, persona: PersonaType, region: string) => void
  onSelectStageNum: (stageNum: number) => void
  onRunLive: () => void
  onOpenTelemetry: () => void
  onOpenHealth: () => void
  onOpenActionDrawer?: () => void
}

export const TopBar: React.FC<TopBarProps> = ({
  activeScenarioId,
  activePersona,
  activeRegion,
  currentStageNum,
  isStale,
  isLiveLoading,
  liveElapsedSeconds,
  telemetry,
  confidenceScore,
  auditScore,
  auditVerdict,
  isAbstained,
  isNominal = false,
  onConfigChange,
  onSelectStageNum,
  onRunLive,
  onOpenTelemetry,
  onOpenHealth,
  onOpenActionDrawer,
}) => {
  // Compute calibrated audit score and verdict label
  const score = auditScore ?? confidenceScore ?? 71
  const isVerified = auditVerdict
    ? auditVerdict.toUpperCase() === "VERIFIED"
    : score >= 70 && !isAbstained

  // Top Nav Category Tabs
  const NAV_TABS = [
    { label: "Signal", targetStage: 1, activeIf: currentStageNum === 1 },
    {
      label: "Understand",
      targetStage: 2,
      activeIf: currentStageNum === 2 || currentStageNum === 3,
    },
    {
      label: "Investigate",
      targetStage: 4,
      activeIf: currentStageNum === 4 || currentStageNum === 5,
    },
    {
      label: "Validate",
      targetStage: 6,
      activeIf: currentStageNum === 6 || currentStageNum === 7,
    },
    { label: "Project", targetStage: 8, activeIf: currentStageNum === 8 },
    { label: "Resolve", targetStage: 9, activeIf: currentStageNum === 9 },
  ]

  return (
    <header className="sticky top-0 z-40 w-full bg-[#181818] border-b border-[#2E2E2E] px-4 py-2.5 shrink-0 select-none">
      <div className="max-w-[1700px] mx-auto flex items-center justify-between gap-4">
        {/* Brand */}
        <div className="flex items-center gap-2.5">
          <div className="w-2.5 h-2.5 rounded-full bg-[#6B9BB0] shadow-[0_0_8px_rgba(107,155,176,0.5)]" />
          <span className="font-bold text-sm tracking-tight text-[#F4EEE0] font-sans">
            BusinessIntelligence<span className="text-[#6B9BB0]">.ai</span>
          </span>
        </div>

        {/* Center Navigation Category Tabs */}
        <nav className="hidden md:flex items-center space-x-6">
          {NAV_TABS.map((tab) => (
            <button
              key={tab.label}
              onClick={() => onSelectStageNum(tab.targetStage)}
              className={`text-xs font-sans font-medium transition-colors cursor-pointer py-1 relative ${
                tab.activeIf
                  ? "text-[#F4EEE0] font-bold border-b-2 border-[#6B9BB0]"
                  : "text-[#9E9788] hover:text-[#D1C9B8]"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>

        {/* Right Controls: Action Directive & Run Investigation */}
        <div className="flex items-center gap-2.5">
          {/* Action Directive & Assessment Drawer Trigger */}
          {onOpenActionDrawer && (
            <button
              onClick={onOpenActionDrawer}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-bold transition-all border cursor-pointer ${
                isNominal
                  ? "bg-[#4E8569]/20 hover:bg-[#4E8569]/30 text-[#78AC91] border-[#4E8569]/40"
                  : isAbstained
                  ? "bg-[#D8453A]/20 hover:bg-[#D8453A]/30 text-[#E56B62] border-[#D8453A]/40"
                  : isVerified
                  ? "bg-[#4E8569]/20 hover:bg-[#4E8569]/30 text-[#78AC91] border-[#4E8569]/40"
                  : "bg-[#A88232]/20 hover:bg-[#A88232]/30 text-[#DEC06A] border-[#A88232]/40"
              }`}
              title="Open System Assessment & Governed Action Drawer"
            >
              <Zap className="w-3.5 h-3.5" />
              <span>
                {isNominal
                  ? "SYSTEM NOMINAL"
                  : isAbstained
                  ? "AUDIT ABSTAIN"
                  : isVerified
                  ? `${score}% AUDIT VERIFIED`
                  : `${score}% AUDIT MARGINAL`}
              </span>
            </button>
          )}

          {/* Primary Action Button */}
          <button
            onClick={onRunLive}
            disabled={isLiveLoading}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-bold font-mono transition-all cursor-pointer ${
              isLiveLoading
                ? "bg-[#252525] border border-[#444444] text-[#D1C9B8] cursor-wait"
                : isStale
                ? "bg-[#6B9BB0]/25 hover:bg-[#6B9BB0]/40 text-[#F4EEE0] border border-[#6B9BB0]/50"
                : "bg-[#6B9BB0]/20 hover:bg-[#6B9BB0]/35 text-[#F4EEE0] border border-[#6B9BB0]/40"
            }`}
          >
            <Play className={`w-3.5 h-3.5 ${isLiveLoading ? "animate-spin" : ""}`} />
            <span>
              {isLiveLoading
                ? `${liveElapsedSeconds.toFixed(1)}s`
                : isStale
                ? "UPDATE"
                : "RUN"}
            </span>
          </button>
        </div>
      </div>
    </header>
  )
}
