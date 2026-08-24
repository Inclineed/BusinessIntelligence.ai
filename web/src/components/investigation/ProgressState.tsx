import React from "react"
import { Radio, CheckCircle2, CircleDot } from "lucide-react"

interface ProgressStateProps {
  scenarioId: string
  persona: string
}

export const ProgressState: React.FC<ProgressStateProps> = ({ scenarioId, persona }) => {
  const stages = [
    { name: "E1 KPI Store", desc: "Loading baseline history & time-series metrics from PostgreSQL" },
    { name: "E2 Signal Detection", desc: "Evaluating z-score deviation corridors & corroboration" },
    { name: "E3 Diagnostic Engine", desc: "Decomposing variance across multi-dimensional segments" },
    { name: "Security Boundary", desc: "Verifying pre-retrieval persona entitlement constraints" },
    { name: "E4 Evidence Assembly", desc: "Retrieving telemetry artifacts from SQL & ChromaDB" },
    { name: "E5 Hypothesis Engine", desc: "Synthesizing causal hypotheses via local LLM" },
    { name: "E6 Challenge Rules", desc: "Running 5 deterministic falsification & contradiction rules" },
    { name: "E7 Decision Engine", desc: "Evaluating winner separation and prescribing action" },
    { name: "E8 & E9 Projection & Memory", desc: "Simulating recovery trajectory & archiving precedent" },
  ]

  return (
    <div className="max-w-3xl mx-auto py-12">
      <div className="p-8 rounded-xl bg-surface border border-hairline shadow-hero space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-hairline">
          <div>
            <div className="flex items-center gap-2">
              <Radio className="w-4 h-4 text-semantic-neutral animate-pulse" />
              <h2 className="text-base font-bold text-white tracking-tight">
                Investigation Pipeline in Progress
              </h2>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5 font-mono">
              Executing 9-engine analytical pipeline on <b className="text-white">{scenarioId}</b> for <b className="text-semantic-neutral">{persona.toUpperCase()}</b>
            </p>
          </div>
          <span className="px-2.5 py-1 rounded text-xs font-mono font-bold bg-semantic-neutral-bg text-semantic-neutral border border-semantic-neutral-border">
            ACTIVE PIPELINE
          </span>
        </div>

        {/* Stages Checklist */}
        <div className="space-y-3.5">
          {stages.map((stage, idx) => (
            <div
              key={idx}
              className="flex items-start gap-3 p-2.5 rounded-lg bg-surface-raised/40 border border-hairline-subtle"
            >
              <div className="mt-0.5">
                <CheckCircle2 className="w-4 h-4 text-semantic-positive" />
              </div>
              <div className="flex-1 text-xs">
                <div className="font-mono font-bold text-white">{stage.name}</div>
                <div className="text-muted-foreground">{stage.desc}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="pt-3 border-t border-hairline text-center text-xs text-muted-foreground font-mono">
          Inference running locally on Ollama (qwen3:8b) · Zero cloud transmission
        </div>
      </div>
    </div>
  )
}
