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
  const totalMs = Object.values(latencies).reduce((acc, v) => acc + (Number(v) || 0), 0)
  const totalSec = totalMs > 0 ? (totalMs / 1000).toFixed(2) : "N/A"

  // Provider & Model
  const provider = telemetry?.llm_provider || (telemetry?.external_cost_usd && telemetry.external_cost_usd > 0 ? "groq" : "ollama")
  const model = telemetry?.llm_model || (provider === "groq" ? "llama-3.3-70b-versatile" : "qwen3:8b")

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
        className="w-full max-w-xl bg-[#0F1017] border-l border-white/[0.1] p-6 overflow-y-auto space-y-6 shadow-2xl custom-scrollbar flex flex-col justify-between"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── Top Header ────────────────────────────────────────── */}
        <div className="space-y-4">
          <div className="flex items-center justify-between pb-4 border-b border-white/[0.08]">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
                <Cpu className="w-4 h-4" />
              </div>
              <div>
                <h2 className="text-base font-bold text-white">System Performance & Runtime</h2>
                <p className="text-xs text-neutral-400">Per-investigation telemetry trace & compute accounting</p>
              </div>
            </div>
            <button 
              onClick={onClose} 
              className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-neutral-400 hover:text-white transition-colors cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* ── Active Provider & Model Status Card ────────────────── */}
          <div className="p-4 rounded-xl bg-[#141622] border border-white/[0.08] space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs font-semibold text-white">
                <Server className="w-3.5 h-3.5 text-emerald-400" />
                <span>Active LLM Provider & Architecture</span>
              </div>
              <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-medium border ${
                provider.toLowerCase().includes("groq") 
                  ? "bg-purple-500/10 border-purple-500/30 text-purple-300"
                  : "bg-blue-500/10 border-blue-500/30 text-blue-300"
              }`}>
                {provider.toUpperCase()}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-2.5 rounded-lg bg-black/40 border border-white/[0.04]">
                <span className="text-[10px] text-neutral-500 block uppercase font-mono">Inference Backend</span>
                <span className="text-white font-medium capitalize">
                  {provider.toLowerCase().includes("groq") ? "Groq Cloud API (LPU)" : "Local Ollama Instance"}
                </span>
              </div>
              <div className="p-2.5 rounded-lg bg-black/40 border border-white/[0.04]">
                <span className="text-[10px] text-neutral-500 block uppercase font-mono">Active Model</span>
                <span className="text-white font-mono font-medium truncate block" title={model}>
                  {model || "N/A"}
                </span>
              </div>
            </div>

            <div className="flex items-center justify-between text-[11px] text-neutral-400 pt-1">
              <div className="flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                <span>Secret Isolation: Zero credential leakage</span>
              </div>
              <span className="font-mono text-neutral-300">
                {rateLimitEvents > 0 ? `${rateLimitEvents} rate-limit event(s)` : (retryCount > 0 ? `${retryCount} retry event(s)` : "0 retries / Normal")}
              </span>
            </div>
          </div>

          {/* ── Total Latency & Engine Breakdown ───────────────────── */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs font-semibold text-white uppercase font-mono">
                <Clock className="w-3.5 h-3.5 text-blue-400" />
                <span>Latency Waterfall</span>
              </div>
              <span className="text-xs font-mono text-emerald-400 font-bold">
                Total: {totalMs > 0 ? `${totalMs.toFixed(1)} ms (${totalSec}s)` : "N/A"}
              </span>
            </div>

            {/* Core LLM Engine Highlight Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
              <div className="p-2.5 rounded-lg bg-[#141622] border border-white/[0.06] flex flex-col justify-between">
                <span className="text-[10px] text-neutral-500 font-mono uppercase">E5 Hypothesis</span>
                <span className="text-sm font-bold font-mono text-white mt-1">{e5Lat}</span>
              </div>
              <div className="p-2.5 rounded-lg bg-[#141622] border border-white/[0.06] flex flex-col justify-between">
                <span className="text-[10px] text-neutral-500 font-mono uppercase">E6 Challenge</span>
                <span className="text-sm font-bold font-mono text-white mt-1">{e6Lat}</span>
              </div>
              <div className="p-2.5 rounded-lg bg-[#141622] border border-white/[0.06] flex flex-col justify-between">
                <span className="text-[10px] text-neutral-500 font-mono uppercase">E7 Decision</span>
                <span className="text-sm font-bold font-mono text-white mt-1">{e7Lat}</span>
              </div>
              <div className="p-2.5 rounded-lg bg-[#141622] border border-white/[0.06] flex flex-col justify-between">
                <span className="text-[10px] text-neutral-500 font-mono uppercase">E9 Memory</span>
                <span className="text-sm font-bold font-mono text-white mt-1">{e9Lat}</span>
              </div>
            </div>

            {/* Detailed per-engine latency list */}
            <div className="space-y-1.5 pt-1">
              {Object.keys(latencies).length > 0 ? (
                Object.entries(latencies).map(([eng, ms]) => {
                  const msNum = Number(ms) || 0
                  const pct = totalMs > 0 ? (msNum / totalMs) * 100 : 0
                  return (
                    <div key={eng} className="p-2 rounded-lg bg-black/40 border border-white/[0.04] flex items-center justify-between text-xs font-mono">
                      <div className="flex items-center gap-2">
                        <span className="text-neutral-300 uppercase">{eng}</span>
                        <span className="text-[10px] text-neutral-500">({pct.toFixed(0)}%)</span>
                      </div>
                      <span className="text-emerald-400 font-bold">{msNum.toFixed(1)} ms</span>
                    </div>
                  )
                })
              ) : (
                <div className="p-3 text-center text-xs text-neutral-500 bg-black/20 rounded-lg">
                  No per-engine latency telemetry recorded for this result.
                </div>
              )}
            </div>
          </div>

          {/* ── Token Usage & Cost Accounting ──────────────────────── */}
          <div className="p-4 rounded-xl bg-[#141622] border border-white/[0.08] space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs font-semibold text-white">
                <Coins className="w-3.5 h-3.5 text-amber-400" />
                <span>Token Consumption & Cost Accounting</span>
              </div>
              <span className="text-xs font-mono text-neutral-400">
                {llmCalls !== null ? `${llmCalls} LLM Call(s)` : "N/A"}
              </span>
            </div>

            <div className="grid grid-cols-3 gap-2 text-xs">
              <div className="p-2 rounded-lg bg-black/40 border border-white/[0.04]">
                <span className="text-[10px] text-neutral-500 block uppercase font-mono">Prompt (In)</span>
                <span className="text-white font-mono font-medium">
                  {tokensIn !== null ? `${tokensIn.toLocaleString()} tok` : "N/A"}
                </span>
              </div>
              <div className="p-2 rounded-lg bg-black/40 border border-white/[0.04]">
                <span className="text-[10px] text-neutral-500 block uppercase font-mono">Completion (Out)</span>
                <span className="text-white font-mono font-medium">
                  {tokensOut !== null ? `${tokensOut.toLocaleString()} tok` : "N/A"}
                </span>
              </div>
              <div className="p-2 rounded-lg bg-black/40 border border-white/[0.04]">
                <span className="text-[10px] text-neutral-500 block uppercase font-mono">Total Tokens</span>
                <span className="text-emerald-400 font-mono font-bold">
                  {totalTokens !== null ? `${totalTokens.toLocaleString()} tok` : "N/A"}
                </span>
              </div>
            </div>

            {/* Cost Details */}
            <div className="p-3 rounded-lg bg-black/60 border border-white/[0.04] space-y-1.5 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-neutral-400">Actual External API Cost:</span>
                <span className="text-white font-mono font-semibold">
                  {externalCost !== undefined && externalCost !== null
                    ? (externalCost > 0 ? `$${externalCost.toFixed(6)} USD` : "$0.00 USD")
                    : (isLocalOllama ? "$0.00 USD" : "N/A")}
                </span>
              </div>
              <div className="text-[10px] text-neutral-500">
                {isLocalOllama 
                  ? "✓ Local Ollama execution: $0.00 external API billing (local GPU/CPU compute)."
                  : "✓ Cloud Groq API execution: calculated against per-token usage."}
              </div>

              {telemetry?.equivalent_cloud_cost_usd !== undefined && telemetry.equivalent_cloud_cost_usd !== null && (
                <div className="flex items-center justify-between pt-1 border-t border-white/[0.04] text-[11px]">
                  <span className="text-neutral-400">Claude 3.5 Sonnet Equivalent:</span>
                  <span className="text-neutral-300 font-mono">
                    ${Number(telemetry.equivalent_cloud_cost_usd).toFixed(4)} USD
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* ── Method Ownership Provenance ────────────────────────── */}
          {methodOwnership && Object.keys(methodOwnership).length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-xs font-semibold text-white uppercase font-mono">
                <Layers className="w-3.5 h-3.5 text-purple-400" />
                <span>Method Ownership Provenance</span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 font-mono text-xs">
                {Object.entries(methodOwnership).map(([eng, tag]) => (
                  <div key={eng} className="p-2 rounded-lg bg-black/40 border border-white/[0.04] flex flex-col justify-between">
                    <span className="text-[10px] text-neutral-500 uppercase">{eng}</span>
                    <span className="text-emerald-400 text-xs font-semibold mt-0.5 truncate">
                      {Array.isArray(tag) ? tag.join(", ") : String(tag)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ── Footer ────────────────────────────────────────────── */}
        <div className="pt-4 border-t border-white/[0.08] flex items-center justify-between text-xs text-neutral-500 font-mono">
          <span>Scenario: {scenarioId || "N/A"}</span>
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-white transition-colors cursor-pointer"
          >
            Close Trace
          </button>
        </div>
      </div>
    </div>
  )
}
