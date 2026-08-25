# Backend → Frontend Product & Interface Specification

**System**: `BusinessIntelligence.ai`  
**Domain**: Evidence-Backed KPI Decision Engine, Root-Cause Diagnostic & Continuous Evaluation System  
**Status**: Authoritative Product & Technical Specification (Derived Strictly from Backend Source of Truth)  
**Date**: August 2026

---

## 1. Executive Summary

This specification establishes the authoritative, end-to-end frontend product and technical requirements for **BusinessIntelligence.ai**. Every user-facing route, component, state machine, data visualization, and interaction model defined herein is directly traced from the existing backend implementation (`api/`, `engines/`, `models.py`, `pipeline/`, `security/`, `evaluation/`, `etl/`, and `config/`).

### Core Backend Capabilities
1. **Deterministic 9-Engine Investigation Pipeline (`E1` $\to$ `E9`)**: Combines SQL aggregations, statistical anomaly corridors, segment decomposition, and deterministic rule-based challenge logic with bounded LLM qualitative reasoning and institutional vector memory.
2. **Strict Quantitative Truth Invariant**: All numbers (KPI values, z-scores, contribution %, confidence scores, recovery %) originate exclusively from deterministic Python/SQL code; the LLM is prohibited from emitting raw unverified numbers.
3. **Role-Based Entitlement Boundary**: Server-side filtering enforces strict persona scopes (`Analyst`, `CFO`, `Manager`) before evidence assembly, ensuring zero unauthorized data leakage.
4. **Structured Human Feedback Loop**: Allows domain analysts to submit structured corrections (`CORRECT`, `INCORRECT`, `PARTIALLY_CORRECT`, `UNSURE`) which execute first-wins institutional validation and retrieval boosts in vector memory.
5. **Continuous Evaluation & Drift Monitoring**: On-demand operational monitoring evaluating 6 key reliability metrics across count-based investigation windows (50 recent vs 50 baseline).
6. **Detailed Cost & Runtime Telemetry**: Tracks per-engine waterfall latency, provider/model metadata, token accounting, and external API cost.

---

## 2. Backend Capability Map

| Capability ID | Capability Name | Purpose | Backend Service / Module | API Endpoint | Input Schema | Output Schema | Allowed Personas | Sync / Async |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **CAP-01** | System Liveness Probe | Verify API and model server availability | `api/main.py` | `GET /health` | None | `{"status": "ok", "llm_backend": str}` | All (Public) | Sync |
| **CAP-02** | Scenario Catalog Discovery | Retrieve available incident scenarios and metadata | `api/main.py` | `GET /scenarios` | None | `{"scenarios": list[ScenarioMeta]}` | All | Sync |
| **CAP-03** | Semantic KPI Contract Query | Retrieve authoritative KPI formulas, lineages, and SLAs | `config/loader.py`, `api/main.py` | `GET /kpi-contract` | None | KPI Contract JSON | All | Sync |
| **CAP-04** | Live Investigation Execution | Run 9-engine root-cause investigation | `pipeline/investigate.py` | `POST /investigate` | `InvestigateRequest(scenario_id, persona, region)` | `InvestigationResult` (JSON) | `analyst`, `cfo`, `manager` (scoped) | Sync (1.5s–30s) |
| **CAP-05** | Structured Feedback Submission | Submit analyst corrections and validate precedent | `api/main.py`, `engines/memory.py` | `POST /feedback` | `FeedbackRequest` | `FeedbackResponse` | `analyst`, `cfo`, `manager` | Sync |
| **CAP-06** | Scenario Feedback History | Retrieve historical audit feedback for a scenario | `api/main.py` | `GET /feedback/{scenario_id}` | Path: `scenario_id` | `{"scenario_id": str, "count": int, "records": list}` | All | Sync |
| **CAP-07** | Feedback Quality Metrics | Global coverage, human agreement rate, validation count | `api/main.py`, `evaluation/feedback_metrics.py` | `GET /feedback/metrics` | None | Feedback Metrics JSON | All | Sync |
| **CAP-08** | Continuous Drift & Health Audit | Evaluate 6 operational reliability metrics | `evaluation/health.py`, `api/main.py` | `GET /evaluation/health` | None | `SystemHealthReport` (JSON) | All | Sync (On-Demand) |
| **CAP-09** | Institutional Precedent Storage | Persist investigation precedent vectors into ChromaDB | `engines/memory.py` | Internal post-run trigger | `InvestigationResult` | Stored boolean status | Backend Internal | Async/Sync |
| **CAP-10** | Precedent Candidate Search | Retrieve historical precedents via oversample+filter | `engines/memory.py` | Executed inside `investigate()` | Scenario text, persona scope | `list[PrecedentItem]` | Backend Internal | Sync |

