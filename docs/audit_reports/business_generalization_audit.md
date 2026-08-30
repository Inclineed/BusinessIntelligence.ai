# Business Generalization & Replicability Audit

> **Audit Type:** Business Generalization & Zero-Engine-Modification Audit  
> **Repository:** `BusinessIntelligence.ai`  
> **Architecture Principle:** Reusable E1–E9 Core Engine + Separate Business Deployment / Configuration Bundle (NOT SaaS Multi-Tenancy)  
> **Objective:** Identify all retail-specific elements that must be decoupled from the core engine so that a new business (FinTech, Logistics, SaaS, Healthcare) can be deployed by simply providing a new configuration and data bundle with **ZERO code changes to E1–E9**.

---

## 1. Executive Summary & Generalization Model

The core reasoning spine (`E1` through `E9`) is designed to be domain-agnostic. Each business deployment operates as its own configured deployment instance with its own database and ChromaDB persistence.

To ensure seamless replicability across any enterprise domain, the system adheres to:

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

```text
REUSABLE CORE (100% Shared, Domain-Agnostic Engine Image)
├── E1 KPI Store & Baseline Statistics
├── E2 Anomaly Detection & Materiality Math
├── E3 Diagnostic Decomposition Slicing
├── E4 Canonical Evidence Normalization
├── E5 Constrained Hypothesis Synthesis
├── E6 Deterministic Challenge & Verification
├── E7 Decision & 7-Field Action Graph
├── E8 Counterfactual Economic Simulation
├── E9 Precedent Vector Memory & Decay
└── Pipeline Orchestrator & Cost Telemetry
         │
         │ Loaded via BusinessContext
         ▼
BUSINESS CONFIGURATION & DATA BUNDLE (Configured per Business Container)
├── config/kpi_contracts.yaml      (Metrics, formulas, grains, drivers, lineage)
├── config/materiality.yaml        (Financial impact multipliers & priority rules)
├── config/sources.yaml            (Heterogeneous feeds, SLAs, cadences, quality)
├── config/entitlements.yaml       (Personas, source allowlists, decision rights)
├── config/memory_retention.yaml   (Precedent TTL limits by source)
├── config/scenarios.yaml          (Incident catalog & time windows)
├── evaluation/ground_truth.json   (Benchmark calibration dataset)
├── PostgreSQL instance            (Domain tables, kpi_values, investigations, feedback)
└── ChromaDB instance              (Unstructured evidence & precedent collections)
```

---

## 2. Decoupling Audit: Hardcoded Retail Elements to Extract

To achieve pure business generalization, the following items must be decoupled from engine code into the business configuration bundle:

| Exact Component / File | Current Retail Hardcoding | Required Generalization Action | Target Business Config Artifact |
| :--- | :--- | :--- | :--- |
| **`pipeline/investigate.py`**<br>([`pipeline/investigate.py#L313-L321`](file:///e:/accenture/pipeline/investigate.py#L313-L321)) | `_SCENARIO_WINDOWS` dictionary hardcodes start/end timestamps for `INC_001`–`INC_008`. | Extract scenario dates from Python code into configuration. | `config/scenarios.yaml` |
| **`engines/hypothesis.py`**<br>([`engines/hypothesis.py#L176-L180`](file:///e:/accenture/engines/hypothesis.py#L176-L180)) | Prompt mentions *"For the INC_001 checkout/payment scenario, consider: H1: A checkout or payment system degradation..."* and default retail driver fallbacks (`footfall`, `average_basket_size`). | Drive hypothesis synthesis prompt dynamically from `kpi_contracts.yaml` drivers (`drivers:` list). Remove all hardcoded prompt text. | `config/kpi_contracts.yaml` |
| **`web/src/lib/api.ts`**<br>([`web/src/lib/api.ts#L3-L68`](file:///e:/accenture/web/src/lib/api.ts#L3-L68)) | `SCENARIO_CATALOG` constant is statically hardcoded in TypeScript with 8 retail incident names. | Replace hardcoded frontend array with dynamic fetch from `/api/scenarios`. | `config/scenarios.yaml` (served via API) |
| **`etl/schema.sql`**<br>([`etl/schema.sql#L48-L147`](file:///e:/accenture/etl/schema.sql#L48-L147)) | Table definitions model retail entities (`orders`, `inventory_events`, `payment_events`). | Domain event tables belong to the business deployment's data layer; core engine interacts only via `kpi_values` and `CanonicalEvidenceRecord`. | `data/schema.sql` (deployment-specific) |

---

## 3. The `BusinessContext` Interface

At startup, the deployment initializes a `BusinessContext` from its configured directory (`BUSINESS_CONFIG_DIR`):

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

## 4. Onboarding Checklist for a New Business Deployment

When standing up `BusinessIntelligence.ai` for a new business, the operator completes the following zero-code steps:

1. **Deploy PostgreSQL & ChromaDB:** Standard database containers for the business instance.
2. **Author `kpi_contracts.yaml`:** Define domain KPIs, SQL aggregation formulas, causal drivers, and anomaly thresholds.
3. **Author `sources.yaml`:** Declare heterogeneous feeds, refresh intervals, SLA minutes, and base data quality ratings.
4. **Author `entitlements.yaml`:** Configure role personas, allowed sources, field masking, and persona decision rights.
5. **Author `memory_retention.yaml`:** Set precedent TTL policies by source ID.
6. **Author `scenarios.yaml`:** Specify active incident scenarios, observation time windows, and incident metadata.
7. **Author `materiality.yaml`:** Set financial impact formulas and business priority scoring rules.
8. **Load Domain Data & Ingest Evidence:** Run standard ETL loaders to populate `kpi_values` and ChromaDB vector collections.
9. **Launch Engine:** The core `E1`–`E9` engine boots up, binds to the `BusinessContext`, and is immediately ready to run investigations.
