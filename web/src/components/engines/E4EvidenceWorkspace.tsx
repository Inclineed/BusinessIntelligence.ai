import React, { useState } from "react"
import { InvestigationResult, EvidenceItem } from "../../types/investigation"
import { SCENARIO_CATALOG } from "../../lib/api"
import { EvidenceInspectionModal } from "../evidence/EvidenceInspectionModal"
import {
  Database,
  FileText,
  Eye,
  ShieldCheck,
  Clock,
  Layers,
  CheckCircle2,
  Server,
  GitCommit,
  MessageSquare,
  AlertCircle,
  ExternalLink,
} from "lucide-react"

interface E4EvidenceWorkspaceProps {
  result: InvestigationResult
}

export const E4EvidenceWorkspace: React.FC<E4EvidenceWorkspaceProps> = ({ result }) => {
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceItem | null>(null)
  const evidenceList = result.evidence || []

  // Dynamic scenario metadata
  const currentScenario =
    SCENARIO_CATALOG.find((s) => s.id === result.scenario_id) || SCENARIO_CATALOG[0]

  // Group evidence by source system for the coverage matrix
  const evidenceBySource: Record<string, EvidenceItem[]> = {}
  evidenceList.forEach((ev) => {
    const src = ev.source_id || "system"
    if (!evidenceBySource[src]) evidenceBySource[src] = []
    evidenceBySource[src].push(ev)
  })

  const sourceKeys = Object.keys(evidenceBySource)

  const getSourceIcon = (sourceId: string) => {
    switch (sourceId.toLowerCase()) {
      case "deployment_log":
      case "release_notes":
        return <GitCommit className="w-4 h-4 text-[#6B9BB0]" />
      case "payment_gateway":
      case "orders":
        return <Server className="w-4 h-4 text-[#6B9BB0]" />
      case "support_tickets":
        return <MessageSquare className="w-4 h-4 text-[#6B9BB0]" />
      case "inventory":
        return <Database className="w-4 h-4 text-[#6B9BB0]" />
      default:
        return <FileText className="w-4 h-4 text-[#6B9BB0]" />
    }
  }

  return (
    <div className="space-y-6 animate-fade-in select-text">
      {/* Stage Header */}
      <header className="space-y-2 border-b border-[#2E2E2E] pb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 rounded bg-[#6B9BB0]/20 text-[#F4EEE0] font-mono text-xs font-bold border border-[#6B9BB0]/40">
              STAGE E4 · GROUNDED EVIDENCE DOSSIER
            </span>
            <span className="text-xs font-mono text-[#9E9788] font-bold">
              {result.scenario_id}
            </span>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#1C1C1C] text-[#9E9788] border border-[#2E2E2E]">
            [SQL + CHROMA EMBEDDING RETRIEVAL]
          </span>
        </div>

        <h1 className="text-2xl font-bold font-sans text-[#F4EEE0] tracking-tight">
          Multi-Source Evidence Assembly &amp; Provenance Verification
        </h1>

        <p className="text-xs text-[#9E9788] font-sans leading-relaxed max-w-3xl">
          Assembling corroborated unstructured documents (deployment release logs, service changelogs) and structured operational databases (gateway metrics, inventory transactions, customer support tickets) with strict cryptographic provenance.
        </p>
      </header>

      {/* Source Systems Coverage Matrix */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {sourceKeys.map((src) => {
          const items = evidenceBySource[src]
          const topItem = items[0]
          const reliability = Math.round((topItem?.reliability_weight ?? 0.95) * 100)
          return (
            <div
              key={src}
              className="p-4 rounded-xl bg-[#1C1C1C] border border-[#2E2E2E] space-y-2 hover:border-[#6B9BB0]/40 transition-colors"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 font-mono text-xs font-bold text-[#F4EEE0] capitalize">
                  {getSourceIcon(src)}
                  <span>{src.replace(/_/g, " ")}</span>
                </div>
                <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-[#6B9BB0]/20 text-[#6B9BB0]">
                  {reliability}% REL
                </span>
              </div>

              <div className="flex justify-between items-center text-[11px] font-mono text-[#9E9788] pt-1 border-t border-white/[0.04]">
                <span>Corroborated:</span>
                <strong className="text-[#F4EEE0]">{items.length} record{items.length > 1 ? "s" : ""}</strong>
              </div>
            </div>
          )
        })}
      </div>

      {/* Grounded Evidence Records Table */}
      <div className="p-6 rounded-2xl bg-[#1C1C1C] border border-[#2E2E2E] space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-[#6B9BB0]" />
            <h4 className="font-mono text-xs font-bold text-[#F4EEE0] uppercase tracking-wider">
              Cryptographically Grounded Evidence Records ({evidenceList.length})
            </h4>
          </div>

          <div className="flex items-center gap-2 text-[11px] font-mono text-[#4E8569]">
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>Zero-Hallucination Citation Enforced</span>
          </div>
        </div>

        {/* Clean Evidence Rows */}
        <div className="space-y-2 pt-2">
          {/* Column Headers */}
          <div className="grid grid-cols-12 gap-3 px-4 py-2 text-[10px] font-mono font-bold uppercase text-[#9E9788] border-b border-[#2E2E2E]">
            <div className="col-span-3">Evidence ID &amp; Ref</div>
            <div className="col-span-5">Summary &amp; Corroborating Content</div>
            <div className="col-span-2">Source / Method</div>
            <div className="col-span-2 text-right">Reliability &amp; Inspect</div>
          </div>

          {/* Row Items */}
          {evidenceList.map((item) => {
            const isUnstructured = item.kind === "unstructured" || item.method === "RETRIEVAL"
            return (
              <div
                key={item.evidence_id}
                onClick={() => setSelectedEvidence(item)}
                className="grid grid-cols-12 gap-3 px-4 py-3.5 rounded-xl bg-[#222222] hover:bg-[#2A2A2A] border border-[#333333] hover:border-[#6B9BB0]/40 transition-all cursor-pointer items-center group text-xs"
              >
                {/* Evidence ID / Ref */}
                <div className="col-span-3 font-mono font-bold text-[#6B9BB0] group-hover:underline flex items-center gap-2 truncate">
                  {getSourceIcon(item.source_id)}
                  <span className="truncate">{item.raw_ref || item.evidence_id}</span>
                </div>

                {/* Evidence Summary */}
                <div className="col-span-5 text-[#D1C9B8] font-sans truncate pr-2 text-xs leading-relaxed">
                  {item.summary}
                </div>

                {/* Source System & Method */}
                <div className="col-span-2 font-mono text-[11px] text-[#9E9788] flex flex-col gap-0.5">
                  <span className="capitalize text-[#D1C9B8]">{item.source_id.replace(/_/g, " ")}</span>
                  <span className="text-[9px] text-[#666666]">
                    [{item.method || (isUnstructured ? "RETRIEVAL" : "SQL")}]
                  </span>
                </div>

                {/* Inspect Action */}
                <div className="col-span-2 text-right flex items-center justify-end gap-2 font-mono text-[11px] text-[#9E9788] group-hover:text-[#F4EEE0]">
                  <span className="font-bold text-[#6B9BB0]">
                    {Math.round((item.reliability_weight ?? 1.0) * 100)}%
                  </span>
                  <Eye className="w-3.5 h-3.5 text-[#6B9BB0]" />
                  <span className="hidden sm:inline">Inspect</span>
                </div>
              </div>
            )
          })}

          {evidenceList.length === 0 && (
            <div className="p-8 text-center text-xs font-mono text-[#9E9788] border border-dashed border-[#333333] rounded-xl">
              No grounded evidence records assembled for this persona or scenario.
            </div>
          )}
        </div>
      </div>

      {/* Modal for Raw Evidence Inspection */}
      {selectedEvidence && (
        <EvidenceInspectionModal
          evidence={selectedEvidence}
          onClose={() => setSelectedEvidence(null)}
        />
      )}
    </div>
  )
}
