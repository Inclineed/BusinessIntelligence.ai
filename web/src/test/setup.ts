import "@testing-library/jest-dom/vitest"
import { cleanup } from "@testing-library/react"
import { afterEach } from "vitest"

// Automatically unmount React trees and clean up DOM after each test
afterEach(() => {
  cleanup()
})
