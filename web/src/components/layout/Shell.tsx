import React from "react"
import { 
  Activity, 
  ShieldCheck, 
  Database, 
  Layers, 
  Search, 
  History, 
  TrendingUp, 
  FileText, 
  Server, 
  Play, 
  Cpu,
  Radio,
  Globe,
  User,
  AlertTriangle
} from "lucide-react"
import { ScenarioMeta, PersonaType, InvestigationResult } from "../../types/investigation"
import { cn } from "../../lib/utils"

interface ShellProps {
  currentView: string
  onViewChange: (view: string) => void
  scenarios: ScenarioMeta[]
  selectedScenarioId: string
  onScenarioChange: (scenarioId: string) => void
  persona: PersonaType
  onPersonaChange: (persona: PersonaType) => void
  region: string
  onRegionChange: (region: string) => void
  onRunInvestigation: () => void
  isLoading: boolean
  result: InvestigationResult | null
  children: React.ReactNode
  onOpenEvidenceDrawer?: (evidenceId?: string) => void
}

const NAV_ITEMS = [
  { id: "overview", label: "Executive Dashboard", icon: Activity },
  { id: "reasoning", label: "Causal Reasoning Trail", icon: Layers },
  { id: "hypotheses", label: "Hypothesis Studio", icon: ShieldCheck },
  { id: "evidence", label: "Evidence Explorer", icon: Search },
  { id: "memory", label: "Precedent Memory (E9)", icon: History },
  { id: "projection", label: "Simulated Recovery", icon: TrendingUp },
  { id: "telemetry", label: "System Audit & Telemetry", icon: FileText },
]

