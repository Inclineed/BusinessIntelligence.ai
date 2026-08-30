import React from "react"
import { InvestigationResult } from "../../types/investigation"
import { RecoveryProjectionGauge } from "../decision/RecoveryProjectionGauge"
import { SimulatedProjection } from "../projection/SimulatedProjection"
import { ShieldAlert, Activity, CheckCircle2, Clock } from "lucide-react"

interface E8OutcomeWorkspaceProps {
  result: InvestigationResult
}

export const E8OutcomeWorkspace: React.FC<E8OutcomeWorkspaceProps> = ({ result }) => {
  const outcome = result.outcome
  const hasValidProjection = Boolean(outcome && outcome.projected_recovery_pct !== undefined)
  const recoveryPct = outcome?.projected_recovery_pct
  const meanTimeToNormalcy = outcome?.mean_time_to_normalcy || "N/A"
  const structuredRec = result.decision?.structured_recommendation

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Stage Header */}
      <header className="space-y-2 border-b border-[#2E2E2E] pb-4">
        <div className="flex items-center justify-between">
          <span className="px-2 py-0.5 rounded bg-[#6B9BB0]/20 text-[#F4EEE0] font-mono text-xs font-bold border border-[#6B9BB0]/40">
            STAGE E8 · PROJECTED OUTCOME
          </span>
          <span
            className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
              hasValidProjection
                ? "bg-[#1C1C1C] text-[#9E9788] border-[#2E2E2E]"
                : "bg-[#D8453A]/10 text-[#E56B62] border-[#D8453A]/30"
            }`}
          >
            {hasValidProjection ? "[SIMULATED]" : "[NON-REMEDIAL · NO SIMULATION]"}
          </span>
        </div>
        <h1 className="text-2xl font-bold font-sans text-[#F4EEE0] tracking-tight">
          Recovery Trajectory &amp; Projected Impact
        </h1>
        <p className="text-xs text-[#9E9788] font-sans leading-relaxed max-w-3xl">
          Forecasting the operational and financial impact of executing the recommended intervention against baseline recovery corridors.
        </p>
      </header>

      {hasValidProjection && outcome ? (
        <>
          {/* 2-Card Projection Metric Summary */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 font-mono">
            <div className="p-6 rounded-2xl bg-[#1C1C1C] border border-[#2E2E2E] text-center space-y-2">
              <div className="text-[11px] text-[#9E9788] uppercase tracking-wider">Projected Recovery</div>
              <div className="text-4xl font-bold text-[#4E8569] tabular-nums">
                {recoveryPct !== undefined ? `${recoveryPct.toFixed(1)}%` : "N/A"}
              </div>
              <div className="text-xs text-[#9E9788]">Target metric: {outcome.projected_metric || "N/A"}</div>
            </div>

            <div className="p-6 rounded-2xl bg-[#1C1C1C] border border-[#2E2E2E] text-center space-y-2">
              <div className="text-[11px] text-[#9E9788] uppercase tracking-wider">Mean Time to Normalcy</div>
              <div className="text-4xl font-bold text-[#6B9BB0] tabular-nums">
                {meanTimeToNormalcy}
              </div>
              <div className="text-xs text-[#9E9788]">Simulated stabilization estimate (non-SLA)</div>
            </div>
          </div>

          {/* Interactive Trajectory Curve & Corridor */}
          <SimulatedProjection outcome={outcome} signals={result.signals} />

          {/* Recovery Projection Gauge Component with Disclaimer */}
          <RecoveryProjectionGauge outcome={outcome} />
        </>
      ) : (
        /* Non-Remedial / Suppressed Projection State */
        <div className="p-8 rounded-2xl bg-[#1C1C1C] border border-[#2E2E2E] space-y-5">
          <div className="flex items-center gap-3 text-[#E56B62]">
            <ShieldAlert className="w-6 h-6 shrink-0" />
            <div>
              <h3 className="text-base font-bold font-mono text-[#F4EEE0] uppercase tracking-wider">
                NO OPERATIONAL RECOVERY PROJECTION
              </h3>
              <div className="text-xs font-mono text-[#E56B62] mt-0.5">
                Reason: Investigation remains non-remedial / insufficiently validated.
              </div>
            </div>
          </div>

          <p className="text-xs text-[#9E9788] font-sans leading-relaxed">
            Operational recovery projections are strictly withheld for non-remedial directives (such as diagnostic investigations, telemetry verification, or abstentions). A forward-looking recovery corridor is generated only when an authorized, causal remediation action is confirmed.
          </p>

          {structuredRec && (
            <div className="p-4 rounded-xl bg-[#141414] border border-[#282828] space-y-2.5 font-mono text-xs">
              <div className="flex items-center justify-between text-[#9E9788] border-b border-[#222222] pb-2">
                <span>Controllable Lever:</span>
                <span className="text-[#F4EEE0] font-bold">{structuredRec.controllable_lever}</span>
              </div>
              <div className="flex items-center justify-between text-[#9E9788] border-b border-[#222222] pb-2">
                <span>Expected Impact:</span>
                <span className="text-[#6B9BB0] font-bold">{structuredRec.expected_impact}</span>
              </div>
              {result.decision?.recommended_action && (
                <div className="pt-1 text-[#9E9788]">
                  <span className="text-[#A8A29E]">Governed Directive: </span>
                  <span className="text-[#F4EEE0]">{result.decision.recommended_action}</span>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

