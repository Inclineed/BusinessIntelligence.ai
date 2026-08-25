import { describe, it, expect, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import React from "react"
import { ErrorBoundary } from "./ErrorBoundary"

// Component that intentionally throws an error during render
const ThrowingComponent = () => {
  throw new Error("Simulated render crash")
}

const SafeComponent = () => <div>Safe Content Rendered</div>

describe("ErrorBoundary", () => {
  it("renders children when no error occurs", () => {
    render(
      <ErrorBoundary>
        <SafeComponent />
      </ErrorBoundary>
    )
    expect(screen.getByText("Safe Content Rendered")).toBeInTheDocument()
  })

  it("catches render errors and displays fallback UI", () => {
    // Suppress console.error during deliberate error test
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {})

    render(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>
    )

    expect(screen.getByText("Rendering Error Intercepted")).toBeInTheDocument()
    expect(screen.getByText(/Simulated render crash/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Reload Application/i })).toBeInTheDocument()

    consoleSpy.mockRestore()
  })

  it("renders custom fallback when provided", () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {})

    render(
      <ErrorBoundary fallback={<div>Custom Error Fallback</div>}>
        <ThrowingComponent />
      </ErrorBoundary>
    )

    expect(screen.getByText("Custom Error Fallback")).toBeInTheDocument()

    consoleSpy.mockRestore()
  })
})
