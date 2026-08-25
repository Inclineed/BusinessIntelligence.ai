import { describe, it, expect } from "vitest"
import { cn, formatMetricValue, formatDelta, formatZScore, cleanLLMTags } from "./utils"

describe("utils", () => {
  describe("cn", () => {
    it("merges tailwind class names correctly", () => {
      expect(cn("px-2 py-1", "bg-red-500", { "text-white": true, "text-black": false })).toBe(
        "px-2 py-1 bg-red-500 text-white"
      )
    })

    it("resolves tailwind conflicts by keeping the latter class", () => {
      expect(cn("p-4", "p-2")).toBe("p-2")
    })
  })

  describe("formatMetricValue", () => {
    it("formats revenue values as currency", () => {
      expect(formatMetricValue("hourly_revenue", 12500)).toEqual({
        formatted: "$12,500",
        unit: "",
      })
      expect(formatMetricValue("hourly_revenue", 45.5)).toEqual({
        formatted: "$45.50",
        unit: "",
      })
    })

    it("formats rate and conversion values as percentages", () => {
      expect(formatMetricValue("hourly_conversion", 0.042)).toEqual({
        formatted: "4.2%",
        unit: "",
      })
      expect(formatMetricValue("failure_rate", 12.5)).toEqual({
        formatted: "12.5%",
        unit: "",
      })
    })

    it("formats latency in milliseconds", () => {
      expect(formatMetricValue("gateway_latency_15min", 245.8)).toEqual({
        formatted: "246",
        unit: " ms",
      })
    })

    it("handles undefined, null, or NaN gracefully", () => {
      expect(formatMetricValue("any_kpi", undefined)).toEqual({
        formatted: "—",
        unit: "",
      })
      expect(formatMetricValue("any_kpi", NaN)).toEqual({
        formatted: "—",
        unit: "",
      })
    })
  })

  describe("formatDelta", () => {
    it("formats positive deltas with a plus sign", () => {
      expect(formatDelta(14.2)).toBe("+14.2%")
    })

    it("formats negative deltas with a minus sign", () => {
      expect(formatDelta(-8.7)).toBe("-8.7%")
    })

    it("formats zero or null deltas safely", () => {
      expect(formatDelta(0)).toBe("0.0%")
      expect(formatDelta(null)).toBe("0.0%")
    })
  })

  describe("formatZScore", () => {
    it("formats standard deviation z-scores with sigma notation", () => {
      expect(formatZScore(3.45)).toBe("z = +3.45σ")
      expect(formatZScore(-2.1)).toBe("z = -2.10σ")
    })

    it("handles undefined or NaN gracefully", () => {
      expect(formatZScore(undefined)).toBe("—")
      expect(formatZScore(NaN)).toBe("—")
    })
  })

  describe("cleanLLMTags", () => {
    it("strips internal method tags from narrative text", () => {
      const raw = "[LLM_NARRATIVE] This incident was caused by [SIMULATED] connection pool saturation."
      expect(cleanLLMTags(raw)).toBe("This incident was caused by  connection pool saturation.")
    })
  })
})
