# Business Generalization & Architecture Boundary Contract

> **Architecture Paradigm:** Reusable Engine Spine + Business Configuration & Data Bundle  
> **Deployment Model:** Single-Business Deployment / Standalone Business Instance (NOT SaaS Multi-Tenancy)  
> **Core Principle:** The core intelligence engine (E1–E9, orchestration, verification, canonical evidence, LLM interface, telemetry, evaluation) is **100% domain-agnostic and reusable**. Deploying the platform for a new business (Retail, FinTech, Logistics, SaaS, Healthcare) requires **ZERO code modifications to E1–E9**—only providing a new business configuration bundle and data store.

---

## 1. Architectural Separation Overview

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 REUSABLE CORE INTELLIGENCE SPINE                                 │
│                                  (Shared, Pure, Domain-Agnostic)                                 │
│                                                                                                  │
│  ┌───────────────────────┐   ┌───────────────────────┐   ┌────────────────────────────────────┐  │
│  │ E1 KPI Metric Engine  │   │ E2 Anomaly Detector   │   │ E3 Diagnostic Decomposition        │  │
│  │ (Baseline stats / Z)  │   │ (±3σ / Corridor math) │   │ (Dimensional slice contribution)   │  │
│  └───────────┬───────────┘   └───────────┬───────────┘   └─────────────────┬──────────────────┘  │
│              │                           │                                 │                     │
│              ▼                           ▼                                 ▼                     │
│  ┌───────────────────────┐   ┌───────────────────────┐   ┌────────────────────────────────────┐  │
│  │ E4 Evidence Normalizer│   │ E5 Hypothesis Engine  │   │ E6 Verification & Challenge Engine │  │
│  │ (Canonical Model)     │   │ (Semantic Synthesis)  │   │ (5 Deterministic Rules / Penalties)│  │
│  └───────────┬───────────┘   └───────────┬───────────┘   └─────────────────┬──────────────────┘  │
│              │                           │                                 │                     │
│              ▼                           ▼                                 ▼                     │
│  ┌───────────────────────┐   ┌───────────────────────┐   ┌────────────────────────────────────┐  │
│  │ E7 Decision & Action  │   │ E8 Counterfactual Sim │   │ E9 Precedent Vector Memory         │  │
│  │ (7-Field Action Graph)│   │ (Economic Projections)│   │ (Cosine Retrieval + Decay + Boost) │  │
│  └───────────────────────┘   └───────────────────────┘   └────────────────────────────────────┘  │
│                                                                                                  │
│  • Investigation Orchestrator (`pipeline/investigate.py`)                                        │
│  • LLM Provider Interface (`llm/provider.py` — Groq / Ollama / OpenAI)                           │
│  • Runtime Telemetry & Cost Tracker (Latency, SQL/Vector queries, Token counts, Dollar cost)    │
│  • Continuous Evaluation Framework (`evaluation/evaluator.py`, `evaluation/health.py`)          │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                ▲
                                                │ Loaded via BusinessContext
                                                ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             BUSINESS-SPECIFIC CONFIGURATION & DATA                               │
│                            (Configured per Business Deployment Instance)                         │
│                                                                                                  │
│  1. KPI Semantic Contract (`kpi_contracts.yaml`)                                                 │
│     - Metric definitions, SQL/Pandas formulas, grains (hourly/daily), driver hierarchies,        │
│       lineage graphs, baseline standard deviations, access levels.                               │
│                                                                                                  │
│  2. Business Materiality & Impact Rules (`materiality.yaml` / contract extensions)               │
│     - Revenue multipliers, customer volume impact, operational criticality levels.               │
│                                                                                                  │
│  3. Heterogeneous Source Registry (`sources.yaml`)                                               │
│     - Source IDs, refresh cadences, SLA thresholds, baseline data quality scores, system owners. │
│                                                                                                  │
│  4. Security & Decision Rights Matrix (`entitlements.yaml`)                                      │
│     - Personas (`analyst`, `cfo`, `manager`), authorized sources, field masking, decision rights. │
│                                                                                                  │
│  5. Precedent Retention & Memory Policy (`memory_retention.yaml`)                                │
│     - Source-specific TTLs, validity expiration, human validation boost weights.                 │
│                                                                                                  │
│  6. Scenario Registry & Dynamic Windows (`scenarios.yaml`)                                       │
│     - Active incident definitions, historical baseline & incident time windows, operational tags.│
│                                                                                                  │
│  7. Evaluation & Benchmark Ground Truth (`ground_truth.json`)                                    │
│     - Expected winning hypotheses, confidence states, reference actions, target metrics.         │
│                                                                                                  │
│  8. Deployment Storage                                                                           │
│     - PostgreSQL database: `kpi_values`, domain events, `investigations`, `feedback`.            │
│     - ChromaDB vector store: `evidence_{scenario_id}`, `investigation_precedents`.               │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Containerized Business Deployment Model

