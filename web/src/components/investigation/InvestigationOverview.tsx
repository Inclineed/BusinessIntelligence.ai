import React, { useState } from "react"
import { InvestigationResult, PersonaType } from "../../types/investigation"
import { TopBar } from "../layout/TopBar"
import { EngineSpine } from "../layout/EngineSpine"
import { LeftObservePanel } from "../layout/LeftObservePanel"
import { RightBeliefPanel } from "../layout/RightBeliefPanel"
import { E1SignalWorkspace } from "../engines/E1SignalWorkspace"
import { E2AnomalyWorkspace } from "../engines/E2AnomalyWorkspace"
import { E3DiagnosticWorkspace } from "../engines/E3DiagnosticWorkspace"
import { E4EvidenceWorkspace } from "../engines/E4EvidenceWorkspace"
import { E5HypothesisWorkspace } from "../engines/E5HypothesisWorkspace"
import { E6ChallengeWorkspace } from "../engines/E6ChallengeWorkspace"
import { E7DecisionWorkspace } from "../engines/E7DecisionWorkspace"
import { E8OutcomeWorkspace } from "../engines/E8OutcomeWorkspace"
import { E9MemoryWorkspace } from "../engines/E9MemoryWorkspace"
import { SystemPerformanceDrawer } from "./SystemPerformanceDrawer"
import { SystemHealthModal } from "./SystemHealthModal"
import { AlertTriangle, Lock, RefreshCw, X } from "lucide-react"

export interface AnalysisConfig {
  scenarioId: string
  persona: PersonaType
  region: string
}

export interface ApiErrorState {
  message: string
  statusCode?: number
  details?: string
}

interface InvestigationOverviewProps {
  result: InvestigationResult
  activeConfig: AnalysisConfig
  evaluatedConfig: AnalysisConfig
  isStale: boolean
  isPreviousResultPinned: boolean
  apiError?: ApiErrorState | null
  onConfigChange: (scenarioId: string, persona: PersonaType, region: string) => void
  onRunLive: (scenarioId?: string, persona?: PersonaType, region?: string) => void
  onKeepViewingPrevious: () => void
  onDismissError?: () => void
  isLiveLoading?: boolean
  liveElapsedSeconds?: number
}

