# Comprehensive Multi-Tenant Architectural Isolation Audit

> **Audit Type:** Architectural Isolation & Multi-Business Onboarding Assessment  
> **Repository:** `BusinessIntelligence.ai`  
> **Target Status:** Multi-Tenant Isolation Strategy  
> **Current Status:** Single-Tenant (Retail-Specialized Demo Context)

---

## 1. Executive Summary & Core Isolation Finding

The current system is designed around a single domain context (*"Retail / Consumer Goods"*). While the mathematical and algorithmic engines (`E1`–`E8`) are largely domain-agnostic, **all stateful storage layers (PostgreSQL tables, ChromaDB collections, global FastAPI lifespans, static YAML contracts, and React catalog constants) are shared globally without a `tenant_id` or namespace partition**.

If a second business is deployed into the existing environment without isolation:
1. **Direct Data Leaks:** Tables querying by `WHERE scenario_id = %s` will mix customer orders, financial revenue, payment latencies, and support tickets between businesses.
2. **E9 Precedent Contamination:** The single `investigation_precedents` ChromaDB collection will recommend retail checkout rollback actions for unrelated financial, healthcare, or logistics incidents.
3. **Drift Health Distortion:** Continuous evaluation windows (50 recent investigations) will blend metrics across tenants, triggering false degradation alarms.
4. **Prompt & Driver Bias:** E5 hypothesis generator prompt templates will inject e-commerce checkout drivers into non-retail domains.

---

## 2. In-Depth Audit by Architectural Subsystem

### Subsystem 1: PostgreSQL Relational Layer

