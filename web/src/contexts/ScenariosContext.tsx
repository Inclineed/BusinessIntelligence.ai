import React, { createContext, useContext, useState, useEffect } from "react"
import { ScenarioMeta } from "../types/investigation"
import { fetchScenarios } from "../lib/api"

interface ScenariosContextValue {
  scenarios: ScenarioMeta[]
  loading: boolean
}

const ScenariosContext = createContext<ScenariosContextValue>({
  scenarios: [],
  loading: true,
})

export const useScenarios = () => useContext(ScenariosContext)

export const ScenariosProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [scenarios, setScenarios] = useState<ScenarioMeta[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let mounted = true
    fetchScenarios().then((data) => {
      if (mounted) {
        setScenarios(data)
        setLoading(false)
      }
    })
    return () => {
      mounted = false
    }
  }, [])

  return (
    <ScenariosContext.Provider value={{ scenarios, loading }}>
      {children}
    </ScenariosContext.Provider>
  )
}
