import React, { useState } from "react"
import { InvestigationOverview } from "./components/investigation/InvestigationOverview"
import { DEFAULT_INC_001 } from "./lib/defaultData"
import { runInvestigation } from "./lib/api"
import { InvestigationResult, PersonaType } from "./types/investigation"

export const App: React.FC = () => {
  const [result, setResult] = useState<InvestigationResult>(DEFAULT_INC_001)
  const [isLiveLoading, setIsLiveLoading] = useState(false)

  const handleRunLive = async (scenarioId: string, persona: PersonaType) => {
    setIsLiveLoading(true)
    try {
      const liveRes = await runInvestigation(scenarioId, persona, "all")
      setResult(liveRes)
    } catch (err) {
      console.warn("Live query encountered error, keeping active view:", err)
    } finally {
      setIsLiveLoading(false)
    }
  }

  return (
    <InvestigationOverview 
      result={result} 
      onRunLive={handleRunLive}
      isLiveLoading={isLiveLoading}
    />
  )
}

export default App
