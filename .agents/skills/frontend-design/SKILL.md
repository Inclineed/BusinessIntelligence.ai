---
name: frontend-design
description: >-
  Comprehensive design guidance for creating distinctive, production-grade, domain-specific UI.
  Use when designing or implementing user interfaces, exploring visual directions, establishing visual hierarchy,
  configuring motion, or auditing aesthetics against generic AI-slop patterns.
---

# Frontend Design Skill

This skill guides the creation of distinctive, production-grade user interfaces that feel like specialized instruments rather than generic SaaS dashboards.

---

## 1. Design Exploration & Variant Philosophy

For major new views or significant interface components, **do not immediately commit to the first obvious idea**. Explore 2–4 genuinely different design directions before settling on an implementation.

### Genuine Variant Archetypes:
1. **Dense Technical Console**: Maximum information bandwidth, aligned columnar data, monospace metric values, thin borders (`border-neutral-800`), dark neutral palette, compact controls, minimal padding.
2. **Editorial Analytical Workspace**: High typographical contrast, structured narrative blocks, prominent contextual summaries, clear visual pacing, focused card groupings.
3. **Spatial / Stream Monitoring Interface**: Real-time event streams, live pulsing telemetry chips, timeline scrubbing, spatial distribution of indicators, reactive counters.
4. **Minimal Analytical Instrument**: Stark precision, micro-charts, zero decorative chrome, maximum data-to-ink ratio, subtle status badges.

> **Rule**: Variants must differ in **composition, hierarchy, density, navigation, and interaction model**—never just a different accent color.

---

## 2. Anti-AI-Slop Manifesto

Generic AI-generated UI suffers from predictable clichés. Every design decision must be intentional and domain-grounded.

### 🚫 Strictly Forbidden Defaults:
* **No automatic purple/blue gradient backgrounds or text gradients.**
* **No excessive glassmorphism** (`backdrop-blur-md` with glowing borders on every container).
* **No card-in-card nesting** where every single paragraph gets its own rounded card.
* **No arbitrary pill tags** scattered everywhere without semantic filtering purpose.
* **No floating decorative gradient blobs** or ambient background lights.
* **No generic hero banners** on internal analytical dashboards.
* **No decorative motion** (e.g. elements sliding in from 4 different directions just for show).

### ✅ Deliberate Craftsmanship:
* **Dark Instrument Palette**: Deep charcoal and neutral blacks (`#0A0A0A`, `#171717`, `#262626`) with semantic status accents (Emerald for positive, Rose/Red for destructive, Amber for watch, Blue/Cyan for technical trace).
* **Information Density**: Allow high information density with aligned tabular baselines, tight metadata grouping, and crisp 1px borders.
* **Typography Hierarchy**: Crisp sans-serif (`Inter`, `-apple-system`) paired with monospace (`JetBrains Mono`) for all financial, latency, token, and statistical quantities.

---

## 3. Motion & Animation Architecture

Animation must answer four questions:
1. **What changed?**
2. **Why did it change?**
3. **Where did it change?**
4. **What should the user notice?**

### Library Selection Hierarchy:
* **Default UI Animation → `Motion` (`framer-motion` / `motion/react`)**:
  * State transitions, drawer/modal enter-exits, accordion expansions, layout morphing, animated tab indicators, hover/active states.
  * Use spring physics: `transition={{ type: "spring", stiffness: 300, damping: 30 }}`.
* **Specialized / Procedural / SVG Animation → `Anime.js`**:
  * Complex timeline sequences, multi-node SVG path animations, procedural particle cascades, complex network graph choreography.
* **Rule**: Never import both libraries for the same simple interaction.

---

## 4. Live System Visualization & Streaming Principles

When representing continuously changing, real-time, or streaming data (telemetry, KPI corridors, event logs, utilization metrics):
* **State-Driven Animation**: Prefer real state changes over simulated decorative motion. Animate only values/regions whose underlying state changed.
* **Preserve Spatial Continuity**: Keep layout elements spatially anchored when values update to avoid disruptive layout shifts or unexpected row jumping.
* **Component Isolation**: Prevent full-component rerenders by isolating high-frequency streaming counters into dedicated memoized leaf components (`React.memo`).
* **Smooth Event Streams**: Event streams and log lines must append or insert smoothly without disrupting reading focus or resetting scroll position.
* **Legible Numerical Transitions**: Use `font-mono tabular-nums` and subtle transitions to communicate value updates clearly.
* **Semantic Color Changes**: Use color changes strictly to communicate semantic state (e.g. normal $\to$ watch $\to$ degraded), never for ambient decoration.
* **Context-Preserving Charts**: Time-series and corridor charts must preserve historical baseline context while progressively extending live data points.
* **Telemetry Throttling**: High-frequency streaming telemetry ($>60\text{Hz}$) must be throttled/coalesced ($100\text{ms}$–$250\text{ms}$) to preserve UI responsiveness.
* **Clarity Over Flash**: Never sacrifice tabular readability, baseline alignment, or visual precision for transition effects.
* **The Core Axiom**: The interface must always communicate:
  $$\text{Current State} + \text{Change} + \text{Direction} + \text{Significance}$$

