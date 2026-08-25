import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatMetricValue(kpiId: string, val: number | undefined | null): { formatted: string; unit: string } {
  if (val === undefined || val === null || isNaN(val)) {
    return { formatted: "—", unit: "" }
  }
  const lower = kpiId.toLowerCase()
  if (lower.includes("revenue") || lower.includes("sales") || lower.includes("arr")) {
    return {
      formatted: val >= 100 ? `$${val.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : `$${val.toFixed(2)}`,
      unit: "",
    }
  }
  if (lower.includes("rate") || lower.includes("conversion") || lower.includes("pct")) {
    const isDecimal = val <= 1.0 && val > 0
    return {
      formatted: `${(isDecimal ? val * 100 : val).toFixed(1)}%`,
      unit: "",
    }
  }
  if (lower.includes("latency") || lower.includes("duration")) {
    return {
      formatted: `${Math.round(val).toLocaleString()}`,
      unit: " ms",
    }
  }
  return {
    formatted: val.toLocaleString(undefined, { maximumFractionDigits: 2 }),
    unit: "",
  }
}

export function formatDelta(deltaPct: number | undefined | null): string {
  if (deltaPct === undefined || deltaPct === null || isNaN(deltaPct)) {
    return "0.0%"
  }
  return `${deltaPct > 0 ? "+" : ""}${deltaPct.toFixed(1)}%`
}

export function formatZScore(z: number | undefined | null): string {
  if (z === undefined || z === null || isNaN(z)) {
    return "—"
  }
  return `z = ${z > 0 ? "+" : ""}${z.toFixed(2)}σ`
}

export function cleanLLMTags(text: string): string {
  if (!text) return ""
  return text
    .replace(/\[LLM_NARRATIVE\]/g, "")
    .replace(/\[LLM\]/g, "")
    .replace(/\[SIMULATED\]/g, "")
    .replace(/\[RULES\]/g, "")
    .trim()
}

/**
 * Determines whether a metric change is adverse/unfavorable based on domain semantics:
 * - Higher is better (revenue, conversion, fill_rate, orders, margin): delta < 0 is adverse.
 * - Lower is better (latency, error_rate, failure_rate, churn, complaints): delta > 0 is adverse.
 */
export function isAdverseMetric(kpiId: string, deltaPct: number | undefined | null): boolean {
  if (deltaPct === undefined || deltaPct === null || isNaN(deltaPct) || deltaPct === 0) {
    return false
  }
  const lower = kpiId.toLowerCase()
  const isLowerBetter =
    lower.includes("latency") ||
    lower.includes("error") ||
    lower.includes("failure") ||
    lower.includes("churn") ||
    lower.includes("drop") ||
    lower.includes("timeout")

  return isLowerBetter ? deltaPct > 0 : deltaPct < 0
}
