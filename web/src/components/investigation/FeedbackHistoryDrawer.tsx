import React, { useEffect, useState } from "react"
import { FeedbackRecord } from "../../types/investigation"
import { getFeedbackForScenario } from "../../lib/api"
import { X, History, CheckCircle2, XCircle, AlertCircle, HelpCircle, MessageSquare } from "lucide-react"

interface FeedbackHistoryDrawerProps {
  scenarioId: string
  isOpen: boolean
  onClose: () => void
}

export const FeedbackHistoryDrawer: React.FC<FeedbackHistoryDrawerProps> = ({
  scenarioId,
  isOpen,
  onClose,
}) => {
  const [records, setRecords] = useState<FeedbackRecord[]>([])
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    if (isOpen && scenarioId) {
      setIsLoading(true)
      getFeedbackForScenario(scenarioId)
        .then((res) => {
          setRecords(res.records || [])
        })
        .catch((err) => {
          console.error("Failed to load feedback history:", err)
        })
        .finally(() => {
          setIsLoading(false)
        })
    }
  }, [isOpen, scenarioId])

  if (!isOpen) return null

  const getVerdictIcon = (verdict: string) => {
    switch (verdict) {
      case "CORRECT":
        return <CheckCircle2 className="w-4 h-4 text-[#4E8569]" />
      case "INCORRECT":
        return <XCircle className="w-4 h-4 text-[#D8453A]" />
      case "PARTIALLY_CORRECT":
        return <AlertCircle className="w-4 h-4 text-[#6B9BB0]" />
      default:
        return <HelpCircle className="w-4 h-4 text-[#9E9788]" />
    }
  }

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-black/60 backdrop-blur-sm animate-fade-in flex justify-end">
      <div className="w-full max-w-md h-full bg-[#181818] border-l border-[#2E2E2E] p-5 shadow-2xl flex flex-col justify-between space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#2E2E2E] pb-3">
          <div className="flex items-center gap-2">
            <History className="w-4 h-4 text-[#6B9BB0]" />
            <span className="text-sm font-bold text-[#F4EEE0] font-mono">
              Feedback Audit History: {scenarioId}
            </span>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded-lg bg-white/5 hover:bg-white/10 border border-[#333333] flex items-center justify-center text-[#9E9788] hover:text-[#F4EEE0] transition-colors cursor-pointer"
            aria-label="Close feedback history drawer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content List */}
        <div className="flex-1 overflow-y-auto space-y-3 pr-1 custom-scrollbar">
          {isLoading ? (
            <div className="p-8 text-center text-xs font-mono text-[#9E9788]">
              Loading scenario audit trail...
            </div>
          ) : records.length === 0 ? (
            <div className="p-8 text-center text-xs font-mono text-[#9E9788]">
              Zero feedback reviews recorded for {scenarioId}.
            </div>
          ) : (
            records.map((rec) => (
              <div
                key={rec.feedback_id}
                className="p-3.5 rounded-xl bg-[#222222] border border-[#333333] space-y-2 text-xs font-mono"
              >
                {/* Top line: Verdict & Persona */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 font-bold">
                    {getVerdictIcon(rec.verdict)}
                    <span className="text-[#F4EEE0]">{rec.verdict}</span>
                  </div>
                  <span className="text-[10px] text-[#9E9788] capitalize px-1.5 py-0.5 rounded bg-[#181818] border border-[#2E2E2E]">
                    {rec.persona}
                  </span>
                </div>

                {/* Analyst Notes */}
                {rec.analyst_notes && (
                  <p className="text-[#D1C9B8] font-sans leading-relaxed text-xs">
                    "{rec.analyst_notes}"
                  </p>
                )}

                {/* Precedent Validation Flag */}
                {rec.validated_precedent && (
                  <div className="text-[10px] text-[#4E8569] flex items-center gap-1 font-bold">
                    <CheckCircle2 className="w-3 h-3" />
                    Validated Vector Precedent #{rec.validation_precedent_id || rec.scenario_id}
                  </div>
                )}

                {/* Timestamp */}
                {rec.received_at && (
                  <div className="text-[10px] text-[#666666]">
                    {new Date(rec.received_at).toLocaleString()}
                  </div>
                )}
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="pt-2 border-t border-[#2E2E2E] flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-[#222222] hover:bg-[#2A2A2A] border border-[#333333] text-[#F4EEE0] font-mono text-xs transition-colors cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
