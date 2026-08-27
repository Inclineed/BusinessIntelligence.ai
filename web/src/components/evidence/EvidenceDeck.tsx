import React, { useState } from "react"
import { EvidenceItem } from "../../types/investigation"
import { FileText, Database, ShieldCheck, Eye, Layers } from "lucide-react"
import { EvidenceInspectionModal } from "./EvidenceInspectionModal"

interface EvidenceDeckProps {
  evidence: EvidenceItem[]
}

export const EvidenceDeck: React.FC<EvidenceDeckProps> = ({ evidence }) => {
  const [inspectedEvidence, setInspectedEvidence] = useState<EvidenceItem | null>(null)

  if (!evidence || evidence.length === 0) {
    return (
      <div className="glass-panel p-6 rounded-xl border border-white/[0.08] text-center">
        <Database className="w-8 h-8 text-neutral-500 mx-auto mb-2" />
        <div className="text-sm font-medium text-neutral-300">No Evidence Assembled</div>
        <div className="text-xs text-neutral-400">Zero evidence records matched the active persona entitlement scope.</div>
      </div>
    )
  }

  return (
    <>
      <div className="glass-panel p-4 rounded-xl border border-white/[0.08]">
        {/* Header */}
        <div className="flex items-center justify-between gap-2 mb-3">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-sky-500/10 border border-sky-500/30 flex items-center justify-center">
              <Database className="w-3.5 h-3.5 text-sky-400" />
            </div>
            <div>
              <div className="text-xs font-mono font-bold text-neutral-200 uppercase tracking-wider">
                [E4] Grounded Evidence Deck & SLA Freshness
              </div>
              <div className="text-[11px] font-mono text-neutral-400">
                {evidence.length} Assembled Records (Structured SQL + Vector Retrieval)
              </div>
            </div>
          </div>
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-black/40 text-neutral-400 border border-white/[0.06]">
            [SQL / RETRIEVAL]
          </span>
        </div>

        {/* Evidence Card Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
          {evidence.map((item) => {
            const isSQL = item.method === "SQL"
            const reliabilityPct = Math.round((item.reliability_weight ?? 1.0) * 100)

            return (
              <div
                key={item.evidence_id}
                onClick={() => setInspectedEvidence(item)}
                className="p-3 rounded-lg bg-surface hover:bg-surface-hover border border-border transition-all cursor-pointer group flex flex-col justify-between gap-2"
              >
                <div>
                  {/* Top line: ID, Source, Reliability */}
                  <div className="flex items-center justify-between gap-2 mb-1.5 font-mono text-xs">
                    <div className="flex items-center gap-1.5">
                      <span className="font-bold text-neutral-200 group-hover:text-sky-300 transition-colors">
                        {item.evidence_id}
                      </span>
                      <span className="text-[10px] px-1 py-0.2 rounded bg-black/40 text-neutral-400">
                        {item.source_id}
                      </span>
                    </div>

                    <div className="flex items-center gap-1">
                      <span className="text-[10px] text-neutral-400">Rel:</span>
                      <span className="font-bold text-emerald-400 text-xs tabular-nums">
                        {reliabilityPct}%
                      </span>
                    </div>
                  </div>

                  {/* Summary Text */}
                  <p className="text-xs text-neutral-300 line-clamp-2 font-sans leading-relaxed">
                    {item.summary}
                  </p>
                </div>

                {/* Bottom line: Method tag & inspect prompt */}
                <div className="flex items-center justify-between text-[10px] font-mono text-neutral-400 border-t border-white/[0.04] pt-1.5">
                  <span>[{item.method}]</span>
                  <span className="flex items-center gap-1 group-hover:text-neutral-200 transition-colors">
                    <Eye className="w-3 h-3 text-neutral-400 group-hover:text-white" />
                    <span>Inspect</span>
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Glass Inspection Modal */}
      {inspectedEvidence && (
        <EvidenceInspectionModal
          evidence={inspectedEvidence}
          onClose={() => setInspectedEvidence(null)}
        />
      )}
    </>
  )
}