```text
                        REUSABLE E1–E9 BASE IMAGE
                         (100% Domain-Agnostic)
                                   │
                ┌──────────────────┴──────────────────┐
                ▼                                     ▼
      Business A Container                  Business B Container
     (e.g. Retail Enterprise)               (e.g. FinTech Banking)
                │                                     │
      ┌─────────┴─────────┐                 ┌─────────┴─────────┐
      │  • Config A       │                 │  • Config B       │
      │  • PostgreSQL A   │                 │  • PostgreSQL B   │
      │  • Vectors A      │                 │  • Vectors B      │
      └───────────────────┘                 └───────────────────┘
```

Each business deployment runs the **exact same immutable E1–E9 container image**, configured via environment variables and mounted volume bundles:

```text
Business A Deployment (Retail Enterprise)
├── Base Image: biai-engine:latest (E1–E9 Core)
├── Volume Mount: /app/config/ -> config_retail/ (kpi_contracts.yaml, sources.yaml, entitlements.yaml)
├── Environment: DATABASE_URL=postgresql://biai:biai@db-retail:5432/retail_db
└── Environment: CHROMA_HOST=chroma-retail, CHROMA_PORT=8000

Business B Deployment (FinTech Banking)
├── Base Image: biai-engine:latest (E1–E9 Core)
├── Volume Mount: /app/config/ -> config_banking/ (kpi_contracts.yaml, sources.yaml, entitlements.yaml)
├── Environment: DATABASE_URL=postgresql://biai:biai@db-banking:5432/banking_db
└── Environment: CHROMA_HOST=chroma-banking, CHROMA_PORT=8000
```

---

## 3. The `BusinessContext` Abstraction

The `BusinessContext` is the lightweight encapsulation loaded at application startup (via environment variable `BUSINESS_CONFIG_DIR` or direct dependency injection) that binds the reusable engine to a business deployment:

```python
@dataclass(frozen=True)
class BusinessContext:
    """Encapsulates all business configuration, semantic contracts, and storage handles for a deployment."""
    business_name: str                  # e.g. "Global Retail Ops" or "Apex Banking"
    domain: str                         # e.g. "Retail / E-Commerce" or "FinTech"
    kpi_contract: dict                  # Loaded from kpi_contracts.yaml
    sources_config: list                # Loaded from sources.yaml
    entitlements_config: dict           # Loaded from entitlements.yaml
    memory_retention_config: dict       # Loaded from memory_retention.yaml
    scenarios_config: dict              # Loaded from scenarios.yaml
    ground_truth: Optional[dict]        # Loaded from ground_truth.json (if present)
    db_conn: Any                        # Deployment PostgreSQL connection pool
    chroma_client: Any                  # Deployment ChromaDB client handle
    llm_provider: LLMProvider           # Shared / configured LLM provider instance
```

---

## 4. Reusable Core vs. Business Configuration Matrix

