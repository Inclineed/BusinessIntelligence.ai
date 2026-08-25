import React from "react"
import { EvidenceItem } from "../../types/investigation"
import { X, FileText, Database, ShieldCheck, Clock, ExternalLink } from "lucide-react"

interface EvidenceInspectionModalProps {
  evidence: EvidenceItem | null
  onClose: () => void
}

export const EvidenceInspectionModal: React.FC<EvidenceInspectionModalProps> = ({ evidence, onClose }) => {
  if (!evidence) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in" onClick={onClose}>
      <div
        className="relative w-full max-w-2xl bg-[#181818] rounded-2xl border border-[#2E2E2E] p-6 shadow-2xl space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#2E2E2E] pb-3">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#6B9BB0]/15 border border-[#6B9BB0]/30 flex items-center justify-center">
              {evidence.method === "SQL" ? (
                <Database className="w-4 h-4 text-[#6B9BB0]" />
              ) : (
                <FileText className="w-4 h-4 text-[#6B9BB0]" />
              )}
            </div>
            <div>
              <div className="text-sm font-bold text-[#F4EEE0] font-mono flex items-center gap-2">
                <span>{evidence.evidence_id}</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#141414] text-[#9E9788] border border-[#2E2E2E]">
                  [{evidence.method}]
                </span>
              </div>
              <div className="text-xs text-[#9E9788] font-mono">
                Source: <span className="text-[#D1C9B8]">{evidence.source_id}</span>
              </div>
            </div>
          </div>

          <button
            onClick={onClose}
            className="w-7 h-7 rounded-lg bg-white/5 hover:bg-white/10 border border-[#333333] flex items-center justify-center text-[#9E9788] hover:text-[#F4EEE0] transition-colors cursor-pointer"
            aria-label="Close evidence modal"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Verbatim Summary */}
        <div className="space-y-1.5">
          <div className="text-[11px] font-mono uppercase tracking-wider text-[#9E9788]">
            Authoritative Summary &amp; Findings
          </div>
          <div className="p-3.5 rounded-xl bg-[#141414] border border-[#2E2E2E] text-xs text-[#D1C9B8] leading-relaxed font-sans">
            {evidence.summary}
          </div>
        </div>

        {/* Reliability & Metadata Attributes */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs font-mono">
          <div className="p-3 rounded-xl bg-[#222222] border border-[#333333] space-y-1">
            <div className="text-[#9E9788] text-[10px] uppercase">Reliability Weight</div>
            <div className="text-sm font-bold text-[#4E8569] tabular-nums">
              {(evidence.reliability_weight * 100).toFixed(0)}%
            </div>
          </div>

          <div className="p-3 rounded-xl bg-[#222222] border border-[#333333] space-y-1">
            <div className="text-[#9E9788] text-[10px] uppercase">Relevance Score</div>
            <div className="text-sm font-bold text-[#6B9BB0] tabular-nums">
              {(evidence.relevance * 100).toFixed(0)}%
            </div>
          </div>

          <div className="p-3 rounded-xl bg-[#222222] border border-[#333333] space-y-1 col-span-2 sm:col-span-1">
            <div className="text-[#9E9788] text-[10px] uppercase">Source Classification</div>
            <div className="text-xs font-bold text-[#F4EEE0] uppercase truncate">
              {evidence.kind || "STRUCTURED SQL"}
            </div>
          </div>
        </div>

        {/* Raw Reference / Table Lineage */}
        {evidence.raw_ref && (
          <div className="space-y-1.5">
            <div className="text-[11px] font-mono uppercase tracking-wider text-[#9E9788]">
              Raw Database / Vector Reference
            </div>
            <div className="p-2.5 rounded-xl bg-[#141414] border border-[#2E2E2E] text-xs font-mono text-[#9E9788] break-all">
              {evidence.raw_ref}
            </div>
          </div>
        )}

        {/* Action button */}
        <div className="flex justify-end pt-2 border-t border-[#2E2E2E]">
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-xl bg-[#222222] hover:bg-[#2A2A2A] border border-[#333333] text-[#F4EEE0] font-mono text-xs transition-colors cursor-pointer"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  )
}
