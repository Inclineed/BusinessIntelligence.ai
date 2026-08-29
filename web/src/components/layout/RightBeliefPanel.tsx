import React, { useEffect } from "react"
import { InvestigationResult, PersonaType } from "../../types/investigation"
import {
  Zap,
  AlertTriangle,
  CheckCircle2,
  TrendingUp,
  History,
  ShieldCheck,
  ArrowRight,
  X,
  Sparkles,
} from "lucide-react"

interface RightBeliefPanelProps {
  result: InvestigationResult
  currentStageNum: number
  persona: PersonaType
  isOpen: boolean
  onClose: () => void
  onExecuteAction?: () => void
}

export const RightBeliefPanel: React.FC<RightBeliefPanelProps> = ({
  result,
  currentStageNum,
  persona,
  isOpen,
  onClose,
  onExecuteAction,
}) => {
  const isAbstained = result.decision?.abstained ?? false
  const winningHypothesis = result.decision?.winning_hypothesis_id || "H1"
  const leadingScored =
    result.scored?.find((s) => s.hypothesis_id === winningHypothesis) || result.scored?.[0]
  const confidenceScore = leadingScored?.final_audit_score
    ? Math.round(leadingScored.final_audit_score * 100)
    : 85

  // SVG Circular Dash math (r=48 => circumference ~ 301.59)
  const circumference = 301.59
  const strokeDashoffset = isAbstained
    ? 0
    : circumference - (confidenceScore / 100) * circumference

  // Close on Escape key press
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose()
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [isOpen, onClose])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end animate-fade-in">
      {/* Backdrop overlay */}
      <div
        className="fixed inset-0 bg-black/60 backdrop-blur-sm transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Slide-over Drawer */}
      <aside
        className="relative w-full max-w-md md:max-w-lg bg-[#181818] border-l border-[#2E2E2E] flex flex-col h-full shadow-2xl z-10 overflow-y-auto custom-scrollbar animate-slide-in-right"
        role="dialog"
        aria-modal="true"
        aria-label="Assessment & Action Directive Drawer"
      >
        {/* Sticky Header with Close Button */}
        <div className="p-4 border-b border-[#2E2E2E] flex justify-between items-center sticky top-0 bg-[#181818]/95 backdrop-blur-md z-10">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#6B9BB0] shadow-[0_0_6px_rgba(107,155,176,0.6)]" />
            <span className="font-mono text-xs font-bold text-[#F4EEE0] uppercase tracking-wider">
              System Assessment &amp; Action Directive
            </span>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg bg-[#222222] hover:bg-[#2E2E2E] text-[#9E9788] hover:text-[#F4EEE0] border border-[#333333] transition-colors"
            title="Close Drawer (Esc)"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-6 flex flex-col justify-between space-y-6 flex-1">
          {/* Top: Dynamic System Belief & Circular Confidence Ring */}
          <div className="space-y-4">
            <div className="space-y-1 text-center">
              <span className="font-mono text-[10px] font-bold text-[#9E9788] uppercase tracking-wider block">
                {currentStageNum <= 2
                  ? "SIGNAL RECOGNITION"
                  : currentStageNum <= 4
                  ? "GROUNDED ASSESSMENT"
                  : currentStageNum <= 6
                  ? "SYSTEM BELIEF"
                  : currentStageNum === 7
                  ? "ACTION DIRECTIVE"
                  : currentStageNum === 8
                  ? "PROJECTED IMPACT"
                  : "INSTITUTIONAL MEMORY"}
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
              <svg
                className="absolute inset-0 w-full h-full transform -rotate-90"
                viewBox="0 0 100 100"
              >
                <circle
                  cx="50"
                  cy="50"
                  fill="transparent"
                  r="48"
                  stroke="#2B2B2B"
                  strokeWidth="3"
                />
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
                  {isAbstained ? "ABSTAIN" : `${confidenceScore}%`}
                </span>
                <span className="text-[9px] font-mono font-bold text-[#9E9788] uppercase tracking-wider">
                  {isAbstained ? "GUARD ACTIVE" : "CONFIDENCE"}
                </span>
              </div>
            </div>
          </div>

          {/* Middle: Stage-Specific Intelligence Insights */}
          <div className="space-y-4 text-xs font-mono">
            {/* Anomaly Severity Card */}
            <div className="p-3.5 rounded-xl bg-[#222222] border border-[#333333] space-y-2">
              <div className="text-[#9E9788] uppercase text-[10px]">Anomaly Significance</div>
              <div className="text-sm font-bold text-[#D8453A]">
                {result.signals?.[0]?.delta_pct
                  ? `${result.signals[0].delta_pct.toFixed(1)}% drop from baseline`
                  : "-14.2% drop"}
              </div>
              <div className="text-[#9E9788] text-[11px]">
                Statistical severity:{" "}
                <span className="text-[#F4EEE0] font-bold">
                  {result.signals?.[0]?.z_score
                    ? `${result.signals[0].z_score.toFixed(2)}σ`
                    : "-3.85σ"}
                </span>
              </div>
            </div>

            {/* Evaluated Root Cause & Narrative */}
            <div className="p-3.5 rounded-xl bg-[#222222] border border-[#333333] space-y-2">
              <div className="text-[#9E9788] uppercase text-[10px]">
                {isAbstained ? "Abstention Rationale" : "Evaluated Causal Rationale"}
              </div>
              <p className="text-[#D1C9B8] font-sans text-xs leading-relaxed">
                {result.decision?.persona_narrative ||
                  (isAbstained
                    ? "Confidence criteria was not satisfied or guard conditions prevented automated execution."
                    : "Payment gateway connection pool exhaustion is corroborated by latency surge and release timestamp alignment.")}
              </p>
            </div>

            {/* Verification Metric */}
            {result.decision?.verification_metric && (
              <div className="p-3 rounded-lg bg-[#181818] border border-[#333333] space-y-1">
                <div className="text-[#6B9BB0] text-[10px] uppercase font-bold">
                  Verification Metric
                </div>
                <div className="text-[#D1C9B8] text-[11px] font-sans">
                  {result.decision.verification_metric}
                </div>
              </div>
            )}

            {/* Projected Impact */}
            {result.outcome && result.outcome.projected_recovery_pct !== undefined && (
              <div className="p-3.5 rounded-xl bg-[#222222] border border-[#333333] space-y-1.5">
                <div className="text-[#9E9788] uppercase text-[10px]">Projected Outcome</div>
                <p className="text-[#D1C9B8] font-sans text-xs leading-relaxed">
                  Projected{" "}
                  <span className="text-[#4E8569] font-bold">
                    {result.outcome.projected_recovery_pct.toFixed(1)}%
                  </span>{" "}
                  recovery on {result.outcome.projected_metric || "primary metric"} · mean time to normalcy{" "}
                  <span className="text-[#6B9BB0] font-bold">
                    {result.outcome.mean_time_to_normalcy || "5 min"}
                  </span>
                  .
                </p>
                <div className="text-[10px] text-[#9E9788] border-t border-white/[0.04] pt-1">
                  * Simulation estimate based on scripted recovery patterns. Not causal proof.
                </div>
              </div>
            )}
          </div>

          {/* Bottom: Mitigation Action Trigger Button */}
          <div className="pt-4 border-t border-[#2E2E2E]">
            <button
              onClick={() => {
                if (onExecuteAction) onExecuteAction()
                onClose()
              }}
              className={`w-full py-3.5 px-4 rounded-xl text-xs font-mono font-bold transition-all flex items-center justify-center gap-2 cursor-pointer shadow-lg ${
                isAbstained
                  ? "bg-[#D8453A]/20 hover:bg-[#D8453A]/30 text-[#E56B62] border border-[#D8453A]/40"
                  : "bg-[#6B9BB0]/20 hover:bg-[#6B9BB0]/35 text-[#F4EEE0] border border-[#6B9BB0]/40"
              }`}
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  isAbstained ? "bg-[#D8453A]" : "bg-[#6B9BB0]"
                }`}
              />
              <span>
                {isAbstained ? "REVIEW ABSTENTION REASON" : "EXECUTE MITIGATION STRATEGY"}
              </span>
            </button>
          </div>
        </div>
      </aside>
    </div>
  )
}
