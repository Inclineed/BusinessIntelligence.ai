# BusinessIntelligence.ai

**Evidence-backed KPI anomaly investigation engine.**

An autonomous pipeline that detects KPI anomalies, assembles evidence from structured and unstructured sources, generates and challenges hypotheses, and produces a confidence-graded recommendation — with every number computed deterministically and every LLM output restricted to narrative.

---

## Architecture

The system is a nine-engine pipeline. Each engine has a single responsibility and a fixed provenance tag (`SQL`, `STATS`, `RULES`, `RETRIEVAL`, `LLM`, or `SIMULATED`). LLMs never produce numbers; quantitative truth belongs exclusively to deterministic engines.

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   E1  KPI Store ························· [SQL]             │
│    ↓                                                        │
│   E2  Signal Detection ·················· [STATS]           │
│    ↓                                                        │
│   E3  Diagnostic Decomposition ·········· [SQL+STATS]       │
│    ↓                                                        │
│   ── Authorization Boundary ─────────────────────────────   │
│    ↓                                                        │
│   E4  Evidence Assembly ················· [SQL+RETRIEVAL]    │
│    ↓                                                        │
│   E5  Hypothesis Generation ············· [LLM]             │
│    ↓                                                        │
│   E6  Challenge / Scoring ··············· [RULES]           │
│    ↓                                                        │
│   E7  Decision ·························· [LLM]             │
│    ↓                                                        │
│   E8  Outcome Projection ··············· [SIMULATED]        │
│    ↓                                                        │
│   E9  Provenance-Aware Memory ··········· [RETRIEVAL+LLM]   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

| Engine | File | Responsibility |
|--------|------|----------------|
| **E1** | `engines/kpi_store.py` | Load KPI values from PostgreSQL with freshness tracking |
| **E2** | `engines/signal.py` | Z-score anomaly detection with corroboration guards |
| **E3** | `engines/diagnostic.py` | Decompose anomalies across dimensions (region, channel, device) |
| **E4** | `engines/evidence.py` | Assemble authorized evidence from SQL sources and ChromaDB |
| **E5** | `engines/hypothesis.py` | LLM generates candidate hypotheses grounded in evidence |
| **E6** | `engines/challenge.py` | Deterministic rule-based scoring and confidence computation |
| **E7** | `engines/decision.py` | LLM generates action recommendations from scored hypotheses |
| **E8** | `engines/outcome.py` | Simulated outcome projection (always labeled SIMULATED) |
| **E9** | `engines/memory.py` | Store and retrieve investigation precedents with full provenance |

The orchestrator (`pipeline/investigate.py`) runs all engines in sequence. The security boundary (`security/entitlements.py`) sits between E3 and E4 — evidence is filtered by persona entitlements before any LLM receives it.

---

## Key Engineering Properties

### 1. Authorization Before Retrieval

The entitlement boundary is enforced *before* evidence reaches any LLM prompt. Persona scopes defined in `config/entitlements.yaml` control which data sources, KPIs, and dimensions are accessible. If the entitlements configuration is missing or malformed, the system fails closed to an empty scope — no data leaks by default.

- Evidence assembly (E4) only queries sources the persona is authorized to see.
- Hypothesis generation (E5) and decision (E7) never receive unauthorized evidence.
- Every evidence object carries a `MethodTag` provenance label traceable to its origin.

### 2. Provenance-Aware Memory

Engine E9 stores investigation precedents in ChromaDB with full metadata:

- `original_confidence_state` — the confidence at time of storage (never overwritten)
- `outcome_type` — whether the precedent is `observed`, `simulated`, or `unknown`
- `scenario_id`, `evidence_ids` — traceability back to source data
- `human_validated`, `validated_at` — explicit human-validation status (defaults safely to unvalidated)
- `created_at` — timestamp for domain-specific retention decay

Simulated or unknown-provenance precedents are excluded from normal retrieval. Human-validated precedents receive a configurable relevance boost. Per-source TTL expiry is enforced via `config/memory_retention.yaml`.

### 3. Held-Out and Adversarial Evaluation

The evaluation framework (`evaluation/evaluator.py`) validates pipeline outputs against ground truth defined in `data/ground_truth.json`. Scenarios are dynamically discovered — there is no hardcoded scenario dispatch in the evaluator.

The evaluation suite includes:
- **Held-out scenarios** (INC_005–INC_007) that were never used during development
- **Cross-domain scenario** (INC_008) using a genuinely different domain (B2B SaaS churn / enterprise SSO failure) with different KPI structures, segment names, and evidence types
- **Adversarial perturbation tests** that verify scoring stability under evidence manipulation

