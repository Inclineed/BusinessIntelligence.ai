---
name: shadcn-registries
description: >-
  Guide for discovering, searching, inspecting, and installing components via the official shadcn CLI,
  MCP server, and curated component registries (shadcn/ui, Aceternity UI, and Bklit UI).
  Use when adding new UI elements, data visualizations, or interactive components.
---

# shadcn Registries & Component Discovery Skill

This skill governs the disciplined discovery, installation, and adaptation of open-source UI primitives.

---

## 1. Registry Architecture

Configured in `web/components.json`:
* **Core Primitives**: `shadcn/ui` (accessible Radix UI foundations with Tailwind CSS).
* **Advanced Presentation**: `@aceternity` (`https://ui.aceternity.com/registry/{name}.json`) — for distinctive interactive patterns and presentation components.
* **Analytical Visualizations**: `@bklit` (`https://ui.bklit.com/r/{name}.json`) — for charts, gauges, sparklines, heatmaps, and operational dashboards.

---

## 2. Component Discovery & Installation Workflow

1. **Search Existing Project**: First check `web/src/components/` to verify if an existing component can be reused or extended.
2. **Search Registries**:
   ```bash
   npx shadcn@latest search <term> --cwd web
   ```
3. **Inspect Implementation**:
   ```bash
   npx shadcn@latest view <component> --cwd web
   ```
4. **Install Component**:
   ```bash
   npx shadcn@latest add <component> --cwd web
   ```
5. **Harmonize with `DESIGN.md`**: Adapt colors, font families, radius tokens, and semantic states to match the project's design system tokens.

---

## 3. Library Selection Matrix

| Library | Primary Use Cases | When NOT to Use |
| :--- | :--- | :--- |
| **shadcn/ui** | Core form controls, dialogs, drawers, dropdowns, tooltips, tabs, badges, popovers. | Do not use default styling without tailoring to the project palette. |
| **Aceternity UI** | High-impact interactive hero elements, subtle spotlight cards, animated tabs, smooth border effects. | Never use on dense analytical tables or repetitive data rows; avoid cluttering data-heavy views. |
| **Bklit UI** | Operational charts, time-series corridors, gauges, telemetry heatmaps, reactive counters. | Do not use for non-data presentation elements. |