export const InvestigationOverview: React.FC<InvestigationOverviewProps> = ({
  result,
  activeConfig,
  evaluatedConfig,
  isStale,
  isPreviousResultPinned,
  apiError = null,
  onConfigChange,
  onRunLive,
  onKeepViewingPrevious,
  onDismissError,
  isLiveLoading = false,
  liveElapsedSeconds = 0,
}) => {
  // Default to E4 (as in the reference) or dynamically navigable from 1 to 9
  const [currentStageNum, setCurrentStageNum] = useState<number>(4)
  const [showPerformanceDrawer, setShowPerformanceDrawer] = useState(false)
  const [showHealthModal, setShowHealthModal] = useState(false)

  const isAccessDenied = result.access_denied || false
  const isAbstained = result.decision?.abstained ?? false

  const renderCurrentWorkspace = () => {
    switch (currentStageNum) {
      case 1:
        return <E1SignalWorkspace result={result} />
      case 2:
        return <E2AnomalyWorkspace result={result} />
      case 3:
        return <E3DiagnosticWorkspace result={result} />
      case 4:
        return <E4EvidenceWorkspace result={result} />
      case 5:
        return <E5HypothesisWorkspace result={result} />
      case 6:
        return <E6ChallengeWorkspace result={result} />
      case 7:
        return <E7DecisionWorkspace result={result} />
      case 8:
        return <E8OutcomeWorkspace result={result} />
      case 9:
        return <E9MemoryWorkspace result={result} persona={activeConfig.persona} />
      default:
        return <E4EvidenceWorkspace result={result} />
    }
  }

  return (
    <div className="h-screen w-screen bg-[#141414] text-[#F8F4E9] flex flex-col overflow-hidden font-sans select-text">
      {/* Top Operations Console Bar */}
      <TopBar
        activeScenarioId={activeConfig.scenarioId}
        activePersona={activeConfig.persona}
        activeRegion={activeConfig.region}
        currentStageNum={currentStageNum}
        isStale={isStale}
        isLiveLoading={isLiveLoading}
        liveElapsedSeconds={liveElapsedSeconds}
        telemetry={result.telemetry}
        onConfigChange={onConfigChange}
        onSelectStageNum={(num) => setCurrentStageNum(num)}
        onRunLive={() => onRunLive()}
        onOpenTelemetry={() => setShowPerformanceDrawer(true)}
        onOpenHealth={() => setShowHealthModal(true)}
      />

      {/* Main 3-Column Command Workspace */}
      <main className="flex-1 flex overflow-hidden relative">
        
        {/* Left Column: Observe & Detect Sidebar */}
        <LeftObservePanel
          result={result}
          activeScenarioId={activeConfig.scenarioId}
          activePersona={activeConfig.persona}
          currentStageNum={currentStageNum}
        />

        {/* Center Column: Engine-Specific Dynamic Workspace */}
        <section className="flex-1 overflow-y-auto bg-[#101010] p-6 lg:p-8 flex flex-col custom-scrollbar">
          
          {/* Persistent E1-E9 Architectural Spine */}
          <EngineSpine
            currentStageNum={currentStageNum}
            onSelectStageNum={(num) => setCurrentStageNum(num)}
            isAbstained={isAbstained}
          />

          {/* Stale or Error Alert Notifications */}
          {apiError && (
            <div className="max-w-4xl mx-auto w-full mb-6 p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-300 text-xs font-mono flex items-start justify-between gap-3 animate-fade-in">
              <div className="flex items-start gap-2.5">
                <AlertTriangle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
                <div>
                  <div className="font-bold text-white">Investigation Request Error ({apiError.statusCode || 500})</div>
                  <div>{apiError.message}</div>
                  {apiError.details && <div className="text-[11px] text-neutral-400 mt-1">{apiError.details}</div>}
                </div>
              </div>
              <button
                onClick={() => onRunLive()}
                className="px-2.5 py-1 rounded bg-red-500/20 hover:bg-red-500/30 text-white font-mono text-[11px] cursor-pointer flex items-center gap-1 shrink-0"
              >
                <RefreshCw className="w-3 h-3" /> Retry
              </button>
            </div>
          )}

          {isStale && !isLiveLoading && (activeConfig.scenarioId !== evaluatedConfig.scenarioId || activeConfig.persona !== evaluatedConfig.persona) && (
            <div className="max-w-4xl mx-auto w-full mb-6 p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs font-mono flex items-center justify-between gap-3 animate-fade-in">
              <span>
                Configuration changed to <strong>{activeConfig.scenarioId}</strong> ({activeConfig.persona}). Currently viewing evaluated result for <strong>{evaluatedConfig.scenarioId}</strong> ({evaluatedConfig.persona}).
              </span>
              <button
                onClick={() => onRunLive()}
                className="px-3 py-1 rounded bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 font-bold text-xs cursor-pointer shrink-0"
              >
                Update Result
              </button>
            </div>
          )}

          {/* Center Workspace Content */}
          <div className="max-w-4xl mx-auto w-full flex-1">
            {isAccessDenied ? (
              <div className="p-8 rounded-2xl bg-[#141622] border border-red-500/30 text-center space-y-4 my-12">
                <div className="w-12 h-12 rounded-2xl bg-red-500/15 border border-red-500/30 flex items-center justify-center mx-auto text-red-400">
                  <Lock className="w-6 h-6" />
                </div>
                <h2 className="text-base font-bold text-white font-mono uppercase">
                  Persona Entitlement Boundary Restricted
                </h2>
                <p className="text-xs text-neutral-300 font-sans leading-relaxed max-w-md mx-auto">
                  {result.reason || "The active persona lacks authorization scope to access the underlying incident data sources."}
                </p>
                <button
                  onClick={() => onConfigChange(activeConfig.scenarioId, "analyst", activeConfig.region)}
                  className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-mono text-xs font-bold cursor-pointer"
                >
                  Switch to Authorized Analyst Persona
                </button>
              </div>
            ) : (
              renderCurrentWorkspace()
            )}
          </div>
        </section>

        {/* Right Column: System Belief & Consequence Panel */}
        <RightBeliefPanel
          result={result}
          currentStageNum={currentStageNum}
          persona={activeConfig.persona}
          onExecuteAction={() => setCurrentStageNum(7)}
        />
      </main>

      {/* Drawers / Modals */}
      <SystemPerformanceDrawer
        telemetry={result.telemetry}
        isOpen={showPerformanceDrawer}
        onClose={() => setShowPerformanceDrawer(false)}
      />

      <SystemHealthModal
        isOpen={showHealthModal}
        onClose={() => setShowHealthModal(false)}
      />
    </div>
  )
}
