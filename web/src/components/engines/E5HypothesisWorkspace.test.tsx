import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import React from "react"
import { E5HypothesisWorkspace } from "./E5HypothesisWorkspace"
import { InvestigationResult } from "../../types/investigation"

const mockResultWithCausalOntology: InvestigationResult = {
  scenario_id: "INC_001",
  persona: "analyst",
  contributions: [],
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
  hypotheses: [
    {
      hypothesis_id: "H1",
      statement: "An internal software release defect in the payment gateway client exhausted connection pools.",
      mechanism_tag: "connection_pool_exhaustion",
      root_cause_type: "INTERNAL_RELEASE",
      affected_subsystem: "payment_gateway",
      proximal_mechanism: "connection_pool_exhaustion",
      symptom_kpis: ["hourly_conversion", "gateway_latency_15min"],
      supporting_evidence_ids: ["EV_REL_001", "EV_GW_002"],
      contradictory_evidence_ids: [],
      reasoning: "Release notes align with latency surge timestamp.",
    },
  ],
  scored: [
    {
      hypothesis_id: "H1",
      support_score: 0.75,
      contradiction_score: 0.0,
      rule_score: 0.85,
      final_audit_score: 0.71,
      audit_verdict: "VERIFIED",
      evidence_sufficiency_score: 0.95,
      evidence_sufficiency_level: "STRONG",
      root_cause_gate_passed: true,
      root_cause_evidence_ids: ["EV_REL_001"],
      root_cause_rationale: "Release evidence verified.",
      rule_results: [
        {
          rule_name: "timeline",
          verdict: "pass",
          rationale: "Release preceded latency spike by 4 minutes.",
        },
      ],
      narrative: "Release v4.3 exhausted connection pool resources.",
    },
  ],
  decision: {
    winning_hypothesis_id: "H1",
    recommended_action: "Roll back release v4.3 checkout-service",
    abstained: false,
  },
  evidence: [
    {
      id: "EV_REL_001",
      source_id: "release_notes",
      method: "SQL",
      observation: "Checkout v4.3 deployed at 14:15 UTC.",
    },
  ],
}

describe("E5HypothesisWorkspace", () => {
  it("renders 4-layer causal ontology and mounted CausalReasoningTrail", () => {
    render(<E5HypothesisWorkspace result={mockResultWithCausalOntology} />)

    // Causal Reasoning Trail header
    expect(screen.getByText(/4-Layer Causal Ontology Trail/i)).toBeInTheDocument()

    // 4 Causal Layers in the Trail and Card
    expect(screen.getAllByText(/INTERNAL RELEASE/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/PAYMENT GATEWAY/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/CONNECTION POOL EXHAUSTION/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/hourly conversion/i).length).toBeGreaterThan(0)

    // Causal Evidence Citations grouped
    expect(screen.getByText(/Root-Cause Evidence:/i)).toBeInTheDocument()
    expect(screen.getByText("EV_REL_001")).toBeInTheDocument()
    expect(screen.getByText(/Mechanism \/ Symptom Evidence:/i)).toBeInTheDocument()
    expect(screen.getByText("EV_GW_002")).toBeInTheDocument()
  })

  it("renders abstention guard banner when hypotheses generation is suppressed", () => {
    const abstainedResult: InvestigationResult = {
      scenario_id: "INC_003",
      persona: "analyst",
      signals: [],
      contributions: [],
      evidence: [],
      hypotheses: [],
      scored: [],
      decision: {
        abstained: true,
        abstention_reason: "Sparse baseline (<14 days)",
      },
    }

    render(<E5HypothesisWorkspace result={abstainedResult} />)
    expect(screen.getByText(/SPARSE BASELINE HISTORY/i)).toBeInTheDocument()
    expect(screen.getByText(/GUARD ACTIVE/i)).toBeInTheDocument()
    expect(screen.getByText(/Statistical Cold-Start Guard/i)).toBeInTheDocument()
  })
})
