import React, { useState, useEffect } from "react"
import { Shell } from "./components/layout/Shell"
import { InvestigationHero } from "./components/investigation/InvestigationHero"
import { SignalCards } from "./components/kpi/SignalCards"
import { DeviationSpectrumChart } from "./components/kpi/DeviationSpectrumChart"
import { CausalReasoningTrail } from "./components/reasoning/CausalReasoningTrail"
import { HypothesisStudio } from "./components/hypothesis/HypothesisStudio"
import { EvidenceExplorer } from "./components/evidence/EvidenceExplorer"
import { EvidenceDrawer } from "./components/evidence/EvidenceDrawer"
import { PrecedentExplorer } from "./components/memory/PrecedentExplorer"
import { SimulatedProjection } from "./components/projection/SimulatedProjection"
import { TelemetryAudit } from "./components/system/TelemetryAudit"
import { EmptyState } from "./components/investigation/EmptyState"
import { ProgressState } from "./components/investigation/ProgressState"
import { fetchScenarios, runInvestigation, SCENARIO_CATALOG } from "./lib/api"
import { PersonaType, ScenarioMeta, InvestigationResult, EvidenceItem } from "./types/investigation"
import { AlertTriangle, ShieldAlert } from "lucide-react"

export const App: React.FC = () => {
  const [currentView, setCurrentView] = useState("overview")
  const [scenarios, setScenarios] = useState<ScenarioMeta[]>(SCENARIO_CATALOG)
  const [selectedScenarioId, setSelectedScenarioId] = useState("INC_001")
  const [persona, setPersona] = useState<PersonaType>("analyst")
  const [region, setRegion] = useState("all")
  
  const [isLoading, setIsLoading] = useState(false)
  const [result, setResult] = useState<InvestigationResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [activeEvidenceDrawer, setActiveEvidenceDrawer] = useState<EvidenceItem | null>(null)

  useEffect(() => {
    fetchScenarios().then((sc) => setScenarios(sc))
  }, [])

  const handleRunInvestigation = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const res = await runInvestigation(selectedScenarioId, persona, region)
      setResult(res)
    } catch (err: any) {
      setError(err.message || "Failed to complete investigation.")
      setResult(null)
    } finally {
      setIsLoading(false)
    }
  }

  const handleOpenEvidenceDrawer = (evidenceId: string) => {
    if (!result || !result.evidence) return
    const found = result.evidence.find((e) => e.evidence_id === evidenceId)
    if (found) {
      setActiveEvidenceDrawer(found)
    }
  }

  return (
    <Shell
      currentView={currentView}
      onViewChange={setCurrentView}
      scenarios={scenarios}
      selectedScenarioId={selectedScenarioId}
      onScenarioChange={setSelectedScenarioId}
      persona={persona}
      onPersonaChange={setPersona}
      region={region}
      onRegionChange={setRegion}
      onRunInvestigation={handleRunInvestigation}
      isLoading={isLoading}
      result={result}
    >
      {/* ── Error Banner ──────────────────────────────────────────────── */}
      {error && (
        <div className="p-4 rounded-lg bg-semantic-critical-bg border border-semantic-critical-border text-xs text-semantic-critical flex items-start gap-2.5">
          <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <div>
            <div className="font-mono font-bold uppercase">PIPELINE EXECUTION ERROR</div>
            <p className="mt-1 text-foreground">{error}</p>
          </div>
        </div>
      )}

      {/* ── In Progress Loading State ──────────────────────────────────── */}
      {isLoading && (
        <ProgressState scenarioId={selectedScenarioId} persona={persona} />
      )}

      {/* ── 403 Access Denied State ───────────────────────────────────── */}
      {!isLoading && result?.access_denied && (
        <div className="max-w-3xl mx-auto py-8">
          <div className="p-8 rounded-xl bg-surface border border-semantic-critical-border shadow-hero space-y-5">
            <div className="flex items-center gap-2 text-semantic-critical">
              <ShieldAlert className="w-6 h-6" />
              <h2 className="text-base font-mono font-bold uppercase tracking-wider">
                ACCESS DENIED · PRE-RETRIEVAL ENTITLEMENT BOUNDARY
              </h2>
            </div>
            <p className="text-sm text-foreground leading-relaxed">
              Persona <b className="text-semantic-warning font-mono">{persona.toUpperCase()}</b> is not authorized to query operational sources required for this investigation.
            </p>
            {result.excluded_sources && result.excluded_sources.length > 0 && (
              <div className="p-4 rounded-lg bg-surface-raised border border-hairline space-y-2">
                <div className="text-xs font-mono font-bold text-muted-foreground uppercase">EXCLUDED SOURCES:</div>
                <div className="flex flex-wrap gap-2">
                  {result.excluded_sources.map((src) => (
                    <span
                      key={src}
                      className="px-2.5 py-1 rounded text-xs font-mono font-bold bg-semantic-critical-bg text-semantic-critical border border-semantic-critical-border"
                    >
                      {src}
                    </span>
                  ))}
                </div>
              </div>
            )}
            <p className="text-xs text-muted-foreground pt-3 border-t border-hairline leading-relaxed">
              <b>Security Policy Invariant:</b> Unauthorized data is filtered before retrieval and is never transmitted to the language model. Switch to the <b>Lead Analyst</b> persona in the sidebar for full scope.
            </p>
          </div>
        </div>
      )}

      {/* ── Empty Landing State ────────────────────────────────────────── */}
      {!isLoading && !result && !error && (
        <EmptyState
          scenarios={scenarios}
          onSelectScenario={(id) => {
            setSelectedScenarioId(id)
            handleRunInvestigation()
          }}
          onRun={handleRunInvestigation}
        />
      )}

      {/* ── Active Investigation Workspace ─────────────────────────────── */}
      {!isLoading && result && !result.access_denied && (
        <div className="space-y-6">
          {/* Executive Hero */}
          <InvestigationHero
            result={result}
            onOpenEvidenceDrawer={handleOpenEvidenceDrawer}
          />

          {/* Module Views */}
          {currentView === "overview" && (
            <div className="space-y-6">
              <SignalCards signals={result.signals} />
              <DeviationSpectrumChart signals={result.signals} />
              <CausalReasoningTrail result={result} />
              <HypothesisStudio
                result={result}
                onOpenEvidenceDrawer={handleOpenEvidenceDrawer}
              />
              <SimulatedProjection outcome={result.outcome} signals={result.signals} />
            </div>
          )}

          {currentView === "reasoning" && (
            <CausalReasoningTrail result={result} />
          )}

          {currentView === "hypotheses" && (
            <HypothesisStudio
              result={result}
              onOpenEvidenceDrawer={handleOpenEvidenceDrawer}
            />
          )}

          {currentView === "evidence" && (
            <EvidenceExplorer
              evidence={result.evidence || []}
              hypotheses={result.hypotheses || []}
              onSelectEvidence={(e) => setActiveEvidenceDrawer(e)}
            />
          )}

          {currentView === "memory" && (
            <PrecedentExplorer precedents={result.precedents} />
          )}

          {currentView === "projection" && (
            <SimulatedProjection outcome={result.outcome} signals={result.signals} />
          )}

          {currentView === "telemetry" && (
            <TelemetryAudit
              telemetry={result.telemetry}
              methodOwnership={result.method_ownership}
              investigationId={result.investigation_id}
            />
          )}
        </div>
      )}

      {/* ── Slide-over Evidence Detail Drawer ─────────────────────────── */}
      <EvidenceDrawer
        evidence={activeEvidenceDrawer}
        isOpen={Boolean(activeEvidenceDrawer)}
        onClose={() => setActiveEvidenceDrawer(null)}
        hypotheses={result?.hypotheses || []}
      />
    </Shell>
  )
}

export default App
