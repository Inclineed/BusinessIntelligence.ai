import React, { useState, useEffect } from "react"
import { getSystemHealth } from "../../lib/api"
import { SystemHealthData, HealthStatusType } from "../../types/investigation"
import { 
  Activity, 
  RefreshCw, 
  X, 
  CheckCircle2, 
  AlertTriangle, 
  AlertOctagon, 
  Clock, 
  TrendingUp, 
  TrendingDown, 
  HelpCircle,
  Database,
  BarChart3,
  ShieldCheck
} from "lucide-react"

interface SystemHealthModalProps {
  isOpen: boolean
  onClose: () => void
}

export const SystemHealthModal: React.FC<SystemHealthModalProps> = ({ isOpen, onClose }) => {
  const [data, setData] = useState<SystemHealthData | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchHealth = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const res = await getSystemHealth()
      setData(res)
    } catch (err: any) {
      setError(err.message || "Failed to fetch health report")
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    if (isOpen) {
      fetchHealth()
    }
  }, [isOpen])

  if (!isOpen) return null

  const getStatusBadge = (status: HealthStatusType) => {
    switch (status) {
      case "HEALTHY":
        return {
          bg: "bg-emerald-500/10 border-emerald-500/30 text-emerald-400",
          icon: <CheckCircle2 className="w-4 h-4 text-emerald-400" />,
          label: "HEALTHY",
        }
      case "WATCH":
        return {
          bg: "bg-amber-500/10 border-amber-500/30 text-amber-400",
          icon: <AlertTriangle className="w-4 h-4 text-amber-400" />,
          label: "WATCH",
        }
      case "DEGRADED":
        return {
          bg: "bg-red-500/10 border-red-500/30 text-red-400",
          icon: <AlertOctagon className="w-4 h-4 text-red-400" />,
          label: "DEGRADED",
        }
      default:
        return {
          bg: "bg-slate-500/10 border-slate-500/30 text-slate-400",
          icon: <HelpCircle className="w-4 h-4 text-slate-400" />,
          label: "INSUFFICIENT DATA",
        }
    }
  }

  const getMetricStatusStyle = (mStatus: string) => {
    switch (mStatus) {
      case "HEALTHY":
        return "text-emerald-400 bg-emerald-500/10 border-emerald-500/20"
      case "WATCH":
        return "text-amber-400 bg-amber-500/10 border-amber-500/20"
      case "DEGRADED":
        return "text-red-400 bg-red-500/10 border-red-500/20"
      default:
        return "text-slate-400 bg-slate-500/10 border-slate-500/20"
    }
  }

  const overallBadge = data ? getStatusBadge(data.status) : null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="bg-[#0D0E15] border border-white/10 rounded-2xl w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col shadow-2xl">
        
        {/* Header */}
        <div className="px-6 py-5 border-b border-white/[0.08] flex items-center justify-between bg-white/[0.02]">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
              <Activity className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h2 className="text-base font-semibold text-white">Continuous Evaluation & System Health</h2>
                {overallBadge && (
                  <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono font-medium border ${overallBadge.bg}`}>
                    {overallBadge.icon}
                    {overallBadge.label}
                  </span>
                )}
              </div>
              <p className="text-xs text-neutral-400">On-demand operational monitoring and drift telemetry across 50-run count-based windows</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={fetchHealth}
              disabled={isLoading}
              className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-neutral-400 hover:text-white transition-colors cursor-pointer disabled:opacity-50"
              title="Refresh Health"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
            </button>
            <button
              onClick={onClose}
              className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-neutral-400 hover:text-white transition-colors cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1 custom-scrollbar">
          {isLoading && !data && (
            <div className="py-20 flex flex-col items-center justify-center text-neutral-400 gap-3">
              <RefreshCw className="w-6 h-6 animate-spin text-emerald-400" />
              <p className="text-xs">Computing on-demand continuous evaluation metrics...</p>
            </div>
          )}

          {error && (
            <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs flex items-center gap-2.5">
              <AlertOctagon className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {data && (
            <>
              {/* Window & Sample Context Bar */}
              <div className="p-4 rounded-xl bg-[#141620] border border-white/[0.06] flex flex-wrap items-center justify-between gap-4 text-xs">
                <div className="flex items-center gap-6">
                  <div>
                    <span className="text-neutral-500 block text-[10px] uppercase font-mono tracking-wider">Sample Lifecycle</span>
                    <span className="text-white font-medium">{data.sample_state.replace(/_/g, " ")}</span>
                  </div>
                  <div className="h-6 w-px bg-white/10" />
                  <div>
                    <span className="text-neutral-500 block text-[10px] uppercase font-mono tracking-wider">Recent Window</span>
                    <span className="text-white font-medium">{data.recent_window_size} runs</span>
                  </div>
                  <div className="h-6 w-px bg-white/10" />
                  <div>
                    <span className="text-neutral-500 block text-[10px] uppercase font-mono tracking-wider">Baseline Window</span>
                    <span className="text-white font-medium">{data.baseline_window_size} runs</span>
                  </div>
                  <div className="h-6 w-px bg-white/10" />
                  <div>
                    <span className="text-neutral-500 block text-[10px] uppercase font-mono tracking-wider">Total Indexed</span>
                    <span className="text-white font-medium">{data.total_investigations} completed</span>
                  </div>
                </div>

                <div className="text-right text-neutral-400 text-[11px]">
                  Generated: {new Date(data.generated_at).toLocaleTimeString()}
                </div>
              </div>

              {/* Status Summary Banner */}
              <div className={`p-4 rounded-xl border ${overallBadge?.bg} flex items-start gap-3`}>
                <div className="mt-0.5">{overallBadge?.icon}</div>
                <div className="space-y-0.5">
                  <div className="text-xs font-semibold text-white">Health Summary</div>
                  <div className="text-xs opacity-90">{data.summary_reason}</div>
                </div>
              </div>

              {/* 6 Core Metrics Grid */}
              <div className="space-y-3">
                <div className="text-xs font-semibold uppercase tracking-wider text-neutral-400 font-mono">
                  Operational Monitoring Metrics (v1)
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
                  
                  {/* Metric 1: E2E Latency */}
                  {data.metrics.e2e_latency_p95_ms && (
                    <div className="p-4 rounded-xl bg-[#141620] border border-white/[0.06] flex flex-col justify-between space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-xs font-medium text-white">
                          <Clock className="w-3.5 h-3.5 text-blue-400" />
                          <span>E2E Latency (p95)</span>
                        </div>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-mono border ${getMetricStatusStyle(data.metrics.e2e_latency_p95_ms.status)}`}>
                          {data.metrics.e2e_latency_p95_ms.status}
                        </span>
                      </div>

                      <div className="space-y-1">
                        <div className="text-xl font-bold font-mono text-white">
                          {data.metrics.e2e_latency_p95_ms.recent_value !== null ? `${(data.metrics.e2e_latency_p95_ms.recent_value / 1000).toFixed(2)}s` : "—"}
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-neutral-400">
                          <span>Baseline: {data.metrics.e2e_latency_p95_ms.baseline_value !== null ? `${(data.metrics.e2e_latency_p95_ms.baseline_value / 1000).toFixed(2)}s` : "None"}</span>
                          {data.metrics.e2e_latency_p95_ms.delta !== null && (
                            <span className={data.metrics.e2e_latency_p95_ms.delta > 0 ? "text-amber-400 font-mono" : "text-emerald-400 font-mono"}>
                              {data.metrics.e2e_latency_p95_ms.delta > 0 ? "+" : ""}{(data.metrics.e2e_latency_p95_ms.delta / 1000).toFixed(2)}s
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="text-[11px] text-neutral-400 pt-2 border-t border-white/[0.04]">
                        {data.metrics.e2e_latency_p95_ms.reason}
                      </div>
                    </div>
                  )}

                  {/* Metric 2: Abstention Rate */}
                  {data.metrics.abstention_rate && (
                    <div className="p-4 rounded-xl bg-[#141620] border border-white/[0.06] flex flex-col justify-between space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-xs font-medium text-white">
                          <HelpCircle className="w-3.5 h-3.5 text-amber-400" />
                          <span>Abstention Rate</span>
                        </div>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-mono border ${getMetricStatusStyle(data.metrics.abstention_rate.status)}`}>
                          {data.metrics.abstention_rate.status}
                        </span>
                      </div>

                      <div className="space-y-1">
                        <div className="text-xl font-bold font-mono text-white">
                          {data.metrics.abstention_rate.recent_value !== null ? `${(data.metrics.abstention_rate.recent_value * 100).toFixed(1)}%` : "—"}
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-neutral-400">
                          <span>Baseline: {data.metrics.abstention_rate.baseline_value !== null ? `${(data.metrics.abstention_rate.baseline_value * 100).toFixed(1)}%` : "None"}</span>
                          {data.metrics.abstention_rate.delta !== null && (
                            <span className="font-mono text-neutral-300">
                              {data.metrics.abstention_rate.delta > 0 ? "+" : ""}{(data.metrics.abstention_rate.delta * 100).toFixed(1)} pts
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="text-[11px] text-neutral-400 pt-2 border-t border-white/[0.04]">
                        {data.metrics.abstention_rate.reason}
                      </div>
                    </div>
                  )}

                  {/* Metric 3: HIGH Confidence Rate */}
                  {data.metrics.high_confidence_rate && (
                    <div className="p-4 rounded-xl bg-[#141620] border border-white/[0.06] flex flex-col justify-between space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-xs font-medium text-white">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                          <span>HIGH-Confidence Rate</span>
                        </div>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-mono border ${getMetricStatusStyle(data.metrics.high_confidence_rate.status)}`}>
                          {data.metrics.high_confidence_rate.status}
                        </span>
                      </div>

                      <div className="space-y-1">
                        <div className="text-xl font-bold font-mono text-white">
                          {data.metrics.high_confidence_rate.recent_value !== null ? `${(data.metrics.high_confidence_rate.recent_value * 100).toFixed(1)}%` : "—"}
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-neutral-400">
                          <span>Baseline: {data.metrics.high_confidence_rate.baseline_value !== null ? `${(data.metrics.high_confidence_rate.baseline_value * 100).toFixed(1)}%` : "None"}</span>
                          {data.metrics.high_confidence_rate.delta !== null && (
                            <span className="font-mono text-neutral-300">
                              {data.metrics.high_confidence_rate.delta > 0 ? "+" : ""}{(data.metrics.high_confidence_rate.delta * 100).toFixed(1)} pts
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="text-[11px] text-neutral-400 pt-2 border-t border-white/[0.04]">
                        {data.metrics.high_confidence_rate.reason}
                      </div>
                    </div>
                  )}

                  {/* Metric 4: Human Agreement Rate */}
                  {data.metrics.human_agreement_rate && (
                    <div className="p-4 rounded-xl bg-[#141620] border border-white/[0.06] flex flex-col justify-between space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-xs font-medium text-white">
                          <ShieldCheck className="w-3.5 h-3.5 text-purple-400" />
                          <span>Human Agreement</span>
                        </div>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-mono border ${getMetricStatusStyle(data.metrics.human_agreement_rate.status)}`}>
                          {data.metrics.human_agreement_rate.status}
                        </span>
                      </div>

                      <div className="space-y-1">
                        <div className="text-xl font-bold font-mono text-white">
                          {data.metrics.human_agreement_rate.recent_value !== null ? `${(data.metrics.human_agreement_rate.recent_value * 100).toFixed(1)}%` : "N/A"}
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-neutral-400">
                          <span>Baseline: {data.metrics.human_agreement_rate.baseline_value !== null ? `${(data.metrics.human_agreement_rate.baseline_value * 100).toFixed(1)}%` : "None"}</span>
                          {data.metrics.human_agreement_rate.delta !== null && (
                            <span className="font-mono text-neutral-300">
                              {data.metrics.human_agreement_rate.delta > 0 ? "+" : ""}{(data.metrics.human_agreement_rate.delta * 100).toFixed(1)} pts
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="text-[11px] text-neutral-400 pt-2 border-t border-white/[0.04]">
                        {data.metrics.human_agreement_rate.reason}
                      </div>
                    </div>
                  )}

                  {/* Metric 5: Citation Violation Rate */}
                  {data.metrics.citation_violation_rate && (
                    <div className="p-4 rounded-xl bg-[#141620] border border-white/[0.06] flex flex-col justify-between space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-xs font-medium text-white">
                          <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
                          <span>Citation Violations</span>
                        </div>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-mono border ${getMetricStatusStyle(data.metrics.citation_violation_rate.status)}`}>
                          {data.metrics.citation_violation_rate.status}
                        </span>
                      </div>

                      <div className="space-y-1">
                        <div className="text-xl font-bold font-mono text-white">
                          {data.metrics.citation_violation_rate.recent_value !== null ? `${(data.metrics.citation_violation_rate.recent_value * 100).toFixed(1)}%` : "—"}
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-neutral-400">
                          <span>Baseline: {data.metrics.citation_violation_rate.baseline_value !== null ? `${(data.metrics.citation_violation_rate.baseline_value * 100).toFixed(1)}%` : "None"}</span>
                          {data.metrics.citation_violation_rate.delta !== null && (
                            <span className="font-mono text-neutral-300">
                              {data.metrics.citation_violation_rate.delta > 0 ? "+" : ""}{(data.metrics.citation_violation_rate.delta * 100).toFixed(1)} pts
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="text-[11px] text-neutral-400 pt-2 border-t border-white/[0.04]">
                        {data.metrics.citation_violation_rate.reason}
                      </div>
                    </div>
                  )}

                  {/* Metric 6: E9 Precedent Relevance */}
                  {data.metrics.e9_retrieval_relevance && (
                    <div className="p-4 rounded-xl bg-[#141620] border border-white/[0.06] flex flex-col justify-between space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-xs font-medium text-white">
                          <Database className="w-3.5 h-3.5 text-cyan-400" />
                          <span>E9 Precedent Relevance</span>
                        </div>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-mono border ${getMetricStatusStyle(data.metrics.e9_retrieval_relevance.status)}`}>
                          {data.metrics.e9_retrieval_relevance.status}
                        </span>
                      </div>

                      <div className="space-y-1">
                        <div className="text-xl font-bold font-mono text-white">
                          {data.metrics.e9_retrieval_relevance.recent_value !== null ? data.metrics.e9_retrieval_relevance.recent_value.toFixed(4) : "—"}
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-neutral-400">
                          <span>Baseline: {data.metrics.e9_retrieval_relevance.baseline_value !== null ? data.metrics.e9_retrieval_relevance.baseline_value.toFixed(4) : "None"}</span>
                          {data.metrics.e9_retrieval_relevance.delta !== null && (
                            <span className="font-mono text-neutral-300">
                              {data.metrics.e9_retrieval_relevance.delta > 0 ? "+" : ""}{data.metrics.e9_retrieval_relevance.delta.toFixed(4)}
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="text-[11px] text-neutral-400 pt-2 border-t border-white/[0.04]">
                        {data.metrics.e9_retrieval_relevance.reason}
                      </div>
                    </div>
                  )}

                </div>
              </div>
            </>
          )}

        </div>

        {/* Footer */}
        <div className="px-6 py-3.5 border-t border-white/[0.06] bg-white/[0.01] flex items-center justify-between text-xs text-neutral-400">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>Operational monitoring active · Continuous drift awareness</span>
          </div>
          <button
            onClick={onClose}
            className="px-3.5 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-white font-medium transition-colors cursor-pointer"
          >
            Close
          </button>
        </div>

      </div>
    </div>
  )
}
