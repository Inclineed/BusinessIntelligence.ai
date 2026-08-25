# BusinessIntelligence.ai — Design System Contract

This document establishes the authoritative, persistent visual and interaction contract for the `BusinessIntelligence.ai` user interface.

---

## 1. Product & Domain
* **Domain**: Evidence-backed KPI Decision Engine, Root-Cause Investigation, and Operational Telemetry.
* **Core Philosophy**: A precision analytical instrument for decision-makers (Analysts, CFOs, Operations Managers) that prioritizes **high information bandwidth, deterministic trust, and clear causal traceability**.

---

## 2. Visual Identity & Design Principles
1. **Instrument, Not Toy**: Looks and feels like a professional trading terminal or mission control console—clean, dense, aligned, and disciplined.
2. **Deterministic Provenance First**: Every number, chart point, and metric badge communicates where it came from (SQL, STATS, RULES, RETRIEVAL, SIMULATED, or LLM).
3. **Restrained, Purposeful Aesthetics**: Dark slate/charcoal foundations (`#0A0A0A`, `#171717`) with crisp 1px borders (`#262626`) and semantic accent highlights.
4. **Data-Driven Dynamics**: Interfaces react with subtle motion when underlying data or execution state changes—never for empty visual decoration.

---

## 3. Typography
* **Primary Sans**: `Inter`, `-apple-system`, `BlinkMacSystemFont`, `sans-serif` (UI chrome, titles, narratives, labels).
* **Monospace Data Font**: `JetBrains Mono`, `ui-monospace`, `monospace` (all KPI values, currency amounts, percentages, latencies, token counts, timestamps, hashes).
* **Type Scale & Hierarchy**:
  * `text-2xl` ($24\text{px}$ / $32\text{px}$ line-height, bold): Main Scenario & Overview Title.
  * `text-lg` ($18\text{px}$ / $28\text{px}$, font-semibold): Card and Engine Section Headers.
  * `text-sm` ($14\text{px}$ / $20\text{px}$, font-medium): Body prose, hypothesis statements, rationale text.
  * `text-xs` ($12\text{px}$ / $16\text{px}$, font-mono): Micro-metadata, source badges, engine timing tags, table headers.
  * `text-[11px]` ($11\text{px}$ / $14\text{px}$, font-mono): Micro-telemetry chips and watermark tags.

---

## 4. Color System & Semantic Tokens

### Base Neutrals
* **Canvas Background**: `#0A0A0A` (`bg-neutral-950`)
* **Elevated Surface (Cards / Panels)**: `#171717` (`bg-neutral-900`)
* **Interactive Hover Surface**: `#262626` (`bg-neutral-800`)
* **Structural Borders**: `#262626` (`border-neutral-800`)
* **Subtle Dividers / Insets**: `rgba(255, 255, 255, 0.05)`
* **Primary Foreground Text**: `#F5F5F5` (`text-neutral-100`)
* **Secondary / Muted Text**: `#A3A3A3` (`text-neutral-400`)
* **Tertiary / Disabled Text**: `#737373` (`text-neutral-500`)

### Semantic State Colors
* **Positive / Grounded / Live (`Emerald`)**: `#22C55E` (`text-emerald-500`, `bg-emerald-500/10`, `border-emerald-500/20`)
* **Destructive / Anomaly / Contradiction (`Rose/Red`)**: `#EF4444` (`text-red-500`, `bg-red-500/10`, `border-red-500/20`)
* **Warning / Watch / Degraded (`Amber`)**: `#F59E0B` (`text-amber-500`, `bg-amber-500/10`, `border-amber-500/20`)
* **Information / Technical Trace (`Cyan/Sky`)**: `#0EA5E9` (`text-sky-500`, `bg-sky-500/10`, `border-sky-500/20`)
* **Neutral / Stale / Unsure (`Zinc`)**: `#71717A` (`text-zinc-400`, `bg-zinc-800/40`, `border-zinc-700/30`)

---