| Layer / Component | Reusable Computational Responsibility | Business-Specific Configuration |
| :--- | :--- | :--- |
| **E1: KPI Store** | Calculates rolling mean ($\mu$), standard deviation ($\sigma$), sample size sufficiency ($N \ge 30$), and data quality flags. | Metric keys (`kpi_id`), SQL aggregation queries, time grains (hourly, 15-min, daily). |
| **E2: Signal & Materiality** | Computes $z$-scores ($z = \frac{x - \mu}{\sigma}$), percentage deltas, anomaly corridor bounds, and financial/volume materiality scores. | Standard deviation thresholds ($3.0\sigma$), percentage trigger limits ($10\%$), financial loss formulas, volume impact multipliers. |
| **E3: Diagnostic Engine** | Computes dimensional segment contributions: $$\text{Contribution}\% = \frac{\Delta \text{Segment}}{\Delta \text{Total}} \times 100$$ | Dimension hierarchies (e.g. `region`, `device`, `carrier`, `asset_class`) defined in `kpi_contracts.yaml`. |
| **E4: Evidence Normalizer** | Transforms heterogeneous inputs (SQL records, event streams, markdown release notes) into standard `CanonicalEvidenceRecord` objects with SHA-256 provenance hashes. | Source definitions in `sources.yaml`, refresh cadences, SLA thresholds, base quality weights. |
| **E5: Hypothesis Engine** | Synthesizes competing root-cause candidate explanations ($H_1, H_2, H_3$) by binding observed anomalies to domain causal drivers. | Causal driver hierarchy (`drivers:` list in `kpi_contracts.yaml`). No hardcoded prompt text. |
| **E6: Challenge Engine** | Executes 5 formal verification rules (Timeline, Segment Alignment, Corroboration, Mechanism Plausibility, Contradiction Penalty) and calculates confidence score $[0, 1]$ or enforces **ABSTAIN**. | Verification rule weights and contradiction penalty thresholds. |
| **E7: Decision Engine** | Formulates structured 7-field action recommendations mapped strictly to the authorized persona's decision rights. | Decision rights mapping (`decision_rights:` in `entitlements.yaml`) per persona (`analyst`, `cfo`, `manager`). |
| **E8: Counterfactual Simulator**| Computes expected economic recovery trajectories and time-to-recovery metrics based on action efficacy parameters. | Financial baseline values and recovery curve coefficients. |
| **E9: Memory Engine** | Computes vector similarity over past precedents, applies confidence weighting, human validation boosts ($+0.1$), and source TTL filtering. | Source-specific TTL limits in `memory_retention.yaml`. |
| **Pipeline Orchestrator** | Coordinates E1 $\rightarrow$ E9 execution, manages dependencies, enforces fail-closed error boundaries, and collects runtime telemetry. | Incident scenario list and observation windows (`scenarios.yaml`). |
| **Telemetry & Cost Tracker** | Measures millisecond execution time per engine, query counts, prompt tokens, completion tokens, and dollar cost ($ USD). | Cost rates per 1K tokens by model provider. |

---

## 5. Core Data Contracts Between Engine and Configuration

### Contract 1: Canonical Evidence Model (`E4`)
Every heterogeneous source (whether daily SQL revenue, hourly gateway telemetry, or unstructured markdown deployment notes) is normalized into this common structure:

```typescript
interface CanonicalEvidenceRecord {
  id: string;                    // Unique identifier (e.g. "ev_deploy_001")
  source_id: string;             // References sources.yaml (e.g. "deployment_log")
  source_name: string;           // Human-readable source name
  entity: string;                // Target entity (e.g. "service:checkout-gateway")
  observation: string;           // Normalized textual summary
  timestamp: string;             // ISO-8601 UTC timestamp
  metric?: string;               // Associated KPI or driver (if numeric)
  dimension?: Record<string, string>; // e.g. { "region": "eu-west", "device": "android" }
  value?: number;                // Observed numeric value (if quantitative)
  freshness_minutes: number;     // Staleness at observation time
  source_reliability: number;    // Calculated weight [0.0, 1.0]
  confidence: number;            // Extraction or measurement confidence [0.0, 1.0]
  method: "SQL" | "STATISTICS" | "BUSINESS_RULE" | "VECTOR_RETRIEVAL" | "LLM";
  lineage: string[];             // Upstream systems trace
  provenance_hash: string;       // SHA-256 signature of source payload
}
```

---

### Contract 2: Materiality & Anomaly Movement (`E2`)
Distinguishes pure statistical significance from business materiality:

```typescript
interface MaterialityAssessment {
  kpi_id: string;
  observed_value: number;
  baseline_mean: number;
  z_score: number;
  delta_pct: number;
  is_statistical_anomaly: boolean;   // |z| >= 3.0
  financial_impact: {
    estimated_loss: number;          // e.g. -1850000.00
    currency: string;                // e.g. "INR" | "USD"
  };
  volume_impact: {
    affected_units_or_users: number; // e.g. 14200
    unit_label: string;              // e.g. "failed transactions"
  };
  business_materiality: "NEGLIGIBLE" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  priority_rank: number;             // 1 = Highest priority for investigation
}
```

---

### Contract 3: Method Transparency Specification (`E1`–`E9`)
Every intermediate calculation and final insight declares its computational method:

```typescript
enum ProcessingMethod {
  DETERMINISTIC_SQL = "SQL",
  DETERMINISTIC_STATS = "STATISTICS",
  DETERMINISTIC_RULES = "BUSINESS_RULE",
  VECTOR_RETRIEVAL = "VECTOR_RETRIEVAL",
  LLM_SYNTHESIS = "LLM_SYNTHESIS",
  HYBRID = "HYBRID",
}

interface MethodProvenance {
  stage: "E1" | "E2" | "E3" | "E4" | "E5" | "E6" | "E7" | "E8" | "E9";
  primary_method: ProcessingMethod;
  is_llm_driven: boolean;
  algorithm_or_prompt_ref: string;
  source_data_refs: string[];
}
```

