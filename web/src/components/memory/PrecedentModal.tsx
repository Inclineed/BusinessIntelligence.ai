import React from "react"
import { PrecedentItem } from "../../types/investigation"
import { History, X, CheckCircle2, ShieldCheck, ArrowRight } from "lucide-react"

interface PrecedentModalProps {
  precedent: PrecedentItem
  onClose: () => void
}

export const PrecedentModal: React.FC<PrecedentModalProps> = ({ precedent, onClose }) => {
  const relevancePct = Math.round((precedent.relevance ?? precedent.retrieval_score ?? 0.85) * 100)

  return (
    <div
      className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg bg-[#181818] border border-[#333333] rounded-2xl p-6 shadow-2xl space-y-5"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#2E2E2E] pb-3">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#6B9BB0]/15 border border-[#6B9BB0]/30 flex items-center justify-center">
              <History className="w-4 h-4 text-[#6B9BB0]" />
            </div>
            <div>
              <div className="text-sm font-bold font-mono text-[#F4EEE0] flex items-center gap-2">
                <span>{precedent.scenario_id}</span>
                {precedent.human_validated && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#4E8569]/20 text-[#78AC91] font-mono flex items-center gap-1 border border-[#4E8569]/30">
                    <CheckCircle2 className="w-3 h-3 text-[#4E8569]" />
                    VALIDATED (+0.10 BOOST)
                  </span>
                )}
              </div>
              <div className="text-xs text-[#9E9788] font-mono">
                Cosine Match Relevance: <span className="text-[#6B9BB0] font-bold">{relevancePct}%</span>
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg bg-white/5 hover:bg-white/10 text-[#9E9788] hover:text-[#F4EEE0] transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Narrative & Winning Hypothesis */}
        <div className="space-y-3 font-sans">
          <div className="p-3.5 rounded-xl bg-[#222222] border border-[#333333] space-y-1">
            <div className="text-[10px] font-mono uppercase font-bold text-[#9E9788]">Precedent Incident Summary</div>
            <p className="text-xs text-[#D1C9B8] leading-relaxed">
              {precedent.summary || "Historical incident pattern stored in vector memory."}
            </p>
          </div>

          {precedent.winning_hypothesis && (
            <div className="p-3.5 rounded-xl bg-[#222222] border border-[#333333] space-y-1">
              <div className="text-[10px] font-mono uppercase font-bold text-[#6B9BB0]">Historical Resolution</div>
              <p className="text-xs text-[#D1C9B8] leading-relaxed">
                {precedent.winning_hypothesis}
              </p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="pt-2 border-t border-[#2E2E2E] flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-[#6B9BB0]/20 hover:bg-[#6B9BB0]/35 text-[#F4EEE0] font-mono text-xs font-bold transition-all cursor-pointer border border-[#6B9BB0]/40"
          >
            Close Inspector
          </button>
        </div>
      </div>
    </div>
  )
}
