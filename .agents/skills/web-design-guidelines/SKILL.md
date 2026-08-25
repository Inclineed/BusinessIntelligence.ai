---
name: web-design-guidelines
description: >-
  Audit and review user interface code for compliance with Vercel Web Interface Guidelines,
  accessibility (WCAG 2.1 AA), keyboard navigation, focus visibility, responsive layouts, and interaction states.
  Use after implementing or modifying UI components.
---

# Web Design Guidelines Skill

Use this skill as an authoritative review layer after implementing frontend components to ensure world-class usability, accessibility, and visual polish.

---

## 1. Audit Workflow

```
IMPLEMENT
   ↓
AUDIT (Web Interface Guidelines & Accessibility)
   ↓
FIX IDENTIFIED ISSUES
   ↓
RE-AUDIT & VERIFY
```

---

## 2. Core Inspection Checklist

### A. Accessibility & Keyboard Navigation
* **Focus Visibility**: Every interactive element (`<button>`, `<a>`, `<input>`, `<select>`, clickable card) must have a visible, high-contrast focus indicator (e.g. `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neutral-400`).
* **Keyboard Operability**: All modals, drawers, and dropdowns must close on `Escape`, trap focus when open, and restore focus to the trigger element on close.
* **Semantic Elements**: Use proper HTML5 semantic elements (`<main>`, `<nav>`, `<header>`, `<section>`, `<article>`, `<aside>`) instead of nested `<div>`s.
* **ARIA Roles**: Interactive non-button elements must have `role="button"`, `tabIndex={0}`, and `onKeyDown={(e) => e.key === "Enter" || e.key === " " && ...}`.
* **Live Regions**: Dynamic streaming content or live health metrics should use `aria-live="polite"` or `role="status"`.

### B. Typography & Text Legibility
* **Contrast Ratios**: Body text must maintain $\ge 4.5:1$ contrast against the background; large headings and muted secondary labels must maintain $\ge 3:1$.
* **Monospace Alignment**: All numbers, timestamps, hashes, currency amounts, and percentages must use `font-mono tabular-nums`.
* **Truncation & Tooltips**: Truncated text (`truncate` / `line-clamp-*`) must provide full content access via a tooltip or inspection popover.

### C. Interaction & Feedback States
* **Disabled vs Loading**: Disabled buttons must prevent click events and clearly show reduced opacity. Loading buttons must show an inline spinner and preserve button dimensions to avoid layout shift.
* **Touch Targets**: Mobile touch targets must be at least $44 \times 44\text{px}$.
* **Empty & Error States**: Components must never display a raw `undefined`, `null`, `NaN`, or empty white container. Render structured fallback cards with recovery actions.

### D. Responsive Layout & Spacing
* **Overflow Guard**: No uncontained horizontal scrollbars on standard viewport widths ($360\text{px}$ to $1920\text{px}$).
* **Z-Index Scale**: Maintain a coherent z-index hierarchy (Base: 0, Sticky: 10, Dropdown: 20, Modal/Drawer: 50, Toast: 100).
