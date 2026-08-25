import React, { useState } from "react"
import { PersonaType, TelemetryData } from "../../types/investigation"
import { SCENARIO_CATALOG } from "../../lib/api"
import { 
  Play, 
  Activity, 
  User, 
  ChevronDown, 
  Cpu, 
  Zap, 
  Lock,
  Globe,
  Sliders
} from "lucide-react"

interface TopBarProps {
  activeScenarioId: string
  activePersona: PersonaType
  activeRegion: string
  currentStageNum: number
  isStale: boolean
  isLiveLoading: boolean
  liveElapsedSeconds: number
  telemetry?: TelemetryData
  confidenceScore?: number
  isAbstained?: boolean
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
  isAbstained,
  onConfigChange,
  onSelectStageNum,
  onRunLive,
  onOpenTelemetry,
  onOpenHealth,
  onOpenActionDrawer,
}) => {
  const [scenarioDropdownOpen, setScenarioDropdownOpen] = useState(false)
  const currentScenario = SCENARIO_CATALOG.find((s) => s.id === activeScenarioId) || SCENARIO_CATALOG[0]

  const formatLatency = (ms?: number) => {
    if (!ms || isNaN(ms)) return "—"
    return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`
  }

  const totalEngineLatency = telemetry?.latency_ms_by_engine
    ? Object.values(telemetry.latency_ms_by_engine).reduce((a, b) => a + b, 0)
    : undefined

  // Top Nav Category Tabs
  const NAV_TABS = [
    { label: "Signal", targetStage: 1, activeIf: currentStageNum === 1 },
    { label: "Understand", targetStage: 2, activeIf: currentStageNum === 2 || currentStageNum === 3 },
    { label: "Investigate", targetStage: 4, activeIf: currentStageNum === 4 || currentStageNum === 5 },
    { label: "Validate", targetStage: 6, activeIf: currentStageNum === 6 || currentStageNum === 7 },
    { label: "Project", targetStage: 8, activeIf: currentStageNum === 8 },
    { label: "Resolution / Act", targetStage: 9, activeIf: currentStageNum === 9 },
  ]

  return (
    <header className="sticky top-0 z-40 w-full bg-[#181818] border-b border-[#2E2E2E] px-4 py-2.5 shrink-0">
      <div className="max-w-[1700px] mx-auto flex items-center justify-between gap-4">
        
        {/* Brand & Incident Selector */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full bg-[#6B9BB0] shadow-[0_0_8px_rgba(107,155,176,0.5)]" />
            <span className="font-bold text-sm tracking-tight text-[#F4EEE0] font-sans">
              BusinessIntelligence<span className="text-[#6B9BB0]">.ai</span>
            </span>
          </div>

          {/* Scenario Selector Dropdown */}
          <div className="relative">
            <button
              onClick={() => setScenarioDropdownOpen(!scenarioDropdownOpen)}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#222222] hover:bg-[#2A2A2A] border border-[#333333] text-xs font-mono text-[#D1C9B8] transition-all cursor-pointer"
              aria-expanded={scenarioDropdownOpen}
              aria-label="Select incident scenario"
            >
              <span className="text-[#6B9BB0] font-bold">{currentScenario.id}</span>
              <span className="text-[#9E9788] max-w-[120px] lg:max-w-[160px] truncate">{currentScenario.title}</span>
              <ChevronDown className="w-3 h-3 text-[#9E9788]" />
            </button>

            {scenarioDropdownOpen && (
              <div className="absolute left-0 mt-1.5 w-80 max-h-96 overflow-y-auto bg-[#1C1C1C] rounded-xl border border-[#333333] p-1.5 shadow-2xl z-50">
                <div className="px-2 py-1 text-[10px] font-mono text-[#9E9788] uppercase tracking-wider border-b border-[#2E2E2E] mb-1">
                  Incident Catalog
                </div>
                {SCENARIO_CATALOG.map((sc) => (
                  <button
                    key={sc.id}
                    onClick={() => {
                      onConfigChange(sc.id, activePersona, activeRegion)
                      setScenarioDropdownOpen(false)
                    }}
                    className={`w-full text-left p-2 rounded-lg text-xs transition-colors flex flex-col gap-0.5 cursor-pointer ${
                      sc.id === activeScenarioId ? "bg-[#6B9BB0]/20 text-[#F4EEE0] border border-[#6B9BB0]/40" : "hover:bg-white/[0.04] text-[#D1C9B8]"
                    }`}
                  >
                    <div className="flex items-center justify-between font-mono">
                      <span className="font-bold text-[#6B9BB0]">{sc.id}</span>
                      <span className="text-[10px] text-[#9E9788] px-1 rounded bg-black/40">{sc.domain}</span>
                    </div>
                    <div className="font-medium text-[#F4EEE0] truncate">{sc.title}</div>
                    <div className="text-[11px] text-[#9E9788] truncate">{sc.description}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
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
                isAbstained
                  ? "bg-[#D8453A]/20 hover:bg-[#D8453A]/30 text-[#E56B62] border-[#D8453A]/40"
                  : "bg-[#6B9BB0]/20 hover:bg-[#6B9BB0]/30 text-[#F4EEE0] border-[#6B9BB0]/40"
              }`}
              title="Open System Assessment & Action Directive Drawer"
            >
              <Zap className="w-3.5 h-3.5 text-[#6B9BB0]" />
              <span>
                {isAbstained ? "ABSTAIN" : `${confidenceScore ?? 85}% ACTION`}
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
            <Play className={`w-3.5 h-3.5 ${isLiveLoading ? 'animate-spin' : ''}`} />
            <span>{isLiveLoading ? `${liveElapsedSeconds.toFixed(1)}s` : isStale ? "UPDATE" : "RUN"}</span>
          </button>
        </div>
      </div>
    </header>
  )
}
