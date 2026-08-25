---
name: accessibility
description: >-
  WCAG 2.1 AA accessibility guidelines, screen reader live regions, focus management,
  keyboard traps prevention, color contrast verification, and ARIA patterns for analytical dashboards.
  Use when designing or reviewing components for full accessibility compliance.
---

# Accessibility (WCAG 2.1 AA) Skill

Guidelines for building fully accessible analytical dashboards and operational control surfaces.

---

## 1. Core Principles

1. **Perceivable**: Text alternatives for all non-text content; color is never the *sole* conveyor of information; minimum contrast ratio $\ge 4.5:1$ for normal text, $\ge 3:1$ for large text ($18\text{pt}+$ or bold $14\text{pt}+$) and graphical UI elements.
2. **Operable**: All interactive elements operable via keyboard alone; no keyboard traps; skip-to-content links; logical tab order; focus indicator clearly visible.
3. **Understandable**: Clear headings, predictable navigation, form inputs have associated `<label>` or `aria-label`, error messages clearly identified and linked via `aria-describedby`.
4. **Robust**: Clean semantic HTML, valid ARIA attributes, compatible with modern assistive technologies.

---

## 2. Real-Time Telemetry & Live Regions

When operational metrics or incident streams update dynamically:
* Use `aria-live="polite"` on summary stat containers so screen readers announce updates without interrupting the user.
* Use `aria-live="assertive"` ONLY for critical system failure alerts or high-priority warnings.
* Use `role="status"` for progress indicators and background fetch notifications.

---

## 3. Keyboard Interaction Rules

* **Dialogs & Drawers**: Focus trapped inside while open; `Escape` closes and restores focus to the trigger button.
* **Tabs**: `ArrowLeft` / `ArrowRight` cycles through tabs; `Space` or `Enter` selects.
* **Dropdowns / Menus**: `ArrowUp` / `ArrowDown` navigates items; `Home` / `End` jumps to first/last; `Escape` closes.
* **Tables / Data Grids**: Tab moves focus into the grid; arrow keys navigate cells when interactive.
