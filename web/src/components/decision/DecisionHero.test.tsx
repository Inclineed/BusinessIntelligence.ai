import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import React from "react"
import { DecisionHero } from "./DecisionHero"
import { DecisionPayload, OutcomeProjection } from "../../types/investigation"

describe("DecisionHero", () => {
  const mockDecision: DecisionPayload = {
    winning_hypothesis_id: "H1",
    recommended_action: "Roll back release v4.3 checkout-service",
    verification_metric: "Ensure gateway latency drops below 200ms within 5 min",
    persona_narrative: "Payment gateway connection exhaustion is confirmed root cause.",
    structured_recommendation: {
      driver: "Gateway connection exhaustion",
      controllable_lever: "Software Release Reversion",
      action: "Roll back release v4.3 checkout-service",
      expected_impact: "Projected 88.0% recovery",
      owner: "Platform Engineering",
      confidence: 0.94,
      monitoring_plan: "Ensure gateway latency drops below 200ms within 5 min",
      authorized_personas: ["analyst", "manager"]
    },
    abstained: false,
  }

  const mockOutcome: OutcomeProjection = {
    method: "SIMULATED",
    projected_recovery_pct: 88.0,
    projected_metric: "order_conversion_rate",
    disclaimer: "Simulated recovery projection based on synthetic calibration.",
  }

  it("renders winning decision action directive and verification metric", () => {
    render(<DecisionHero decision={mockDecision} outcome={mockOutcome} />)

    expect(screen.getByText("Roll back release v4.3 checkout-service")).toBeInTheDocument()
    expect(screen.getByText("Ensure gateway latency drops below 200ms within 5 min")).toBeInTheDocument()
    expect(screen.getByText("88.0%")).toBeInTheDocument()
    expect(screen.getByText("[STRUCTURED]")).toBeInTheDocument()
    expect(screen.getByText("Software Release Reversion")).toBeInTheDocument()
    expect(screen.getByText("Platform Engineering")).toBeInTheDocument()
    expect(screen.getByText("94%")).toBeInTheDocument()
  })

  it("renders explicit system abstention when abstained is true", () => {
    const abstainedDecision: DecisionPayload = {
      abstained: true,
      abstention_reason: "Sparse historical baseline data (<14 days)",
    }

    render(<DecisionHero decision={abstainedDecision} />)

    expect(screen.getByText("SYSTEM ABSTAINED")).toBeInTheDocument()
    expect(screen.getByText("Sparse historical baseline data (<14 days)")).toBeInTheDocument()
  })
})