## 5. Spacing Scale & Visual Density
* **Compact Spacing**: Dense technical layout with `gap-2` ($8\text{px}$) to `gap-4` ($16\text{px}$) between metrics; `p-3` ($12\text{px}$) to `p-5` ($20\text{px}$) inside analytical cards.
* **Layout Grid**: 12-column responsive layout or flexible CSS grid with structured sidebar navigation and dominant multi-column analysis canvas.
* **Aligned Baselines**: Values, labels, and status badges within tables and cards must maintain strict baseline alignment across columns.

---

## 6. Border Radius & Shadows
* **Border Radius**:
  * Badges & Chips: `rounded-md` ($6\text{px}$) or `rounded-full` for compact status dots.
  * Buttons & Inputs: `rounded-lg` ($8\text{px}$).
  * Cards & Containers: `rounded-xl` ($12\text{px}$) or `rounded-2xl` ($16\text{px}$).
* **Elevation / Shadows**:
  * Default Card: `shadow-sm` or subtle 1px border.
  * Hover Card: `shadow-md shadow-black/40` with border transition to `#383838`.
  * Modal / Drawer: `shadow-2xl shadow-black/80` with dark backdrop `bg-black/80 backdrop-blur-sm`.

---

## 7. Component Patterns

### A. Navigation & Top Bar
* Top bar fixed with scenario selector dropdown, persona switch tabs, runtime telemetry chip, system health button, and run button.
* Clear visual indication of active persona (`Analyst`, `CFO`, `Manager`) and current scenario scope.

### B. Buttons & Interactive Controls
* **Primary Action**: Emerald background (`bg-emerald-600 hover:bg-emerald-500 text-white font-medium shadow-sm active:scale-[0.98]`).
* **Secondary / Ghost**: Dark neutral (`bg-neutral-800 hover:bg-neutral-700 text-neutral-200 border border-neutral-700`).
* **Destructive**: Rose background or border (`bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30`).
* **Loading State**: Preserves button dimensions with an embedded spinning SVG indicator.

### C. Cards & Containers
* Surface `#171717`, border 1px `#262626`.
* Header contains section badge (e.g. `[E1] KPI Store`), title, and metadata chips.
* Body contains structured data rows, charts, or evidence summaries.

### D. Tables & Data Lists
* Header row: `text-xs font-mono uppercase tracking-wider text-neutral-400 bg-neutral-900/50 border-b border-neutral-800`.
* Data rows: Compact padding (`py-2.5 px-3`), hover highlight (`hover:bg-neutral-800/40`), tabular numbers with aligned decimal points.

### E. Charts, Gauges & Data Visualizations
* Composable charts using Recharts / Bklit UI.
* Dark-mode palette: Emerald `#22C55E`, Rose `#EF4444`, Sky `#0EA5E9`, Amber `#F59E0B`, Purple `#A855F7`.
* Custom tooltips with dark background (`bg-neutral-900 border border-neutral-700 text-xs shadow-xl`).
* Explicit corridor shading for baseline boundaries ($\pm 3\sigma$).

### F. Status Indicators & Badges
* Explicit badges for Method Tags (`[SQL]`, `[STATS]`, `[RULES]`, `[RETRIEVAL]`, `[LLM_NARRATIVE]`, `[SIMULATED]`).
* Confidence Badges: `HIGH` (Emerald), `MEDIUM` (Amber), `LOW` (Red), `ABSTAIN` (Zinc/Neutral).
* Human Validation Badges: Verified indicator with link to feedback record.

### G. Loading, Empty & Error States
* **Loading**: Subtle pulse skeleton or indeterminate top-border shimmer with elapsed seconds counter.
* **Empty**: Clean slate with an illustrative icon, explanation of why data is empty, and a clear action (e.g. `Run Investigation`).
* **Error**: High-visibility warning container with error details and a retry button.

## 8. Live System Visualization & Streaming Data Architecture

When representing continuously changing, real-time, or streaming data (telemetry, KPI corridors, event logs, utilization metrics, inference states):

