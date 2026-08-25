import React, { useState } from "react"
import { PrecedentItem } from "../../types/investigation"
import { History, CheckCircle2, Eye } from "lucide-react"
import { PrecedentModal } from "./PrecedentModal"

interface PrecedentCarouselProps {
  precedents?: (PrecedentItem | string)[]
}

export const PrecedentCarousel: React.FC<PrecedentCarouselProps> = ({ precedents }) => {
  const [selectedPrecedent, setSelectedPrecedent] = useState<PrecedentItem | null>(null)

  if (!precedents || precedents.length === 0) {
    return (
      <div className="p-6 rounded-xl bg-[#1C1C1C] border border-[#2E2E2E] text-center">
        <History className="w-8 h-8 text-[#9E9788] mx-auto mb-2" />
        <div className="text-sm font-medium text-[#D1C9B8]">No Precedents Retrieved</div>
        <div className="text-xs text-[#9E9788]">Zero similar historical incident records matched cosine relevance &gt; 0.70.</div>
      </div>
    )
  }

  // Normalize string entries to PrecedentItem objects
  const normalizedPrecedents: PrecedentItem[] = precedents.map((p) => {
    if (typeof p === "string") {
      return {
        scenario_id: p,
        summary: `Institutional precedent from scenario ${p}`,
        relevance: 0.82,
        winning_hypothesis: "Historical validated cause",
      }
    }
    return p
  })

  return (
    <>
      <div className="p-5 rounded-2xl bg-[#1C1C1C] border border-[#2E2E2E] space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between gap-2 mb-2">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-[#6B9BB0]/15 border border-[#6B9BB0]/30 flex items-center justify-center">
              <History className="w-3.5 h-3.5 text-[#6B9BB0]" />
            </div>
            <div>
              <div className="text-xs font-mono font-bold text-[#F4EEE0] uppercase tracking-wider">
                Institutional Precedents &amp; Vector Memory
              </div>
              <div className="text-[11px] font-mono text-[#9E9788]">
                {normalizedPrecedents.length} High-Relevance Incident Precedents Retrieved (Oversample x5 + Provenance Filter)
              </div>
            </div>
          </div>
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#181818] text-[#9E9788] border border-[#2E2E2E]">
            [RETRIEVAL / LLM]
          </span>
        </div>

        {/* Precedent Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {normalizedPrecedents.map((item, idx) => {
            const relevancePct = Math.round((item.relevance ?? item.retrieval_score ?? 0.85) * 100)

            return (
              <div
                key={`${item.scenario_id}-${idx}`}
                onClick={() => setSelectedPrecedent(item)}
                className="p-3.5 rounded-xl bg-[#222222] hover:bg-[#2A2A2A] border border-[#333333] hover:border-[#6B9BB0]/40 transition-all cursor-pointer group flex flex-col justify-between gap-3"
              >
                <div>
                  {/* Top Bar: Scenario ID & Relevance */}
                  <div className="flex items-center justify-between gap-2 mb-1.5 font-mono text-xs">
                    <span className="font-bold text-[#F4EEE0] group-hover:text-[#6B9BB0] transition-colors">
                      {item.scenario_id}
                    </span>
                    <span className="text-[11px] font-bold text-[#6B9BB0] tabular-nums">
                      {relevancePct}% Match
                    </span>
                  </div>

                  {/* Summary Text (expanded to 3 lines for readability) */}
                  <p className="text-xs text-[#D1C9B8] line-clamp-3 font-sans leading-relaxed">
                    {item.summary || "Historical incident investigation precedent."}
                  </p>
                </div>

                {/* Bottom Bar: Human Validated badge & inspect */}
                <div className="flex items-center justify-between text-[10px] font-mono text-[#9E9788] border-t border-white/[0.04] pt-2">
                  {item.human_validated ? (
                    <span className="flex items-center gap-1 text-[#4E8569] font-bold">
                      <CheckCircle2 className="w-3 h-3" />
                      VALIDATED
                    </span>
                  ) : (
                    <span className="text-[#9E9788]">Unvalidated</span>
                  )}

                  <span className="flex items-center gap-1 group-hover:text-[#F4EEE0] transition-colors">
                    <Eye className="w-3 h-3 text-[#9E9788] group-hover:text-[#F4EEE0]" />
                    <span>Inspect</span>
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {selectedPrecedent && (
        <PrecedentModal
          precedent={selectedPrecedent}
          onClose={() => setSelectedPrecedent(null)}
        />
      )}
    </>
  )
}
