---
name: frontend-testing
description: >-
  Comprehensive frontend testing strategy covering unit tests (Vitest), component isolation & integration tests
  (React Testing Library), and live end-to-end user flow verification.
  Use when creating, maintaining, or auditing frontend test suites.
---

# Frontend Testing Strategy Skill

A production-grade frontend environment requires a rigorous 3-tier testing pyramid to prevent regressions, verify accessibility, and guarantee live demonstration reliability.

---

## 1. The 3-Tier Testing Pyramid

```
        ▲
       / \
      /   \      LEVEL 3: End-to-End (E2E) Live Verification
     / E2E \     • Full user journeys across live FastAPI & React frontend
    /───────\    • Persona switching, live SSE/investigate, feedback submission
   /         \
  / COMPONENT \  LEVEL 2: Component & Integration Testing (React Testing Library)
 /             \ • Mocked state transitions, loading skeletons, error boundaries
/───────────────\• Keyboard focus, ARIA role compliance, modal/drawer rendering
/                 \
/       UNIT        \ LEVEL 1: Fast Deterministic Unit Tests (Vitest)
/                     \• Formatters, metric calculations, delta & z-score math
───────────────────────• Regex sanitizers, tag cleaners, utility functions
```

---

## 2. Level 1: Unit Testing (Vitest)

* **Location**: `web/src/**/*.test.ts` (e.g. `web/src/lib/utils.test.ts`).
* **Focus**: Pure functions, mathematical transformations, string cleaners, date formatters.
* **Execution**: `npm test` in `web/` (or `npm run test:watch` for active TDD).
* **Requirements**:
  * 100% deterministic, zero network or timer leakage.
  * Test boundary conditions (e.g. `null`, `undefined`, `NaN`, zero divisions, negative values).

---

## 3. Level 2: Component Testing (React Testing Library + JSDOM)

* **Location**: `web/src/**/*.test.tsx` (e.g. `web/src/components/common/ErrorBoundary.test.tsx`).
* **Focus**: Rendering correctness, user interactions, accessible query selection, error containment.
* **Testing Best Practices**:
  * Use semantic queries: `screen.getByRole("button", { name: /run investigation/i })` rather than `.class-name` or `div > div`.
  * Verify loading states and disabled button behaviors during pending requests.
  * Verify modal and drawer focus traps and `Escape` key handlers.
  * Verify error boundaries render recovery actions without crashing the parent application.

---

## 4. Level 3: End-to-End (E2E) & Live Demo Rehearsal

* **Focus**: Complete user journeys with live backend integration (`FastAPI` on `:8000` + `Vite` on `:3000`/`:5173`).
* **Authoritative 5-Step Demo Verification Script**:
  1. **Scenario Selection**: Select `INC_001` (Payment Gateway Regression) $\to$ Verify KPI cards, charts, and telemetry load.
  2. **Persona Boundary Check**: Switch persona from `Analyst` to `CFO` $\to$ Verify technical deployment and gateway telemetry are stripped, while business revenue/inventory are preserved.
  3. **Abstention Verification**: Select `INC_002` (Ambiguous Causes) $\to$ Verify system flags ambiguous causes and displays explicit `ABSTAIN` banner without recommending reckless actions.
  4. **Feedback & Institutional Memory**: Submit a `CORRECT` structured feedback review as Analyst $\to$ Verify precedent validation badge and $+0.10$ retrieval boost are applied.
  5. **Continuous Evaluation Trace**: Open `System Performance Drawer` and `System Health Modal` $\to$ Verify 6 operational health metrics and waterfall latencies render accurately.
