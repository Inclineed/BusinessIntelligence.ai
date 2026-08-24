import React, { useState, useRef, useEffect } from "react"
import { SCENARIO_CATALOG, ScenarioCatalogItem } from "../../lib/defaultData"
import { ChevronDown, Check, ShieldCheck, Sparkles, AlertCircle } from "lucide-react"
import { PersonaType } from "../../types/investigation"

interface ScenarioSelectorProps {
  selectedScenarioId: string
  onSelectScenario: (scenarioId: string) => void
  disabled?: boolean
}

export const ScenarioSelector: React.FC<ScenarioSelectorProps> = ({
  selectedScenarioId,
  onSelectScenario,
  disabled = false,
}) => {
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const activeScenario =
    SCENARIO_CATALOG.find((s) => s.id === selectedScenarioId) || SCENARIO_CATALOG[0]

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-between gap-3 px-3.5 py-2 rounded-xl bg-[#0E0F16] border border-white/[0.08] hover:border-emerald-500/40 transition-all text-left group min-w-[280px] max-w-[380px] focus:outline-none focus:ring-1 focus:ring-emerald-500/50 shadow-sm"
      >
        <div className="flex items-center gap-2.5 truncate">
          <span className="px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-400 font-mono font-bold text-xs border border-emerald-500/20">
            {activeScenario.id}
          </span>
          <div className="truncate">
            <div className="text-xs font-semibold text-white truncate">{activeScenario.label}</div>
            <div className="text-[10px] text-neutral-400 truncate">{activeScenario.domain}</div>
          </div>
        </div>
        <ChevronDown
          className={`w-4 h-4 text-neutral-400 transition-transform duration-200 flex-shrink-0 group-hover:text-white ${
            isOpen ? "rotate-180 text-emerald-400" : ""
          }`}
        />
      </button>

      {isOpen && (
        <div className="absolute right-0 top-full mt-2 w-[380px] max-h-[420px] overflow-y-auto rounded-2xl bg-[#12131D] border border-white/[0.12] shadow-2xl p-2 z-50 space-y-1 backdrop-blur-xl">
          <div className="px-2.5 py-1.5 text-[10px] font-mono font-bold uppercase tracking-wider text-neutral-400 border-b border-white/[0.06] mb-1">
            Available Scenarios ({SCENARIO_CATALOG.length})
          </div>

          {SCENARIO_CATALOG.map((item) => {
            const isSelected = item.id === selectedScenarioId
            return (
              <div
                key={item.id}
                onClick={() => {
                  onSelectScenario(item.id)
                  setIsOpen(false)
                }}
                className={`p-2.5 rounded-xl cursor-pointer transition-all flex items-start justify-between gap-3 ${
                  isSelected
                    ? "bg-emerald-500/10 border border-emerald-500/30 text-white"
                    : "hover:bg-white/[0.04] text-neutral-300 hover:text-white border border-transparent"
                }`}
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span
                      className={`px-2 py-0.5 rounded text-[11px] font-mono font-bold ${
                        isSelected
                          ? "bg-emerald-500 text-black"
                          : "bg-white/[0.06] text-neutral-300"
                      }`}
                    >
                      {item.id}
                    </span>
                    <span className="text-xs font-bold text-white">{item.label}</span>
                  </div>
                  <div className="text-[11px] text-neutral-400 leading-snug line-clamp-1">
                    {item.description}
                  </div>
                  <div className="text-[10px] text-emerald-400/80 font-medium">
                    {item.domain}
                  </div>
                </div>

                {isSelected && (
                  <Check className="w-4 h-4 text-emerald-400 flex-shrink-0 mt-1" />
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

interface PersonaSelectorProps {
  selectedPersona: PersonaType
  onSelectPersona: (persona: PersonaType) => void
  disabled?: boolean
}

export const PersonaSelector: React.FC<PersonaSelectorProps> = ({
  selectedPersona,
  onSelectPersona,
  disabled = false,
}) => {
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const personas: { id: PersonaType; label: string; desc: string }[] = [
    { id: "analyst", label: "Analyst", desc: "Full evidence & raw metric telemetry access" },
    { id: "cfo", label: "CFO", desc: "Executive business & revenue impact aggregates" },
    { id: "manager", label: "Manager", desc: "Regional scope authorized boundaries" },
  ]

  const activePersona = personas.find((p) => p.id === selectedPersona) || personas[0]

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-between gap-2.5 px-3 py-2 rounded-xl bg-[#0E0F16] border border-white/[0.08] hover:border-emerald-500/40 transition-all text-left group min-w-[150px] focus:outline-none focus:ring-1 focus:ring-emerald-500/50 shadow-sm"
      >
        <div className="flex items-center gap-2 truncate">
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
          <span className="text-xs font-semibold text-white capitalize">{activePersona.label}</span>
        </div>
        <ChevronDown
          className={`w-3.5 h-3.5 text-neutral-400 transition-transform duration-200 flex-shrink-0 group-hover:text-white ${
            isOpen ? "rotate-180 text-emerald-400" : ""
          }`}
        />
      </button>

      {isOpen && (
        <div className="absolute right-0 top-full mt-2 w-[240px] rounded-2xl bg-[#12131D] border border-white/[0.12] shadow-2xl p-2 z-50 space-y-1 backdrop-blur-xl">
          <div className="px-2.5 py-1 text-[10px] font-mono font-bold uppercase tracking-wider text-neutral-400 border-b border-white/[0.06] mb-1">
            Access Scope
          </div>

          {personas.map((p) => {
            const isSelected = p.id === selectedPersona
            return (
              <div
                key={p.id}
                onClick={() => {
                  onSelectPersona(p.id)
                  setIsOpen(false)
                }}
                className={`p-2 rounded-xl cursor-pointer transition-all flex items-center justify-between gap-2 ${
                  isSelected
                    ? "bg-emerald-500/10 border border-emerald-500/30 text-white"
                    : "hover:bg-white/[0.04] text-neutral-300 hover:text-white border border-transparent"
                }`}
              >
                <div>
                  <div className="text-xs font-bold text-white capitalize">{p.label}</div>
                  <div className="text-[10px] text-neutral-400 leading-tight">{p.desc}</div>
                </div>
                {isSelected && <Check className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
