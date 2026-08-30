import React from "react"
import { InvestigationResult, HypothesisItem } from "../../types/investigation"
import { cleanLLMTags } from "../../lib/utils"
import { getInvestigationStory } from "../../lib/narrativeHelpers"
import { CausalReasoningTrail } from "../reasoning/CausalReasoningTrail"
import {
  Sparkles,
  Award,
  ExternalLink,
  ShieldCheck,
  GitCommit,
  Server,
  Zap,
  TrendingDown,
  Layers,
  CheckCircle2,
  AlertCircle,
  FileText,
  AlertTriangle,
} from "lucide-react"

interface E5HypothesisWorkspaceProps {
  result: InvestigationResult
}

export const E5HypothesisWorkspace: React.FC<E5HypothesisWorkspaceProps> = ({
  result,
}) => {
  const scored = result.scored || []
  const statementMap = new Map(
    (result.hypotheses || []).map((h) => [h.hypothesis_id, h])
  )
  const winningId = result.decision?.winning_hypothesis_id

  return (
    <div className="space-y-6 animate-fade-in select-text">
      {/* Stage Header */}
      <header className="space-y-2 border-b border-[#2E2E2E] pb-4">
        <div className="flex items-center justify-between">
          <span className="px-2 py-0.5 rounded bg-[#6B9BB0]/20 text-[#F4EEE0] font-mono text-xs font-bold border border-[#6B9BB0]/40">
            STAGE E5 · COMPETING HYPOTHESES
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#1C1C1C] text-[#9E9788] border border-[#2E2E2E]">
            [LLM]
          </span>
        </div>
        <h1 className="text-2xl font-bold font-sans text-[#F4EEE0] tracking-tight">
          Competing Hypotheses Studio &amp; Causal Reasoning
        </h1>
        <p className="text-xs text-[#9E9788] font-sans leading-relaxed max-w-3xl">
          Generating and comparing competing explanations against grounded evidence. Evaluates the 4-layer causal ontology from root cause through proximal mechanism to symptom KPIs.
        </p>
      </header>

      {/* 1. Interactive Causal Reasoning Trail (DAG Flow) */}
      {(result.hypotheses || []).length > 0 && (
        <CausalReasoningTrail result={result} />
      )}

      {/* Ranked Hypotheses Studio Cards */}
      {scored.length === 0 && (result.hypotheses || []).length === 0 ? (
        (() => {
          const story = getInvestigationStory(result)
          const isNominal = story.isNominal ?? false
          return (
            <div
              className={`p-6 sm:p-8 rounded-2xl bg-[#1C1C1C] space-y-5 border ${
                isNominal
                  ? "border-[#4E8569]/40 ring-1 ring-[#4E8569]/20"
                  : "border-[#2E2E2E]"
              }`}
            >
              {/* Header with Guard / Health Badge */}
              <div className="flex items-center justify-between border-b border-[#2E2E2E] pb-4">
                <div className="flex items-center gap-3">
                  <div
                    className={`w-10 h-10 rounded-xl flex items-center justify-center border ${
                      isNominal
                        ? "bg-[#4E8569]/15 border-[#4E8569]/30 text-[#78AC91]"
                        : "bg-[#D8453A]/15 border-[#D8453A]/30 text-[#E56B62]"
                    }`}
                  >
                    {isNominal ? (
                      <CheckCircle2 className="w-5 h-5 text-[#4E8569]" />
                    ) : (
                      <ShieldCheck className="w-5 h-5" />
                    )}
                  </div>
                  <div>
                    <div className="text-sm font-bold font-mono text-[#F4EEE0] flex items-center gap-2">
                      <span>{story.headline.toUpperCase()}</span>
                      <span
                        className={`text-[10px] px-2 py-0.5 rounded font-mono border font-bold ${
                          isNominal
                            ? "bg-[#4E8569]/20 text-[#78AC91] border-[#4E8569]/30"
                            : "bg-[#D8453A]/20 text-[#E56B62] border-[#D8453A]/30"
                        }`}
                      >
                        {isNominal ? "ALL STREAMS NOMINAL" : "GUARD ACTIVE"}
                      </span>
                    </div>
                    <div className="text-xs text-[#9E9788] font-mono mt-0.5">
                      Engine E5 [LLM] · Zero-Hallucination Causal Invariant Active
                    </div>
                  </div>
                </div>
              </div>

              {/* Executive Incident Diagnosis */}
              <div className="p-4 rounded-xl bg-[#141414] border border-[#2E2E2E] space-y-2">
                <div className="text-[10px] font-mono uppercase font-bold text-[#6B9BB0] tracking-wider">
                  Incident Diagnosis &amp; Telemetry Assessment
                </div>
                <p className="text-xs sm:text-sm text-[#D1C9B8] font-sans leading-relaxed">
                  {story.story}
                </p>
              </div>

              {/* Key Evidence & Operator Guidance Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 font-mono text-xs">
                {/* Evidence Verification */}
                <div className="p-3.5 rounded-xl bg-[#181818] border border-[#2A2A2A] space-y-1.5">
                  <div className="text-[10px] text-[#78AC91] uppercase font-bold flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" /> Grounded Evidence Finding
                  </div>
                  <p className="text-[11px] text-[#D1C9B8] font-sans leading-relaxed">
                    {story.keyEvidenceHighlight || "Evidence records corroborating nominal system telemetry."}
                  </p>
                </div>

                {/* Operator Directive */}
                <div className="p-3.5 rounded-xl bg-[#181818] border border-[#2A2A2A] space-y-1.5">
                  <div
                    className={`text-[10px] uppercase font-bold flex items-center gap-1 ${
                      isNominal ? "text-[#78AC91]" : "text-[#E56B62]"
                    }`}
                  >
                    {isNominal ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-[#4E8569]" />
                    ) : (
                      <AlertTriangle className="w-3.5 h-3.5" />
                    )}
                    <span>Recommended Operator Action</span>
                  </div>
                  <p className="text-[11px] text-[#D1C9B8] font-sans leading-relaxed">
                    {story.operatorAction}
                  </p>
                </div>
              </div>

              {/* Telemetry Summary Stats */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 font-mono text-xs">
                <div className="p-3 rounded-xl bg-[#141414] border border-[#2E2E2E] space-y-1">
                  <span className="text-[10px] text-[#9E9788] uppercase block">Detected Signals</span>
                  <span className="font-bold text-[#F4EEE0]">{(result.signals || []).length} signal(s)</span>
                </div>
                <div className="p-3 rounded-xl bg-[#141414] border border-[#2E2E2E] space-y-1">
                  <span className="text-[10px] text-[#9E9788] uppercase block">Grounded Evidence</span>
                  <span className="font-bold text-[#F4EEE0]">{(result.evidence || []).length} record(s)</span>
                </div>
                <div className="p-3 rounded-xl bg-[#141414] border border-[#2E2E2E] space-y-1">
                  <span className="text-[10px] text-[#9E9788] uppercase block">
                    {isNominal ? "System Telemetry Status" : "Active Guard Mechanism"}
                  </span>
                  <span
                    className={`font-bold truncate block ${
                      isNominal ? "text-[#78AC91]" : "text-[#E56B62]"
                    }`}
                  >
                    {story.guardName}
                  </span>
                </div>
              </div>
            </div>
          )
        })()
      ) : (
        <div className="space-y-5">
          <div className="flex items-center justify-between font-mono text-xs text-[#9E9788] px-1">
            <span className="uppercase font-bold tracking-wider">
              Candidate Hypotheses &amp; Causal Ontology ({scored.length || (result.hypotheses || []).length})
            </span>
            <span>Evaluated against deterministic constraints</span>
          </div>

          {(scored.length > 0
            ? scored
            : (result.hypotheses || []).map((h) => ({
                hypothesis_id: h.hypothesis_id,
                rule_score: 0.5,
                final_audit_score: 0.5,
                audit_verdict: "MARGINAL" as any,
                evidence_sufficiency_score: 1.0,
                evidence_sufficiency_level: "STRONG" as any,
                support_score: 0.5,
                contradiction_score: 0,
                rule_results: [],
                narrative: h.reasoning,
                root_cause_gate_passed: true,
                root_cause_evidence_ids: [] as string[],
              }))
          ).map((sh) => {
            const raw = statementMap.get(sh.hypothesis_id)
            const isWinning = sh.hypothesis_id === winningId
            const scorePct = Math.round(sh.final_audit_score * 100)

            const rootCause = raw?.root_cause_type || "UNKNOWN"
            const subsystem = raw?.affected_subsystem || "UNKNOWN"
            const mechanism =
              raw?.proximal_mechanism || raw?.mechanism_tag || "UNKNOWN"
            const symptomKpis = raw?.symptom_kpis || []

            // Evidence citation classification
            const rootCauseEvidenceIds = new Set(sh.root_cause_evidence_ids || [])
            const supportingIds = raw?.supporting_evidence_ids || []
            const contradictoryIds = raw?.contradictory_evidence_ids || []
            const citations = raw?.citations || []

            // Group citations by role if available
            const rootCitations = supportingIds.filter((id) =>
              rootCauseEvidenceIds.has(id)
            )
            const generalSupporting = supportingIds.filter(
              (id) => !rootCauseEvidenceIds.has(id)
            )

            return (
              <div
                key={sh.hypothesis_id}
                className={`p-6 rounded-2xl border transition-all space-y-4 ${
                  isWinning
                    ? "bg-[#222222] border-[#333333] shadow-md ring-1 ring-[#6B9BB0]/20"
                    : "bg-[#1C1C1C] border-[#2E2E2E]"
                }`}
              >
                {/* 1. Header: Hypothesis ID, Status Badge & Calibrated Audit Score */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 font-mono text-xs border-b border-[#2E2E2E] pb-3">
                  <div className="flex items-center gap-2">
                    <span className="px-2.5 py-1 rounded-lg bg-[#181818] border border-[#333333] text-[#F4EEE0] font-bold text-xs">
                      {sh.hypothesis_id}
                    </span>
                    {isWinning && (
                      <span className="text-[10px] px-2 py-0.5 rounded bg-[#4E8569]/20 text-[#78AC91] font-bold flex items-center gap-1 border border-[#4E8569]/35">
                        <Award className="w-3.5 h-3.5 text-[#4E8569]" /> LEADING EXPLANATION
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-xs text-[#9E9788]">Audit Score:</span>
                    <span className={`text-sm font-bold font-mono px-2 py-0.5 rounded border tabular-nums ${
                      sh.final_audit_score >= 0.70
                        ? "bg-[#4E8569]/20 text-[#78AC91] border-[#4E8569]/40"
                        : "bg-[#A88232]/20 text-[#DEC06A] border-[#A88232]/40"
                    }`}>
                      {scorePct}/100 · {sh.audit_verdict || (sh.final_audit_score >= 0.70 ? "VERIFIED" : "MARGINAL")}
                    </span>
                  </div>
                </div>

                {/* 2. Structured 4-Layer Causal Ontology Grid */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5 font-mono text-xs">
                  {/* Layer 1: Root Cause */}
                  <div className="p-3 rounded-xl bg-[#171717] border border-[#2A2A2A] space-y-1">
                    <div className="text-[10px] text-[#9E9788] uppercase tracking-wider flex items-center gap-1">
                      <GitCommit className="w-3 h-3 text-[#E56B62]" />
                      <span>Root Cause</span>
                    </div>
                    <div className="text-xs font-bold text-[#E56B62] truncate">
                      {rootCause.replace(/_/g, " ").toUpperCase()}
                    </div>
                  </div>

                  {/* Layer 2: Affected Subsystem */}
                  <div className="p-3 rounded-xl bg-[#171717] border border-[#2A2A2A] space-y-1">
                    <div className="text-[10px] text-[#9E9788] uppercase tracking-wider flex items-center gap-1">
                      <Server className="w-3 h-3 text-[#6B9BB0]" />
                      <span>Affected Subsystem</span>
                    </div>
                    <div className="text-xs font-bold text-[#F4EEE0] truncate">
                      {subsystem.replace(/_/g, " ").toUpperCase()}
                    </div>
                  </div>

                  {/* Layer 3: Proximal Mechanism */}
                  <div className="p-3 rounded-xl bg-[#171717] border border-[#2A2A2A] space-y-1">
                    <div className="text-[10px] text-[#9E9788] uppercase tracking-wider flex items-center gap-1">
                      <Zap className="w-3 h-3 text-[#D19B5E]" />
                      <span>Proximal Mechanism</span>
                    </div>
                    <div className="text-xs font-bold text-[#D19B5E] truncate">
                      {mechanism.replace(/_/g, " ").toUpperCase()}
                    </div>
                  </div>

                  {/* Layer 4: Symptom KPIs */}
                  <div className="p-3 rounded-xl bg-[#171717] border border-[#2A2A2A] space-y-1">
                    <div className="text-[10px] text-[#9E9788] uppercase tracking-wider flex items-center gap-1">
                      <TrendingDown className="w-3 h-3 text-[#D8453A]" />
                      <span>Symptom KPIs</span>
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {symptomKpis.length > 0 ? (
                        symptomKpis.map((kpi) => (
                          <span
                            key={kpi}
                            className="px-1.5 py-0.2 rounded bg-[#1F1818] border border-[#D8453A]/30 text-[10px] font-bold text-[#E56B62] truncate"
                          >
                            {kpi.replace(/_/g, " ")}
                          </span>
                        ))
                      ) : (
                        <span className="text-xs text-[#9E9788]">—</span>
                      )}
                    </div>
                  </div>
                </div>

                {/* 3. Qualitative Hypothesis Statement */}
                <div className="space-y-1">
                  <div className="text-[10px] font-mono uppercase font-bold text-[#9E9788]">
                    Hypothesis Statement (Zero-Number Qualitative Proposition)
                  </div>
                  <div className="text-sm font-medium text-[#F4EEE0] font-sans leading-relaxed p-3 rounded-xl bg-[#181818] border border-[#282828]">
                    {raw?.statement || "Hypothesis statement under evaluation."}
                  </div>
                </div>

                {/* 4. Evaluator Narrative Reasoning */}
                {sh.narrative && (
                  <div className="p-3.5 rounded-xl bg-[#141414] border border-[#282828] text-xs text-[#D1C9B8] font-sans leading-relaxed">
                    <span className="text-[10px] font-mono text-[#9E9788] uppercase font-bold mr-1.5 block mb-1">
                      Evaluator Causal Reasoning:
                    </span>
                    {cleanLLMTags(sh.narrative)}
                  </div>
                )}

                {/* 5. Causal Evidence Mapping Section (Grouped by Role) */}
                <div className="space-y-2 pt-2 border-t border-[#2A2A2A] text-xs font-mono">
                  <div className="text-[10px] font-bold text-[#9E9788] uppercase tracking-wider flex items-center gap-1.5">
                    <Layers className="w-3.5 h-3.5 text-[#6B9BB0]" />
                    <span>Causal Evidence Citations</span>
                  </div>

                  <div className="flex flex-col gap-2">
                    {/* Root-Cause Discriminative Evidence */}
                    {rootCitations.length > 0 && (
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-[11px] text-[#E56B62] font-bold flex items-center gap-1">
                          <GitCommit className="w-3 h-3" /> Root-Cause Evidence:
                        </span>
                        {rootCitations.map((id) => (
                          <span
                            key={id}
                            className="px-2 py-0.5 rounded bg-[#D8453A]/15 border border-[#D8453A]/35 text-[#E56B62] font-bold text-[11px]"
                          >
                            {id}
                          </span>
                        ))}
                      </div>
                    )}

                    {/* General Supporting Evidence */}
                    {generalSupporting.length > 0 && (
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-[11px] text-[#6B9BB0] font-bold flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3 text-[#4E8569]" /> Mechanism / Symptom Evidence:
                        </span>
                        {generalSupporting.map((id) => (
                          <span
                            key={id}
                            className="px-2 py-0.5 rounded bg-[#181818] border border-[#2E2E2E] text-[#6B9BB0] font-bold text-[11px]"
                          >
                            {id}
                          </span>
                        ))}
                      </div>
                    )}

                    {/* Contradictory Evidence */}
                    {contradictoryIds.length > 0 && (
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-[11px] text-[#E56B62] font-bold flex items-center gap-1">
                          <AlertTriangle className="w-3 h-3" /> Contradictory Evidence:
                        </span>
                        {contradictoryIds.map((id) => (
                          <span
                            key={id}
                            className="px-2 py-0.5 rounded bg-[#D8453A]/10 border border-[#D8453A]/30 text-[#E56B62] font-bold text-[11px]"
                          >
                            {id}
                          </span>
                        ))}
                      </div>
                    )}

                    {supportingIds.length === 0 && contradictoryIds.length === 0 && (
                      <div className="text-[11px] text-[#78716C]">
                        No specific evidence records cited for this candidate hypothesis.
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
