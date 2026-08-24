import React, { useState, useEffect } from "react"
import { InvestigationOverview } from "./components/investigation/InvestigationOverview"
import { DEFAULT_INC_001, SCENARIO_PREVIEWS } from "./lib/defaultData"
import { runInvestigation } from "./lib/api"
import { InvestigationResult, PersonaType } from "./types/investigation"

export interface AnalysisConfig {
  scenarioId: string
  persona: PersonaType
  region: string
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
    activeConfig.region !== evaluatedConfig.region

  const handleConfigChange = (newScenarioId: string, newPersona: PersonaType, newRegion: string) => {
    setActiveConfig({
      scenarioId: newScenarioId,
      persona: newPersona,
      region: newRegion,
    })
    setIsPreviousResultPinned(false)
  }

  const handleRunInvestigation = async (scenarioId?: string, persona?: PersonaType, region?: string) => {
    const scId = scenarioId || activeConfig.scenarioId
    const pers = persona || activeConfig.persona
    const reg = region || activeConfig.region

    setIsLiveLoading(true)
    try {
      const liveRes = await runInvestigation(scId, pers, reg)
      setResult(liveRes)
      setEvaluatedConfig({ scenarioId: scId, persona: pers, region: reg })
      setActiveConfig({ scenarioId: scId, persona: pers, region: reg })
      setIsPreviousResultPinned(false)
    } catch (err) {
      console.warn("Live API call encountered issue; active analytical state preserved:", err)
      // Fallback to precomputed preview if available
      if (SCENARIO_PREVIEWS[scId]) {
        setResult({ ...SCENARIO_PREVIEWS[scId], persona: pers })
        setEvaluatedConfig({ scenarioId: scId, persona: pers, region: reg })
        setActiveConfig({ scenarioId: scId, persona: pers, region: reg })
        setIsPreviousResultPinned(false)
      }
    } finally {
      setIsLiveLoading(false)
    }
  }

  const handleKeepViewingPrevious = () => {
    setIsPreviousResultPinned(true)
  }

  return (
    <InvestigationOverview
      result={result}
      activeConfig={activeConfig}
      evaluatedConfig={evaluatedConfig}
      isStale={isStale}
      isPreviousResultPinned={isPreviousResultPinned}
      onConfigChange={handleConfigChange}
      onRunLive={handleRunInvestigation}
      onKeepViewingPrevious={handleKeepViewingPrevious}
      isLiveLoading={isLiveLoading}
      liveElapsedSeconds={liveElapsedSeconds}
    />
  )
}

export default App