1. **State-Driven, Not Decorative**: Prefer real state changes over simulated decorative motion. Animate only values and regions whose underlying state actually changed.
2. **Spatial Continuity**: Preserve spatial continuity and element position when values update (avoid layout shifts or reordering list rows abruptly).
3. **Targeted Subcomponent Rerenders**: Isolate high-frequency telemetry counters (e.g. streaming tokens, latencies) in dedicated leaf components (`React.memo`) to avoid full-page or parent component rerenders.
4. **Smooth Event Ingestion**: Event streams and log lines should append or top-insert smoothly without displacing reading focus or resetting scroll position.
5. **Legible Numeric Transitions**: Numerical transitions must use `font-mono tabular-nums` and subtle value roll-overs rather than wild spinning animations.
6. **Semantic State Coloring**: Use color transitions solely to communicate semantic state (e.g. Emerald $\to$ Amber $\to$ Red for threshold breaches), never for ambient decoration.
7. **Context-Preserving Charts**: Time-series charts and corridor graphs must preserve historical baseline context while progressively extending the live data window.
8. **Throttled / Coalesced Telemetry**: High-frequency streaming telemetry ($>60\text{Hz}$) must be throttled or RAF-coalesced ($100\text{ms}$–$250\text{ms}$ buckets) to prevent UI thread lockup.
9. **Clarity Over Flash**: Never sacrifice tabular readability, baseline alignment, or visual precision for transition effects.

> **Visual Axiom**: The interface must always communicate:
> $$\text{CURRENT STATE} + \text{CHANGE} + \text{DIRECTION} + \text{SIGNIFICANCE}$$

---

## 9. Animation & Motion Guidelines

```
DEFAULT UI TRANSITIONS
      ↓
Motion (framer-motion / motion/react)
(Spring physics, enters/exits, layout morphs, drawer slides)

SPECIALIZED SVG / TIMELINES
      ↓
Anime.js
(Multi-stage timeline choreography, complex SVG path animations)
```

* **Restrained Motion**: Keep durations between $150\text{ms}$ and $300\text{ms}$.
* **Data Reactivity**: When values update, trigger smooth transitions (`tabular-nums` counting or subtle highlight flashes).

---

## 10. Library Selection Rules

| Tool | When to Use | When NOT to Use |
| :--- | :--- | :--- |
| **shadcn/ui** | Core accessible UI building blocks (dialogs, dropdowns, tooltips, tabs, buttons, badges, popovers). | Never leave default light-mode or generic styles unaligned with the dark palette. |
| **Aceternity UI** | High-impact visual accents, subtle spotlight cards, animated tab transitions, distinctive presentation moments. | Never use on high-density data tables or repetitive list rows where it adds visual noise. |
| **Bklit UI** | Operational charts, time-series corridors, telemetry heatmaps, sparklines, reactive counters. | Do not use for non-visualization UI chrome. |
| **Motion** | Standard UI animation, modal/drawer transitions, layout shifts, tab switching, card hover feedback. | Avoid for complex SVG path morphing or multi-stage procedural timelines. |
| **Anime.js** | Specialized multi-node SVG path animations, complex timeline choreography, procedural cascades. | Never use for standard button clicks or basic dialog enter/exit. |

---

## 10. Anti-Patterns & AI-Slop Checklist
* ❌ Avoid generic purple-to-blue gradient headers.
* ❌ Avoid excessive glassmorphism with heavy backdrop blur everywhere.
* ❌ Avoid nested cards that create a "Russian doll" effect.
* ❌ Avoid arbitrary decorative motion that does not communicate state change.
* ❌ Avoid centered marketing-hero layouts inside analytical dashboards.
* ❌ Avoid unformatted numbers (always use commas, fixed decimals, and currency/metric units).

---

## 11. Testing & Quality Assurance Contract
* **Unit Testing (Vitest)**: Mandatory for all data parsers, formatting utilities, metric math, and delta/z-score logic (`web/src/**/*.test.ts`).
* **Component Testing (React Testing Library + JSDOM)**: Mandatory for complex interactive components, persona-scoped views, modal/drawer accessibility, and error boundaries (`web/src/**/*.test.tsx`).
* **End-to-End Verification**: Live demonstration dry runs verifying the 5-step user journey against the live FastAPI backend on `:8000`.
* **Execution Gate**: `npm test` and `npm run build` must both pass with zero errors before any frontend change is considered complete.