export const Shell: React.FC<ShellProps> = ({
  currentView,
  onViewChange,
  scenarios,
  selectedScenarioId,
  onScenarioChange,
  persona,
  onPersonaChange,
  region,
  onRegionChange,
  onRunInvestigation,
  isLoading,
  result,
  children,
}) => {
  const activeScenario = scenarios.find((s) => s.id === selectedScenarioId) || scenarios[0]
  const isEvalOnly = activeScenario?.status === "evaluation_only"

  // Determine status tag
  let statusBadge = { label: "STANDBY", color: "text-muted-foreground", bg: "bg-surface-raised" }
  if (isLoading) {
    statusBadge = { label: "INVESTIGATING", color: "text-semantic-neutral", bg: "bg-semantic-neutral-bg" }
  } else if (result) {
    if (result.access_denied) {
      statusBadge = { label: "ACCESS DENIED (403)", color: "text-semantic-critical", bg: "bg-semantic-critical-bg" }
    } else if (result.decision?.abstained) {
      statusBadge = { label: "ABSTAINED", color: "text-semantic-warning", bg: "bg-semantic-warning-bg" }
    } else {
      const winner = result.decision?.winning_hypothesis_id
      const winScored = result.scored?.find((s) => s.hypothesis_id === winner)
      const conf = winScored?.audit_verdict || "VERIFIED"
      if (conf === "VERIFIED") {
        statusBadge = { label: "RESOLVED · HIGH CONFIDENCE", color: "text-semantic-positive", bg: "bg-semantic-positive-bg" }
      } else {
        statusBadge = { label: `EVALUATED · ${conf}`, color: "text-semantic-neutral", bg: "bg-semantic-neutral-bg" }
      }
    }
  }

  return (
    <div className="flex min-h-screen bg-canvas text-foreground">
      {/* ── Left Navigation Rail ────────────────────────────────────────── */}
      <aside className="w-[310px] flex-shrink-0 bg-surface border-r border-hairline flex flex-col justify-between p-5 z-20">
        <div>
          {/* Logo & Branding */}
          <div className="flex items-center gap-3 pb-5 mb-5 border-b border-hairline">
            <div className="w-9 h-9 rounded-lg bg-surface-raised border border-hairline-bright flex items-center justify-center text-semantic-neutral shadow-glow">
              <Cpu className="w-5 h-5" />
            </div>
            <div>
              <div className="text-base font-bold tracking-tight text-white flex items-center gap-1.5">
                BusinessIntelligence<span className="text-semantic-neutral">.ai</span>
              </div>
              <div className="text-[10px] font-mono font-semibold tracking-wider text-muted-foreground uppercase">
                ANALYST WORKSTATION · v1.0
              </div>
            </div>
          </div>

          {/* Navigation Items */}
          <div className="mb-6">
            <div className="text-[11px] font-mono font-semibold tracking-wider text-muted-foreground uppercase mb-2.5 px-2">
              WORKSTATION MODULES
            </div>
            <nav className="space-y-1">
              {NAV_ITEMS.map((item) => {
                const Icon = item.icon
                const isActive = currentView === item.id
                return (
                  <button
                    key={item.id}
                    onClick={() => onViewChange(item.id)}
                    className={cn(
                      "w-full flex items-center gap-3 px-3 py-2 rounded-md text-xs font-medium transition-all duration-150 text-left",
                      isActive
                        ? "bg-surface-raised text-white border border-hairline-bright font-semibold shadow-sm"
                        : "text-muted-foreground hover:bg-surface-hover hover:text-foreground border border-transparent"
                    )}
                  >
                    <Icon className={cn("w-4 h-4", isActive ? "text-semantic-neutral" : "text-muted-foreground")} />
                    <span>{item.label}</span>
                  </button>
                )
              })}
            </nav>
          </div>

          {/* Incident Scenario Selector */}
          <div className="mb-5 pt-4 border-t border-hairline">
            <label className="text-[11px] font-mono font-semibold tracking-wider text-muted-foreground uppercase block mb-1.5 px-1">
              INCIDENT SCENARIO
            </label>
            <select
              value={selectedScenarioId}
              onChange={(e) => onScenarioChange(e.target.value)}
              className="w-full bg-surface-raised border border-hairline hover:border-hairline-bright focus:border-semantic-neutral rounded-md px-3 py-2 text-xs text-foreground font-medium outline-none transition-colors"
            >
              {scenarios.map((sc) => (
                <option key={sc.id} value={sc.id} className="bg-surface text-foreground py-1">
                  {sc.id} — {sc.title}
                </option>
              ))}
            </select>

            {/* Scenario Meta Info Card */}
            {activeScenario && (
              <div className="mt-2.5 bg-surface-raised/80 border border-hairline rounded-md p-2.5 text-xs">
                <div className="flex justify-between items-center mb-1">
                  <span className="font-mono text-[11px] font-semibold text-semantic-neutral">
                    {activeScenario.domain}
                  </span>
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {activeScenario.type}
                  </span>
                </div>
                <p className="text-[11px] text-muted-foreground leading-relaxed line-clamp-2">
                  {activeScenario.description}
                </p>
              </div>
            )}
          </div>

          {/* Persona & Region Scope */}
          <div className="space-y-3 mb-6">
            <div>
              <label className="text-[11px] font-mono font-semibold tracking-wider text-muted-foreground uppercase block mb-1 px-1 flex items-center gap-1.5">
                <User className="w-3 h-3" /> ANALYST PERSONA (SCOPE)
              </label>
              <select
                value={persona}
                onChange={(e) => onPersonaChange(e.target.value as PersonaType)}
                className="w-full bg-surface-raised border border-hairline hover:border-hairline-bright focus:border-semantic-neutral rounded-md px-3 py-2 text-xs text-foreground font-medium outline-none transition-colors"
              >
                <option value="analyst">Lead Analyst — Full System Scope</option>
                <option value="cfo">CFO / Executive — Aggregate Only</option>
                <option value="manager">Regional Manager — Restricted Scope</option>
              </select>
            </div>

            <div>
              <label className="text-[11px] font-mono font-semibold tracking-wider text-muted-foreground uppercase block mb-1 px-1 flex items-center gap-1.5">
                <Globe className="w-3 h-3" /> REGIONAL BOUNDARY
              </label>
              <select
                value={region}
                onChange={(e) => onRegionChange(e.target.value)}
                className="w-full bg-surface-raised border border-hairline hover:border-hairline-bright focus:border-semantic-neutral rounded-md px-3 py-2 text-xs text-foreground font-medium outline-none transition-colors"
              >
                <option value="all">All Regions (Global Baseline)</option>
                <option value="us-east">US-East Region Only</option>
                <option value="us-west">US-West Region Only</option>
                <option value="eu-central">EU-Central Region Only</option>
                <option value="apac">APAC Region Only</option>
              </select>
            </div>
          </div>

          {/* Primary Action Button */}
          <button
            onClick={onRunInvestigation}
            disabled={isLoading || isEvalOnly}
            className={cn(
              "w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-md font-semibold text-xs transition-all shadow-md",
              isEvalOnly
                ? "bg-surface-raised text-muted-foreground border border-hairline cursor-not-allowed"
                : isLoading
                ? "bg-surface-raised text-semantic-neutral border border-semantic-neutral/40 cursor-wait animate-pulse"
                : "bg-semantic-neutral text-white hover:bg-blue-600 active:scale-[0.99] border border-blue-400/40 shadow-glow"
            )}
          >
            {isLoading ? (
              <>
                <Radio className="w-4 h-4 animate-spin text-semantic-neutral" />
                <span>INVESTIGATING...</span>
              </>
            ) : isEvalOnly ? (
              <>
                <AlertTriangle className="w-4 h-4 text-semantic-warning" />
                <span>EVALUATION HARNESS ONLY</span>
              </>
            ) : (
              <>
                <Play className="w-4 h-4 fill-current" />
                <span>RUN INVESTIGATION</span>
              </>
            )}
          </button>
        </div>

        {/* System Health Widget */}
        <div className="pt-4 border-t border-hairline">
          <div className="text-[10px] font-mono font-semibold tracking-wider text-muted-foreground uppercase mb-2 flex items-center justify-between">
            <span>INFRASTRUCTURE</span>
            <span className="text-semantic-positive">3/3 READY</span>
          </div>
          <div className="space-y-1.5 font-mono text-[11px]">
            <div className="flex justify-between items-center text-muted-foreground">
              <span>PostgreSQL 15</span>
              <span className="text-semantic-positive flex items-center gap-1">● 5432</span>
            </div>
            <div className="flex justify-between items-center text-muted-foreground">
              <span>ChromaDB Vector</span>
              <span className="text-semantic-positive flex items-center gap-1">● 8000</span>
            </div>
            <div className="flex justify-between items-center text-muted-foreground">
              <span>Ollama (qwen3:8b)</span>
              <span className="text-semantic-positive flex items-center gap-1">● 11434</span>
            </div>
          </div>
        </div>
      </aside>

      {/* ── Main Canvas View ───────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        {/* Top Header Bar */}
        <header className="h-16 px-8 border-b border-hairline bg-surface/80 backdrop-blur-md sticky top-0 z-10 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="font-mono font-bold text-xs bg-semantic-neutral-bg text-semantic-neutral border border-semantic-neutral-border px-2.5 py-1 rounded">
              {activeScenario?.id || "INC_001"}
            </span>
            <div>
              <h1 className="text-sm font-bold text-white tracking-tight flex items-center gap-2">
                {activeScenario?.title}
                <span className="text-xs font-normal text-muted-foreground">({activeScenario?.domain})</span>
              </h1>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="text-xs text-muted-foreground font-mono">
              SCOPE: <span className="text-white font-semibold">{persona.toUpperCase()} / {region.toUpperCase()}</span>
            </div>
            <div className={cn("px-3 py-1 rounded text-xs font-mono font-bold flex items-center gap-1.5 border border-hairline", statusBadge.bg, statusBadge.color)}>
              <span className="w-2 h-2 rounded-full bg-current animate-pulse"></span>
              {statusBadge.label}
            </div>
          </div>
        </header>

        {/* Content Container */}
        <main className="p-8 max-w-[1600px] w-full mx-auto space-y-6">
          {children}
        </main>
      </div>
    </div>
  )
}