---

## 3. Domain Entities & Data Models

### 3.1 `AnomalySignal` ([models.py:L160-L177](file:///e:/accenture/models.py#L160-L177))
* **Fields**: `kpi_id: str`, `observed: float`, `expected: float`, `delta_pct: float` (clamped $[-100, 100]$), `z_score: float` (clamped $[-1000, 1000]$), `is_anomaly: bool`, `corroborated_by: list[str]`, `sparse_history: bool`, `data_quality_suspect: bool`, `method: MethodTag.STATS`.
* **UI Representation**: KPI metric card, z-score deviation badge, anomaly status pill, corridor sparkline.

### 3.2 `DimensionContribution` ([models.py:L179-L191](file:///e:/accenture/models.py#L179-L191))
* **Fields**: `dimension: str` (e.g. `"device"`, `"channel"`), `segment: str` (e.g. `"android"`, `"web"`), `contribution_pct: float` ($[0, 100]$), `segment_delta_pct: float`, `method: MethodTag.SQL`.
* **UI Representation**: Contribution breakdown bar chart, segment percentage distribution table.

### 3.3 `Evidence` ([models.py:L193-L234](file:///e:/accenture/models.py#L193-L234))
* **Fields**: `evidence_id: str` (e.g. `"EV_deploy_v43"`), `kind: str` (`"structured"` | `"unstructured"`), `summary: str`, `source_id: str`, `reliability_weight: float` ($[0, 1]$), `relevance: float` ($[0, 1]$), `raw_ref: str`, `method: MethodTag` (`SQL` | `RETRIEVAL`).
* **UI Representation**: Interactive evidence card, reliability badge, source origin chip, expandable citation modal.

### 3.4 `Hypothesis` & `ScoredHypothesis` ([models.py:L256-L320](file:///e:/accenture/models.py#L256-L320))
* **Fields**: `hypothesis_id: str` (`"H1"`, `"H2"`, `"H3"`), `statement: str` (strictly qualitative, no raw numbers), `reasoning: str`, `citations: list[EvidenceCitation]`, `rule_results: list[RuleResult]`, `support_score: float`, `contradiction_penalty: float`, `final_score: float` ($[0, 1]$), `confidence_state: ConfidenceState` (`HIGH`, `MEDIUM`, `LOW`, `ABSTAIN`), `narrative: str`, `disqualification_reason: Optional[str]`, `violations: list[CitationViolation]`.
* **UI Representation**: Ranked hypothesis card, confidence meter, 5-rule evaluation matrix (Timeline, Mechanism, Segment, Corroboration, Contradiction), citation link pills.

### 3.5 `Decision` & `OutcomeProjection` ([models.py:L324-L366](file:///e:/accenture/models.py#L324-L366))
* **Fields**: `abstained: bool`, `winning_hypothesis_id: Optional[str]`, `recommended_action: Optional[str]`, `verification_metric: Optional[str]`, `persona_narrative: str`, `abstention_reason: Optional[str]`, `outcome.outcome_type: OutcomeType` (`SIMULATED`), `outcome.projected_recovery_pct: float`, `outcome.projected_metric: str`, `outcome.disclaimer: str`.
* **UI Representation**: Primary Action Hero Panel, Recovery Projection Gauge/Curve, Persona Narrative Summary, Abstention Warning Banner.

### 3.6 `Telemetry` ([models.py:L370-L387](file:///e:/accenture/models.py#L370-L387))
* **Fields**: `llm_provider: str` (`"Groq"`, `"Ollama"`), `llm_model: str`, `latency_ms_by_engine: dict[str, float]` (E1–E9), `llm_calls: int`, `llm_tokens_in: int`, `llm_tokens_out: int`, `external_cost_usd: float`, `equivalent_cloud_cost_usd: Optional[float]`, `rate_limit_events: int`.
* **UI Representation**: Header summary badge, System Performance Drawer with engine waterfall breakdown and cost economics.

