import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import React from "react"
import { LeftObservePanel } from "./LeftObservePanel"
import { DEFAULT_INC_001 } from "../../lib/defaultData"

describe("LeftObservePanel", () => {
  it("renders expanded sidebar with full details when isCollapsed is false", () => {
    const onToggle = vi.fn()
    const onConfigChange = vi.fn()
    const onOpenTelemetry = vi.fn()
    const onOpenHealth = vi.fn()
    render(
      <LeftObservePanel
        result={DEFAULT_INC_001}
        activeScenarioId="INC_001"
        activePersona="analyst"
        activeRegion="all"
        currentStageNum={1}
        isCollapsed={false}
        onToggleCollapse={onToggle}
        onConfigChange={onConfigChange}
        onOpenTelemetry={onOpenTelemetry}
        onOpenHealth={onOpenHealth}
      />
    )

    expect(screen.getAllByText("INC_001").length).toBeGreaterThan(0)
    expect(screen.getByTitle("Collapse Sidebar (~56px Rail)")).toBeInTheDocument()

    fireEvent.click(screen.getByTitle("Collapse Sidebar (~56px Rail)"))
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it("renders collapsed 56px icon rail when isCollapsed is true", () => {
    const onToggle = vi.fn()
    const onConfigChange = vi.fn()
    const onOpenTelemetry = vi.fn()
    const onOpenHealth = vi.fn()
    render(
      <LeftObservePanel
        result={DEFAULT_INC_001}
        activeScenarioId="INC_001"
        activePersona="analyst"
        activeRegion="all"
        currentStageNum={1}
        isCollapsed={true}
        onToggleCollapse={onToggle}
        onConfigChange={onConfigChange}
        onOpenTelemetry={onOpenTelemetry}
        onOpenHealth={onOpenHealth}
      />
    )

    expect(screen.getByTitle("Expand Sidebar")).toBeInTheDocument()
    fireEvent.click(screen.getByTitle("Expand Sidebar"))
    expect(onToggle).toHaveBeenCalledTimes(1)
  })
})