---

### Contract 4: Structured 7-Field Action Recommendation (`E7`)
Replaces open-ended narrative suggestions with an actionable, role-authorized decision record:

```typescript
interface StructuredActionRecommendation {
  driver: string;                    // e.g. "Payment Gateway PG-07 elevated timeout rate"
  controllable_lever: string;        // e.g. "Gateway routing weight allocation"
  action: string;                    // e.g. "Reroute 100% of EU-West payment traffic to Gateway PG-02"
  expected_impact: string;           // e.g. "Restores conversion rate from 0.8% to 2.4% within 15 minutes"
  owner: string;                     // e.g. "Platform Engineering / Payments On-Call"
  confidence: number;                // e.g. 0.88
  monitoring_plan: string;           // e.g. "Monitor payment_failure_rate_15min; alert if > 0.5% after 20m"
  authorized_personas: ("analyst" | "cfo" | "manager")[]; // Decision rights mapping
}
```

---

### Contract 5: Uncertainty & Abstention Object (`E6`)
Explicitly explains *why* the system chose to abstain and what missing evidence would resolve it:

```typescript
interface UncertaintyExplanation {
  confidence_score: number;          // e.g. 0.41 (< 0.50 threshold)
  confidence_state: "HIGH" | "MEDIUM" | "LOW" | "ABSTAIN";
  abstention_reason: string;         // e.g. "Contradictory evidence: Gateway latency spike refuted by inventory stockout logs"
  evidence_coverage_ratio: number;   // e.g. 0.35 (35% of required driver signals available)
  contradiction_count: number;       // e.g. 2 active contradictions
  missing_evidence: string[];        // e.g. ["Deployment log for payment-service v4.2", "Bank gateway status webhook"]
  recommended_next_action: string;   // e.g. "Request manual telemetry pull for Gateway PG-07 before executing rollback"
}
```

---

### Contract 6: Runtime Execution & Telemetry Summary
Tracks platform efficiency, operational costs, and engine latencies per investigation:

```typescript
interface RuntimeTelemetry {
  investigation_id: string;
  total_latency_ms: number;
  engine_latencies: Record<string, number>; // { "E1": 12, "E2": 8, "E4": 42, "E5": 820, "E6": 15, "E7": 610, ... }
  sql_queries_executed: number;
  vector_searches_executed: number;
  llm_calls: {
    provider: string;              // "groq" | "ollama"
    model: string;                 // "llama-3.3-70b-versatile" | "qwen2.5:7b"
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    estimated_cost_usd: number;
  };
  cache_metrics: {
    embedding_cache_hit: boolean;
    result_cache_hit: boolean;
  };
}
```

---

## 6. Business Generalization: Decoupling Retail Hardcodings

To make the codebase 100% business-generalized, the following items will be cleanly separated from engine code into configuration:

1. **Move Scenario Windows from Code to Config:**
   * Extract `_SCENARIO_WINDOWS` dictionary from `pipeline/investigate.py` into a business `config/scenarios.yaml`.
2. **Dynamic Causal Drivers in E5 Hypothesis Prompts:**
   * Replace hardcoded checkout/payment prompt text in `engines/hypothesis.py` with dynamic driver injection loaded directly from `kpi_contracts.yaml`.
3. **Dynamic Frontend Scenario Catalog:**
   * Replace the hardcoded `SCENARIO_CATALOG` constant in `web/src/lib/api.ts` with a dynamic `/api/scenarios` endpoint that loads from the active business configuration.

---

## 7. Onboarding Workflow for a New Business

When deploying `BusinessIntelligence.ai` for a new business, the operator supplies a **Business Configuration & Data Bundle**:

```text
my_business_deployment/
├── config/
│   ├── kpi_contracts.yaml      # Definitions, formulas, drivers, lineages, access policies
│   ├── sources.yaml            # Data feeds, update frequencies, SLAs, quality weights
│   ├── entitlements.yaml       # Personas, authorized sources, decision rights
│   ├── memory_retention.yaml   # Precedent TTL rules by source
│   ├── scenarios.yaml          # Incident scenarios and observation time windows
│   └── materiality.yaml        # Business impact multipliers and priority criteria
├── data/
│   └── schema.sql              # Transactional and metric tables for PostgreSQL
├── vectors/
│   └── seed_evidence/          # Unstructured incident documentation, release logs
└── evaluation/
    └── ground_truth.json       # Benchmark evaluation ground truth
```

**Zero changes to E1–E9 engine code are required.**
