# Agent Guidelines & AI-Native Frontend Workflow

This repository contains **BusinessIntelligence.ai**, an evidence-backed KPI decision engine with a React/Vite/Tailwind frontend (`web/`) and Python FastAPI backend (`api/`).

---

## 1. Frontend Development Workflow

Whenever designing, implementing, or updating user interface components, **NEVER** treat frontend work as `PROMPT → ONE-SHOT UI → DONE`. Follow this disciplined, multi-stage workflow:

```
USER REQUIREMENT
        ↓
UNDERSTAND THE DOMAIN & PERSONA CONTEXT
        ↓
CHECK DESIGN.md (Design System Contract)
        ↓
DESIGN EXPLORATION (2–4 genuine variant concepts for major new features)
        ↓
SELECT VISUAL DIRECTION & DEFINE HIERARCHY
        ↓
SEARCH EXISTING COMPONENTS (web/src/components/)
        ↓
SEARCH REGISTRIES (shadcn / Aceternity / Bklit)
        ↓
IMPLEMENT REAL STATE & DATA INTERACTION
        ↓
ADD DATA-DRIVEN MOTION (Motion default / Anime.js for specialized)
        ↓
AUTOMATED UNIT & COMPONENT TESTING (Vitest / React Testing Library)
        ↓
WEB DESIGN GUIDELINES & ACCESSIBILITY AUDIT
        ↓
REACT 19 & PERFORMANCE AUDIT
        ↓
FIX IDENTIFIED ISSUES
        ↓
FINAL POLISH & BUILD VERIFICATION
```

---

## 2. Variant-Style Design Exploration

For major new views or significant features:
* Explore **2–4 genuinely different design directions** (e.g. *Dense Technical Console*, *Editorial Analytical Workspace*, *Spatial Monitoring Interface*, *Minimal Analytical Instrument*).
* Variants must differ in **composition, density, information hierarchy, navigation, and interaction model**—never just different accent colors.
* Once a direction is chosen, align it with [DESIGN.md](./DESIGN.md) and implement consistently.

---

## 3. Component Discovery & Reuse Rules

Before creating any new component from scratch:
1. **Search the existing project** in `web/src/components/`.
2. **Check [DESIGN.md](./DESIGN.md)** for existing patterns and tokens.
3. **Check `shadcn/ui`** for accessible UI primitives (`npx shadcn@latest search <term> --cwd web`).
4. **Check `@aceternity`** for advanced presentation components.
5. **Check `@bklit`** for data visualization, charts, and telemetry components.
6. **Reuse or adapt** existing implementations rather than adding redundant code.

---

## 4. Library Selection Matrix

| Library | Primary Use Cases | When NOT to Use |
| :--- | :--- | :--- |
| **shadcn/ui** | Core UI primitives (dialogs, dropdowns, tooltips, tabs, buttons, badges, popovers). | Never leave default light-mode or generic styles unaligned with the dark palette. |
| **Aceternity UI** | High-impact visual accents, spotlight cards, animated tabs, distinctive presentation moments. | Never use on high-density data tables or repetitive list rows where it adds visual clutter. |
| **Bklit UI** | Operational charts, time-series corridors, telemetry heatmaps, sparklines, reactive counters. | Do not use for standard non-data UI chrome. |
| **Motion** | Standard UI animation, modal/drawer transitions, layout shifts, tab switching, card hover feedback. | Avoid for complex SVG path morphing or multi-stage procedural timelines. |
| **Anime.js** | Specialized multi-node SVG path animations, complex timeline choreography, procedural cascades. | Never use for standard button clicks or basic dialog enter/exit. |

---

## 5. Anti-AI-Slop Rules

Every design decision must be intentional and domain-grounded:
* ❌ **No automatic purple/blue gradient backgrounds or text gradients.**
* ❌ **No excessive glassmorphism** with heavy blur and glowing borders everywhere.
* ❌ **No card-in-card nesting** where every sentence gets its own rounded box.
* ❌ **No arbitrary pill tags** without semantic filtering or status meaning.
* ❌ **No decorative motion** that does not communicate state change.
* ❌ **No centered marketing-hero layouts** on internal analytical dashboards.
* ✅ **Focus on high information density, aligned monospace tabular numbers, crisp 1px borders, and clear causal provenance.**

---

## 6. Live System Visualization Principles

When representing continuously changing, real-time, or streaming data (telemetry, KPI corridors, event logs, utilization metrics):
* **State-Driven Animation**: Animate only values/regions whose underlying state changed; prefer real state changes over simulated decorative motion.
* **Spatial Continuity**: Preserve spatial layout continuity when values update (prevent layout shifts or jarring row reorders).
* **Component Isolation**: Avoid full-component rerenders for streaming updates by isolating live counters into dedicated memoized leaf components.
* **Smooth Event Ingestion**: Event streams and log feeds must append/insert smoothly without disrupting reading flow or resetting scroll position.
* **Legible Numerical Transitions**: Use `font-mono tabular-nums` and subtle transitions to communicate value changes cleanly.
* **Semantic Color States**: Use color changes strictly to communicate semantic state (e.g. status transition, threshold breach), never for decoration.
* **Contextual Historical Charts**: Charts must preserve historical baseline context while progressively extending live data points.
* **Throttling & Coalescing**: High-frequency streaming telemetry must be throttled/coalesced ($100\text{ms}$–$250\text{ms}$) to preserve UI thread responsiveness.
* **Clarity First**: Never sacrifice tabular readability or baseline alignment for transition effects.
* **Core Axiom**: The interface must always communicate: $\text{Current State} + \text{Change} + \text{Direction} + \text{Significance}$.

---

## 7. Testing Strategy & Verification Requirement

After every frontend modification:
1. **Automated Unit & Component Testing**: Run `npm test` in `web/` to execute the Vitest and React Testing Library suites. Every utility, data parser, and complex UI state transition must have automated coverage.
2. **Run Web Design Guidelines Audit**: Verify focus rings (`focus-visible:ring-2`), keyboard navigation (`Escape`, `Enter`), color contrast ($\ge 4.5:1$), and responsive layout.
3. **Run React Best Practices Audit**: Verify stable callbacks, effect cleanups, error boundary containment, and no unnecessary parent rerenders.
4. **Verify Production Build**: Run `npm run build` in `web/` to guarantee zero TypeScript or Vite bundle errors.
