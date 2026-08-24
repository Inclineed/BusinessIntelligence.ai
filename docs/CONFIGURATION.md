# Configuration Architecture & Schemas

This document explains the configuration subsystem, schema validation rules, fail-closed loading mechanics, and runtime operational impact of configuration files in **BusinessIntelligence.ai**.

---

## 1. Fail-Closed Loader Architecture (`config/loader.py`)

All configuration files are loaded via strict, schema-validating functions in `config/loader.py`:
- `load_kpi_contract(path)`
- `load_entitlements(path)`
- `load_sources(path)`
- `load_memory_retention(path)`

### Invariant: Zero Default Domain Fallback
There is no implicit fallback domain or default entitlement set. If any configuration file is missing, empty, or fails schema validation, the loaders raise `ConfigError` immediately.

---

## 2. Configuration Files & Schemas

### `config/kpi_contract.yaml` (KPI Semantic Contract)
- **Purpose**: Defines business metrics, driver relationships, SLA thresholds, and allowed breakdown dimensions.
- **Loader**: `load_kpi_contract(path)`
- **Primary Consumer**: Engines E1 (KPI Store), E2 (Signal Detection), and E3 (Diagnostic Decomposition).
- **Failure Behavior**: Missing file or invalid schema raises `ConfigError` and halts the investigation pipeline.
- **Important Keys**: `direction_is_good`, `sla_minutes`, `dimensions`, `driver_kpis`.

```yaml
domain: ecommerce_checkout
version: "1.0"

kpis:
  conversion_rate:
    description: "Percentage of checkout sessions completing successfully"
    unit: "percentage"
    direction_is_good: "increase"
    aggregation: "hourly"
    sla_minutes: 60
    dimensions: ["device", "region", "channel"]
    driver_kpis:
      - payment_failure_rate
      - gateway_latency_15min
```

### `config/entitlements.yaml` (Persona Entitlements)
- **Purpose**: Controls which data sources, fields, and regions each user persona is authorized to query.
- **Loader**: `load_entitlements(path)`
- **Primary Consumer**: `SecurityEngine` (which constrains E4 Evidence Assembly).
- **Failure Behavior**: Missing file or invalid schema triggers fail-closed behavior (empty authorization scope).
- **Important Keys**: `authorized_sources`, `authorized_regions`.

```yaml
personas:
  analyst:
    authorized_sources:
      - orders
      - payment_gateway
      - inventory
      - marketing
      - deployment_log
      - support_tickets
      - release_notes
    authorized_regions: "all"

  manager:
    authorized_sources:
      - orders
      - inventory
    authorized_regions: "all"

  cfo:
    authorized_sources:
      - orders
      - inventory
    authorized_regions: "all"
```

### `config/sources.yaml` (Source Registry)
- **Purpose**: Registers all physical data stores, database tables, vector collections, data quality ratings, and freshness SLAs.
- **Loader**: `load_sources(path)`
- **Primary Consumer**: `SourceRegistry` (used by E1 and E4).
- **Failure Behavior**: Missing file or invalid schema raises `ConfigError`.
- **Important Keys**: `type`, `table`/`collection`, `sla_minutes`, `data_quality`.

```yaml
sources:
  payment_gateway:
    type: "postgres"
    table: "payment_events"
    sla_minutes: 60
    data_quality: 0.95
    description: "Payment transaction logs and error status codes"

  deployment_log:
    type: "chromadb"
    collection: "deployment_log"
    sla_minutes: 1440
    data_quality: 0.90
    description: "CI/CD deployment logs and release metadata"

  support_tickets:
    type: "chromadb"
    collection: "support_tickets"
    sla_minutes: 120
    data_quality: 0.80
    description: "Customer support ticket transcripts and categories"
```

### `config/memory_retention.yaml` (Memory Retention Policy)
- **Purpose**: Defines time-to-live (TTL) expiration windows for historical precedent records stored in ChromaDB.
- **Loader**: `load_memory_retention(path)`
- **Primary Consumer**: Engine E9 (Precedent Memory).
- **Failure Behavior**: Missing file or invalid schema raises `ConfigError`.
- **Important Keys**: `default_ttl_days`, `by_source`.

```yaml
retention:
  default_ttl_days: 90
  by_source:
    - source_id: payment_gateway
      ttl_days: 60
    - source_id: marketing
      ttl_days: 30
    - source_id: deployment_log
      ttl_days: 365
```

---

## 3. In-Memory Source Registry (`config/registry.py`)

`SourceRegistry` provides the runtime interface for querying source metadata and computing freshness:

```python
class SourceRegistry:
    def get(self, source_id: str) -> SourceRegistryEntry:
        """Returns entry with sla_minutes, data_quality, and freshness_status."""
        ...
```

### Runtime Freshness Determination
When Engine E1 or E4 queries a source:
1. Calculates $\Delta t = \text{now} - \text{latest\_timestamp}$.
2. Compares $\Delta t$ against `entry.sla_minutes`.
3. Classifies `FreshnessStatus`:
   - `FRESH`: $\Delta t \le \text{SLA}$
   - `STALE`: $\text{SLA} < \Delta t \le 2 \times \text{SLA}$
   - `CRITICAL_STALE`: $\Delta t > 2 \times \text{SLA}$
   - `UNKNOWN`: Missing timestamp or `sla_minutes == 0`.
