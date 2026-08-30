import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import React from "react"
import { E3DiagnosticWorkspace } from "./E3DiagnosticWorkspace"
import { InvestigationResult } from "../../types/investigation"

describe("E3DiagnosticWorkspace", () => {
  const mockResult: InvestigationResult = {
    scenario_id: "INC_001",
    persona: "analyst",
    signals: [
      {
        kpi_id: "gateway_latency_15min",
        observed: 450,
        expected: 80,
        delta_pct: 462.5,
        z_score: 4.88,
        is_anomaly: true,
      },
      {
        kpi_id: "hourly_conversion",
        observed: 1.2,
        expected: 20.1,
        delta_pct: -94.0,
        z_score: -4.2,
        is_anomaly: true,
      },
    ],
    materiality: [
      {
        kpi_id: "gateway_latency_15min",
        observed_value: 450,
        baseline_mean: 80,
        z_score: 4.88,
        delta_pct: 462.5,
        is_statistical_anomaly: true,
        business_materiality: "CRITICAL",
        priority_rank: 1,
        financial_impact: 125000,
      },
      {
        kpi_id: "hourly_conversion",
        observed_value: 1.2,
        baseline_mean: 20.1,
        z_score: -4.2,
        delta_pct: -94.0,
        is_statistical_anomaly: true,
        business_materiality: "CRITICAL",
        priority_rank: 2,
        financial_impact: 95000,
      },
    ],
    contributions: [
      {
        dimension: "device",
        segment: "android",
        contribution_pct: 52.0,
        segment_delta_pct: -85.0,
      },
      {
        dimension: "device",
        segment: "ios",
        contribution_pct: 30.0,
        segment_delta_pct: -20.0,
      },
    ],
    hypotheses: [],
    scored: [],
    decision: {},
    evidence: [],
  }

  it("renders E2 -> E3 Context Bridge explanatory banner with actual API values", () => {
    render(<E3DiagnosticWorkspace result={mockResult} />)

    // Context Bridge text
    expect(screen.getByText(/Top overall anomaly:/i)).toBeInTheDocument()
    expect(screen.getByText("gateway_latency_15min")).toBeInTheDocument()
    expect(screen.getByText("hourly_conversion")).toBeInTheDocument()
    expect(
      screen.getByText(/Because this system-level KPI has no dimensional slices/i)
    ).toBeInTheDocument()

    // Breakdown table
    expect(screen.getAllByText(/android/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/52.0%/i).length).toBeGreaterThan(0)
  })
})
