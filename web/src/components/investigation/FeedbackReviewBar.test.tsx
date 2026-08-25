import { describe, it, expect } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import React from "react"
import { FeedbackReviewBar } from "./FeedbackReviewBar"
import { DEFAULT_INC_001 } from "../../lib/defaultData"

describe("FeedbackReviewBar", () => {
  it("renders structured review options and submit button", () => {
    render(<FeedbackReviewBar result={DEFAULT_INC_001} persona="analyst" />)

    expect(screen.getByText("Analyst Structured Review & Precedent Validation")).toBeInTheDocument()
    expect(screen.getByText("Confirmed Correct")).toBeInTheDocument()
    expect(screen.getByText("Incorrect Explanation")).toBeInTheDocument()
    expect(screen.getByText("Partially Correct")).toBeInTheDocument()
    expect(screen.getByText("Unsure / Inconclusive")).toBeInTheDocument()
    expect(screen.getByText("Submit Review")).toBeInTheDocument()
  })

  it("allows selecting different verdicts", () => {
    render(<FeedbackReviewBar result={DEFAULT_INC_001} persona="analyst" />)

    const incorrectBtn = screen.getByText("Incorrect Explanation")
    fireEvent.click(incorrectBtn)

    expect(incorrectBtn.closest("button")).toHaveClass("font-bold")
  })
})
