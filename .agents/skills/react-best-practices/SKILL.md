---
name: react-best-practices
description: >-
  Audit and optimize React components and architecture for rendering performance,
  unnecessary rerender elimination, state management, network waterfalls, bundle size, and memory leak prevention.
  Use during and after implementing React features.
---

# React Best Practices & Performance Skill

Ensure that frontend code is not only visually polished but also technically resilient, performant, and memory-efficient.

---

## 1. Performance Checklist

### A. Rerender Optimization
* **Stable Callbacks & Memos**: Wrap event handlers passed to deep child lists in `useCallback` when children are memoized.
* **Primitive Hook Dependencies**: Never pass newly constructed object/array literals inside `useEffect` or `useMemo` dependency arrays.
* **Component Granularity**: Separate fast-updating state (e.g. streaming counters, live timer seconds, text input keystrokes) into isolated subcomponents so the entire parent view does not rerender.

### B. Memory & Effect Cleanup
* **Timer & Listener Cleanup**: Every `setTimeout`, `setInterval`, `requestAnimationFrame`, or `addEventListener` inside `useEffect` must return an explicit cleanup function.
* **Abort Controllers**: Fetch operations and async telemetry polls should support `AbortController` to cancel pending requests when components unmount or scenario IDs change.

### C. Bundle Size & Code Splitting
* **Tree-Shaking Icons & Utils**: Import specific icons directly from `lucide-react` (e.g. `import { Shield, Activity } from "lucide-react"`).
* **Lazy Loading Heavy Visualizations**: Heavy modal contents or complex SVG chart packages should be lazily loaded via `React.lazy` / `Suspense` when not visible on initial page load.

### D. Error Boundaries & Fallback Grace
* **Local Boundary Wrapping**: Complex analytical cards or visualization panels must be wrapped in `<ErrorBoundary>` to isolate crashes and prevent entire page unmounting.
