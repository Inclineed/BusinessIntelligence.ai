import React from "react"
import { InvestigationResult, PersonaType } from "../../types/investigation"
import { Zap, AlertTriangle, CheckCircle2, TrendingUp, History, ShieldCheck, ArrowRight } from "lucide-react"

interface RightBeliefPanelProps {
  result: InvestigationResult
  currentStageNum: number
  persona: PersonaType
  onExecuteAction?: () => void
}

export const RightBeliefPanel: React.FC<RightBeliefPanelProps> = ({
  result,
  currentStageNum,
  persona,
  onExecuteAction,
}) => {
  const isAbstained = result.decision?.abstained ?? false
  const winningHypothesis = result.decision?.winning_hypothesis_id || "H1"
  const leadingScored = result.scored?.find((s) => s.hypothesis_id === winningHypothesis) || result.scored?.[0]
  const confidenceScore = leadingScored?.final_score ? Math.round(leadingScored.final_score * 100) : 91
  const recoveryPct = result.outcome?.projected_recovery_pct ?? 88.0

  // SVG Circular Dash math (r=48 => circumference ~ 301.59)
  const circumference = 301.59
  const strokeDashoffset = isAbstained 
    ? 0 
    : circumference - (confidenceScore / 100) * circumference

  return (
    <aside className="w-80 lg:w-96 bg-[#181818] flex flex-col border-l border-[#2E2E2E] shrink-0 z-30 overflow-y-auto custom-scrollbar">
      <div className="p-6 flex flex-col h-full justify-between space-y-6">
        
        {/* Top: Dynamic System Belief Header */}
        <div className="space-y-4">
          <div className="space-y-1">
            <span className="font-mono text-[10px] font-bold text-[#9E9788] uppercase tracking-wider block">
              {currentStageNum <= 2 ? "SIGNAL RECOGNITION" : currentStageNum <= 4 ? "GROUNDED ASSESSMENT" : currentStageNum <= 6 ? "SYSTEM BELIEF" : currentStageNum === 7 ? "ACTION DIRECTIVE" : currentStageNum === 8 ? "PROJECTED IMPACT" : "INSTITUTIONAL MEMORY"}
            </span>
            <h2 className="text-base font-bold font-sans text-[#F4EEE0] leading-snug">
              {isAbstained
                ? "Autonomous Abstention Triggered"
                : result.decision?.recommended_action
                ? result.decision.recommended_action
                : "Mitigate Primary Gateway Latency"}
            </h2>
          </div>

          {/* Circular SVG Confidence Ring */}
          <div className="relative w-36 h-36 mx-auto flex items-center justify-center rounded-full border border-[#2E2E2E] my-2 bg-[#1C1C1C]">
            <svg className="absolute inset-0 w-full h-full transform -rotate-90" viewBox="0 0 100 100">
              <circle cx="50" cy="50" fill="transparent" r="48" stroke="#2B2B2B" strokeWidth="3" />
              <circle
                cx="50"
                cy="50"
                fill="transparent"
                r="48"
                stroke={isAbstained ? "#D8453A" : "#6B9BB0"}
                strokeDasharray={circumference}
                strokeDashoffset={strokeDashoffset}
                strokeLinecap="round"
                strokeWidth="3"
                className="transition-all duration-700 ease-out"
              />
            </svg>
            <div className="text-center z-10 flex flex-col items-center">
              <span className="text-3xl font-bold font-mono text-[#F4EEE0] leading-none block mb-1 tabular-nums">
                {isAbstained ? "ABSTAIN" : confidenceScore}
              </span>
              <span className="text-[9px] font-mono font-bold text-[#9E9788] uppercase tracking-wider">
                {isAbstained ? "GUARD ACTIVE" : "CONFIDENCE"}
              </span>
            </div>
          </div>
        </div>

        {/* Middle: Stage-Specific Intelligence Summary */}
        <div className="space-y-4 text-xs font-mono">
          {currentStageNum <= 2 && (
            <div className="p-3.5 rounded-xl bg-[#222222] border border-[#333333] space-y-2">
              <div className="text-[#9E9788] uppercase text-[10px]">Anomaly Significance</div>
              <div className="text-sm font-bold text-[#D8453A]">
                {result.signals?.[0]?.delta_pct ? `${result.signals[0].delta_pct.toFixed(1)}% drop from baseline` : "-14.2% drop"}
              </div>
              <div className="text-[#9E9788] text-[11px]">
                Statistical severity: <span className="text-[#F4EEE0] font-bold">{result.signals?.[0]?.z_score ? `${result.signals[0].z_score.toFixed(2)}σ` : "-3.85σ"}</span>
              </div>
            </div>
          )}

          {currentStageNum === 3 && (
            <div className="p-3.5 rounded-xl bg-[#222222] border border-[#333333] space-y-2">
              <div className="text-[#9E9788] uppercase text-[10px]">Primary Segment Driver</div>
              <div className="text-sm font-bold text-[#6B9BB0]">
                {result.contributions?.[0] ? `${result.contributions[0].dimension}: ${result.contributions[0].segment}` : "device: android"}
              </div>
              <div className="text-[#9E9788] text-[11px]">
                Explains <span className="text-[#F4EEE0] font-bold">{result.contributions?.[0]?.contribution_pct.toFixed(0) || "88"}%</span> of aggregate anomaly drop.
              </div>
            </div>
          )}

          {currentStageNum === 4 && (
            <div className="p-3.5 rounded-xl bg-[#222222] border border-[#333333] space-y-2">
              <div className="text-[#9E9788] uppercase text-[10px]">Strongest Evidence Source</div>
              <div className="text-sm font-bold text-[#4E8569]">
                {result.evidence?.[0]?.evidence_id || "EV_gateway_latency"} ({result.evidence?.[0]?.source_id || "payment_gateway"})
              </div>
              <div className="text-[#9E9788] text-[11px]">
                Reliability weight: <span className="text-[#F4EEE0] font-bold">{result.evidence?.[0]?.reliability_weight ? `${Math.round(result.evidence[0].reliability_weight * 100)}%` : "98%"}</span>
              </div>
            </div>
          )}

          {currentStageNum >= 5 && currentStageNum <= 7 && (
            <div className="space-y-3">
              <div className="p-3.5 rounded-xl bg-[#222222] border border-[#333333] space-y-1.5">
                <div className="text-[#9E9788] uppercase text-[10px]">Evaluated Rationale</div>
                <p className="text-[#D1C9B8] font-sans text-xs leading-relaxed">
                  {result.decision?.persona_narrative || "Payment gateway connection pool exhaustion is supported by latency correlation and release timestamp alignment."}
                </p>
              </div>

              {result.decision?.verification_metric && (
                <div className="p-3 rounded-lg bg-[#181818] border border-[#333333] space-y-1">
                  <div className="text-[#6B9BB0] text-[10px] uppercase font-bold">Verification Metric</div>
                  <div className="text-[#D1C9B8] text-[11px] font-sans">
                    {result.decision.verification_metric}
                  </div>
                </div>
              )}
            </div>
          )}

          {currentStageNum === 8 && (
            <div className="p-3.5 rounded-xl bg-[#222222] border border-[#333333] space-y-2">
              <div className="text-[#9E9788] uppercase text-[10px]">Projected Outcome</div>
              <p className="text-[#D1C9B8] font-sans text-xs leading-relaxed">
                Executing mitigation is projected to recover <span className="text-[#4E8569] font-bold">{recoveryPct.toFixed(1)}%</span> of lost conversion within standard SLA windows.
              </p>
              <div className="text-[10px] text-[#9E9788] border-t border-white/[0.04] pt-1.5">
                * Simulated calibration outcome; not historical proof.
              </div>
            </div>
          )}

          {currentStageNum === 9 && (
            <div className="p-3.5 rounded-xl bg-[#222222] border border-[#333333] space-y-2">
              <div className="text-[#9E9788] uppercase text-[10px]">Precedent Grounding</div>
              <p className="text-[#D1C9B8] font-sans text-xs leading-relaxed">
                Incident parameters matched with institutional precedent <span className="text-[#6B9BB0] font-bold">{result.precedents?.[0] ? (typeof result.precedents[0] === 'string' ? result.precedents[0] : result.precedents[0].scenario_id) : "INC_001"}</span> (+0.10 retrieval validation applied).
              </p>
            </div>
          )}
        </div>

        {/* Bottom: Consequential Action Trigger Button */}
        <div className="pt-4 border-t border-[#2E2E2E]">
          <button
            onClick={onExecuteAction}
            className={`w-full py-3.5 px-4 rounded-xl text-xs font-mono font-bold transition-all flex items-center justify-center gap-2 cursor-pointer shadow-lg ${
              isAbstained
                ? "bg-[#D8453A]/20 hover:bg-[#D8453A]/30 text-[#E56B62] border border-[#D8453A]/40"
                : "bg-[#6B9BB0]/20 hover:bg-[#6B9BB0]/35 text-[#F4EEE0] border border-[#6B9BB0]/40"
            }`}
          >
            <span className={`w-2 h-2 rounded-full ${isAbstained ? "bg-[#D8453A]" : "bg-[#6B9BB0]"}`} />
            <span>{isAbstained ? "REVIEW ABSTENTION REASON" : "EXECUTE MITIGATION STRATEGY"}</span>
          </button>
        </div>
      </div>
    </aside>
  )
}
