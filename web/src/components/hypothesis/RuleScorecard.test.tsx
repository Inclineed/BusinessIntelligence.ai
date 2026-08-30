import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import React from "react"
import { RuleScorecard } from "./RuleScorecard"
import { RuleResult, ScoredHypothesisItem, HypothesisItem } from "../../types/investigation"

describe("RuleScorecard", () => {
  const mockRules: RuleResult[] = [
    {
      rule_name: "timeline",
      verdict: "pass",
      rationale: "Release preceded latency spike.",
    },
    {
      rule_name: "contradiction",
      verdict: "pass",
      rationale: "Zero contradictory evidence records found.",
    },
  ]

  const mockScoredPass: ScoredHypothesisItem = {
    hypothesis_id: "H1",
    support_score: 0.8,
    contradiction_score: 0,
    rule_score: 0.9,
    final_audit_score: 0.75,
    audit_verdict: "VERIFIED",
    evidence_sufficiency_score: 1.0,
    evidence_sufficiency_level: "STRONG",
    rule_results: mockRules,
    root_cause_gate_passed: true,
    root_cause_evidence_ids: ["EV_REL_001"],
    root_cause_rationale: "Deployment logs confirm software release.",
  }

  const mockHypothesis: HypothesisItem = {
    hypothesis_id: "H1",
    statement: "Release defect",
    root_cause_type: "INTERNAL_RELEASE",
    affected_subsystem: "payment_gateway",
    proximal_mechanism: "connection_pool_exhaustion",
    symptom_kpis: ["hourly_conversion"],
    supporting_evidence_ids: ["EV_REL_001"],
    contradictory_evidence_ids: [],
  }

  it("renders Root-Cause Evidence Gate with GATE PASSED banner", () => {
    render(
      <RuleScorecard
        ruleResults={mockRules}
        scoredHypothesis={mockScoredPass}
        hypothesis={mockHypothesis}
      />
    )

    expect(screen.getByText("Root-Cause Evidence Gate")).toBeInTheDocument()
    expect(screen.getByText("GATE PASSED")).toBeInTheDocument()
    expect(screen.getByText("INTERNAL RELEASE")).toBeInTheDocument()
    expect(screen.getByText("EV_REL_001")).toBeInTheDocument()
    expect(screen.getByText("Deployment logs confirm software release.")).toBeInTheDocument()
  })

  it("renders Root-Cause Evidence Gate with GATE FAILED banner when gate fails", () => {
    const mockScoredFail: ScoredHypothesisItem = {
      ...mockScoredPass,
      root_cause_gate_passed: false,
      root_cause_rationale: "No deployment records found. Capped at MARGINAL.",
      root_cause_evidence_ids: [],
    }

    render(
      <RuleScorecard
        ruleResults={mockRules}
        scoredHypothesis={mockScoredFail}
        hypothesis={mockHypothesis}
      />
    )

    expect(screen.getByText("GATE FAILED (CAPPED AT MARGINAL)")).toBeInTheDocument()
    expect(screen.getByText("No deployment records found. Capped at MARGINAL.")).toBeInTheDocument()
  })
})
