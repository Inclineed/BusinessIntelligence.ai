import React from "react"
import { X, Database, ShieldCheck, Clock, ExternalLink, FileText, CheckCircle2, AlertCircle } from "lucide-react"
import { EvidenceItem, HypothesisItem } from "../../types/investigation"
import { cn } from "../../lib/utils"

interface EvidenceDrawerProps {
  evidence: EvidenceItem | null
  isOpen: boolean
  onClose: () => void
  hypotheses: HypothesisItem[]
}

export const EvidenceDrawer: React.FC<EvidenceDrawerProps> = ({ evidence, isOpen, onClose, hypotheses }) => {
  if (!isOpen || !evidence) return null

  const isFresh = (evidence.reliability_weight ?? 1.0) >= 0.85
  const citingHyps = hypotheses.filter(
    (h) =>
      h.supporting_evidence_ids?.includes(evidence.evidence_id ?? "") ||
      h.contradictory_evidence_ids?.includes(evidence.evidence_id ?? "")
  )

  return (
    <div className="fixed inset-0 z-50 overflow-hidden flex justify-end">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/60 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      ></div>

      {/* Slide-over Panel */}
      <div className="relative w-full max-w-xl bg-surface-raised border-l border-hairline p-6 shadow-2xl flex flex-col justify-between overflow-y-auto z-10 animate-in slide-in-from-right duration-200">
        <div className="space-y-6">
          {/* Header */}
          <div className="flex items-center justify-between pb-4 border-b border-hairline">
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm font-bold text-semantic-neutral bg-semantic-neutral-bg border border-semantic-neutral-border px-2.5 py-1 rounded">
                ◈ {evidence.evidence_id}
              </span>
              <span className="text-xs font-mono text-muted-foreground uppercase">
                {evidence.method} ARTIFACT
              </span>
            </div>
            <button
              onClick={onClose}
              className="p-1.5 rounded-md hover:bg-surface-hover text-muted-foreground hover:text-white transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Core Metrics: Reliability & Relevance */}
          <div className="grid grid-cols-2 gap-4 p-4 rounded-lg bg-surface border border-hairline">
            <div>
              <div className="text-[10px] font-mono text-muted-foreground uppercase flex items-center gap-1 mb-1">
                <ShieldCheck className="w-3.5 h-3.5 text-semantic-positive" /> SOURCE RELIABILITY (SLA)
              </div>
              <div className="text-xl font-bold font-mono text-white">
                {(evidence.reliability_weight ?? 1.0).toFixed(3)}
              </div>
              <span className={cn("inline-block text-[10px] font-mono font-bold mt-1 px-1.5 py-0.5 rounded border", isFresh ? "text-semantic-positive bg-semantic-positive-bg border-semantic-positive-border" : "text-semantic-warning bg-semantic-warning-bg border-semantic-warning-border")}>
                {isFresh ? "FRESH (WITHIN SLA)" : "STALE / DOWN-WEIGHTED"}
              </span>
            </div>

            <div>
              <div className="text-[10px] font-mono text-muted-foreground uppercase flex items-center gap-1 mb-1">
                <Clock className="w-3.5 h-3.5 text-semantic-neutral" /> RELEVANCE TO SIGNAL
              </div>
              <div className="text-xl font-bold font-mono text-white">
                {(evidence.relevance ?? 1.0).toFixed(3)}
              </div>
              <span className="inline-block text-[10px] font-mono text-muted-foreground mt-1">
                Cosine Similarity Score
              </span>
            </div>
          </div>

          {/* Evidence Full Summary */}
          <div className="space-y-2">
            <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-muted-foreground">
              AUTHENTICATED EVIDENCE PAYLOAD
            </h3>
            <div className="p-4 rounded-lg bg-surface border border-hairline text-sm text-foreground leading-relaxed font-sans">
              {evidence.summary}
            </div>
          </div>

          {/* Source Provenance Ledger */}
          <div className="space-y-2">
            <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-muted-foreground">
              SOURCE PROVENANCE & ISOLATION
            </h3>
            <div className="p-3.5 rounded-lg bg-surface border border-hairline space-y-2 text-xs font-mono">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Source Identifier:</span>
                <span className="text-white font-semibold">{evidence.source_id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Retrieval Method:</span>
                <span className="text-semantic-neutral font-semibold">{evidence.method}</span>
              </div>
              {evidence.raw_ref && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Raw Reference / Table:</span>
                  <span className="text-foreground">{evidence.raw_ref}</span>
                </div>
              )}
            </div>
          </div>

          {/* Hypotheses utilizing this evidence */}
          <div className="space-y-2">
            <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-muted-foreground">
              HYPOTHESIS UTILIZATION & CITATIONS
            </h3>
            {citingHyps.length > 0 ? (
              <div className="space-y-2">
                {citingHyps.map((h) => {
                  const isSupport = h.supporting_evidence_ids?.includes(evidence.evidence_id ?? "")
                  return (
                    <div
                      key={h.hypothesis_id}
                      className="p-3 rounded-lg bg-surface border border-hairline flex items-center justify-between text-xs"
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-white bg-surface-raised px-2 py-0.5 rounded border border-hairline">
                          {h.hypothesis_id}
                        </span>
                        <span className="text-muted-foreground line-clamp-1">{h.statement}</span>
                      </div>
                      <span className={cn("text-[10px] font-mono font-bold px-2 py-0.5 rounded border", isSupport ? "text-semantic-positive bg-semantic-positive-bg border-semantic-positive-border" : "text-semantic-critical bg-semantic-critical-bg border-semantic-critical-border")}>
                        {isSupport ? "SUPPORTS" : "CONTRADICTS"}
                      </span>
                    </div>
                  )
                })}
              </div>
            ) : (
              <div className="p-3 rounded-lg bg-surface border border-hairline text-xs text-muted-foreground font-mono">
                No active hypotheses cited this artifact directly.
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="pt-4 border-t border-hairline mt-6 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-md bg-surface-hover hover:bg-surface-raised text-xs font-semibold text-white border border-hairline transition-colors"
          >
            Close Inspector
          </button>
        </div>
      </div>
    </div>
  )
}
