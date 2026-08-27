import React from "react"
import { EvidenceItem } from "../../types/investigation"
import { X, FileText, Database, ShieldCheck, Clock, ExternalLink, ArrowDown } from "lucide-react"

interface EvidenceInspectionModalProps {
  evidence: EvidenceItem | null
  onClose: () => void
}

export const EvidenceInspectionModal: React.FC<EvidenceInspectionModalProps> = ({ evidence, onClose }) => {
  if (!evidence) return null

  const methodColors: Record<string, string> = {
    SQL: "text-sky-400 border-sky-400/30 bg-sky-400/10",
    STATISTICS: "text-emerald-400 border-emerald-400/30 bg-emerald-400/10",
    BUSINESS_RULE: "text-amber-400 border-amber-400/30 bg-amber-400/10",
    VECTOR_RETRIEVAL: "text-purple-400 border-purple-400/30 bg-purple-400/10",
    LLM: "text-orange-400 border-orange-400/30 bg-orange-400/10",
    HYBRID: "text-pink-400 border-pink-400/30 bg-pink-400/10",
  }
  const methodKey = evidence.method || "SQL"
  const badgeStyle = methodColors[methodKey] || "text-[#9E9788] border-[#333333] bg-[#1A1A1A]"

  const getMethodActionText = (method: string) => {
    if (method === "SQL") return "SQL Normalization"
    if (method === "LLM") return "LLM Extraction"
    if (method === "VECTOR_RETRIEVAL") return "Vector Retrieval & Ranking"
    if (method === "STATISTICS") return "Statistical Aggregation"
    if (method === "BUSINESS_RULE") return "Rule Engine Evaluation"
    if (method === "HYBRID") return "Hybrid Multi-Step Extraction"
    return "Extraction & Normalization"
  }

  const displayId = evidence.id || evidence.evidence_id || "EV_RECORD"
  const displaySource = evidence.source_id || evidence.source_name || "unknown"
  const displayObservation = evidence.observation || evidence.summary || evidence.raw_ref || "No observation recorded"

  const confVal = evidence.confidence ?? evidence.relevance
  const relVal = evidence.source_reliability ?? evidence.reliability_weight
  const revVal = evidence.relevance ?? evidence.confidence

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in" onClick={onClose}>
      <div
        className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto bg-[#181818] rounded-2xl border border-[#2E2E2E] p-6 shadow-2xl space-y-6 scrollbar-hide"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#2E2E2E] pb-3">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#6B9BB0]/15 border border-[#6B9BB0]/30 flex items-center justify-center">
              {methodKey === "SQL" || methodKey === "STATISTICS" ? (
                <Database className="w-4 h-4 text-[#6B9BB0]" />
              ) : (
                <FileText className="w-4 h-4 text-[#6B9BB0]" />
              )}
            </div>
            <div>
              <div className="text-sm font-bold text-[#F4EEE0] font-mono flex items-center gap-2">
                <span>{displayId}</span>
              </div>
              <div className="text-xs text-[#9E9788] font-mono">
                Source: <span className="text-[#D1C9B8] capitalize">{displaySource.replace(/_/g, " ")}</span>
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

        {/* Metadata Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-xs font-mono">
          <div className="p-3 rounded-xl bg-[#222222] border border-[#333333] space-y-1 sm:col-span-2">
            <div className="text-[#9E9788] text-[10px] uppercase">Timing &amp; Freshness</div>
            <div className="text-sm font-bold text-[#F4EEE0] truncate">
              {evidence.timestamp ? (typeof evidence.timestamp === "string" ? evidence.timestamp.replace("T", " ").slice(0, 19) : String(evidence.timestamp)) : "—"}{" "}
              <span className="text-[#6B9BB0] text-xs font-normal ml-1">
                ({evidence.freshness_minutes != null ? `${Math.round(evidence.freshness_minutes)}m ago` : "4m ago"})
              </span>
            </div>
          </div>
          <div className="p-3 rounded-xl bg-[#222222] border border-[#333333] space-y-1">
            <div className="text-[#9E9788] text-[10px] uppercase">Confidence</div>
            <div className="text-sm font-bold text-[#D1C9B8] tabular-nums">
              {confVal != null ? Number(confVal).toFixed(2) : "—"}
            </div>
          </div>
          <div className="p-3 rounded-xl bg-[#222222] border border-[#333333] space-y-1">
            <div className="text-[#9E9788] text-[10px] uppercase">Reliability</div>
            <div className="text-sm font-bold text-[#4E8569] tabular-nums">
              {relVal != null ? Number(relVal).toFixed(2) : "—"}
            </div>
          </div>
          <div className="p-3 rounded-xl bg-[#222222] border border-[#333333] space-y-1">
            <div className="text-[#9E9788] text-[10px] uppercase">Relevance</div>
            <div className="text-sm font-bold text-[#6B9BB0] tabular-nums">
              {revVal != null ? Number(revVal).toFixed(2) : "—"}
            </div>
          </div>
        </div>

        {/* Lineage Flow (Source -> Method -> Canonical) */}
        <div className="space-y-3">
          <div className="text-[11px] font-mono uppercase tracking-wider text-[#9E9788] flex items-center gap-2">
            <ShieldCheck className="w-3.5 h-3.5 text-[#4E8569]" />
            Method Provenance Lineage
          </div>
          
          <div className="relative pl-6 space-y-4 before:absolute before:inset-y-0 before:left-2.5 before:w-px before:bg-[#2E2E2E]">
            
            {/* Step 1: Source */}
            <div className="relative">
              <div className="absolute -left-6 top-1.5 w-2 h-2 rounded-full bg-[#333333] border-2 border-[#181818]" />
              <div className="space-y-1.5">
                <div className="text-[10px] font-mono uppercase text-[#9E9788]">
                  Source Record
                </div>
                <div className="p-3 rounded-xl bg-[#141414] border border-[#2E2E2E] text-xs font-mono text-[#9E9788] break-all">
                  {evidence.raw_ref || "No raw reference available"}
                </div>
              </div>
            </div>

            {/* Step 2: Method */}
            <div className="relative">
              <div className="absolute -left-[27px] top-1/2 -translate-y-1/2 bg-[#181818] py-1">
                <ArrowDown className="w-3 h-3 text-[#666666]" />
              </div>
              <div className="flex items-center gap-3 py-1">
                <span className={`font-mono text-[10px] px-2 py-0.5 rounded border ${badgeStyle}`}>
                  [{methodKey}]
                </span>
                <span className="text-xs font-mono text-[#D1C9B8]">
                  {getMethodActionText(methodKey)}
                </span>
              </div>
            </div>

            {/* Step 3: Canonical */}
            <div className="relative">
              <div className="absolute -left-[27px] top-1/2 -translate-y-1/2 bg-[#181818] py-1">
                <ArrowDown className="w-3 h-3 text-[#666666]" />
              </div>
              <div className="space-y-1.5">
                <div className="text-[10px] font-mono uppercase text-[#4E8569]">
                  Canonical Evidence
                </div>
                <div className="p-3.5 rounded-xl bg-[#1C1C1C] border border-[#4E8569]/30 text-sm text-[#F4EEE0] leading-relaxed font-sans shadow-[0_0_15px_rgba(78,133,105,0.05)]">
                  {displayObservation}
                </div>
              </div>
            </div>

          </div>
        </div>

        {/* Action button */}
        <div className="flex justify-end pt-4 border-t border-[#2E2E2E]">
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
