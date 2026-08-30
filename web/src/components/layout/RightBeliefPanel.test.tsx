import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import React from "react"
import { RightBeliefPanel } from "./RightBeliefPanel"
import { DEFAULT_INC_001 } from "../../lib/defaultData"

describe("RightBeliefPanel", () => {
  it("renders nothing when isOpen is false", () => {
    const onClose = vi.fn()
    const { container } = render(
      <RightBeliefPanel
        result={DEFAULT_INC_001}
        currentStageNum={4}
        persona="analyst"
        isOpen={false}
        onClose={onClose}
      />
    )

    expect(container.firstChild).toBeNull()
  })

  it("renders slide-over drawer when isOpen is true and triggers onClose", () => {
    const onClose = vi.fn()
    render(
      <RightBeliefPanel
        result={DEFAULT_INC_001}
        currentStageNum={4}
        persona="analyst"
        isOpen={true}
        onClose={onClose}
      />
    )

    expect(
      screen.getByText(/Governed Action Directive/i)
    ).toBeInTheDocument()
    expect(screen.getByTitle("Close Drawer")).toBeInTheDocument()

    fireEvent.click(screen.getByTitle("Close Drawer"))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
