import React, { useState, useEffect } from "react"
import { InvestigationOverview } from "./components/investigation/InvestigationOverview"
import { DEFAULT_INC_001 } from "./lib/defaultData"
import { runInvestigation, ApiInvestigationError } from "./lib/api"
import { InvestigationResult, PersonaType } from "./types/investigation"
import { ErrorBoundary } from "./components/common/ErrorBoundary"

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

export const App: React.FC = () => {
  // Active configuration selected in the UI dropdowns
  const [activeConfig, setActiveConfig] = useState<AnalysisConfig>({
    scenarioId: "INC_001",
    persona: "analyst",
    region: "all",
  })

  // The configuration under which the currently displayed result was actually generated
  const [evaluatedConfig, setEvaluatedConfig] = useState<AnalysisConfig>({
    scenarioId: "INC_001",
    persona: "analyst",
    region: "all",
  })

  const [result, setResult] = useState<InvestigationResult>(DEFAULT_INC_001)
  const [isLiveLoading, setIsLiveLoading] = useState(false)
  const [liveElapsedSeconds, setLiveElapsedSeconds] = useState(0)
  const [isPreviousResultPinned, setIsPreviousResultPinned] = useState(false)
  const [apiError, setApiError] = useState<ApiErrorState | null>(null)

  // Stopwatch timer for truthful live progress display
  useEffect(() => {
    let timer: any = null
    if (isLiveLoading) {
      setLiveElapsedSeconds(0)
      const startTime = Date.now()
      timer = setInterval(() => {
        setLiveElapsedSeconds((Date.now() - startTime) / 1000)
      }, 100)
    } else {
      setLiveElapsedSeconds(0)
    }
    return () => {
      if (timer) clearInterval(timer)
    }
  }, [isLiveLoading])

  // Is the current result stale with respect to active dropdown configuration?
  const isStale =
    activeConfig.scenarioId !== evaluatedConfig.scenarioId ||
    activeConfig.persona !== evaluatedConfig.persona ||
    (activeConfig.persona === "manager" &&
      (activeConfig.region || "all") !== (evaluatedConfig.region || "all"))

  const handleConfigChange = (newScenarioId: string, newPersona: PersonaType, newRegion: string) => {
    const resolvedRegion = newPersona !== "manager" ? "all" : (newRegion === "all" ? "us-east" : newRegion)
    setActiveConfig({
      scenarioId: newScenarioId,
      persona: newPersona,
      region: resolvedRegion,
    })
    setIsPreviousResultPinned(false)
    setApiError(null)
  }

  const handleRunInvestigation = async (scenarioId?: string, persona?: PersonaType, region?: string) => {
    const scId = scenarioId || activeConfig.scenarioId
    const pers = persona || activeConfig.persona
    const reg = pers !== "manager" ? "all" : (region || activeConfig.region || "us-east")

    setIsLiveLoading(true)
    setApiError(null)

    try {
      const liveRes = await runInvestigation(scId, pers, reg)
      setResult(liveRes)
      setEvaluatedConfig({ scenarioId: scId, persona: pers, region: reg })
      setActiveConfig({ scenarioId: scId, persona: pers, region: reg })
      setIsPreviousResultPinned(false)
      setApiError(null)
    } catch (err: any) {
      console.error("Investigation run failed:", err)
      const errState: ApiErrorState = {
        message: err.message || "Investigation execution failed",
        statusCode: err.statusCode || 500,
        details: err.details || "The FastAPI backend on http://localhost:8080 encountered an error or timeout while processing this request.",
      }
      setApiError(errState)
    } finally {
      setIsLiveLoading(false)
    }
  }

  const handleKeepViewingPrevious = () => {
    setIsPreviousResultPinned(true)
  }

  const handleDismissError = () => {
    setApiError(null)
  }

  return (
    <ErrorBoundary>
      <InvestigationOverview
        result={result}
        activeConfig={activeConfig}
        evaluatedConfig={evaluatedConfig}
        isStale={isStale}
        isPreviousResultPinned={isPreviousResultPinned}
        apiError={apiError}
        onConfigChange={handleConfigChange}
        onRunLive={handleRunInvestigation}
        onKeepViewingPrevious={handleKeepViewingPrevious}
        onDismissError={handleDismissError}
        isLiveLoading={isLiveLoading}
        liveElapsedSeconds={liveElapsedSeconds}
      />
    </ErrorBoundary>
  )
}

export default App
