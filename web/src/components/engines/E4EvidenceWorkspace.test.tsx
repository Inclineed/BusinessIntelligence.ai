import { describe, it, expect } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import React from "react"
import { E4EvidenceWorkspace } from "./E4EvidenceWorkspace"
import { InvestigationResult } from "../../types/investigation"

const mockCanonicalResult: InvestigationResult = {
  scenario_id: "INC_001",
  persona: "analyst",
  signals: [],
  contributions: [],
  hypotheses: [],
  scored: [],
  decision: {},
  evidence: [
    {
      id: "EV_CANONICAL_01",
      source_id: "payment_gateway",
      source_name: "Payment Gateway",
      entity: "checkout_service",
      observation: "Connection pool exhaustion observed at 14:18 UTC.",
      timestamp: "2026-08-27T14:18:00.000Z",
      source_reliability: 0.99,
      confidence: 0.94,
      relevance: 0.92,
      method: "SQL",
      raw_ref: "pg_stat_activity WHERE app_name = 'checkout_v43'",
      freshness_minutes: 3.5,
    },
    {
      id: "EV_CANONICAL_02",
      source_id: "support_tickets",
      source_name: "Support Tickets",
      entity: "zendesk",
      observation: "42 customer support tickets reporting checkout spinner freezing.",
      timestamp: "2026-08-27T14:20:00.000Z",
      source_reliability: 0.90,
      confidence: 0.88,
      method: "LLM",
      raw_ref: "zendesk_tickets_queue_tier1",
    }
  ]
}

describe("E4EvidenceWorkspace", () => {
  it("renders live canonical evidence without throwing", () => {
    render(<E4EvidenceWorkspace result={mockCanonicalResult} />)
    expect(screen.getByText(/STAGE E4 · GROUNDED EVIDENCE DOSSIER/i)).toBeInTheDocument()
    expect(screen.getByText(/Connection pool exhaustion/i)).toBeInTheDocument()
    expect(screen.getByText(/42 customer support tickets/i)).toBeInTheDocument()
  })

  it("opens the EvidenceInspectionModal on click with method lineage", () => {
    render(<E4EvidenceWorkspace result={mockCanonicalResult} />)
    const sqlRow = screen.getByText(/Connection pool exhaustion/i)
    fireEvent.click(sqlRow)

    expect(screen.getByText(/Method Provenance Lineage/i)).toBeInTheDocument()
    expect(screen.getByText(/SQL Normalization/i)).toBeInTheDocument()
    expect(screen.getByText(/Done/i)).toBeInTheDocument()
  })
})