### 3.7 `StructuredFeedbackRecord` ([models.py:L419-L442](file:///e:/accenture/models.py#L419-L442))
* **Fields**: `feedback_id: int`, `investigation_id: str`, `scenario_id: str`, `persona: str`, `verdict: FeedbackVerdict` (`CORRECT`, `INCORRECT`, `PARTIALLY_CORRECT`, `UNSURE`), `corrected_hypothesis_id: Optional[str]`, `corrected_confidence_state: Optional[str]`, `corrected_action: Optional[str]`, `evidence_grounding_correct: Optional[bool]`, `analyst_notes: Optional[str]`, `validated_precedent: bool`, `validation_precedent_id: Optional[str]`, `received_at: str`.
* **UI Representation**: Inline feedback review bar, analyst feedback history drawer, precedent validation badge.

---

## 4. Personas & Authorization Matrix

Server-side enforcement in [security/entitlements.py](file:///e:/accenture/security/entitlements.py) strictly dictates what each persona is permitted to see and do:

| Feature / Data Entity | Analyst Persona | CFO Persona | Operations Manager Persona |
| :--- | :--- | :--- | :--- |
| **Authorized Sources** | All 7 sources (`orders`, `payment_gateway`, `inventory`, `marketing`, `deployment_log`, `support_tickets`, `release_notes`) | Restricted to `orders` and `inventory` only | Restricted to `orders` and `inventory` (scoped to `region`) |
| **Region Scope** | Global (`all`) | Global (`all`) | Regional (`own_only` e.g. `us-east`) |
| **Technical Telemetry** | Full gateway latency, error codes, deployment commits | Completely stripped before LLM ingestion | Completely stripped |
| **Customer Tickets** | View raw Zendesk ticket messages & devices | Hidden | Hidden |
| **Recommended Actions** | Technical operational directives (e.g. `"Roll back v4.3 checkout-service"`) | High-level business / supplier coordination | Regional segment / store mitigation |
| **Institutional Precedent Validation** | Can mark precedents as `human_validated=True` via `CORRECT` verdict | Observations recorded; cannot stamp precedent validation | Observations recorded; cannot stamp validation |
| **Access Denied Fallback** | Never denied for standard scenarios | Denied if querying technical-only incident slices | Denied if request lacks required `region` parameter |

---

## 5. Application Information Architecture

The UI is structured into three primary functional workspaces:

```
BUSINESSINTELLIGENCE.AI
├── TOP BAR (Global Navigation & System State)
│   ├── Scenario Catalog Selector (INC_001 → INC_008)
│   ├── Persona Lens Switcher (Analyst | CFO | Manager)
│   ├── Region Filter Dropdown (Active when Manager selected)
│   ├── Runtime Telemetry Chip (Provider, Latency, Cost) → Opens System Performance Drawer
│   ├── System Health Button (Drift Status Badge) → Opens Continuous Evaluation Modal
│   └── Run Investigation Action Button
│
├── MAIN WORKSPACE: INCIDENT INVESTIGATION CANVAS
│   ├── Incident Summary Header & KPI Status Bar
│   ├── Engine Pipeline Navigation Rail (E1 → E8 Stage Selector)
│   ├── Stage 1: Signals & Anomaly Detection (E1 KPI Store + E2 Signal Engine)
│   ├── Stage 2: Diagnostic & Segment Decomposition (E3 Diagnostic Engine)
│   ├── Stage 3: Evidence Grounding & SLA Freshness (E4 Evidence Engine)
│   ├── Stage 4: Competing Hypotheses & Rule Challenge (E5 Hypothesis + E6 Challenge)
│   ├── Stage 5: Executive Decision, Action & Outcome (E7 Decision + E8 Outcome)
│   └── Stage 6: Institutional Precedents & Memory (E9 Memory Engine)
│
├── INTERACTION & AUDIT DRAWERS (Secondary Overlays)
│   ├── Inline Feedback & Precedent Review Bar (Bottom Sticky)
│   ├── System Performance & Cost Drawer (Right Slide-over)
│   ├── Continuous Evaluation & Drift Monitoring Modal (Center Modal)
│   ├── Historical Feedback Audit Drawer (Right Slide-over)
│   └── Raw Incident Trace & API Payloads Modal
```

---

## 6. Route & Screen Specification

### 6.1 Route `/` (Main Investigation Workspace)
* **Purpose**: Primary operational canvas for investigating KPI regressions, viewing causal evidence, and acting on recommendations.
* **Primary Persona**: `Analyst` (Default), `CFO`, `Manager`.
* **Key Components**:
  * `InvestigationHeader`: Scenario metadata, persona switcher, trigger button.
  * `KPISignalGrid`: Real-time metric cards with delta % and z-scores.
  * `DiagnosticBreakdown`: Dimensional contribution horizontal bar charts.
  * `EvidenceDeck`: Authorized structured/unstructured evidence cards with freshness SLA badges.
  * `HypothesisMatrix`: Competing hypotheses with 5-rule challenge scorecards.
  * `DecisionHero`: Grounded action recommendation or clear abstention banner with recovery curve.
  * `PrecedentCarousel`: Retrieved historical precedents with confidence and validation status.
  * `FeedbackReviewBar`: Interactive analyst review toolbar.

### 6.2 Modal `/evaluation/health` (Continuous Evaluation & Drift Monitor)
* **Purpose**: Observability dashboard tracking system reliability, model drift, and latency degradation across 50-run count-based windows.
* **Key Components**:
  * Health status banner (`HEALTHY`, `WATCH`, `DEGRADED`, `INSUFFICIENT_DATA`).
  * 6 metric cards with recent value, baseline value, delta, and status reason.
  * Window size counters (Recent vs Baseline).

### 6.3 Drawer `/telemetry/performance` (System Performance & Trace)
* **Purpose**: Deep-dive operational trace inspecting engine execution times, token counts, and cloud economics.
* **Key Components**:
  * LLM Provider & Model badges (`Groq / llama-3.3-70b-versatile` or `Ollama / qwen3:8b`).
  * Engine waterfall bar chart (E1 to E9 latency breakdown).
  * Token accounting card (Prompt vs Completion tokens).
  * Economics card (Local $0.00 compute vs Groq API billing vs Claude reference cost).

---

## 7. Backend → Frontend Traceability Matrix

| Backend Capability | API Endpoint | Frontend Surface | Primary UI Component | User Action | Response Representation | Failure State |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Catalog Discovery** | `GET /scenarios` | Top Bar | `ScenarioSelector` | Select incident scenario | Populates catalog dropdown with live badges | Fallback to hardcoded scenarios |
| **Investigation Run** | `POST /investigate` | Main Canvas | `InvestigationOverview` | Click "Run Investigation" | Renders complete 9-engine result | Banner error + HTTP 403/500 modal |
| **Persona Switching** | `POST /investigate` | Top Bar | `PersonaSwitcher` | Click Analyst/CFO/Manager | Re-executes investigation with persona scope | 403 Access Denied if unauthorized |
| **Feedback Submission**| `POST /feedback` | Bottom Bar | `FeedbackReviewBar` | Submit Verdict & Notes | Shows validation confirmation toast | Red error toast; rollback state |
| **Feedback History** | `GET /feedback/{id}`| Side Drawer | `FeedbackHistoryDrawer` | Click "View Feedback History" | Lists past submissions and reviewer notes | Empty state card |
| **Drift Monitoring** | `GET /evaluation/health`| Modal | `SystemHealthModal` | Click "System Health" badge | Displays 6 drift metrics and health status | "Database Unavailable" modal |
| **Runtime Telemetry** | Telemetry in result | Header Chip | `SystemPerformanceDrawer` | Click "⚡ 2.8s" chip | Opens engine latency waterfall & cost | Displays "N/A" for missing timers |

---

## 8. Frontend State Machines

### 8.1 Investigation Execution Lifecycle
```
[IDLE] (Scenario Selected, Cached / Blank Result)
  │
  ▼ User clicks "Run Investigation" or changes Persona
[SUBMITTING] (Payload validated, HTTP POST dispatched)
  │
  ▼ Request in-flight
[RUNNING] (Vite animated shimmer active, elapsed seconds counter ticking)
  │
  ├──► [SUCCESS 200] ──► Render Signals, Evidence, Hypotheses, Decision, Precedents
  │
  ├──► [ACCESS_DENIED 403] ──► Render Persona Restricted Security Banner
  │
  ├──► [TIMEOUT / 500] ──► Render Error Banner with Retry & "Keep Viewing Previous"
```

### 8.2 Structured Feedback Submission Lifecycle
```
[UNREVIEWED] (Feedback Bar active)
  │
  ▼ User selects Verdict (CORRECT / INCORRECT / PARTIALLY_CORRECT / UNSURE)
[DRAFTING] (Optional corrected hypothesis, confidence, action, and notes filled)
  │
  ▼ User clicks "Submit Review"
[SUBMITTING_FEEDBACK] (POST /feedback in-flight)
  │
  ├──► [SUCCESS 200]
  │       ├── If CORRECT + Analyst ──► Badge: "Precedent Human-Validated" (Green)
  │       └── If Other / Non-Analyst ──► Badge: "Feedback Recorded" (Neutral)
  │
  └──► [FAILED 500] ──► Error Toast: "Failed to persist feedback. Retrying..."
```

---

## 9. Real-Time & Streaming Requirements

1. **Investigation Latency Counter**: During investigation execution, the UI must render an active millisecond/second timer (`font-mono`) updating at $10\text{Hz}$ to communicate that backend LLM/SQL inference is actively executing.
2. **Tabular Number Roll-Overs**: When switching scenarios or re-running investigations, numerical counters (`observed`, `z_score`, `contribution_pct`, `latency_ms`) must transition smoothly using `font-mono tabular-nums`.
3. **No Unsolicited Rerenders**: Streaming or live counters must be isolated in memoized leaf components (`React.memo`) to avoid triggering full React component tree reconciliations.
4. **Historical vs Live Separation**: Time-series charts must visually differentiate historical baseline corridors (shaded grey band) from the active anomaly period (shaded rose/red band).

---

## 10. Metrics & Visualization Requirements

| Metric | Source Engine | Data Type | Formula / Range | Best Frontend Representation |
| :--- | :--- | :--- | :--- | :--- |
| **KPI Value** | E1 KPI Store | Numeric (Currency / Ratio / ms) | Depends on KPI contract | Large tabular-num card with formatted unit (`$`, `%`, `ms`) |
| **Anomaly Delta %** | E2 Signal | Float percentage | $\frac{\text{Observed} - \text{Expected}}{\text{Expected}} \times 100$ | Sign-colored badge (`+14.2%` green/red) |
| **Statistical Z-Score**| E2 Signal | Float ($\sigma$) | $\frac{\text{Observed} - \mu}{\sigma}$ ($[-1000, 1000]$) | Monospace badge: `z = +3.45σ` |
| **Segment Contribution**| E3 Diagnostic | Percentage | Share of total delta ($[0, 100\%]$) | Horizontal stacked distribution bar |
| **Evidence Reliability**| E4 Evidence | Weight ($[0, 1]$) | Decay based on SLA staleness | 1–5 pip indicator or decimal pill (`0.85`) |
| **Hypothesis Support** | E6 Challenge | Score ($[0, 1]$) | Weighted sum of 5 rule scores | Segmented progress bar |
| **Contradiction Penalty**| E6 Challenge | Score ($[0, 1]$) | Sum of refuting evidence weights | Red penalty indicator (`-0.40`) |
| **Projected Recovery** | E8 Outcome | Percentage ($[0, 100\%]$) | Deterministic recovery curve | Circular gauge or projection line chart |
| **E2E Latency p95** | Health Service | Latency (ms) | 95th percentile of recent 50 runs | Metric delta card against baseline |
| **Abstention Drift Rate**| Health Service | Ratio ($[0, 1]$) | Count of abstentions / total runs | Drift indicator with $\pm 15\%$ watch band |

---

## 11. Forms & User Actions Specification

### 11.1 Investigation Request Form (Top Bar)
* **Fields**:
  * `scenario_id`: Select dropdown (8 options: `INC_001` to `INC_008`). Default: `INC_001`.
  * `persona`: Segmented tab switch (`analyst`, `cfo`, `manager`). Default: `analyst`.
  * `region`: Text input / select dropdown (enabled only when `persona == "manager"`).
* **Submission**: Click `Run Investigation` button or press `Ctrl + Enter`.
* **Validation**: If `persona == "manager"` and `region` is empty, highlight region input with validation tooltip.

### 11.2 Structured Feedback Submission Form (Review Bar)
* **Fields**:
  * `verdict`: Radio group / toggle buttons (`CORRECT`, `INCORRECT`, `PARTIALLY_CORRECT`, `UNSURE`). Required. Default: `CORRECT`.
  * `corrected_hypothesis_id`: Dropdown (`H1`, `H2`, `H3`). Optional (active on `INCORRECT`/`PARTIALLY_CORRECT`).
  * `corrected_confidence_state`: Dropdown (`HIGH`, `MEDIUM`, `LOW`, `ABSTAIN`). Optional.
  * `corrected_action`: Text area ($1$–$5000$ chars). Optional.
  * `evidence_grounding_correct`: Checkbox toggle. Default: `true`.
  * `analyst_notes`: Text area ($1$–$5000$ chars). Optional.
* **Submission**: Click `Submit Review` button.
* **Behavior**: Optimistically disables button and renders validation badge upon HTTP 200.

---

## 12. Search, Filter & Sorting Requirements

1. **Scenario Search & Filter**: Filter catalog by Domain (`E-Commerce`, `Infrastructure`, `Security`) and Status (`Live`, `Evaluation Only`).
2. **Evidence Filtering**: Filter assembled evidence deck by Source (`orders`, `payment_gateway`, `deployment_log`, etc.) and Method (`SQL`, `RETRIEVAL`).
3. **Hypothesis Sorting**: Fixed sort descending by `final_score` ($[0, 1]$).
4. **Precedent Filtering**: Filter retrieved institutional precedents by `ConfidenceState` and `Human Validated` status.

---

## 13. Error & Edge-State Matrix

| Error Scenario | HTTP Code | Backend Trigger | Frontend UI Treatment |
| :--- | :---: | :--- | :--- |
| **Unsupported Persona** | `422` | Invalid persona string passed | Form validation toast: "Please select a valid persona." |
| **Entitlements Unresolvable**| `403` | Configuration load failure (Fail Closed) | Security banner: "Access Denied — Entitlements could not be resolved." |
| **Empty Authorization Scope**| `403` | Persona has zero access to scenario sources | Amber warning card: "Access Restricted: You lack access to data for this incident." |
| **Scenario Not Found** | `404` | Investigation ID not found during feedback | Red error toast: "Incident investigation record not found." |
| **Postgres Down on Investigate**| `200` (Degraded) | DB fails $\to$ E1 returns NaN $\to$ E2 no signals $\to$ E7 Abstains | Clean informational card: "Data Unavailable — System safely abstained." |
| **Groq / Ollama Down** | `200` (Degraded) | E5/E7 LLM fails $\to$ E7 falls back to synthetic abstain payload | Warning banner: "LLM Narrative Unavailable — Fallback abstention active." |
| **Postgres Down on Health Check**| `503` | Database connection unavailable | Modal error state: "Continuous evaluation metrics unavailable." |
| **Groq HTTP 429 Rate Limit** | `200` (Retried) | Rate limit backoff retried in backend | Telemetry chip displays retry badge: `Rate Limits: 1` |

---

## 14. API Contract for Frontend (`web/src/lib/api.ts`)

```typescript
// Core API Methods matching backend endpoints
export interface ApiClient {
  getHealth(): Promise<{ status: string; llm_backend: string }>;
  getScenarios(): Promise<{ scenarios: ScenarioMeta[] }>;
  getKpiContract(): Promise<Record<string, any>>;
  investigate(req: InvestigateRequest): Promise<InvestigationResult>;
  submitFeedback(req: StructuredFeedbackSubmission): Promise<FeedbackResponse>;
  getFeedbackForScenario(scenarioId: string): Promise<{ scenario_id: string; count: number; records: FeedbackRecord[] }>;
  getFeedbackMetrics(): Promise<FeedbackMetricsSummary>;
  getSystemHealth(): Promise<SystemHealthData>;
}
```

---

## 15. Recommended Frontend Architecture

```
web/src/
├── components/
│   ├── layout/               # TopBar, AppShell, PersonaSwitcher, ScenarioSelector
│   ├── investigation/        # Main Canvas, InvestigationOverview, StageSteppers
│   ├── kpi/                  # KPISignalGrid, MetricCard, CorridorChart
│   ├── diagnostic/           # DimensionalContributionBar, SegmentTable
│   ├── evidence/             # EvidenceCard, FreshnessBadge, CitationModal
│   ├── hypothesis/           # HypothesisCard, RuleMatrix, ConfidenceMeter
│   ├── decision/             # DecisionHero, ActionCard, RecoveryProjectionGauge
│   ├── memory/               # PrecedentCard, InstitutionalMemoryCarousel
│   ├── system/               # SystemPerformanceDrawer, SystemHealthModal
│   └── common/               # ErrorBoundary, Tooltip, TabularNum, Badge
├── lib/
│   ├── api.ts                # Authoritative typed backend API client
│   ├── defaultData.ts        # Fully-typed offline mock fallback dataset (INC_001)
│   └── utils.ts              # Formatting utilities (currency, pct, ms, z-score)
├── types/
│   └── investigation.ts      # Authoritative TypeScript mirror of models.py
└── test/
    └── setup.ts              # Vitest & Testing Library DOM matchers
```

---

## 16. Security & Data Exposure Rules

1. **Zero Secret Leakage**: API responses and frontend views must never expose API keys, credential rotation pool indexes, database credentials, or internal file paths.
2. **Persona Boundary Respect**: The frontend must never attempt to render fields stripped by the backend (e.g. `support_tickets` or `deployment_log` for the `CFO` persona).
3. **Fail-Closed Presentation**: If `access_denied` is true, suppress all analytical metric containers and display the official access-denied security card.
4. **Input Sanitization**: All user inputs in the feedback text area must be constrained to 5,000 characters and stripped of executable scripts.

---

## 17. Testing Requirements Matrix

| Layer | Target | Framework | Success Criteria |
| :--- | :--- | :--- | :--- |
| **Unit Testing** | `utils.ts`, formatters, sanitizers | Vitest | 100% pass on numbers, deltas, currencies, z-scores |
| **Component Testing** | `ErrorBoundary`, `PersonaSwitcher`, `EvidenceCard` | React Testing Library + JSDOM | Renders without crashing; handles mock props; keyboard accessible |
| **Integration Testing**| `InvestigationOverview`, `FeedbackReviewBar` | Vitest + Mock API | Verified state transitions (Loading $\to$ Success $\to$ Error) |
| **E2E Live Verification**| Full user journey (`INC_001` $\to$ `INC_002` $\to$ Feedback) | Live Browser Dry Run | 0 console errors; verified live API roundtrips |

---

## 18. Gaps & Missing Backend Capabilities

### P0 — Blocking (None)
*All core investigation, feedback, and drift monitoring endpoints are live and operational.*

### P1 — Important (Enhancements)
1. **Granular Action Recommendation Schema**:
   * *Gap*: `models.Decision` provides a single `recommended_action: Optional[str]` string rather than discrete `owner`, `controllable_lever`, and `expected_impact` fields.
   * *Frontend Treatment*: Frontend currently renders the narrative action string directly; should support parsing structured sub-blocks when available.
2. **True Wall-Clock E2E Middleware Timer**:
   * *Gap*: `HealthMonitorService` sums engine latencies rather than recording full HTTP wall-clock duration.
   * *Frontend Treatment*: Displays engine summed latency and explicitly notes internal compute duration.

### P2 — Nice-to-Have
1. **Server-Sent Events (SSE) Streaming for Long Runs**:
   * *Gap*: `/investigate` currently runs as a synchronous HTTP POST. On slow local LLMs, this can take 15–30s.
   * *Frontend Treatment*: Implemented animated live seconds timer and background execution state to keep UI fully responsive.

---

## 19. Summary & Metrics

```
============================================================
FINAL BACKEND → FRONTEND PRODUCT DISCOVERY SUMMARY
============================================================
TOTAL BACKEND CAPABILITIES:            10
TOTAL USER-FACING CAPABILITIES:         8
TOTAL FRONTEND ROUTES PROPOSED:         3 (Main Canvas, System Health, Performance Trace)
TOTAL MAJOR UI SURFACES:                8 (Header, Signals, Diagnostic, Evidence, Hypotheses, Decision, Precedents, Feedback)
TOTAL REAL-TIME / LIVE SURFACES:        3 (Inference Latency Counter, Tabular Numbers, Health Monitor)
TOTAL VISUALIZATION REQUIREMENTS:      10 (KPI Card, Z-Score Badge, Distribution Bar, Evidence Deck, Rule Matrix, Confidence Meter, Recovery Gauge, Precedent Carousel, Latency Waterfall, Drift Cards)
TOTAL PERSONAS:                         3 (Analyst, CFO, Operations Manager)
TOTAL IMPORTANT BACKEND GAPS:           2 (Granular Action Schema, SSE Stream)
============================================================
```
