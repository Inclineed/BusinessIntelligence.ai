import React, { useState } from "react"
import { Search, Database, ShieldCheck, ChevronRight, Filter } from "lucide-react"
import { EvidenceItem, HypothesisItem } from "../../types/investigation"
import { cn } from "../../lib/utils"

interface EvidenceExplorerProps {
  evidence: EvidenceItem[]
  hypotheses: HypothesisItem[]
  onSelectEvidence: (evidence: EvidenceItem) => void
}

export const EvidenceExplorer: React.FC<EvidenceExplorerProps> = ({
  evidence,
  hypotheses,
  onSelectEvidence,
}) => {
  const [searchQuery, setSearchQuery] = useState("")
  const [selectedSource, setSelectedSource] = useState("all")

  if (!evidence || evidence.length === 0) {
    return (
      <div className="p-8 rounded-lg bg-surface border border-hairline text-center text-muted-foreground text-xs">
        No evidence artifacts retrieved under current persona entitlement scope.
      </div>
    )
  }

  // Summary calculations
  const sources = Array.from(new Set(evidence.map((e) => e.source_id)))
  const freshCount = evidence.filter((e) => (e.reliability_weight ?? 1.0) >= 0.85).length
  const meanRelevance = evidence.reduce((acc, e) => acc + (e.relevance ?? 1.0), 0) / evidence.length

  // Filtered evidence
  const filtered = evidence.filter((e) => {
    const matchesSource = selectedSource === "all" || e.source_id === selectedSource
    const matchesSearch =
      (e.evidence_id ?? "").toLowerCase().includes(searchQuery.toLowerCase()) ||
      (e.summary ?? "").toLowerCase().includes(searchQuery.toLowerCase()) ||
      e.source_id.toLowerCase().includes(searchQuery.toLowerCase())
    return matchesSource && matchesSearch
  })

  return (
    <div className="space-y-6">
      {/* Header & Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 rounded-lg bg-surface border border-hairline shadow-card">
          <div className="text-[11px] font-mono text-muted-foreground uppercase">TOTAL ARTIFACTS</div>
          <div className="text-2xl font-bold font-mono text-white mt-1">{evidence.length}</div>
        </div>
        <div className="p-4 rounded-lg bg-surface border border-hairline shadow-card">
          <div className="text-[11px] font-mono text-muted-foreground uppercase">DISTINCT SOURCES</div>
          <div className="text-2xl font-bold font-mono text-white mt-1">{sources.length}</div>
        </div>
        <div className="p-4 rounded-lg bg-surface border border-hairline shadow-card">
          <div className="text-[11px] font-mono text-muted-foreground uppercase">FRESHNESS SLA MET</div>
          <div className="text-2xl font-bold font-mono text-semantic-positive mt-1">
            {freshCount} <span className="text-xs text-muted-foreground font-normal">/ {evidence.length}</span>
          </div>
        </div>
        <div className="p-4 rounded-lg bg-surface border border-hairline shadow-card">
          <div className="text-[11px] font-mono text-muted-foreground uppercase">MEAN RELEVANCE</div>
          <div className="text-2xl font-bold font-mono text-semantic-neutral mt-1">{meanRelevance.toFixed(2)}</div>
        </div>
      </div>

      {/* Filter & Search Bar */}
      <div className="flex flex-wrap gap-4 items-center justify-between p-4 rounded-lg bg-surface border border-hairline shadow-card">
        {/* Search */}
        <div className="relative flex-1 min-w-[240px]">
          <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search evidence by ID, keyword, or telemetry payload..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-surface-raised border border-hairline hover:border-hairline-bright focus:border-semantic-neutral rounded-md pl-9 pr-3 py-2 text-xs text-white placeholder:text-muted-foreground outline-none transition-colors"
          />
        </div>

        {/* Source Pills */}
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            onClick={() => setSelectedSource("all")}
            className={cn(
              "px-3 py-1.5 rounded-md text-xs font-mono font-semibold transition-colors",
              selectedSource === "all"
                ? "bg-surface-raised text-white border border-hairline-bright shadow-sm"
                : "text-muted-foreground hover:bg-surface-hover hover:text-white"
            )}
          >
            ALL SOURCES
          </button>
          {sources.map((src) => (
            <button
              key={src}
              onClick={() => setSelectedSource(src)}
              className={cn(
                "px-3 py-1.5 rounded-md text-xs font-mono transition-colors",
                selectedSource === src
                  ? "bg-surface-raised text-white border border-hairline-bright font-semibold shadow-sm"
                  : "text-muted-foreground hover:bg-surface-hover hover:text-white"
              )}
            >
              {src.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Evidence Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filtered.map((e) => {
          const isFresh = (e.reliability_weight ?? 1.0) >= 0.85
          return (
            <div
              key={(e.evidence_id ?? "")}
              onClick={() => onSelectEvidence(e)}
              className="group p-4 rounded-lg bg-surface border border-hairline hover:border-semantic-neutral/60 cursor-pointer transition-all duration-150 shadow-card flex flex-col justify-between"
            >
              <div>
                <div className="flex justify-between items-center mb-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-bold text-semantic-neutral bg-semantic-neutral-bg border border-semantic-neutral-border px-2 py-0.5 rounded">
                      ◈ {(e.evidence_id ?? "")}
                    </span>
                    <span className="font-mono text-[10px] text-muted-foreground uppercase">{e.source_id}</span>
                  </div>
                  <span className={cn("text-[10px] font-mono font-bold px-2 py-0.5 rounded border", isFresh ? "text-semantic-positive bg-semantic-positive-bg border-semantic-positive-border" : "text-semantic-warning bg-semantic-warning-bg border-semantic-warning-border")}>
                    {isFresh ? "FRESH" : "DOWN-WEIGHTED"}
                  </span>
                </div>

                <p className="text-xs text-foreground font-sans line-clamp-3 leading-relaxed mb-3">
                  {(e.summary ?? "")}
                </p>
              </div>

              <div className="pt-3 border-t border-hairline-subtle flex justify-between items-center text-[11px] font-mono text-muted-foreground">
                <div className="flex items-center gap-3">
                  <span>Rel: <b className="text-white">{(e.relevance ?? 1.0).toFixed(2)}</b></span>
                  <span>Weight: <b className={isFresh ? "text-semantic-positive" : "text-semantic-warning"}>{(e.reliability_weight ?? 1.0).toFixed(2)}</b></span>
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-surface-raised border border-hairline">{e.method}</span>
                </div>
                <span className="text-semantic-neutral group-hover:translate-x-0.5 transition-transform flex items-center text-[11px] font-sans font-medium">
                  Inspect <ChevronRight className="w-3.5 h-3.5 ml-0.5" />
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
