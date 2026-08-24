import React from "react"
import { Play, Sparkles, Shield, Cpu, ArrowRight } from "lucide-react"
import { ScenarioMeta } from "../../types/investigation"

interface EmptyStateProps {
  scenarios: ScenarioMeta[]
  onSelectScenario: (scenarioId: string) => void
  onRun: () => void
}

export const EmptyState: React.FC<EmptyStateProps> = ({ scenarios, onSelectScenario, onRun }) => {
  return (
    <div className="max-w-4xl mx-auto py-12 text-center space-y-8">
      {/* Hero Badge & Title */}
      <div className="space-y-3">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-semantic-neutral-bg border border-semantic-neutral-border text-semantic-neutral text-xs font-mono font-semibold">
          <Cpu className="w-3.5 h-3.5" />
          <span>EVIDENCE-BACKED KPI REASONING PLATFORM</span>
        </div>
        <h2 className="text-3xl sm:text-4xl font-bold tracking-tight text-white">
          Autonomous Incident Investigation & Attribution
        </h2>
        <p className="text-sm text-muted-foreground max-w-2xl mx-auto leading-relaxed">
          Select an incident scenario from the operational catalog or click below to launch the 9-engine analytical pipeline with verifiable evidence and falsification audit.
        </p>
      </div>

      {/* 3 Pillars */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-left">
        <div className="p-5 rounded-lg bg-surface border border-hairline shadow-card space-y-2">
          <div className="flex items-center gap-2 text-xs font-mono font-bold text-semantic-critical">
            <span>●</span> 01. DETECT
          </div>
          <h3 className="text-sm font-bold text-white">Statistical Corridor Monitoring</h3>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Evaluates rolling ±3.0σ z-scores with data-quality and baseline-history guardrails to prevent false alarms.
          </p>
        </div>

        <div className="p-5 rounded-lg bg-surface border border-hairline shadow-card space-y-2">
          <div className="flex items-center gap-2 text-xs font-mono font-bold text-semantic-neutral">
            <span>●</span> 02. EXPLAIN
          </div>
          <h3 className="text-sm font-bold text-white">Empirical Evidence Assembly</h3>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Assembles authorized telemetry artifacts from SQL & ChromaDB before cognitive hypothesis synthesis.
          </p>
        </div>

        <div className="p-5 rounded-lg bg-surface border border-hairline shadow-card space-y-2">
          <div className="flex items-center gap-2 text-xs font-mono font-bold text-semantic-positive">
            <span>●</span> 03. DECIDE
          </div>
          <h3 className="text-sm font-bold text-white">Actionable Resolution</h3>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Scores candidate causes through 5 deterministic falsification rules, prescribing audited operational action.
          </p>
        </div>
      </div>

      {/* Quick Launch Cards */}
      <div className="p-6 rounded-xl bg-surface border border-hairline shadow-hero text-left space-y-4">
        <div className="flex justify-between items-center">
          <span className="text-xs font-mono font-bold uppercase tracking-wider text-white">
            Quick Launch Scenarios
          </span>
          <span className="text-[11px] font-mono text-muted-foreground">SELECT TO CONFIGURE</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {scenarios.slice(0, 4).map((sc) => (
            <div
              key={sc.id}
              onClick={() => {
                onSelectScenario(sc.id)
              }}
              className="group p-3.5 rounded-lg bg-surface-raised border border-hairline hover:border-semantic-neutral/60 cursor-pointer transition-all flex items-center justify-between"
            >
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-mono text-xs font-bold text-semantic-neutral">{sc.id}</span>
                  <span className="text-[10px] font-mono text-muted-foreground">({sc.domain})</span>
                </div>
                <div className="text-xs font-semibold text-white group-hover:text-semantic-neutral transition-colors">
                  {sc.title}
                </div>
              </div>
              <ArrowRight className="w-4 h-4 text-muted-foreground group-hover:text-semantic-neutral group-hover:translate-x-1 transition-all flex-shrink-0" />
            </div>
          ))}
        </div>

        <div className="pt-3 flex justify-center">
          <button
            onClick={onRun}
            className="flex items-center gap-2 px-6 py-2.5 rounded-md bg-semantic-neutral hover:bg-blue-600 text-xs font-bold text-white shadow-glow transition-all active:scale-[0.99]"
          >
            <Play className="w-4 h-4 fill-current" />
            <span>RUN INC_001 INVESTIGATION NOW</span>
          </button>
        </div>
      </div>
    </div>
  )
}