| Exact Component / Table | Classification | Why Isolation is Required | Risk if Shared / Leaked | Current Repo Behavior | Already Isolated? |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **`sources` table**<br>([`etl/schema.sql`](file:///e:/accenture/etl/schema.sql#L10-L21)) | **MUST BE ISOLATED** | Contains business-specific data source schemas, table origins, internal SLA minutes, and data ownership contacts. | Business A discovers internal source names, connection topologies, and ingestion owners of Business B. | Single global `sources` table keyed only on `source_id`. | ❌ **No** |
| **`kpi_values` table**<br>([`etl/schema.sql`](file:///e:/accenture/etl/schema.sql#L28-L43)) | **MUST BE ISOLATED** | Holds raw numeric KPI metrics, granular dimensional filters (`JSONB`), and time-series observations. | Complete leakage of proprietary financial, conversion, and operational metrics. | Keyed on `(kpi_id, scenario_id, period)`. Identical scenario IDs (e.g. `INC_001`) collide and overwrite data. | ❌ **No** |
| **Domain Event Tables**<br>(`orders`, `payment_events`, `inventory_events`, `marketing_events`, `support_tickets`, `deployment_log`)<br>([`etl/schema.sql`](file:///e:/accenture/etl/schema.sql#L48-L147)) | **MUST BE ISOLATED** | Store transaction IDs, customer device fingerprints, payment gateway error codes, SKU inventory levels, marketing spend, and software deployment git changelogs. | Massive GDPR/PII breach, exposure of financial transaction volume, and leakage of proprietary code/deployment notes. | Tables are hardcoded with retail column schemas (`store_id`, `sku_id`, `aov`). Keyed only by `scenario_id`. | ❌ **No** |
| **`investigations` table**<br>([`etl/schema.sql`](file:///e:/accenture/etl/schema.sql#L177-L187)) | **MUST BE ISOLATED** | Persists complete investigation result payloads (`result_json JSONB`) containing root-cause diagnoses, executive action directives, and LLM reasoning. | Business A reads executive strategic directives and system vulnerability assessments of Business B. | Keyed on `investigation_id` with `scenario_id` indexing. No tenant partitioning. | ❌ **No** |
| **`feedback` table**<br>([`etl/schema.sql`](file:///e:/accenture/etl/schema.sql#L152-L172)) | **MUST BE ISOLATED** | Stores human analyst corrections, validated precedent links, and internal operational feedback notes. | Internal analyst notes, dispute resolutions, and operational corrections leak across business boundaries. | Shared global table. Keyed on `feedback_id` and `investigation_id`. | ❌ **No** |
| **`data_quality_log` table**<br>([`pipeline/investigate.py`](file:///e:/accenture/pipeline/investigate.py#L253-L265)) | **MUST BE ISOLATED** | Records ingestion timestamps and data quality confidence scores per scenario. | Ingestion lag in Business A falsely triggers data-quality guards and suppresses investigations in Business B. | Queried by `scenario_id` and `ts` only. | ❌ **No** |
| **Database Connection Pool**<br>([`api/main.py`](file:///e:/accenture/api/main.py#L151-L157)) | **NEEDS EXPLICIT TENANT KEY / NAMESPACE** | Global connection pool executing all queries against a single PostgreSQL database (`DATABASE_URL`). | Query collision or cross-tenant query execution without schema isolation. | Single global `state.db_conn` instantiated at server startup. | ❌ **No** |

---

### Subsystem 2: ChromaDB Vector Storage & Embedding Layer

| Exact Component / Collection | Classification | Why Isolation is Required | Risk if Shared / Leaked | Current Repo Behavior | Already Isolated? |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **`evidence_{scenario_id}` Collections**<br>([`engines/evidence.py`](file:///e:/accenture/engines/evidence.py#L452)) | **MUST BE ISOLATED** | Stores unstructured vector embeddings of release notes, internal engineering documentation, and support tickets. | Business A retrieves private engineering changelogs and customer tickets of Business B during vector search. | Collection name is hardcoded to `evidence_{scenario_id}` (e.g. `evidence_INC_001`). Collides immediately. | ❌ **No** |
| **`investigation_precedents` Collection**<br>([`engines/memory.py`](file:///e:/accenture/engines/memory.py#L38)) | **MUST BE ISOLATED** | The centralized E9 institutional memory bank storing embeddings of all past resolved incidents and recommended actions. | Severe E9 contamination: an incident in a FinTech tenant matches a retail e-commerce precedent, recommending irrelevant or damaging actions. | Single static collection name `_COLLECTION_NAME = "investigation_precedents"` shared globally. | ❌ **No** |
| **Embedding Generation Pipeline**<br>([`llm/provider.py`](file:///e:/accenture/llm/provider.py#L204-L226)) | **CAN BE SHARED SAFELY** | Pure stateless vector transformation (`bge-m3` model via Ollama/HuggingFace). | None, provided input text is tenant-scoped and vectors are stored in isolated collections. | Stateless HTTP POST to `/api/embed`. | ✅ **Yes** |

---

### Subsystem 3: KPI & Semantic Layer

| Exact Component / Contract | Classification | Why Isolation is Required | Risk if Shared / Leaked | Current Repo Behavior | Already Isolated? |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **`kpi_contracts.yaml`**<br>([`config/kpi_contracts.yaml`](file:///e:/accenture/config/kpi_contracts.yaml)) | **SHARED CODE, BUSINESS-SCOPED CONFIG** | Defines business domain, KPI formulas, metric grains, drivers (`payment_success_rate`, `footfall`), and statistical thresholds. | Financial / SaaS metrics will be evaluated using retail e-commerce formulas and irrelevant drivers. | Loaded once at startup into global `app.state.kpi_contract`. Hardcoded to *"Retail / Consumer Goods"*. | ❌ **No** |
| **Lineage & Dependency Graph**<br>([`config/kpi_contracts.yaml`](file:///e:/accenture/config/kpi_contracts.yaml#L30-L32)) | **MUST BE ISOLATED** | Specifies upstream systems (`pos_system → orders → hourly_revenue`). | Invalid upstream dependencies cause root-cause challenge rules to fail. | Statically declared inside the single contract file. | ❌ **No** |
| **Statistical Breach Thresholds**<br>([`config/kpi_contracts.yaml`](file:///e:/accenture/config/kpi_contracts.yaml#L27-L29)) | **SHARED CODE, BUSINESS-SCOPED CONFIG** | Baseline standard deviation limits ($z = 3.0\sigma$, $\Delta\% = 10\%$, min sample count = 30). | High-volatility businesses (e.g. trading) get continuous false alarms; low-volatility businesses miss critical breaches. | Default static thresholds applied across all scenarios. | ❌ **No** |

---

### Subsystem 4: Source Configuration & Reliability

| Exact Component / File | Classification | Why Isolation is Required | Risk if Shared / Leaked | Current Repo Behavior | Already Isolated? |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **`sources.yaml`**<br>([`config/sources.yaml`](file:///e:/accenture/config/sources.yaml)) | **SHARED CODE, BUSINESS-SCOPED CONFIG** | Declares source IDs (`orders`, `payment_gateway`), refresh cadences, SLA limits, and baseline data quality weights. | Tenant A's batch sync schedule enforces inappropriate staleness penalties on Tenant B's streaming data. | Loaded once into global `app.state.sources_config`. Hardcoded to 7 retail sources. | ❌ **No** |
| **Source Reliability Scoring Engine**<br>([`config/registry.py`](file:///e:/accenture/config/registry.py)) | **CAN BE SHARED SAFELY** | Mathematical calculation of dynamic reliability weight: $$\text{weight} = \text{base\_quality} \times \exp\left(-\frac{\text{staleness}}{\text{SLA}}\right)$$ | None (stateless algorithm). | Calculates weights dynamically based on the active source registry configuration. | ✅ **Yes** |

---

### Subsystem 5: Scenario & Runtime Configuration

| Exact Component / File | Classification | Why Isolation is Required | Risk if Shared / Leaked | Current Repo Behavior | Already Isolated? |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **Scenario Time Windows (`_SCENARIO_WINDOWS`)**<br>([`pipeline/investigate.py`](file:///e:/accenture/pipeline/investigate.py#L313-L321)) | **SHARED CODE, BUSINESS-SCOPED CONFIG** | Maps each scenario to fixed observation timestamps (e.g. Jan 8–15, 2024). | A new tenant's live data will be filtered against hardcoded 2024 timestamps from the demonstration dataset. | Hardcoded dictionary inside `investigate.py` referencing `INC_001` through `INC_008`. | ❌ **No** |
| **Calendar, Timezone & Currency Assumptions** | **MUST BE ISOLATED** | Operating timezones (UTC vs. EST vs. JST), regional boundaries (`eu-west`, `apac`), and currency definitions. | Metrics aggregated in mismatched timezones distort diurnal seasonality calculations in E2. | Hardcoded UTC assumptions and retail region strings. | ❌ **No** |

---

### Subsystem 6: Security & Entitlements Engine

| Exact Component / File | Classification | Why Isolation is Required | Risk if Shared / Leaked | Current Repo Behavior | Already Isolated? |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **`entitlements.yaml`**<br>([`config/entitlements.yaml`](file:///e:/accenture/config/entitlements.yaml)) | **SHARED CODE, BUSINESS-SCOPED CONFIG** | Role-based authorization rules mapping personas (`analyst`, `cfo`, `manager`) to authorized data sources and field allowlists. | Persona in Business B inherits retail source access rules (`sku_id`, `store_id`) rather than their own domain data. | Single global configuration loaded at server startup into `app.state.entitlements_config`. | ❌ **No** |
| **`SecurityEngine` Policy Evaluator**<br>([`security/entitlements.py`](file:///e:/accenture/security/entitlements.py)) | **CAN BE SHARED SAFELY** | Evaluates persona scopes, computes field masking, and enforces fail-closed authorization. | None (stateless enforcement engine). | Pure evaluation logic executing over whatever `EntitlementsConfig` is supplied. | ✅ **Yes** |

---

### Subsystem 7: E9 Memory, Precedents & Human Learning

| Exact Component / File | Classification | Why Isolation is Required | Risk if Shared / Leaked | Current Repo Behavior | Already Isolated? |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **`memory_retention.yaml`**<br>([`config/memory_retention.yaml`](file:///e:/accenture/config/memory_retention.yaml)) | **SHARED CODE, BUSINESS-SCOPED CONFIG** | Defines precedent Time-To-Live (TTL) expiration rules by source ID (e.g. 30 days for marketing, 365 days for deploy logs). | Incompatible memory retention policies applied across businesses. | Single static YAML loaded globally by `MemoryEngine`. | ❌ **No** |
| **Precedent Storage & Vector Matcher**<br>([`engines/memory.py`](file:///e:/accenture/engines/memory.py)) | **NEEDS EXPLICIT TENANT KEY / NAMESPACE** | Stores precedent embeddings and queries top-$k$ nearest matches with confidence boosts and human validation weights. | **High Risk:** Cross-tenant precedent pollution. Business A adopts root-cause recommendations generated by Business B. | All precedents write to the single `investigation_precedents` ChromaDB collection. | ❌ **No** |
| **Human Validation Feedback Loop**<br>([`api/main.py`](file:///e:/accenture/api/main.py#L770-L860)) | **MUST BE ISOLATED** | Analyst corrections to hypotheses, confidence overrides, and precedent confirmations. | Business A's analysts accidentally boost or refute precedents belonging to Business B. | Updates global `feedback` table and marks precedent in shared ChromaDB collection. | ❌ **No** |

---

### Subsystem 8: Continuous Evaluation & Drift Monitoring

| Exact Component / File | Classification | Why Isolation is Required | Risk if Shared / Leaked | Current Repo Behavior | Already Isolated? |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **Operational Health Evaluator**<br>([`evaluation/health.py`](file:///e:/accenture/evaluation/health.py)) | **MUST BE ISOLATED** | Computes 6 operational health metrics (latency p95, abstention rate, human agreement rate, citation violation rate) across rolling windows (50 recent vs 50 baseline). | Operational drift in Business A corrupts Business B's health status, triggering false `DEGRADED` platform alerts. | Queries the global `investigations` and `feedback` tables directly with no tenant filtering. | ❌ **No** |
| **Ground Truth Benchmark Suite**<br>([`data/ground_truth.json`](file:///e:/accenture/data/ground_truth.json)) | **MUST BE ISOLATED** | Benchmark evaluation dataset specifying expected winning hypothesis, confidence state, and target action per scenario. | System accuracy benchmarks become meaningless if evaluated against another business's ground truth. | Single JSON file tailored to `INC_001`–`INC_008`. | ❌ **No** |
| **Evaluation Engine**<br>([`evaluation/evaluator.py`](file:///e:/accenture/evaluation/evaluator.py)) | **CAN BE SHARED SAFELY** | Mathematical scoring of precision, recall, citation accuracy, and abstention compliance. | None (stateless evaluator). | Pure comparison function executing against the supplied ground truth. | ✅ **Yes** |

---

### Subsystem 9: LLM Prompts & Semantic Inference

| Exact Component / File | Classification | Why Isolation is Required | Risk if Shared / Leaked | Current Repo Behavior | Already Isolated? |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **E5 Hypothesis System & User Prompts**<br>([`engines/hypothesis.py`](file:///e:/accenture/engines/hypothesis.py#L174-L208)) | **SHARED CODE, BUSINESS-SCOPED CONFIG** | Generates hypothesis candidate guidelines and mentions domain failure patterns (e.g. checkout code, inventory stockouts). | Prompts bias the LLM toward retail/checkout concepts when investigating healthcare, logistics, or SaaS businesses. | Prompt templates contain hardcoded mentions of `INC_001 checkout/payment scenario` and retail drivers. | ❌ **No** |
| **LLM Provider Clients**<br>([`llm/provider.py`](file:///e:/accenture/llm/provider.py)) | **CAN BE SHARED SAFELY** | Manages API communication with Groq / Ollama, token limits, JSON mode enforcement, and credential rotation. | None (stateless HTTP client). | Global provider instance shared across requests. | ✅ **Yes** |

---

### Subsystem 10: API State & Frontend Client

| Exact Component / File | Classification | Why Isolation is Required | Risk if Shared / Leaked | Current Repo Behavior | Already Isolated? |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **FastAPI Request Lifespan & Handlers**<br>([`api/main.py`](file:///e:/accenture/api/main.py#L122-L176)) | **NEEDS EXPLICIT TENANT KEY / NAMESPACE** | Global `app.state` stores singleton instances of DB connection, ChromaDB client, and parsed YAML configs. | Every incoming API request shares the exact same retail configuration and database connection. | No `tenant_id` header or body parameter accepted by `/investigate`, `/feedback`, or `/health`. | ❌ **No** |
| **Scenario Catalog Constants**<br>([`web/src/lib/api.ts`](file:///e:/accenture/web/src/lib/api.ts#L3-L68)) | **SHARED CODE, BUSINESS-SCOPED CONFIG** | Frontend scenario metadata array defining scenario IDs, titles, descriptions, and domains. | UI shows retail incident titles (`INC_001 Payment Gateway Latency...`) regardless of what business is logged in. | Hardcoded TypeScript constant `SCENARIO_CATALOG`. | ❌ **No** |
| **Frontend State & Local Caching**<br>([`web/src/components/investigation/InvestigationOverview.tsx`](file:///e:/accenture/web/src/components/investigation/InvestigationOverview.tsx)) | **MUST BE ISOLATED** | Browser React state, active scenario selection, and cached investigation payloads. | Switching tenants inside the same browser session without cache flushing displays previous tenant's confidential investigation results. | In-memory React component state and un-namespaced state management. | ❌ **No** |

---

## 3. Specific Cross-Business Contamination Risks

```
                                    CROSS-TENANT CONTAMINATION VECTORS
  ┌───────────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │                                                                                                           │
  │  [Tenant A: FinTech Bank]                                                  [Tenant B: E-Commerce Store]   │
  │            │                                                                            │                 │
  │            ▼                                                                            ▼                 │
  │  ┌───────────────────────┐                                                     ┌───────────────────────┐  │
  │  │ Fraud / AML Outage    │                                                     │ Checkout Latency      │  │
  │  └──────────┬────────────┘                                                     └───────────┬───────────┘  │
  │             │                                                                              │              │
  │             ▼                                                                              ▼              │
  │  ══════════════════════════════════════ SHARED UNISOLATED LAYERS ══════════════════════════════════════   │
  │  • PostgreSQL DB: Table collision on `scenario_id='INC_001'` & mixed `investigations` history             │
  │  • ChromaDB E9: `investigation_precedents` suggests retail checkout rollbacks for bank fraud failures      │
  │  • Health Service: Bank query latency spikes degrade global drift health score for the e-commerce store  │
  │  • LLM Prompting: Hypothesis generator prompts inject retail drivers into banking investigation          │
  │  ══════════════════════════════════════════════════════════════════════════════════════════════════════   │
  │                                                                                                           │
  └───────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### A. Cross-Business Data Leakage Risks
* **Direct SQL Exposure:** All queries filter solely by `scenario_id`. If two tenants share the same database and scenario names overlap (`INC_001`), customer transactions, order numbers, and support tickets will mix.
* **Result Inspection Leak:** The `/investigations` endpoint returns raw JSON blobs without tenant ownership validation.

### B. Cross-Business E9 Precedent Contamination
* The Memory Engine (`engines/memory.py`) stores all historical incident summaries in a single ChromaDB collection named `investigation_precedents`.
* During vector search, an incident in Business B will retrieve high-similarity precedents from Business A, recommending irrelevant or damaging actions.

### C. Cross-Business KPI & Threshold Contamination
* Global KPI contracts enforce retail-specific metric formulas (`hourly_revenue`, `hourly_conversion`) and fixed thresholds ($z = 3.0\sigma$, $\Delta\% = 10\%$).
* High-frequency trading or SaaS businesses sharing these thresholds will experience false-positive anomaly triggers in E2 or diagnostic failure in E3.

### D. Cross-Business Evaluation & Baseline Contamination
* Continuous drift evaluation in `evaluation/health.py` computes rolling latency, abstention rates, and human agreement over the last 50 global investigations.
* Interleaved investigations from different businesses will corrupt drift detection and produce false degradation alerts.

### E. Cross-Business Feedback & Validation Contamination
* Analyst feedback submitted via `/feedback` applies positive retrieval boosts (`HUMAN_VALIDATION_BOOST = 0.1`) to precedents in the global ChromaDB collection.
* An analyst at Business A validating a hypothesis will unintentionally elevate that precedent's retrieval rank for all other tenants.

### F. Cross-Business Cached Frontend State Contamination
* The React client maintains in-memory investigation results without tenant namespacing.
* Navigating between tenant workspaces in the UI without cache invalidation will flash previously loaded evidence dossiers and metric breakdowns.

---

## 4. Architectural Isolation Matrix

| Subsystem / Layer | Isolation Strategy | Storage / Config Boundary | Scope Classification |
| :--- | :--- | :--- | :--- |
| **PostgreSQL Structured Data** | Database Schema per Tenant or Dedicated DB | `tenant_{id}.*` or isolated PostgreSQL instance | **MUST BE ISOLATED** |
| **PostgreSQL History & Feedback** | Partitioned Tables / Tenant Filter | `investigations` & `feedback` with `tenant_id` index | **MUST BE ISOLATED** |
| **ChromaDB Evidence Vectors** | Dedicated Collection per Scenario/Tenant | `evidence_{tenant_id}_{scenario_id}` | **MUST BE ISOLATED** |
| **ChromaDB E9 Precedent Memory** | Dedicated Collection per Tenant | `precedents_{tenant_id}` | **MUST BE ISOLATED** |
| **KPI Semantic Contracts** | Tenant Config Bundle | `tenants/{tenant_id}/kpi_contracts.yaml` | **SHARED CODE, BUSINESS-SCOPED CONFIG** |
| **Source Registry & SLAs** | Tenant Config Bundle | `tenants/{tenant_id}/sources.yaml` | **SHARED CODE, BUSINESS-SCOPED CONFIG** |
| **Security & Entitlements** | Tenant Config Bundle | `tenants/{tenant_id}/entitlements.yaml` | **SHARED CODE, BUSINESS-SCOPED CONFIG** |
| **Memory TTL & Retention** | Tenant Config Bundle | `tenants/{tenant_id}/memory_retention.yaml` | **SHARED CODE, BUSINESS-SCOPED CONFIG** |
| **Evaluation Ground Truth** | Tenant Benchmark Pack | `tenants/{tenant_id}/ground_truth.json` | **MUST BE ISOLATED** |
| **Scenario Catalog & Windows** | Dynamic API Endpoint / Tenant Config | `tenants/{tenant_id}/scenarios.json` | **SHARED CODE, BUSINESS-SCOPED CONFIG** |
| **FastAPI Request Context** | Multi-Tenant Dependency Injector | Header: `X-Tenant-ID` $\rightarrow$ Scoped `Dependencies` | **NEEDS EXPLICIT TENANT KEY** |
| **Frontend Workspace & Catalog** | Multi-Tenant Router & Store | Route: `/:tenantId/investigate` | **NEEDS EXPLICIT TENANT KEY** |
| **Algorithmic Engines (E1–E8)** | Pure Stateless Execution Code | Shared binary / container | **CAN BE SHARED SAFELY** |
| **LLM & Embedding Connectors** | Stateless Provider Infrastructure | Shared API gateway pool | **CAN BE SHARED SAFELY** |

---

## 5. Retail-Specific Hardcoded Elements in Existing Code

1. **Hardcoded SQL Event Tables in Schema:**
   * [`etl/schema.sql`](file:///e:/accenture/etl/schema.sql): Table definitions strictly model retail entities (`orders`, `inventory_events`, `payment_events`).
2. **Hardcoded Prompt Domain Mentions:**
   * [`engines/hypothesis.py`](file:///e:/accenture/engines/hypothesis.py#L176-L180): Explicitly prompts the LLM with: *"For the INC_001 checkout/payment scenario, consider: H1: A checkout or payment system degradation..."* and default retail driver fallbacks (`footfall`, `average_basket_size`).
3. **Hardcoded Scenario Date Windows:**
   * [`pipeline/investigate.py`](file:///e:/accenture/pipeline/investigate.py#L313-L321): `_SCENARIO_WINDOWS` dictionary hardcodes start and end dates to January/February 2024 for `INC_001`–`INC_008`.
4. **Hardcoded Frontend Catalog:**
   * [`web/src/lib/api.ts`](file:///e:/accenture/web/src/lib/api.ts#L3-L68): `SCENARIO_CATALOG` constant is statically compiled into the client with 8 retail incident definitions.
5. **Hardcoded Global ChromaDB Collection Name:**
   * [`engines/memory.py`](file:///e:/accenture/engines/memory.py#L38): Static string `_COLLECTION_NAME = "investigation_precedents"`.

---

## 6. Minimal Architectural Abstraction for Multi-Business Onboarding

### The `TenantContext` Container

```python
@dataclass(frozen=True)
class TenantContext:
    """Encapsulates all isolated configurations and resource handles for a specific business."""
    tenant_id: str
    db_schema: str                      # PostgreSQL schema or isolated connection string
    chroma_prefix: str                  # Namespace prefix for vector collections
    kpi_contract: dict                  # Parsed kpi_contracts.yaml for this tenant
    sources_config: list                # Parsed sources.yaml for this tenant
    entitlements_config: dict           # Parsed entitlements.yaml for this tenant
    memory_retention_config: dict       # Parsed memory_retention.yaml for this tenant
    ground_truth: Optional[dict]        # Benchmark ground truth for this tenant
    scenario_catalog: list[dict]        # Active incident definitions and date windows
```

### Dependency Injection Flow at the API Boundary:

```
HTTP Request (Header: X-Tenant-ID: "healthcare_corp")
                      │
                      ▼
       [TenantContextResolver Middleware]
                      │
      ┌───────────────┴───────────────┐
      ▼                               ▼
[Load Tenant Configs]       [Bind PostgreSQL Schema]
(kpi, sources, rbac)        (SET search_path = healthcare_corp)
      │                               │
      └───────────────┬───────────────┘
                      │
                      ▼
          [Scoped Dependencies]
                      │
                      ▼
          [investigate() Pipeline]
       (Executes E1–E9 in complete isolation)
```

---

## 7. Recommended Business Onboarding Boundary

When onboarding a new business/tenant, the system must deploy an isolated **Tenant Configuration & Data Bundle** conforming to the following structure:

```
tenants/
└── <tenant_id>/
    ├── config/
    │   ├── kpi_contracts.yaml      # Business metrics, formulas, drivers, and thresholds
    │   ├── sources.yaml            # Data sources, update cadences, SLAs, and quality weights
    │   ├── entitlements.yaml       # Role-based personas, field allowlists, and regional scope
    │   ├── memory_retention.yaml   # Precedent TTL and source-specific memory expiration
    │   └── scenarios.yaml          # Scenario catalog, analysis windows, and metadata
    ├── db/
    │   └── schema.sql              # Business-specific transactional tables (PostgreSQL schema)
    ├── vectors/
    │   └── seed_evidence/          # Unstructured markdown release notes, incident changelogs
    └── evaluation/
        └── ground_truth.json       # Calibration benchmarks and expected decision outcomes
```

### Execution Lifecycle for a Tenant:
$$\boxed{\text{Tenant Definition}} \longrightarrow \boxed{\text{Data Schema}} \longrightarrow \boxed{\text{Semantic Contract}} \longrightarrow \boxed{\text{Source Registry}} \longrightarrow \boxed{\text{RBAC Policy}} \longrightarrow \boxed{\text{Vector Collections}} \longrightarrow \boxed{\text{E9 Memory Bank}} \longrightarrow \boxed{\text{Evaluation Suite}}$$
