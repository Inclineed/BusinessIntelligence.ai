import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import React from "react"
import { PipelineRail } from "./PipelineRail"
import { DEFAULT_INC_001 } from "../../lib/defaultData"

describe("PipelineRail", () => {
  it("renders all 9 analytical stages from E1 to E9", () => {
    render(<PipelineRail result={DEFAULT_INC_001} />)

    expect(screen.getByText("E1")).toBeInTheDocument()
    expect(screen.getByText("E2")).toBeInTheDocument()
    expect(screen.getByText("E3")).toBeInTheDocument()
    expect(screen.getByText("E4")).toBeInTheDocument()
    expect(screen.getByText("E5")).toBeInTheDocument()
    expect(screen.getByText("E6")).toBeInTheDocument()
    expect(screen.getByText("E7")).toBeInTheDocument()
    expect(screen.getByText("E8")).toBeInTheDocument()
    expect(screen.getByText("E9")).toBeInTheDocument()

    expect(screen.getByText("[SQL]")).toBeInTheDocument()
    expect(screen.getByText("[STATS]")).toBeInTheDocument()
    expect(screen.getAllByText("[LLM]").length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText("[SIMULATED]")).toBeInTheDocument()
  })

  it("calls onSelectStage callback when a stage button is clicked", () => {
    const handleSelect = vi.fn()
    render(<PipelineRail result={DEFAULT_INC_001} onSelectStage={handleSelect} />)

    const e4Button = screen.getByText("E4").closest("button")
    expect(e4Button).toBeInTheDocument()
    if (e4Button) {
      fireEvent.click(e4Button)
    }

    expect(handleSelect).toHaveBeenCalledWith("e4")
  })

  it("handles abstained result status gracefully", () => {
    const abstainedResult = {
      ...DEFAULT_INC_001,
      decision: {
        ...DEFAULT_INC_001.decision,
        abstained: true,
        abstention_reason: "Ambiguous competing causes",
      },
    }

    render(<PipelineRail result={abstainedResult} />)
    expect(screen.getByText("E7")).toBeInTheDocument()
  })
})
