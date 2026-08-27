import React from "react"
import { InvestigationResult } from "../../types/investigation"
import { Sparkles, Award, ExternalLink, ShieldCheck } from "lucide-react"

interface E5HypothesisWorkspaceProps {
  result: InvestigationResult
}

export const E5HypothesisWorkspace: React.FC<E5HypothesisWorkspaceProps> = ({ result }) => {
  const scored = result.scored || []
  const statementMap = new Map((result.hypotheses || []).map((h) => [h.hypothesis_id, h]))
  const winningId = result.decision?.winning_hypothesis_id

  return (
    <div className="space-y-6 animate-fade-in">
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
          Generating and comparing competing explanations against grounded evidence. Strictly bounded qualitative reasoning without hallucinated metrics.
        </p>
      </header>

      {/* Ranked Hypotheses Studio Cards */}
      {scored.length === 0 && (result.hypotheses || []).length === 0 ? (
        <div className="p-8 rounded-2xl bg-[#1C1C1C] border border-[#2E2E2E] space-y-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[#D8453A]/15 border border-[#D8453A]/30 flex items-center justify-center text-[#E56B62]">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <div className="text-sm font-bold font-mono text-[#F4EEE0] flex items-center gap-2">
                <span>HYPOTHESIS GENERATION SUPPRESSED</span>
                <span className="text-[10px] px-2 py-0.5 rounded bg-[#D8453A]/20 text-[#E56B62] font-mono border border-[#D8453A]/30 font-bold">
                  ABSTENTION GUARD ACTIVE
                </span>
              </div>
              <div className="text-xs text-[#9E9788] font-mono mt-0.5">
                Engine E5 [LLM] · Zero-Hallucination Causal Constraint
              </div>
            </div>
          </div>

          <p className="text-xs text-[#D1C9B8] font-sans leading-relaxed">
            Candidate causal explanations were not generated for this scenario. Under the system's causal invariants (Req 8.7 &amp; Req 13.2), the language model is strictly prohibited from fabricating hypotheses without grounded, authorized evidence.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 font-mono text-xs">
            <div className="p-3 rounded-xl bg-[#141414] border border-[#2E2E2E] space-y-1">
              <span className="text-[10px] text-[#9E9788] uppercase block">Detected Signals</span>
              <span className="font-bold text-[#F4EEE0]">{(result.signals || []).length} signal(s)</span>
            </div>
            <div className="p-3 rounded-xl bg-[#141414] border border-[#2E2E2E] space-y-1">
              <span className="text-[10px] text-[#9E9788] uppercase block">Authorized Evidence</span>
              <span className="font-bold text-[#F4EEE0]">{(result.evidence || []).length} item(s)</span>
            </div>
            <div className="p-3 rounded-xl bg-[#141414] border border-[#2E2E2E] space-y-1">
              <span className="text-[10px] text-[#9E9788] uppercase block">Abstention Reason</span>
              <span className="font-bold text-[#E56B62] truncate block">
                {result.decision?.abstention_reason || "insufficient_grounding"}
              </span>
            </div>
          </div>

          <div className="text-[11px] text-[#9E9788] font-mono border-t border-[#2E2E2E] pt-3 flex items-center justify-between">
            <span>To inspect underlying telemetry or technical evidence:</span>
            <span className="text-[#6B9BB0] font-bold">Switch to Analyst Persona</span>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {(scored.length > 0 ? scored : (result.hypotheses || []).map((h) => ({ hypothesis_id: h.hypothesis_id, final_score: 0.5, support_score: 0.5, contradiction_penalty: 0, rule_results: [], narrative: h.reasoning }))).map((sh) => {
            const raw = statementMap.get(sh.hypothesis_id)
            const isWinning = sh.hypothesis_id === winningId
            const scorePct = Math.round(sh.final_score * 100)

            const hasSupport = raw?.supporting_evidence_ids && raw.supporting_evidence_ids.length > 0
            const hasContradiction = raw?.contradictory_evidence_ids && raw.contradictory_evidence_ids.length > 0

            return (
              <div
                key={sh.hypothesis_id}
                className={`p-5 rounded-2xl border transition-all ${
                  isWinning
                    ? "bg-[#222222] border-[#333333]"
                    : "bg-[#1C1C1C] border-[#2E2E2E]"
                }`}
              >
                {/* Top line: ID, Title, Prob/Score */}
                <div className="flex items-center justify-between gap-2 mb-2 font-mono text-xs">
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded bg-[#181818] border border-[#333333] text-[#F4EEE0] font-bold">
                      {sh.hypothesis_id}
                    </span>
                    {isWinning && (
                      <span className="text-[10px] px-2 py-0.5 rounded bg-[#4E8569]/20 text-[#78AC91] font-bold flex items-center gap-1 border border-[#4E8569]/35">
                        <Award className="w-3 h-3 text-[#4E8569]" /> LEADING EXPLANATION
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-xs text-[#9E9788]">Support Score:</span>
                    <span className="text-sm font-bold text-[#F4EEE0] tabular-nums">{scorePct}/100</span>
                  </div>
                </div>

                {/* Statement */}
                <div className="text-sm font-medium text-[#F4EEE0] font-sans leading-relaxed mb-3">
                  {raw?.statement || "Hypothesis statement under evaluation."}
                </div>

                {/* Evaluator Narrative Reasoning */}
                {sh.narrative && (
                  <div className="p-3.5 rounded-xl bg-[#141414] border border-[#2E2E2E] text-xs text-[#D1C9B8] font-sans leading-relaxed mb-3">
                    <span className="text-[10px] font-mono text-[#9E9788] uppercase font-bold mr-1.5">
                      Evaluator Reasoning:
                    </span>
                    {sh.narrative}
                  </div>
                )}

                {/* Citations & Evidence Links */}
                {(hasSupport || hasContradiction) && (
                  <div className="flex flex-col gap-2 text-[11px] font-mono text-[#9E9788] pt-3 mt-1 border-t border-white/[0.04]">
                    {hasSupport && (
                      <div className="flex items-center gap-2 flex-wrap">
                        <span>Supporting Evidence:</span>
                        {raw.supporting_evidence_ids.map((id) => (
                          <span key={id} className="px-1.5 py-0.5 rounded bg-[#181818] border border-[#2E2E2E] text-[#6B9BB0] font-bold">
                            {id}
                          </span>
                        ))}
                      </div>
                    )}

                    {hasContradiction && (
                      <div className="flex items-center gap-2 flex-wrap mt-1">
                        <span className="text-[#E56B62]/80">Contradictory Evidence:</span>
                        {raw.contradictory_evidence_ids.map((id) => (
                          <span key={id} className="px-1.5 py-0.5 rounded bg-[#D8453A]/10 border border-[#D8453A]/30 text-[#E56B62] font-bold">
                            {id}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
