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
          bg: "bg-[#4E8569]/20 border-[#4E8569]/40 text-[#78AC91]",
          icon: <CheckCircle2 className="w-4 h-4 text-[#4E8569]" />,
          label: "HEALTHY",
        }
      case "WATCH":
        return {
          bg: "bg-[#6B9BB0]/20 border-[#6B9BB0]/40 text-[#6B9BB0]",
          icon: <AlertTriangle className="w-4 h-4 text-[#6B9BB0]" />,
          label: "WATCH",
        }
      case "DEGRADED":
        return {
          bg: "bg-[#D8453A]/20 border-[#D8453A]/40 text-[#E56B62]",
          icon: <AlertOctagon className="w-4 h-4 text-[#D8453A]" />,
          label: "DEGRADED",
        }
      default:
        return {
          bg: "bg-[#2B2B2B] border-[#444444] text-[#9E9788]",
          icon: <HelpCircle className="w-4 h-4 text-[#9E9788]" />,
          label: "INSUFFICIENT DATA",
        }
    }
  }

  const getMetricStatusStyle = (mStatus: string) => {
    switch (mStatus) {
      case "HEALTHY":
        return "text-[#78AC91] bg-[#4E8569]/15 border-[#4E8569]/30"
      case "WATCH":
        return "text-[#6B9BB0] bg-[#6B9BB0]/15 border-[#6B9BB0]/30"
      case "DEGRADED":
        return "text-[#E56B62] bg-[#D8453A]/15 border-[#D8453A]/30"
      default:
        return "text-[#9E9788] bg-[#222222] border-[#333333]"
    }
  }

  const overallBadge = data ? getStatusBadge(data.status) : null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="bg-[#181818] border border-[#2E2E2E] rounded-2xl w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col shadow-2xl">
        
        {/* Header */}
        <div className="px-6 py-5 border-b border-[#2E2E2E] flex items-center justify-between bg-[#1C1C1C]">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#4E8569]/15 border border-[#4E8569]/30 flex items-center justify-center text-[#4E8569]">
              <Activity className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h2 className="text-base font-semibold text-[#F4EEE0]">Continuous Evaluation &amp; System Health</h2>
                {overallBadge && (
                  <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono font-medium border ${overallBadge.bg}`}>
                    {overallBadge.icon}
                    {overallBadge.label}
                  </span>
                )}
              </div>
              <p className="text-xs text-[#9E9788]">On-demand operational monitoring and drift telemetry across 50-run count-based windows</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={fetchHealth}
              disabled={isLoading}
              className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-[#9E9788] hover:text-[#F4EEE0] transition-colors cursor-pointer disabled:opacity-50"
              title="Refresh Health"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
            </button>
            <button
              onClick={onClose}
              className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-[#9E9788] hover:text-[#F4EEE0] transition-colors cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1 custom-scrollbar">
          {isLoading && !data && (
            <div className="py-20 flex flex-col items-center justify-center text-[#9E9788] gap-3">
              <RefreshCw className="w-6 h-6 animate-spin text-[#6B9BB0]" />
              <p className="text-xs font-mono">Computing on-demand continuous evaluation metrics...</p>
            </div>
          )}

          {error && (
            <div className="p-4 rounded-xl bg-[#D8453A]/15 border border-[#D8453A]/30 text-[#E56B62] text-xs flex items-center gap-2.5">
              <AlertOctagon className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {data && (
            <>
              {/* Window & Sample Context Bar */}
              <div className="p-4 rounded-xl bg-[#222222] border border-[#333333] flex flex-wrap items-center justify-between gap-4 text-xs font-mono">
                <div className="flex items-center gap-6">
                  <div>
                    <span className="text-[#9E9788] block text-[10px] uppercase">Sample Lifecycle</span>
                    <span className="text-[#F4EEE0] font-medium">{data.sample_state.replace(/_/g, " ")}</span>
                  </div>
                  <div className="h-6 w-px bg-[#333333]" />
                  <div>
                    <span className="text-[#9E9788] block text-[10px] uppercase">Recent Window</span>
                    <span className="text-[#F4EEE0] font-medium">{data.recent_window_size} runs</span>
                  </div>
                  <div className="h-6 w-px bg-[#333333]" />
                  <div>
                    <span className="text-[#9E9788] block text-[10px] uppercase">Baseline Window</span>
                    <span className="text-[#F4EEE0] font-medium">{data.baseline_window_size} runs</span>
                  </div>
                  <div className="h-6 w-px bg-[#333333]" />
                  <div>
                    <span className="text-[#9E9788] block text-[10px] uppercase">Total Indexed</span>
                    <span className="text-[#F4EEE0] font-medium">{data.total_investigations} completed</span>
                  </div>
                </div>

                <div className="text-right text-[#9E9788] text-[11px]">
                  Generated: {new Date(data.generated_at).toLocaleTimeString()}
                </div>
              </div>

              {/* Status Summary Banner */}
              <div className={`p-4 rounded-xl border ${overallBadge?.bg} flex items-start gap-3`}>
                <div className="mt-0.5">{overallBadge?.icon}</div>
                <div className="space-y-0.5">
                  <div className="text-xs font-semibold text-[#F4EEE0]">Health Summary</div>
                  <div className="text-xs opacity-90 text-[#D1C9B8]">{data.summary_reason}</div>
                </div>
              </div>

              {/* 6 Core Metrics Grid */}
              <div className="space-y-3">
                <div className="text-xs font-semibold uppercase tracking-wider text-[#9E9788] font-mono">
                  Operational Monitoring Metrics (v1)
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
                  
                  {/* Metric 1: E2E Latency */}
                  {data.metrics.e2e_latency_p95_ms && (
                    <div className="p-4 rounded-xl bg-[#222222] border border-[#333333] flex flex-col justify-between space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-xs font-medium text-[#F4EEE0]">
                          <Clock className="w-3.5 h-3.5 text-[#6B9BB0]" />
                          <span>E2E Latency (p95)</span>
                        </div>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-mono border ${getMetricStatusStyle(data.metrics.e2e_latency_p95_ms.status)}`}>
                          {data.metrics.e2e_latency_p95_ms.status}
                        </span>
                      </div>

                      <div className="space-y-1">
                        <div className="text-xl font-bold font-mono text-[#F4EEE0]">
                          {data.metrics.e2e_latency_p95_ms.recent_value !== null ? `${(data.metrics.e2e_latency_p95_ms.recent_value / 1000).toFixed(2)}s` : "—"}
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-[#9E9788] font-mono">
                          <span>Baseline: {data.metrics.e2e_latency_p95_ms.baseline_value !== null ? `${(data.metrics.e2e_latency_p95_ms.baseline_value / 1000).toFixed(2)}s` : "None"}</span>
                          {data.metrics.e2e_latency_p95_ms.delta !== null && (
                            <span className={data.metrics.e2e_latency_p95_ms.delta > 0 ? "text-[#D8453A]" : "text-[#4E8569]"}>
                              {data.metrics.e2e_latency_p95_ms.delta > 0 ? "+" : ""}{(data.metrics.e2e_latency_p95_ms.delta / 1000).toFixed(2)}s
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="text-[11px] text-[#9E9788] pt-2 border-t border-white/[0.04]">
                        {data.metrics.e2e_latency_p95_ms.reason}
                      </div>
                    </div>
                  )}

                  {/* Metric 2: Abstention Rate */}
                  {data.metrics.abstention_rate && (
                    <div className="p-4 rounded-xl bg-[#222222] border border-[#333333] flex flex-col justify-between space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-xs font-medium text-[#F4EEE0]">
                          <HelpCircle className="w-3.5 h-3.5 text-[#6B9BB0]" />
                          <span>Abstention Rate</span>
                        </div>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-mono border ${getMetricStatusStyle(data.metrics.abstention_rate.status)}`}>
                          {data.metrics.abstention_rate.status}
                        </span>
                      </div>

                      <div className="space-y-1">
                        <div className="text-xl font-bold font-mono text-[#F4EEE0]">
                          {data.metrics.abstention_rate.recent_value !== null ? `${(data.metrics.abstention_rate.recent_value * 100).toFixed(1)}%` : "—"}
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-[#9E9788] font-mono">
                          <span>Baseline: {data.metrics.abstention_rate.baseline_value !== null ? `${(data.metrics.abstention_rate.baseline_value * 100).toFixed(1)}%` : "None"}</span>
                          {data.metrics.abstention_rate.delta !== null && (
                            <span className="text-[#D1C9B8]">
                              {data.metrics.abstention_rate.delta > 0 ? "+" : ""}{(data.metrics.abstention_rate.delta * 100).toFixed(1)} pts
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="text-[11px] text-[#9E9788] pt-2 border-t border-white/[0.04]">
                        {data.metrics.abstention_rate.reason}
                      </div>
                    </div>
                  )}

                  {/* Metric 3: HIGH Confidence Rate */}
                  {data.metrics.high_confidence_rate && (
                    <div className="p-4 rounded-xl bg-[#222222] border border-[#333333] flex flex-col justify-between space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-xs font-medium text-[#F4EEE0]">
                          <CheckCircle2 className="w-3.5 h-3.5 text-[#4E8569]" />
                          <span>HIGH-Confidence Rate</span>
                        </div>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-mono border ${getMetricStatusStyle(data.metrics.high_confidence_rate.status)}`}>
                          {data.metrics.high_confidence_rate.status}
                        </span>
                      </div>

                      <div className="space-y-1">
                        <div className="text-xl font-bold font-mono text-[#F4EEE0]">
                          {data.metrics.high_confidence_rate.recent_value !== null ? `${(data.metrics.high_confidence_rate.recent_value * 100).toFixed(1)}%` : "—"}
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-[#9E9788] font-mono">
                          <span>Baseline: {data.metrics.high_confidence_rate.baseline_value !== null ? `${(data.metrics.high_confidence_rate.baseline_value * 100).toFixed(1)}%` : "None"}</span>
                          {data.metrics.high_confidence_rate.delta !== null && (
                            <span className="text-[#D1C9B8]">
                              {data.metrics.high_confidence_rate.delta > 0 ? "+" : ""}{(data.metrics.high_confidence_rate.delta * 100).toFixed(1)} pts
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="text-[11px] text-[#9E9788] pt-2 border-t border-white/[0.04]">
                        {data.metrics.high_confidence_rate.reason}
                      </div>
                    </div>
                  )}

                  {/* Metric 4: Human Agreement Rate */}
                  {data.metrics.human_agreement_rate && (
                    <div className="p-4 rounded-xl bg-[#222222] border border-[#333333] flex flex-col justify-between space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-xs font-medium text-[#F4EEE0]">
                          <ShieldCheck className="w-3.5 h-3.5 text-[#6B9BB0]" />
                          <span>Human Agreement</span>
                        </div>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-mono border ${getMetricStatusStyle(data.metrics.human_agreement_rate.status)}`}>
                          {data.metrics.human_agreement_rate.status}
                        </span>
                      </div>

                      <div className="space-y-1">
                        <div className="text-xl font-bold font-mono text-[#F4EEE0]">
                          {data.metrics.human_agreement_rate.recent_value !== null ? `${(data.metrics.human_agreement_rate.recent_value * 100).toFixed(1)}%` : "N/A"}
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-[#9E9788] font-mono">
                          <span>Baseline: {data.metrics.human_agreement_rate.baseline_value !== null ? `${(data.metrics.human_agreement_rate.baseline_value * 100).toFixed(1)}%` : "None"}</span>
                          {data.metrics.human_agreement_rate.delta !== null && (
                            <span className="text-[#D1C9B8]">
                              {data.metrics.human_agreement_rate.delta > 0 ? "+" : ""}{(data.metrics.human_agreement_rate.delta * 100).toFixed(1)} pts
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="text-[11px] text-[#9E9788] pt-2 border-t border-white/[0.04]">
                        {data.metrics.human_agreement_rate.reason}
                      </div>
                    </div>
                  )}

                  {/* Metric 5: Citation Violation Rate */}
                  {data.metrics.citation_violation_rate && (
                    <div className="p-4 rounded-xl bg-[#222222] border border-[#333333] flex flex-col justify-between space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-xs font-medium text-[#F4EEE0]">
                          <AlertTriangle className="w-3.5 h-3.5 text-[#D8453A]" />
                          <span>Citation Violations</span>
                        </div>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-mono border ${getMetricStatusStyle(data.metrics.citation_violation_rate.status)}`}>
                          {data.metrics.citation_violation_rate.status}
                        </span>
                      </div>

                      <div className="space-y-1">
                        <div className="text-xl font-bold font-mono text-[#F4EEE0]">
                          {data.metrics.citation_violation_rate.recent_value !== null ? `${(data.metrics.citation_violation_rate.recent_value * 100).toFixed(1)}%` : "—"}
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-[#9E9788] font-mono">
                          <span>Baseline: {data.metrics.citation_violation_rate.baseline_value !== null ? `${(data.metrics.citation_violation_rate.baseline_value * 100).toFixed(1)}%` : "None"}</span>
                          {data.metrics.citation_violation_rate.delta !== null && (
                            <span className="text-[#D1C9B8]">
                              {data.metrics.citation_violation_rate.delta > 0 ? "+" : ""}{(data.metrics.citation_violation_rate.delta * 100).toFixed(1)} pts
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="text-[11px] text-[#9E9788] pt-2 border-t border-white/[0.04]">
                        {data.metrics.citation_violation_rate.reason}
                      </div>
                    </div>
                  )}

                  {/* Metric 6: E9 Precedent Relevance */}
                  {data.metrics.e9_retrieval_relevance && (
                    <div className="p-4 rounded-xl bg-[#222222] border border-[#333333] flex flex-col justify-between space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-xs font-medium text-[#F4EEE0]">
                          <Database className="w-3.5 h-3.5 text-[#6B9BB0]" />
                          <span>E9 Precedent Relevance</span>
                        </div>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-mono border ${getMetricStatusStyle(data.metrics.e9_retrieval_relevance.status)}`}>
                          {data.metrics.e9_retrieval_relevance.status}
                        </span>
                      </div>

                      <div className="space-y-1">
                        <div className="text-xl font-bold font-mono text-[#F4EEE0]">
                          {data.metrics.e9_retrieval_relevance.recent_value !== null ? data.metrics.e9_retrieval_relevance.recent_value.toFixed(4) : "—"}
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-[#9E9788] font-mono">
                          <span>Baseline: {data.metrics.e9_retrieval_relevance.baseline_value !== null ? data.metrics.e9_retrieval_relevance.baseline_value.toFixed(4) : "None"}</span>
                          {data.metrics.e9_retrieval_relevance.delta !== null && (
                            <span className="text-[#D1C9B8]">
                              {data.metrics.e9_retrieval_relevance.delta > 0 ? "+" : ""}{data.metrics.e9_retrieval_relevance.delta.toFixed(4)}
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="text-[11px] text-[#9E9788] pt-2 border-t border-white/[0.04]">
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
        <div className="px-6 py-3.5 border-t border-[#2E2E2E] bg-[#1C1C1C] flex items-center justify-between text-xs text-[#9E9788] font-mono">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#4E8569]" />
            <span>Operational monitoring active · Continuous drift awareness</span>
          </div>
          <button
            onClick={onClose}
            className="px-3.5 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-[#F4EEE0] font-medium transition-colors cursor-pointer"
          >
            Close
          </button>
        </div>

      </div>
    </div>
  )
}
