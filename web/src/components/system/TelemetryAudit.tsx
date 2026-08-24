import React, { useState } from "react"
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Cell } from "recharts"
import { FileText, Cpu, CheckCircle2, Clock, DollarSign, Send } from "lucide-react"
import { TelemetryData } from "../../types/investigation"
import { submitFeedback } from "../../lib/api"

interface TelemetryAuditProps {
  telemetry?: TelemetryData
  methodOwnership?: Record<string, string | string[]>
  investigationId?: string
}

const LLM_ENGINES = new Set(["hypothesis", "decision", "memory", "challenge"])

export const TelemetryAudit: React.FC<TelemetryAuditProps> = ({
  telemetry,
  methodOwnership = {},
  investigationId,
}) => {
  const [feedbackText, setFeedbackText] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitStatus, setSubmitStatus] = useState<{ success?: boolean; message?: string } | null>(null)

  const latency = telemetry?.latency_ms_by_engine || {}
  const totalMs = Object.values(latency).reduce((acc, v) => acc + (typeof v === "number" ? v : 0), 0)
  const llmMs = Object.entries(latency)
    .filter(([k]) => LLM_ENGINES.has(k.toLowerCase()))
    .reduce((acc, [, v]) => acc + (typeof v === "number" ? v : 0), 0)
  const detMs = Math.max(0, totalMs - llmMs)
  const llmShare = totalMs > 0 ? (llmMs / totalMs) * 100 : 0

  // Latency chart data
  const chartData = Object.entries(latency)
    .filter(([, v]) => typeof v === "number")
    .map(([k, v]) => ({
      engine: k.toUpperCase(),
      ms: Number((v as number).toFixed(1)),
      isLLM: LLM_ENGINES.has(k.toLowerCase()),
    }))
    .sort((a, b) => b.ms - a.ms)

  const handleSubmitFeedback = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!feedbackText.trim()) return

    setIsSubmitting(true)
    setSubmitStatus(null)

    try {
      const res = await submitFeedback(investigationId || "LIVE_SESSION", feedbackText)
      if (res.success) {
        setSubmitStatus({ success: true, message: `Analyst feedback recorded (Feedback ID: ${res.feedback_id || "OK"})` })
        setFeedbackText("")
      } else {
        setSubmitStatus({ success: false, message: res.error || "Failed to submit feedback" })
      }
    } catch (err: any) {
      setSubmitStatus({ success: false, message: err.message || "Network error submitting feedback" })
    } finally {
      setIsSubmitting(false)
    }
  }

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const d = payload[0].payload
      return (
        <div className="bg-surface-raised border border-hairline-bright p-3 rounded-md shadow-xl text-xs font-mono">
          <div className="font-bold text-white mb-1">{d.engine} Engine</div>
          <div className="flex justify-between gap-4 text-muted-foreground">
            <span>Execution Latency:</span>
            <span className="text-white font-bold">{d.ms} ms</span>
          </div>
          <div className="flex justify-between gap-4 text-muted-foreground">
            <span>Type:</span>
            <span className={d.isLLM ? "text-semantic-cognitive font-bold" : "text-semantic-neutral font-bold"}>
              {d.isLLM ? "Cognitive LLM" : "Deterministic Code"}
            </span>
          </div>
        </div>
      )
    }
    return null
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-sm font-mono font-bold uppercase tracking-wider text-white flex items-center gap-2">
          <FileText className="w-4 h-4 text-semantic-neutral" />
          System Audit, Method Ownership & Telemetry
        </h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Verifiable execution trace proving strict separation between quantitative deterministic engines and cognitive narrative generation.
        </p>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 rounded-lg bg-surface border border-hairline shadow-card">
          <div className="text-[11px] font-mono text-muted-foreground uppercase flex items-center gap-1">
            <Clock className="w-3.5 h-3.5" /> WALL CLOCK RUNTIME
          </div>
          <div className="text-2xl font-bold font-mono text-white mt-1">
            {(totalMs / 1000).toFixed(2)}s
          </div>
        </div>

        <div className="p-4 rounded-lg bg-surface border border-hairline shadow-card">
          <div className="text-[11px] font-mono text-muted-foreground uppercase flex items-center gap-1">
            <Cpu className="w-3.5 h-3.5 text-semantic-neutral" /> DETERMINISTIC RUNTIME
          </div>
          <div className="text-2xl font-bold font-mono text-semantic-neutral mt-1">
            {(detMs / 1000).toFixed(2)}s
          </div>
        </div>

        <div className="p-4 rounded-lg bg-surface border border-hairline shadow-card">
          <div className="text-[11px] font-mono text-muted-foreground uppercase flex items-center gap-1">
            <Cpu className="w-3.5 h-3.5 text-semantic-cognitive" /> COGNITIVE LLM RUNTIME
          </div>
          <div className="text-2xl font-bold font-mono text-semantic-cognitive mt-1">
            {(llmMs / 1000).toFixed(2)}s <span className="text-xs text-muted-foreground font-normal">({llmShare.toFixed(0)}%)</span>
          </div>
        </div>

        <div className="p-4 rounded-lg bg-surface border border-hairline shadow-card">
          <div className="text-[11px] font-mono text-muted-foreground uppercase flex items-center gap-1">
            <DollarSign className="w-3.5 h-3.5 text-semantic-positive" /> INFERENCE COST
          </div>
          <div className="text-2xl font-bold font-mono text-semantic-positive mt-1">
            $0.00 <span className="text-xs text-muted-foreground font-normal">(Local Ollama)</span>
          </div>
        </div>
      </div>

      {/* Latency Waterfall & Method Ownership */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-6 p-5 rounded-lg bg-surface border border-hairline shadow-card">
          <div className="flex justify-between items-center mb-3">
            <span className="text-xs font-mono font-bold uppercase tracking-wider text-white">
              Engine Latency Waterfall (ms)
            </span>
            <div className="flex items-center gap-3 text-[10px] font-mono text-muted-foreground">
              <span className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 bg-semantic-neutral rounded-sm"></span> Deterministic
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 bg-semantic-cognitive rounded-sm"></span> Cognitive LLM
              </span>
            </div>
          </div>

          <div className="h-[230px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart layout="vertical" data={chartData} margin={{ top: 5, right: 30, left: 70, bottom: 5 }}>
                <XAxis
                  type="number"
                  tick={{ fill: "#64748B", fontSize: 10, fontFamily: "JetBrains Mono" }}
                  axisLine={{ stroke: "#1E2B3E" }}
                />
                <YAxis
                  type="category"
                  dataKey="engine"
                  tick={{ fill: "#94A3B8", fontSize: 10, fontFamily: "JetBrains Mono" }}
                  axisLine={{ stroke: "#1E2B3E" }}
                  tickLine={false}
                  width={80}
                />
                <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
                <Bar dataKey="ms" barSize={10} radius={[0, 2, 2, 0]}>
                  {chartData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.isLLM ? "#9061F9" : "#3F83F8"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="lg:col-span-6 p-5 rounded-lg bg-surface border border-hairline shadow-card flex flex-col justify-between">
          <div>
            <span className="text-xs font-mono font-bold uppercase tracking-wider text-white block mb-3">
              Engine Method Provenance Ledger
            </span>
            <div className="space-y-2 font-mono text-xs max-h-[220px] overflow-y-auto pr-1">
              {Object.entries(methodOwnership).map(([eng, tags]) => {
                const tagList = Array.isArray(tags) ? tags : [tags]
                return (
                  <div
                    key={eng}
                    className="flex justify-between items-center p-2 rounded bg-surface-raised border border-hairline-subtle"
                  >
                    <span className="text-white font-semibold">{eng.toUpperCase()}</span>
                    <div className="flex gap-1.5">
                      {tagList.map((t, idx) => (
                        <span
                          key={idx}
                          className="px-2 py-0.5 rounded text-[10px] bg-surface border border-hairline text-semantic-neutral"
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Analyst Feedback Submission */}
      <div className="p-5 rounded-lg bg-surface border border-hairline shadow-card space-y-3">
        <div className="flex justify-between items-center">
          <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-white">
            Human Analyst Validation & Precedent Feedback
          </h3>
          <span className="text-[11px] font-mono text-muted-foreground">
            ID: {investigationId || "ACTIVE_SESSION"}
          </span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Submitting resolution notes stamps the historical record with <b className="text-semantic-positive">human_validated=True</b> in ChromaDB, creating verified institutional memory.
        </p>

        <form onSubmit={handleSubmitFeedback} className="space-y-3 pt-2">
          <textarea
            rows={3}
            value={feedbackText}
            onChange={(e) => setFeedbackText(e.target.value)}
            placeholder="Confirm operational cause, rollback effectiveness, or domain caveats..."
            className="w-full bg-surface-raised border border-hairline hover:border-hairline-bright focus:border-semantic-neutral rounded-md p-3 text-xs text-white placeholder:text-muted-foreground outline-none transition-colors"
          />

          <div className="flex justify-between items-center">
            {submitStatus && (
              <span className={`text-xs font-mono ${submitStatus.success ? "text-semantic-positive" : "text-semantic-critical"}`}>
                {submitStatus.message}
              </span>
            )}
            {!submitStatus && <span></span>}

            <button
              type="submit"
              disabled={isSubmitting || !feedbackText.trim()}
              className="flex items-center gap-1.5 px-4 py-2 rounded-md bg-semantic-neutral hover:bg-blue-600 disabled:opacity-50 text-xs font-semibold text-white transition-colors"
            >
              <Send className="w-3.5 h-3.5" />
              <span>{isSubmitting ? "Submitting..." : "Submit Analyst Feedback"}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
