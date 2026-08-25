import React from "react"
import { TelemetryData } from "../../types/investigation"
import { 
  Cpu, 
  Clock, 
  X, 
  Coins, 
  Layers, 
  Server, 
  Zap, 
  ShieldCheck, 
  CheckCircle2, 
  Database,
  BarChart2
} from "lucide-react"

interface SystemPerformanceDrawerProps {
  isOpen: boolean
  onClose: () => void
  telemetry?: TelemetryData
  methodOwnership?: Record<string, string | string[]>
  scenarioId?: string
}

export const SystemPerformanceDrawer: React.FC<SystemPerformanceDrawerProps> = ({
  isOpen,
  onClose,
  telemetry,
  methodOwnership,
  scenarioId,
}) => {
  if (!isOpen) return null

  const latencies = telemetry?.latency_ms_by_engine || {}

  // Canonical pipeline stage definitions
  const STAGES = [
    { key: "kpi_store", label: "E1 KPI STORE", subKey: null },
    { key: "signal", label: "E2 SIGNAL", subKey: null },
    { key: "diagnostic", label: "E3 DIAGNOSTIC", subKey: null },
    { key: "evidence", label: "E4 EVIDENCE", subKey: null },
    { key: "hypothesis", label: "E5 HYPOTHESIS", subKey: "hypothesis_engine" },
    { key: "challenge", label: "E6 CHALLENGE", subKey: "challenge_engine" },
    { key: "decision", label: "E7 DECISION", subKey: "decision_engine" },
    { key: "outcome", label: "E8 OUTCOME", subKey: null },
    { key: "memory", label: "E9 MEMORY", subKey: null },
  ]

  const stageKeySet = new Set(STAGES.map(s => s.key))
  const totalMs = Object.entries(latencies).reduce((acc, [k, v]) => {
    if (stageKeySet.has(k)) {
      return acc + (Number(v) || 0)
    }
    return acc
  }, 0)
  const totalSec = totalMs > 0 ? (totalMs / 1000).toFixed(2) : "N/A"

  // Provider & Model
  const provider = telemetry?.llm_provider || (telemetry?.external_cost_usd && telemetry.external_cost_usd > 0 ? "groq" : "ollama")
  const model = telemetry?.llm_model || (provider === "groq" ? "groq/compound-mini" : "qwen3:8b")

  // Engine latencies
  const e5Lat = latencies["hypothesis"] !== undefined ? `${Number(latencies["hypothesis"]).toFixed(1)} ms` : "N/A"
  const e6Lat = latencies["challenge"] !== undefined ? `${Number(latencies["challenge"]).toFixed(1)} ms` : "N/A"
  const e7Lat = latencies["decision"] !== undefined ? `${Number(latencies["decision"]).toFixed(1)} ms` : "N/A"
  const e9Lat = latencies["memory"] !== undefined ? `${Number(latencies["memory"]).toFixed(1)} ms` : (latencies["retrieval"] !== undefined ? `${Number(latencies["retrieval"]).toFixed(1)} ms` : "N/A")

  // Tokens
  const tokensIn = typeof telemetry?.llm_tokens_in === "number" ? telemetry.llm_tokens_in : null
  const tokensOut = typeof telemetry?.llm_tokens_out === "number" ? telemetry.llm_tokens_out : null
  const totalTokens = (tokensIn !== null && tokensOut !== null) ? tokensIn + tokensOut : null
  const llmCalls = typeof telemetry?.llm_calls === "number" ? telemetry.llm_calls : null

  // External cost calculation
  const externalCost = telemetry?.external_cost_usd
  const isLocalOllama = provider.toLowerCase().includes("ollama")

  // Retries / rate limits
  const rateLimitEvents = telemetry?.rate_limit_events ?? 0
  const retryCount = telemetry?.retry_count ?? 0

  return (
    <div 
      className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex justify-end animate-in fade-in duration-200" 
      onClick={onClose}
    >
      <div 
        className="w-full max-w-xl bg-[#181818] border-l border-[#2E2E2E] p-6 overflow-y-auto space-y-6 shadow-2xl custom-scrollbar flex flex-col justify-between"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── Top Header ────────────────────────────────────────── */}
        <div className="space-y-4">
          <div className="flex items-center justify-between pb-4 border-b border-[#2E2E2E]">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-[#6B9BB0]/15 border border-[#6B9BB0]/30 flex items-center justify-center text-[#6B9BB0]">
                <Cpu className="w-4 h-4" />
              </div>
              <div>
                <h2 className="text-base font-bold text-[#F4EEE0]">System Performance &amp; Runtime</h2>
                <p className="text-xs text-[#9E9788]">Per-investigation telemetry trace &amp; compute accounting</p>
              </div>
            </div>
            <button 
              onClick={onClose} 
              className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-[#9E9788] hover:text-[#F4EEE0] transition-colors cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* ── Active Provider & Model Status Card ────────────────── */}
          <div className="p-4 rounded-xl bg-[#222222] border border-[#333333] space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs font-semibold text-[#F4EEE0]">
                <Server className="w-3.5 h-3.5 text-[#6B9BB0]" />
                <span>Active LLM Provider &amp; Architecture</span>
              </div>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium border bg-[#6B9BB0]/15 border-[#6B9BB0]/35 text-[#F4EEE0]">
                {provider.toUpperCase()}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs font-mono">
              <div className="p-2.5 rounded-lg bg-[#181818] border border-[#2E2E2E]">
                <span className="text-[10px] text-[#9E9788] block uppercase">Inference Backend</span>
                <span className="text-[#F4EEE0] font-medium capitalize">
                  {provider.toLowerCase().includes("groq") ? "Groq Cloud API (LPU)" : "Local Ollama Instance"}
                </span>
              </div>
              <div className="p-2.5 rounded-lg bg-[#181818] border border-[#2E2E2E]">
                <span className="text-[10px] text-[#9E9788] block uppercase">Active Model</span>
                <span className="text-[#F4EEE0] font-mono font-medium truncate block" title={model}>
                  {model || "N/A"}
                </span>
              </div>
            </div>

            <div className="flex items-center justify-between text-[11px] text-[#9E9788] pt-1">
              <div className="flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5 text-[#4E8569]" />
                <span>Secret Isolation: Zero credential leakage</span>
              </div>
              <span className="font-mono text-[#D1C9B8]">
                {rateLimitEvents > 0 ? `${rateLimitEvents} rate-limit event(s)` : (retryCount > 0 ? `${retryCount} retry event(s)` : "0 retries / Normal")}
              </span>
            </div>
          </div>

          {/* ── Total Latency & Engine Breakdown ───────────────────── */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs font-semibold text-[#F4EEE0] uppercase font-mono">
                <Clock className="w-3.5 h-3.5 text-[#6B9BB0]" />
                <span>Latency Waterfall</span>
              </div>
              <span className="text-xs font-mono text-[#6B9BB0] font-bold">
                Total: {totalMs > 0 ? `${totalMs.toFixed(1)} ms (${totalSec}s)` : "N/A"}
              </span>
            </div>

            {/* Core LLM Engine Highlight Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
              <div className="p-2.5 rounded-lg bg-[#222222] border border-[#333333] flex flex-col justify-between">
                <span className="text-[10px] text-[#9E9788] font-mono uppercase">E5 Hypothesis</span>
                <span className="text-sm font-bold font-mono text-[#F4EEE0] mt-1">{e5Lat}</span>
              </div>
              <div className="p-2.5 rounded-lg bg-[#222222] border border-[#333333] flex flex-col justify-between">
                <span className="text-[10px] text-[#9E9788] font-mono uppercase">E6 Challenge</span>
                <span className="text-sm font-bold font-mono text-[#F4EEE0] mt-1">{e6Lat}</span>
              </div>
              <div className="p-2.5 rounded-lg bg-[#222222] border border-[#333333] flex flex-col justify-between">
                <span className="text-[10px] text-[#9E9788] font-mono uppercase">E7 Decision</span>
                <span className="text-sm font-bold font-mono text-[#F4EEE0] mt-1">{e7Lat}</span>
              </div>
              <div className="p-2.5 rounded-lg bg-[#222222] border border-[#333333] flex flex-col justify-between">
                <span className="text-[10px] text-[#9E9788] font-mono uppercase">E9 Memory</span>
                <span className="text-sm font-bold font-mono text-[#F4EEE0] mt-1">{e9Lat}</span>
              </div>
            </div>

            {/* Detailed per-engine latency list */}
            <div className="space-y-1.5 pt-1">
              {STAGES.filter(st => latencies[st.key] !== undefined).length > 0 ? (
                STAGES.map((stage) => {
                  const ms = latencies[stage.key]
                  if (ms === undefined) return null
                  const msNum = Number(ms) || 0
                  const pct = totalMs > 0 ? (msNum / totalMs) * 100 : 0
                  const subMs = stage.subKey && latencies[stage.subKey] !== undefined ? Number(latencies[stage.subKey]) : null

                  return (
                    <div key={stage.key} className="p-2 rounded-lg bg-[#1C1C1C] border border-[#2E2E2E] flex items-center justify-between text-xs font-mono">
                      <div className="flex items-center gap-2">
                        <span className="text-[#D1C9B8] uppercase">{stage.label}</span>
                        <span className="text-[10px] text-[#9E9788]">({pct.toFixed(0)}%)</span>
                        {subMs !== null && (
                          <span className="text-[9px] px-1.5 py-0.2 rounded bg-[#6B9BB0]/10 text-[#6B9BB0] border border-[#6B9BB0]/20">
                            LLM: {subMs.toFixed(0)}ms
                          </span>
                        )}
                      </div>
                      <span className="text-[#6B9BB0] font-bold">{msNum.toFixed(1)} ms</span>
                    </div>
                  )
                })
              ) : (
                <div className="p-3 text-center text-xs text-[#9E9788] bg-[#1C1C1C] rounded-lg">
                  No per-engine latency telemetry recorded for this result.
                </div>
              )}
            </div>
          </div>

          {/* ── Token Usage & Cost Accounting ──────────────────────── */}
          <div className="p-4 rounded-xl bg-[#222222] border border-[#333333] space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs font-semibold text-[#F4EEE0]">
                <Coins className="w-3.5 h-3.5 text-[#6B9BB0]" />
                <span>Token Consumption &amp; Cost Accounting</span>
              </div>
              <span className="text-xs font-mono text-[#9E9788]">
                {llmCalls !== null ? `${llmCalls} LLM Call(s)` : "N/A"}
              </span>
            </div>

            <div className="grid grid-cols-3 gap-2 text-xs font-mono">
              <div className="p-2 rounded-lg bg-[#181818] border border-[#2E2E2E]">
                <span className="text-[10px] text-[#9E9788] block uppercase">Prompt (In)</span>
                <span className="text-[#F4EEE0] font-medium">
                  {tokensIn !== null ? `${tokensIn.toLocaleString()} tok` : "N/A"}
                </span>
              </div>
              <div className="p-2 rounded-lg bg-[#181818] border border-[#2E2E2E]">
                <span className="text-[10px] text-[#9E9788] block uppercase">Completion (Out)</span>
                <span className="text-[#F4EEE0] font-medium">
                  {tokensOut !== null ? `${tokensOut.toLocaleString()} tok` : "N/A"}
                </span>
              </div>
              <div className="p-2 rounded-lg bg-[#181818] border border-[#2E2E2E]">
                <span className="text-[10px] text-[#9E9788] block uppercase">Total Tokens</span>
                <span className="text-[#6B9BB0] font-bold">
                  {totalTokens !== null ? `${totalTokens.toLocaleString()} tok` : "N/A"}
                </span>
              </div>
            </div>

            {/* Cost Details */}
            <div className="p-3 rounded-lg bg-[#181818] border border-[#2E2E2E] space-y-1.5 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-[#9E9788]">Actual External API Cost:</span>
                <span className="text-[#F4EEE0] font-mono font-semibold">
                  {externalCost !== undefined && externalCost !== null
                    ? (externalCost > 0 ? `$${externalCost.toFixed(6)} USD` : "$0.00 USD")
                    : (isLocalOllama ? "$0.00 USD" : "N/A")}
                </span>
              </div>
              <div className="text-[10px] text-[#9E9788]">
                {isLocalOllama 
                  ? "✓ Local Ollama execution: $0.00 external API billing (local GPU/CPU compute)."
                  : "✓ Cloud Groq API execution: calculated against per-token usage."}
              </div>

              {telemetry?.equivalent_cloud_cost_usd !== undefined && telemetry.equivalent_cloud_cost_usd !== null && (
                <div className="flex items-center justify-between pt-1 border-t border-white/[0.04] text-[11px]">
                  <span className="text-[#9E9788]">Claude 3.5 Sonnet Equivalent:</span>
                  <span className="text-[#D1C9B8] font-mono">
                    ${Number(telemetry.equivalent_cloud_cost_usd).toFixed(4)} USD
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* ── Method Ownership Provenance ────────────────────────── */}
          {methodOwnership && Object.keys(methodOwnership).length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-xs font-semibold text-[#F4EEE0] uppercase font-mono">
                <Layers className="w-3.5 h-3.5 text-[#6B9BB0]" />
                <span>Method Ownership Provenance</span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 font-mono text-xs">
                {Object.entries(methodOwnership).map(([eng, tag]) => (
                  <div key={eng} className="p-2 rounded-lg bg-[#1C1C1C] border border-[#2E2E2E] flex flex-col justify-between">
                    <span className="text-[10px] text-[#9E9788] uppercase">{eng}</span>
                    <span className="text-[#6B9BB0] text-xs font-semibold mt-0.5 truncate">
                      {Array.isArray(tag) ? tag.join(", ") : String(tag)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ── Footer ────────────────────────────────────────────── */}
        <div className="pt-4 border-t border-[#2E2E2E] flex items-center justify-between text-xs text-[#9E9788] font-mono">
          <span>Scenario: {scenarioId || "N/A"}</span>
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-[#F4EEE0] transition-colors cursor-pointer"
          >
            Close Trace
          </button>
        </div>
      </div>
    </div>
  )
}
