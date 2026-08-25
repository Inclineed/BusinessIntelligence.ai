import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import React from "react"
import { KPISignalGrid } from "./KPISignalGrid"
import { AnomalySignal } from "../../types/investigation"

describe("KPISignalGrid", () => {
  const mockSignals: AnomalySignal[] = [
    {
      kpi_id: "order_conversion_rate",
      observed: 0.021,
      expected: 0.035,
      delta_pct: -40.0,
      z_score: -3.85,
      is_anomaly: true,
      corroborated_by: ["payment_gateway_latency_p95"],
    },
    {
      kpi_id: "hourly_revenue",
      observed: 4820000,
      expected: 5610000,
      delta_pct: -14.08,
      z_score: -3.45,
      is_anomaly: true,
    },
  ]

  it("renders metric cards with tabular values, z-scores, and anomaly badges", () => {
    render(<KPISignalGrid signals={mockSignals} />)

    expect(screen.getByText(/order conversion rate/i)).toBeInTheDocument()
    expect(screen.getByText(/hourly revenue/i)).toBeInTheDocument()
    expect(screen.getAllByText("ANOMALY BREACH").length).toBe(2)
    expect(screen.getAllByText("[STATS]").length).toBe(2)
  })

  it("renders empty state gracefully when signals array is empty", () => {
    render(<KPISignalGrid signals={[]} />)
    expect(screen.getByText("No Signal Telemetry Available")).toBeInTheDocument()
  })
})
