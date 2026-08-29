import React, { useState } from "react"
import { InvestigationResult, FeedbackVerdict, PersonaType } from "../../types/investigation"
import { submitStructuredFeedback } from "../../lib/api"
import { 
  ThumbsUp, 
  ThumbsDown, 
  HelpCircle, 
  AlertCircle, 
  Send, 
  CheckCircle2, 
  History,
  ChevronUp,
  ChevronDown,
  Sparkles
} from "lucide-react"
import { FeedbackHistoryDrawer } from "./FeedbackHistoryDrawer"

interface FeedbackReviewBarProps {
  result: InvestigationResult
  persona: PersonaType
}

export const FeedbackReviewBar: React.FC<FeedbackReviewBarProps> = ({ result, persona }) => {
  const [verdict, setVerdict] = useState<FeedbackVerdict>("CORRECT")
  const [notes, setNotes] = useState("")
  const [correctedHypothesis, setCorrectedHypothesis] = useState("")
  const [correctedConfidence, setCorrectedConfidence] = useState("")
  const [correctedAction, setCorrectedAction] = useState("")
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submissionResult, setSubmissionResult] = useState<{
    success: boolean
    validatedPrecedent?: boolean
    feedbackId?: number
    error?: string
  } | null>(null)
  const [showHistoryDrawer, setShowHistoryDrawer] = useState(false)

  const handleSubmit = async () => {
    if (!result.investigation_id && !result.scenario_id) return

    setIsSubmitting(true)
    setSubmissionResult(null)

    try {
      const res = await submitStructuredFeedback({
        investigation_id: result.investigation_id || `${result.scenario_id}_${persona}_latest`,
        scenario_id: result.scenario_id,
        persona: persona,
        verdict: verdict,
        analyst_notes: notes.trim() || undefined,
        corrected_hypothesis_id: correctedHypothesis || undefined,
        corrected_audit_verdict: correctedConfidence || undefined,
        corrected_action: correctedAction || undefined,
        evidence_grounding_correct: true,
      })

      if (res.success) {
        setSubmissionResult({
          success: true,
          validatedPrecedent: res.validated_precedent,
          feedbackId: res.feedback_id,
        })
      } else {
        setSubmissionResult({
          success: false,
          error: res.error || "Failed to persist feedback",
        })
      }
    } catch (err: any) {
      setSubmissionResult({
        success: false,
        error: err.message || "Network error submitting feedback",
      })
    } finally {
      setIsSubmitting(false)
    }
  }

  const isAnalyst = persona === "analyst"

  return (
    <>
      <div className="rounded-2xl border border-[#2E2E2E] bg-[#1C1C1C] p-4 shadow-2xl space-y-3">
        {/* Header line: Title & History Trigger */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-[#6B9BB0]" />
            <span className="text-xs font-mono font-bold text-[#F4EEE0] uppercase tracking-wider">
              Analyst Structured Review &amp; Precedent Validation
            </span>
          </div>

          <button
            onClick={() => setShowHistoryDrawer(true)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#222222] hover:bg-[#2A2A2A] border border-[#333333] text-[11px] font-mono text-[#D1C9B8] transition-colors cursor-pointer"
          >
            <History className="w-3 h-3 text-[#6B9BB0]" />
            <span>Audit History</span>
          </button>
        </div>

        {/* Verdict Selector Buttons */}
        <div className="flex flex-wrap items-center gap-2">
          {[
            { id: "CORRECT", label: "Confirmed Correct", icon: ThumbsUp },
            { id: "INCORRECT", label: "Incorrect Explanation", icon: ThumbsDown },
            { id: "PARTIALLY_CORRECT", label: "Partially Correct", icon: AlertCircle },
            { id: "UNSURE", label: "Unsure / Inconclusive", icon: HelpCircle },
          ].map((item) => {
            const isSelected = verdict === item.id
            const Icon = item.icon
            return (
              <button
                key={item.id}
                onClick={() => setVerdict(item.id as FeedbackVerdict)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono transition-all cursor-pointer ${
                  isSelected
                    ? "bg-[#6B9BB0]/25 border border-[#6B9BB0]/50 text-[#F4EEE0] font-bold shadow-sm"
                    : "bg-[#222222] hover:bg-[#2A2A2A] border border-[#333333] text-[#9E9788]"
                }`}
              >
                <Icon className={`w-3.5 h-3.5 ${isSelected ? 'text-[#6B9BB0]' : 'text-[#9E9788]'}`} />
                <span>{item.label}</span>
              </button>
            )
          })}
        </div>

        {/* Notes & Submission Bar */}
        <div className="flex flex-col sm:flex-row items-center gap-2">
          <input
            type="text"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Add analyst context or investigation rationale (optional)..."
            className="w-full bg-[#181818] border border-[#2E2E2E] px-3 py-2 rounded-lg text-xs text-[#F4EEE0] placeholder-[#666666] focus:outline-none focus:border-[#6B9BB0] font-sans"
          />

          <div className="flex items-center gap-2 w-full sm:w-auto shrink-0 justify-end">
            <button
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="p-2 rounded-lg bg-[#222222] hover:bg-[#2A2A2A] border border-[#333333] text-[#9E9788] hover:text-[#F4EEE0] transition-colors cursor-pointer"
              title="Toggle corrections panel"
            >
              {showAdvanced ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>

            <button
              onClick={handleSubmit}
              disabled={isSubmitting}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[#6B9BB0]/25 hover:bg-[#6B9BB0]/40 text-[#F4EEE0] border border-[#6B9BB0]/50 text-xs font-mono font-bold transition-all cursor-pointer disabled:opacity-50"
            >
              <Send className="w-3.5 h-3.5" />
              <span>{isSubmitting ? "Submitting..." : "Submit Review"}</span>
            </button>
          </div>
        </div>

        {/* Advanced Correction Fields */}
        {showAdvanced && (
          <div className="p-3 rounded-xl bg-[#141414] border border-[#2E2E2E] grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-xs font-mono animate-fade-in">
            <div className="space-y-1">
              <label className="text-[10px] text-[#9E9788]">Corrected Hypothesis ID</label>
              <input
                type="text"
                value={correctedHypothesis}
                onChange={(e) => setCorrectedHypothesis(e.target.value)}
                placeholder="e.g. H2"
                className="w-full bg-[#1C1C1C] border border-[#2E2E2E] px-2 py-1.5 rounded text-xs text-[#F4EEE0] focus:outline-none"
              />
            </div>

            <div className="space-y-1">
              <label className="text-[10px] text-[#9E9788]">Corrected Confidence</label>
              <select
                value={correctedConfidence}
                onChange={(e) => setCorrectedConfidence(e.target.value)}
                className="w-full bg-[#1C1C1C] border border-[#2E2E2E] px-2 py-1.5 rounded text-xs text-[#F4EEE0] focus:outline-none"
              >
                <option value="">No change</option>
                <option value="VERIFIED">HIGH</option>
                <option value="MARGINAL">MEDIUM</option>
                <option value="REJECTED">LOW</option>
                <option value="ABSTAIN">ABSTAIN</option>
              </select>
            </div>

            <div className="space-y-1">
              <label className="text-[10px] text-[#9E9788]">Corrected Action Directive</label>
              <input
                type="text"
                value={correctedAction}
                onChange={(e) => setCorrectedAction(e.target.value)}
                placeholder="e.g. Roll back v4.2"
                className="w-full bg-[#1C1C1C] border border-[#2E2E2E] px-2 py-1.5 rounded text-xs text-[#F4EEE0] focus:outline-none"
              />
            </div>
          </div>
        )}

        {/* Confirmation or Error Banner */}
        {submissionResult && (
          <div
            className={`p-3 rounded-xl text-xs font-mono flex items-center justify-between gap-2 animate-fade-in ${
              submissionResult.success
                ? "bg-[#4E8569]/20 border border-[#4E8569]/40 text-[#78AC91]"
                : "bg-[#D8453A]/20 border border-[#D8453A]/40 text-[#E56B62]"
            }`}
          >
            <div className="flex items-center gap-2">
              {submissionResult.success ? (
                <CheckCircle2 className="w-4 h-4 text-[#4E8569]" />
              ) : (
                <AlertCircle className="w-4 h-4 text-[#D8453A]" />
              )}
              <span>
                {submissionResult.success
                  ? submissionResult.validatedPrecedent && isAnalyst
                    ? `Feedback recorded (#${submissionResult.feedbackId}). Precedent validated in vector memory (+0.10 boost applied)!`
                    : `Feedback recorded (#${submissionResult.feedbackId}) for scenario audit.`
                  : submissionResult.error}
              </span>
            </div>
            <button
              onClick={() => setSubmissionResult(null)}
              className="text-[#9E9788] hover:text-[#F4EEE0] text-[11px] cursor-pointer"
            >
              Dismiss
            </button>
          </div>
        )}
      </div>

      {/* History Drawer */}
      <FeedbackHistoryDrawer
        scenarioId={result.scenario_id}
        isOpen={showHistoryDrawer}
        onClose={() => setShowHistoryDrawer(false)}
      />
    </>
  )
}
