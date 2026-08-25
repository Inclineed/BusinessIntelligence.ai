import React, { useState } from "react"
import { InvestigationResult, PersonaType, TelemetryData } from "../../types/investigation"
import { SCENARIO_CATALOG } from "../../lib/api"
import { formatMetricValue, formatDelta, isAdverseMetric } from "../../lib/utils"
import {
  Activity,
  AlertTriangle,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Cpu,
  Database,
  Globe,
  Radio,
  ShieldCheck,
  User,
  Zap,
} from "lucide-react"

interface LeftObservePanelProps {
  result: InvestigationResult
  activeScenarioId: string
  activePersona: PersonaType
  activeRegion: string
  currentStageNum: number
  isCollapsed: boolean
  telemetry?: TelemetryData
  onToggleCollapse: () => void
  onConfigChange: (scenarioId: string, persona: PersonaType, region: string) => void
  onOpenTelemetry: () => void
  onOpenHealth: () => void
}

export const LeftObservePanel: React.FC<LeftObservePanelProps> = ({
  result,
  activeScenarioId,
  activePersona,
  activeRegion,
  currentStageNum,
  isCollapsed,
  telemetry,
  onToggleCollapse,
  onConfigChange,
  onOpenTelemetry,
  onOpenHealth,
}) => {
  const [scenarioDropdownOpen, setScenarioDropdownOpen] = useState(false)
  const currentScenario =
    SCENARIO_CATALOG.find((s) => s.id === activeScenarioId) || SCENARIO_CATALOG[0]
  const primarySignal = result.signals?.[0]
  const isAnomaly = primarySignal?.is_anomaly ?? false
  const hasGuardAlerts = Boolean(
    primarySignal?.sparse_history ||
      primarySignal?.data_quality_suspect ||
      result.decision?.abstained
  )

  const formatLatency = (ms?: number) => {
    if (!ms || isNaN(ms)) return "—"
    return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`
  }

  const totalEngineLatency = telemetry?.latency_ms_by_engine
    ? Object.values(telemetry.latency_ms_by_engine).reduce((a, b) => a + b, 0)
    : undefined

  // -------------------------------------------------------------------------
  // Collapsed Rail View (~56px / w-14)
  // -------------------------------------------------------------------------
  if (isCollapsed) {
    return (
      <aside
        className="w-14 bg-[#181818] flex flex-col items-center py-2.5 border-r border-[#2E2E2E] shrink-0 z-30 justify-between transition-all duration-300 select-none"
        aria-label="Incident Context Rail"
      >
        {/* Top Section: Expand Toggle, Scenario Selector Popover, Persona */}
        <div className="flex flex-col items-center gap-2.5 w-full">
          <button
            onClick={onToggleCollapse}
            title="Expand Sidebar"
            className="w-8 h-8 rounded-lg bg-[#222222] hover:bg-[#2A2A2A] text-[#9E9788] hover:text-[#F4EEE0] flex items-center justify-center border border-[#333333] transition-colors cursor-pointer"
          >
            <ChevronRight className="w-4 h-4" />
          </button>

          <div className="w-8 h-px bg-[#2E2E2E] my-0.5" />

          {/* Scenario Indicator Icon + Interactive Selector Popover */}
          <div className="relative">
            <button
              onClick={() => setScenarioDropdownOpen(!scenarioDropdownOpen)}
              className={`w-9 h-9 rounded-xl flex items-center justify-center border cursor-pointer transition-all ${
                isAnomaly
                  ? "bg-[#D8453A]/20 border-[#D8453A]/50 text-[#E56B62] hover:border-[#D8453A]"
                  : "bg-[#4E8569]/20 border-[#4E8569]/50 text-[#78AC91] hover:border-[#4E8569]"
              }`}
              title={`Active: ${currentScenario.id} (${currentScenario.title}) — Click to switch incident`}
            >
              <Radio className="w-4 h-4 animate-pulse" />
            </button>

            {scenarioDropdownOpen && (
              <div className="absolute left-12 top-0 z-50 w-72 max-h-96 overflow-y-auto bg-[#1C1C1C] rounded-xl border border-[#333333] p-1.5 shadow-2xl custom-scrollbar">
                <div className="px-2 py-1 text-[10px] font-mono text-[#9E9788] uppercase tracking-wider border-b border-[#2E2E2E] mb-1">
                  Switch Incident Scenario
                </div>
                {SCENARIO_CATALOG.map((sc) => (
                  <button
                    key={sc.id}
                    onClick={() => {
                      onConfigChange(sc.id, activePersona, activeRegion)
                      setScenarioDropdownOpen(false)
                    }}
                    className={`w-full text-left p-2 rounded-lg text-xs transition-colors flex flex-col gap-0.5 cursor-pointer ${
                      sc.id === activeScenarioId
                        ? "bg-[#6B9BB0]/20 text-[#F4EEE0] border border-[#6B9BB0]/40"
                        : "hover:bg-white/[0.04] text-[#D1C9B8]"
                    }`}
                  >
                    <div className="flex items-center justify-between font-mono">
                      <span className="font-bold text-[#6B9BB0]">{sc.id}</span>
                      <span className="text-[10px] text-[#9E9788] px-1 rounded bg-black/40">
                        {sc.domain}
                      </span>
                    </div>
                    <div className="font-medium text-[#F4EEE0] truncate">{sc.title}</div>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Persona Quick Switch Icon */}
          <div className="relative group flex items-center justify-center">
            <div className="w-9 h-9 rounded-xl bg-[#222222] border border-[#333333] text-[#6B9BB0] flex items-center justify-center font-mono font-bold text-xs">
              {activePersona[0].toUpperCase()}
            </div>

            {/* Persona Switcher Tooltip Menu */}
            <div className="absolute left-12 top-0 z-50 hidden group-hover:flex flex-col w-44 p-2 rounded-xl bg-[#1C1C1C] border border-[#333333] shadow-2xl text-xs font-mono">
              <span className="text-[#9E9788] text-[10px] uppercase font-bold mb-1.5 px-1">
                Switch Persona Scope
              </span>
              {(["analyst", "cfo", "manager"] as PersonaType[]).map((p) => (
                <button
                  key={p}
                  onClick={() => onConfigChange(activeScenarioId, p, activeRegion)}
                  className={`px-2 py-1 rounded text-left capitalize transition-colors flex items-center justify-between cursor-pointer ${
                    activePersona === p
                      ? "bg-[#6B9BB0]/25 text-[#F4EEE0] font-bold"
                      : "text-[#9E9788] hover:text-[#F4EEE0] hover:bg-[#252525]"
                  }`}
                >
                  <span>{p}</span>
                  {activePersona === p && <span className="w-1.5 h-1.5 rounded-full bg-[#6B9BB0]" />}
                </button>
              ))}
            </div>
          </div>

          {/* Secondary Feeds Count Badge */}
          {result.signals && result.signals.length > 1 && (
            <div
              className="relative group flex items-center justify-center"
              title={`${result.signals.length - 1} Secondary Telemetry Streams`}
            >
              <div className="w-9 h-9 rounded-xl bg-[#222222] border border-[#333333] text-[#9E9788] group-hover:text-[#F4EEE0] flex flex-col items-center justify-center text-[10px] font-mono font-bold transition-colors">
                <Activity className="w-3.5 h-3.5 mb-0.5 text-[#6B9BB0]" />
                <span className="leading-none text-[9px]">{result.signals.length - 1}</span>
              </div>

              {/* Tooltip */}
              <div className="absolute left-12 top-0 z-50 hidden group-hover:flex flex-col w-56 p-2.5 rounded-lg bg-[#1C1C1C] border border-[#333333] shadow-xl text-xs text-[#F4EEE0] pointer-events-none">
                <span className="font-mono text-[10px] font-bold text-[#9E9788] uppercase mb-1">
                  Corroborating Telemetry
                </span>
                {result.signals.slice(1).map((s) => (
                  <div
                    key={s.kpi_id}
                    className="flex justify-between items-center text-[11px] font-mono py-0.5"
                  >
                    <span className="text-[#D1C9B8] truncate max-w-[120px]">
                      {s.kpi_id.replace(/_/g, " ")}
                    </span>
                    <span
                      className={
                        isAdverseMetric(s.kpi_id, s.delta_pct)
                          ? "text-[#E56B62] font-bold"
                          : "text-[#78AC91] font-bold"
                      }
                    >
                      {formatDelta(s.delta_pct)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Guard Alert Warning Icon */}
          {hasGuardAlerts && (
            <div
              className="relative group flex items-center justify-center"
              title="Guard Conditions Active"
            >
              <div className="w-8 h-8 rounded-lg bg-[#D8453A]/20 border border-[#D8453A]/40 text-[#E56B62] flex items-center justify-center">
                <AlertTriangle className="w-4 h-4" />
              </div>
              <div className="absolute left-12 top-0 z-50 hidden group-hover:flex flex-col w-52 p-2.5 rounded-lg bg-[#1C1C1C] border border-[#D8453A]/40 shadow-xl text-[11px] font-mono text-[#E56B62] pointer-events-none">
                <span className="font-bold mb-1">Active Guard Alerts:</span>
                {primarySignal?.sparse_history && <div>• Baseline &lt; 14 days</div>}
                {primarySignal?.data_quality_suspect && <div>• Quality index &lt; 0.80</div>}
                {result.decision?.abstained && <div>• Decision abstained</div>}
              </div>
            </div>
          )}
        </div>

        {/* Bottom Section: Telemetry & Health Modal Triggers */}
        <div className="flex flex-col items-center gap-2 w-full">
          {/* Telemetry Button */}
          <button
            onClick={onOpenTelemetry}
            className="w-9 h-9 rounded-xl bg-[#222222] hover:bg-[#2A2A2A] border border-[#333333] text-[#D1C9B8] flex items-center justify-center transition-colors cursor-pointer"
            title={`System Performance & Cost: ${formatLatency(totalEngineLatency)}`}
          >
            <Cpu className="w-4 h-4 text-[#6B9BB0]" />
          </button>

          {/* Health Button */}
          <button
            onClick={onOpenHealth}
            className="w-9 h-9 rounded-xl bg-[#222222] hover:bg-[#2A2A2A] border border-[#333333] text-[#4E8569] flex items-center justify-center transition-colors cursor-pointer"
            title="System Health & Drift Modal"
          >
            <Activity className="w-4 h-4" />
          </button>
        </div>
      </aside>
    )
  }

  // -------------------------------------------------------------------------
  // Expanded Sidebar View (288px / w-72)
  // -------------------------------------------------------------------------
  return (
    <aside className="w-72 lg:w-80 bg-[#181818] flex flex-col border-r border-[#2E2E2E] shrink-0 z-30 overflow-y-auto custom-scrollbar transition-all duration-300">
      {/* Top Header: Incident Context Selector & Collapse Button directly aligned */}
      <div className="p-3 border-b border-[#2E2E2E] flex justify-between items-center sticky top-0 bg-[#181818]/95 backdrop-blur-md z-20 gap-2">
        {/* Incident Catalog Selector Dropdown */}
        <div className="relative flex-1 min-w-0">
          <button
            onClick={() => setScenarioDropdownOpen(!scenarioDropdownOpen)}
            className="w-full flex items-center justify-between gap-1.5 px-2.5 py-1.5 rounded-lg bg-[#222222] hover:bg-[#2A2A2A] border border-[#333333] text-xs font-mono text-[#D1C9B8] transition-all cursor-pointer truncate"
            aria-expanded={scenarioDropdownOpen}
            aria-label="Select incident scenario"
          >
            <div className="flex items-center gap-1.5 truncate">
              <span className="text-[#6B9BB0] font-bold shrink-0">{currentScenario.id}</span>
              <span className="text-[#F4EEE0] truncate text-[11px]">{currentScenario.title}</span>
            </div>
            <ChevronDown className="w-3.5 h-3.5 text-[#9E9788] shrink-0" />
          </button>

          {/* Catalog Dropdown Menu */}
          {scenarioDropdownOpen && (
            <div className="absolute left-0 mt-1.5 w-72 max-h-96 overflow-y-auto bg-[#1C1C1C] rounded-xl border border-[#333333] p-1.5 shadow-2xl z-50 custom-scrollbar">
              <div className="px-2 py-1 text-[10px] font-mono text-[#9E9788] uppercase tracking-wider border-b border-[#2E2E2E] mb-1">
                Incident Catalog
              </div>
              {SCENARIO_CATALOG.map((sc) => (
                <button
                  key={sc.id}
                  onClick={() => {
                    onConfigChange(sc.id, activePersona, activeRegion)
                    setScenarioDropdownOpen(false)
                  }}
                  className={`w-full text-left p-2 rounded-lg text-xs transition-colors flex flex-col gap-0.5 cursor-pointer ${
                    sc.id === activeScenarioId
                      ? "bg-[#6B9BB0]/20 text-[#F4EEE0] border border-[#6B9BB0]/40"
                      : "hover:bg-white/[0.04] text-[#D1C9B8]"
                  }`}
                >
                  <div className="flex items-center justify-between font-mono">
                    <span className="font-bold text-[#6B9BB0]">{sc.id}</span>
                    <span className="text-[10px] text-[#9E9788] px-1 rounded bg-black/40">
                      {sc.domain}
                    </span>
                  </div>
                  <div className="font-medium text-[#F4EEE0] truncate">{sc.title}</div>
                  <div className="text-[10px] text-[#9E9788] truncate">{sc.description}</div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Inline Collapse Button */}
        <button
          onClick={onToggleCollapse}
          title="Collapse Sidebar (~56px Rail)"
          className="p-1.5 rounded-lg bg-[#222222] hover:bg-[#2A2A2A] text-[#9E9788] hover:text-[#F4EEE0] border border-[#333333] transition-colors cursor-pointer shrink-0"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
      </div>

      <div className="p-3.5 flex flex-col gap-3.5 flex-1 justify-between">
        <div className="space-y-3.5">
          {/* Persona Switcher Section */}
          <div className="space-y-1.5">
            <div className="flex justify-between items-center text-xs font-mono">
              <span className="text-[#9E9788] text-[10px] uppercase font-bold">
                Persona Perspective
              </span>
              <span className="text-[10px] px-1.5 py-0.2 rounded bg-[#6B9BB0]/20 text-[#6B9BB0] font-bold">
                {activePersona === "analyst" ? "UNRESTRICTED" : "RBAC SCOPED"}
              </span>
            </div>

            <div className="grid grid-cols-3 p-1 rounded-xl bg-[#222222] border border-[#333333] gap-1">
              {(["analyst", "cfo", "manager"] as PersonaType[]).map((p) => {
                const isActive = activePersona === p
                return (
                  <button
                    key={p}
                    onClick={() => onConfigChange(activeScenarioId, p, activeRegion)}
                    className={`py-1.5 px-2 rounded-lg text-xs font-mono capitalize transition-all cursor-pointer text-center ${
                      isActive
                        ? "bg-[#6B9BB0]/30 text-[#F4EEE0] font-bold border border-[#6B9BB0]/50 shadow-sm"
                        : "text-[#9E9788] hover:text-[#D1C9B8] hover:bg-[#2A2A2A]"
                    }`}
                    aria-pressed={isActive}
                  >
                    {p}
                  </button>
                )
              })}
            </div>

            {/* Region Input for Manager */}
            {activePersona === "manager" && (
              <div className="flex items-center justify-between bg-[#222222] border border-[#333333] px-3 py-1.5 rounded-xl text-xs font-mono animate-fade-in">
                <div className="flex items-center gap-1.5 text-[#9E9788]">
                  <Globe className="w-3.5 h-3.5" />
                  <span className="text-[11px]">Region Scope:</span>
                </div>
                <input
                  type="text"
                  value={activeRegion === "all" ? "us-east" : activeRegion}
                  onChange={(e) => onConfigChange(activeScenarioId, activePersona, e.target.value)}
                  placeholder="e.g. us-east"
                  className="w-20 bg-transparent text-[#F4EEE0] font-bold focus:outline-none text-right text-xs"
                />
              </div>
            )}
          </div>

          {/* Primary Scenario Details Card */}
          <div className="p-3.5 rounded-xl bg-[#222222] border border-[#333333] transition-colors relative overflow-hidden space-y-2">
            {/* Left indicator bar */}
            <div
              className={`absolute left-0 top-0 bottom-0 w-1 ${
                isAnomaly ? "bg-[#D8453A]" : "bg-[#4E8569]"
              }`}
            />

            <div className="flex items-center justify-between text-xs font-mono">
              <span className="font-bold text-[#F4EEE0]">{currentScenario.id}</span>
              <span
                className={`text-[10px] px-1.5 py-0.5 rounded font-mono uppercase font-bold ${
                  isAnomaly
                    ? "bg-[#D8453A]/20 text-[#E56B62]"
                    : "bg-[#4E8569]/20 text-[#78AC91]"
                }`}
              >
                {isAnomaly ? "Critical Anomaly" : "Nominal Signal"}
              </span>
            </div>

            <h3 className="text-xs font-bold text-[#F4EEE0] leading-snug">
              {currentScenario.title}
            </h3>

            <p className="text-[11px] text-[#D1C9B8] leading-relaxed">
              {currentScenario.description}
            </p>

            <div className="flex items-center justify-between font-mono text-[11px] pt-1 border-t border-white/[0.04]">
              <span className="text-[#9E9788]">
                Domain: <span className="text-[#D1C9B8]">{currentScenario.domain}</span>
              </span>
              <span className="text-[#9E9788]">
                Confidence:{" "}
                <span className="text-[#6B9BB0] font-bold">
                  {result.scored?.[0]?.final_score
                    ? `${Math.round(result.scored[0].final_score * 100)}%`
                    : "85%"}
                </span>
              </span>
            </div>
          </div>

          {/* Supporting Signals & Observations */}
          {result.signals && result.signals.length > 1 && (
            <div className="space-y-1.5">
              <span className="text-[10px] font-mono uppercase text-[#9E9788] tracking-wider block">
                Secondary Telemetry Feeds ({result.signals.length - 1})
              </span>
              {result.signals.slice(1).map((sig) => {
                const { formatted, unit } = formatMetricValue(sig.kpi_id, sig.observed)
                const delta = formatDelta(sig.delta_pct)
                const isAdverse = isAdverseMetric(sig.kpi_id, sig.delta_pct) || sig.is_anomaly
                return (
                  <div
                    key={sig.kpi_id}
                    className="p-2.5 rounded-lg bg-[#222222] border border-[#333333] text-xs font-mono space-y-1"
                  >
                    <div className="flex justify-between items-center">
                      <span className="text-[#D1C9B8] font-bold uppercase truncate max-w-[150px]">
                        {sig.kpi_id.replace(/_/g, " ")}
                      </span>
                      <span
                        className={
                          isAdverse
                            ? "text-[#E56B62] font-bold"
                            : "text-[#78AC91] font-bold"
                        }
                      >
                        {delta}
                      </span>
                    </div>
                    <div className="flex justify-between text-[11px] text-[#9E9788]">
                      <span>
                        Observed: {formatted}
                        {unit}
                      </span>
                      <span>z = {sig.z_score.toFixed(2)}σ</span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {/* Data Quality & System Guard Alerts */}
          {hasGuardAlerts && (
            <div className="p-3 rounded-lg bg-[#D8453A]/15 border border-[#D8453A]/30 text-[#E56B62] text-xs font-mono space-y-1.5">
              <div className="flex items-center gap-1.5 font-bold">
                <AlertTriangle className="w-3.5 h-3.5 text-[#D8453A]" />
                <span>Guard Conditions</span>
              </div>
              {primarySignal?.sparse_history && (
                <div className="text-[11px] text-[#E56B62]/90">
                  • Historical baseline &lt; 14 days
                </div>
              )}
              {primarySignal?.data_quality_suspect && (
                <div className="text-[11px] text-[#E56B62]/90">
                  • Data quality index &lt; 0.80
                </div>
              )}
              {result.decision?.abstained && (
                <div className="text-[11px] text-[#E56B62]/90">
                  • Automated decision abstention active
                </div>
              )}
            </div>
          )}
        </div>

        {/* Bottom Operations & Health Row */}
        <div className="grid grid-cols-2 gap-2 pt-3 border-t border-[#2E2E2E]">
          {/* Telemetry Button */}
          <button
            onClick={onOpenTelemetry}
            className="p-2.5 rounded-xl bg-[#222222] hover:bg-[#2A2A2A] border border-[#333333] flex flex-col justify-between text-left transition-colors cursor-pointer group"
            title="Open System Performance & Cost Drawer"
          >
            <div className="flex items-center justify-between text-[10px] font-mono text-[#9E9788]">
              <span>RUNTIME</span>
              <Cpu className="w-3.5 h-3.5 text-[#6B9BB0]" />
            </div>
            <div className="text-xs font-mono font-bold text-[#F4EEE0] mt-1 tabular-nums">
              {formatLatency(totalEngineLatency)}
            </div>
          </button>

          {/* Health Button */}
          <button
            onClick={onOpenHealth}
            className="p-2.5 rounded-xl bg-[#222222] hover:bg-[#2A2A2A] border border-[#333333] flex flex-col justify-between text-left transition-colors cursor-pointer group"
            title="Open Continuous Drift & Reliability Modal"
          >
            <div className="flex items-center justify-between text-[10px] font-mono text-[#9E9788]">
              <span>SYSTEM</span>
              <Activity className="w-3.5 h-3.5 text-[#4E8569]" />
            </div>
            <div className="text-xs font-mono font-bold text-[#4E8569] mt-1">
              NOMINAL
            </div>
          </button>
        </div>
      </div>
    </aside>
  )
}