Every evaluation dimension is validated with explicit pass/fail reporting. Missing or incomplete ground-truth specifications fail loudly rather than silently skipping checks.

---

## Measured Results

These numbers are from automated test runs against the live pipeline (PostgreSQL + ChromaDB + Ollama).

| Metric | Value |
|--------|-------|
| Automated tests passing | **243 / 243** |
| Held-out scenarios validated | **4** (INC_005, INC_006, INC_007, INC_008) |
| Cross-domain scenarios | **1** (INC_008 — B2B SaaS, entirely different KPI structure) |
| Authorization violations | **0** |
| Hallucinated evidence references | **0** |
| Citation fidelity violations | **0** |
| Provenance-complete precedent records | **8 / 8** |

### Held-Out Scorecard

| Scenario | Domain | Anomaly | Winner | Confidence | Dimensions Passed |
|----------|--------|---------|--------|------------|-------------------|
| INC_005 | E-commerce (trailing bucket guard) | `False` ✓ | — (abstained) | — | 8/8 |
| INC_006 | E-commerce (compound cause) | `True` ✓ | H1 ✓ | HIGH ✓ | 8/8 |
| INC_007 | E-commerce (gradual degradation) | `True` ✓ | H1 ✓ | HIGH ✓ | 7/7 |
| INC_008 | B2B SaaS (enterprise SSO failure) | `True` ✓ | H1 ✓ | HIGH ✓ | 7/7 |

### What These Numbers Do and Do Not Prove

**Measured** (reproducible from test suite):
- The authorization boundary prevents data leakage across all tested personas and scenarios.
- The pipeline produces zero hallucinated evidence references across all scenarios.
- Held-out scenarios — unseen during development — pass all evaluation dimensions.
- Cross-domain generalization works for at least one non-trivial domain shift.

**Architecture claims** (not yet statistically validated):
- Confidence calibration reporting exists (`evaluation/calibration.py`) but the current dataset (N=8) is too small for meaningful calibration metrics. The target for statistical significance is N ≥ 30.
- Memory decay and human-validation boost are implemented and unit-tested but have not been evaluated at scale.

---

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- [Ollama](https://ollama.ai) with `qwen3:8b` and `bge-m3` models
- ChromaDB 0.5+

### Setup

```bash
# Start infrastructure
docker compose up -d postgres chromadb

# Install dependencies
pip install -r requirements.txt

# Pull LLM models
ollama pull qwen3:8b
ollama pull bge-m3

# Load data and run ETL
python etl/generate_held_out.py

# Run the demo pipeline (INC_001)
python run_demo.py

# Validate held-out scenarios
python scripts/validate_held_out.py

# Run the full test suite
pytest
```

### Configuration

| File | Purpose |
|------|---------|
| `config/entitlements.yaml` | Persona → data source authorization scopes |
| `config/kpi_contract.yaml` | KPI semantic definitions and driver relationships |
| `config/sources.yaml` | Data source registry (PostgreSQL tables, ChromaDB collections) |
| `config/memory_retention.yaml` | Per-source TTL for precedent expiry |
| `data/ground_truth.json` | Expected evaluation outputs for all scenarios |

### Project Structure

```
├── engines/              # E1–E9 engine implementations
│   ├── kpi_store.py      #   E1: KPI loading from PostgreSQL
│   ├── signal.py         #   E2: Z-score anomaly detection
│   ├── diagnostic.py     #   E3: Dimensional decomposition
│   ├── evidence.py       #   E4: Evidence assembly (SQL + ChromaDB)
│   ├── hypothesis.py     #   E5: LLM hypothesis generation
│   ├── challenge.py      #   E6: Deterministic scoring and confidence
│   ├── decision.py       #   E7: LLM action recommendation
│   ├── outcome.py        #   E8: Simulated outcome projection
│   └── memory.py         #   E9: Provenance-aware precedent memory
├── pipeline/
│   └── investigate.py    # Orchestrator (E1→E9)
├── security/
│   └── entitlements.py   # Authorization boundary (fail-closed)
├── evaluation/
│   ├── evaluator.py      # Dynamic ground-truth evaluation
│   └── calibration.py    # Confidence calibration reporting
├── config/               # YAML configuration files
├── data/                 # Ground truth and seed data
├── etl/                  # Data generation and ingestion
├── llm/                  # LLM provider abstraction (Ollama)
├── models.py             # Shared data models and enums
├── tests/                # 243 automated tests
├── scripts/              # Validation and maintenance scripts
├── run_demo.py           # Full pipeline demo (INC_001)
└── docker-compose.yml    # PostgreSQL + ChromaDB infrastructure
```

---

## License

See repository for license details.
