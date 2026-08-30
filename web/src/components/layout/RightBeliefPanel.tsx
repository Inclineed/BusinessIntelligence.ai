import React, { useEffect } from "react"
import { InvestigationResult, PersonaType } from "../../types/investigation"
import { cleanLLMTags } from "../../lib/utils"
import { getInvestigationStory } from "../../lib/narrativeHelpers"
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
  ShieldAlert,
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
  const story = getInvestigationStory(result)
  const isNominal = story.isNominal ?? false
  const isAbstained = result.decision?.abstained ?? false
  const winningHypothesis = result.decision?.winning_hypothesis_id || "H1"
  const leadingScored =
    result.scored?.find((s) => s.hypothesis_id === winningHypothesis) ||
    result.scored?.[0]

  const auditScore = leadingScored?.final_audit_score != null
    ? Math.round(leadingScored.final_audit_score * 100)
    : (isAbstained ? 0 : 71)

  const auditVerdict =
    leadingScored?.audit_verdict ||
    (isAbstained
      ? "ABSTAIN"
      : auditScore >= 70
      ? "VERIFIED"
      : "MARGINAL")

  const getVerdictLabel = () => {
    if (isNominal) return "SYSTEM HEALTHY"
    if (isAbstained) return "AUDIT ABSTAIN"
    switch (auditVerdict.toUpperCase()) {
      case "VERIFIED":
        return "AUDIT VERIFIED"
      case "MARGINAL":
        return "AUDIT MARGINAL"
      case "REJECTED":
        return "AUDIT REJECTED"
      default:
        return "AUDIT SCORE"
    }
  }

  // SVG Circular Dash math (r=48 => circumference ~ 301.59)
  const circumference = 301.59
  const strokeDashoffset = isAbstained
    ? 0
    : circumference - (auditScore / 100) * circumference

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
    <div className="fixed inset-0 z-50 flex justify-end animate-fade-in select-text">
      {/* Backdrop overlay */}
      <div
        className="fixed inset-0 bg-black/60 backdrop-blur-sm transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Slide-over Drawer */}
      {/* Drawer Container */}
      <aside className="absolute inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-md bg-[#181818] border-l border-[#2E2E2E] shadow-2xl p-6 flex flex-col justify-between overflow-y-auto animate-slide-in-right">
          {/* Top: Header & High-Level Directive */}
          <div className="space-y-4">
            <div className="flex items-center justify-between border-b border-[#2E2E2E] pb-4">
              <div className="flex items-center gap-2">
                <div
                  className={`w-7 h-7 rounded-lg flex items-center justify-center border ${
                    isNominal
                      ? "bg-[#4E8569]/20 border-[#4E8569]/40 text-[#78AC91]"
                      : isAbstained
                      ? "bg-[#D8453A]/20 border-[#D8453A]/40 text-[#E56B62]"
                      : "bg-[#6B9BB0]/20 border-[#6B9BB0]/40 text-[#6B9BB0]"
                  }`}
                >
                  {isNominal ? (
                    <ShieldCheck className="w-4 h-4 text-[#4E8569]" />
                  ) : isAbstained ? (
                    <AlertTriangle className="w-4 h-4 text-[#D8453A]" />
                  ) : (
                    <Zap className="w-4 h-4 text-[#6B9BB0]" />
                  )}
                </div>
                <div>
                  <h3 className="font-mono text-xs font-bold text-[#F4EEE0] uppercase tracking-wider">
                    {isNominal
                      ? "System Telemetry Status"
                      : isAbstained
                      ? "Audit Abstention Status"
                      : "Governed Action Directive"}
                  </h3>
                  <span className="text-[10px] font-mono text-[#9E9788]">
                    Persona: <strong className="text-[#D1C9B8] capitalize">{persona}</strong> · Stage E{currentStageNum}
                  </span>
                </div>
              </div>

              <button
                onClick={onClose}
                className="p-1.5 rounded-lg text-[#9E9788] hover:text-[#F4EEE0] hover:bg-[#252525] transition-colors cursor-pointer"
                title="Close Drawer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Governed Directive Title */}
            <div className="space-y-1">
              <span className="text-[10px] font-mono uppercase text-[#9E9788] tracking-wider block">
                {currentStageNum <= 2
                  ? "SIGNAL RECOGNITION"
                  : currentStageNum <= 4
                  ? "GROUNDED ASSESSMENT"
                  : currentStageNum <= 6
                  ? "SYSTEM BELIEF & AUDIT"
                  : currentStageNum === 7
                  ? "GOVERNED ACTION DIRECTIVE"
                  : currentStageNum === 8
                  ? "PROJECTED RECOVERY IMPACT"
                  : "INSTITUTIONAL MEMORY"}
              </span>
              <h2 className="text-base font-bold font-sans text-[#F4EEE0] leading-snug">
                {isNominal
                  ? "All Telemetry Within Normal Baseline"
                  : isAbstained
                  ? "Autonomous Abstention Triggered"
                  : result.decision?.recommended_action
                  ? result.decision.recommended_action
                  : "Mitigate Primary Gateway Latency"}
              </h2>
            </div>

            {/* Circular SVG Audit Score Ring */}
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
                  stroke={
                    isNominal
                      ? "#4E8569"
                      : isAbstained
                      ? "#D8453A"
                      : auditScore >= 70
                      ? "#4E8569"
                      : "#A88232"
                  }
                  strokeDasharray={circumference}
                  strokeDashoffset={strokeDashoffset}
                  strokeLinecap="round"
                  strokeWidth="3"
                  className="transition-all duration-700 ease-out"
                />
              </svg>
              <div className="text-center z-10 flex flex-col items-center">
                <span className="text-3xl font-bold font-mono text-[#F4EEE0] leading-none block mb-1 tabular-nums">
                  {isNominal ? "100%" : isAbstained ? "ABSTAIN" : `${auditScore}%`}
                </span>
                <span
                  className={`text-[9px] font-mono font-bold uppercase tracking-wider ${
                    isNominal
                      ? "text-[#78AC91]"
                      : isAbstained
                      ? "text-[#E56B62]"
                      : auditScore >= 70
                      ? "text-[#78AC91]"
                      : "text-[#DEC06A]"
                  }`}
                >
                  {getVerdictLabel()}
                </span>
              </div>
            </div>
          </div>

          {/* Middle: Stage-Specific Intelligence Insights */}
          <div className="space-y-4 text-xs font-mono">
            {/* Anomaly Severity Card */}
            <div className="p-3.5 rounded-xl bg-[#222222] border border-[#333333] space-y-2">
              <div className="text-[#9E9788] uppercase text-[10px]">
                {isNominal ? "Telemetry Stability" : "Anomaly Significance"}
              </div>
              <div
                className={`text-sm font-bold ${
                  isNominal ? "text-[#78AC91]" : "text-[#D8453A]"
                }`}
              >
                {isNominal
                  ? "0.0% variance from baseline"
                  : result.signals?.[0]?.delta_pct
                  ? `${result.signals[0].delta_pct.toFixed(1)}% drop from baseline`
                  : "-14.2% drop"}
              </div>
              <div className="text-[#9E9788] text-[11px]">
                {isNominal ? (
                  <span>Corridor bounds: <strong className="text-[#78AC91]">Within calibrated ±3.0σ</strong></span>
                ) : (
                  <span>
                    Statistical severity:{" "}
                    <span className="text-[#F4EEE0] font-bold">
                      {result.signals?.[0]?.z_score
                        ? `${result.signals[0].z_score.toFixed(2)}σ`
                        : "-3.85σ"}
                    </span>
                  </span>
                )}
              </div>
            </div>

            {/* Evaluated Root Cause & Narrative */}
            <div className="p-3.5 rounded-xl bg-[#222222] border border-[#333333] space-y-2">
              <div className="text-[#9E9788] uppercase text-[10px] flex items-center justify-between">
                <span>
                  {isNominal
                    ? "Telemetry Assessment"
                    : isAbstained
                    ? "Abstention Diagnosis"
                    : "Evaluated Causal Rationale"}
                </span>
                {isAbstained && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#D8453A]/20 text-[#E56B62] border border-[#D8453A]/30 font-mono font-bold">
                    {story.guardName}
                  </span>
                )}
                {isNominal && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#4E8569]/20 text-[#78AC91] border border-[#4E8569]/30 font-mono font-bold">
                    HEALTHY
                  </span>
                )}
              </div>
              <p className="text-[#D1C9B8] font-sans text-xs leading-relaxed">
                {result.decision?.persona_narrative && !isAbstained && !isNominal
                  ? cleanLLMTags(result.decision.persona_narrative)
                  : story.story}
              </p>
              {story.operatorAction && (
                <div
                  className={`text-[11px] font-mono border-t border-white/[0.06] pt-1.5 leading-snug ${
                    isNominal
                      ? "text-[#78AC91]"
                      : isAbstained
                      ? "text-[#E56B62]"
                      : "text-[#6B9BB0]"
                  }`}
                >
                  <strong className="text-[#F4EEE0]">Directive:</strong> {story.operatorAction}
                </div>
              )}
            </div>

            {/* Verification Metric */}
            {result.decision?.verification_metric && !isNominal && (
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
            {result.outcome && result.outcome.projected_recovery_pct !== undefined && !isNominal && (
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

          {/* Bottom: Governed Action Dispatch Trigger Button */}
          <div className="pt-4 border-t border-[#2E2E2E]">
            <button
              onClick={() => {
                if (onExecuteAction && !isNominal) onExecuteAction()
                onClose()
              }}
              className={`w-full py-3.5 px-4 rounded-xl text-xs font-mono font-bold transition-all flex items-center justify-center gap-2 cursor-pointer shadow-lg ${
                isNominal
                  ? "bg-[#4E8569]/20 hover:bg-[#4E8569]/30 text-[#78AC91] border border-[#4E8569]/40"
                  : isAbstained
                  ? "bg-[#D8453A]/20 hover:bg-[#D8453A]/30 text-[#E56B62] border border-[#D8453A]/40"
                  : "bg-[#6B9BB0]/20 hover:bg-[#6B9BB0]/35 text-[#F4EEE0] border border-[#6B9BB0]/40"
              }`}
            >
              {isNominal ? (
                <ShieldCheck className="w-4 h-4 text-[#4E8569]" />
              ) : (
                <span
                  className={`w-2 h-2 rounded-full ${
                    isAbstained ? "bg-[#D8453A]" : "bg-[#6B9BB0]"
                  }`}
                />
              )}
              <span>
                {isNominal
                  ? "SYSTEM NOMINAL · NO ACTION REQUIRED"
                  : isAbstained
                  ? "REVIEW ABSTENTION REASON"
                  : "DISPATCH GOVERNED ACTION"}
              </span>
            </button>
          </div>
        </div>
      </aside>
    </div>
  )
}
