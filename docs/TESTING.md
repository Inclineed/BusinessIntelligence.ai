# Testing Architecture & Verification Guide

This document details the automated test suite, verification layers, regression suites, and reproduction commands for **BusinessIntelligence.ai**.

---

## 1. Test Architecture Overview

The repository features an automated test suite comprising **243 passing tests** across 11 test modules in `tests/`, ensuring coverage of mathematical logic, security boundaries, vector memory, adversarial perturbations, and end-to-end pipeline execution.

```
tests/
├── test_kpi_store.py             # E1 KPI loading & SQL contract checks
├── test_signal.py                # E2 Z-score detection & partial bucket guards
├── test_diagnostic.py            # E3 Dimensional decomposition & dominance
├── test_evidence.py              # E4 SLA reliability decay & query pre-filters
├── test_challenge_smoke.py       # E6 Operational rules & deterministic score math
├── test_citation_validation.py   # D16 Citation fidelity & phantom ID guards
├── test_security.py              # Authorization boundaries & fail-closed scopes
├── test_memory.py                # E9 ChromaDB storage, weighting & TTL decay
├── test_overfitting.py           # Held-out evaluation & adversarial perturbations
└── test_fidelity.py              # Text normalization & citation fidelity
```

---

## 2. Test Module Breakdown

### Core Engine Tests
- **`test_kpi_store.py`**: Verifies PostgreSQL time-series queries, freshness stamping, and SLA calculation under normal and degraded conditions.
- **`test_signal.py`**: Tests statistical anomaly thresholds ($|z| \ge 2.0$), directionality assertions, and the trailing partial bucket anomaly guard (`INC_005`).
- **`test_diagnostic.py`**: Validates dimensional delta calculations across `device`, `region`, and `channel`, confirming Android dominance detection in `INC_001`.
- **`test_evidence.py`**: Validates linear freshness decay, zero-weight SLA handling, deterministic SHA-256 evidence hashing, and pre-query source filtering.

### Challenge, Scoring & Citation Tests
- **`test_challenge_smoke.py`**: Tests the five operational rules (`timeline`, `segment_alignment`, `kpi_corroboration`, `mechanism_consistency`, `contradiction`), support score capping, contradiction penalties, and deterministic confidence banding.
- **`test_citation_validation.py` & `test_fidelity.py`**: Asserts that hypotheses citing phantom evidence IDs or altering quoted evidence text are disqualified (`final_score=0.0`, `ABSTAIN`).

### Security & Authorization Tests
- **`test_security.py`**:
  - Validates fail-closed behavior on missing or invalid `config/entitlements.yaml`.
  - Asserts that restricted personas (`manager`, `cfo`) cannot access technical telemetry (`payment_gateway`, `deployment_log`).
  - Verifies that pre-query filters prevent unauthorized queries at the database layer.

### Precedent Memory & Provenance Tests
- **`test_memory.py`**:
  - Validates ChromaDB upsert operations within the 5.0s SLA.
  - Tests confidence retrieval weighting (`HIGH=1.0`, `MEDIUM=0.6`, `ABSTAIN=0.2`, `LOW=0.1`).
  - Tests human-validation tagging (`mark_validated()`) and the `+0.1` relevance boost.
  - Tests domain-specific TTL expiry filtering against `config/memory_retention.yaml`.
  - Asserts that simulated and legacy unknown-provenance records are excluded from normal retrieval.

### Generalization & Adversarial Tests
- **`test_overfitting.py`**:
  - Validates dynamic scenario discovery and ground-truth schema validation in `evaluation/evaluator.py`.
  - Executes adversarial perturbations (evidence deletion, contradiction injection, citation tampering) to prove scoring monotonicity.
  - Validates cross-domain B2B SaaS scenario `INC_008`.

---

## 3. Reproduction & Execution Commands

### Run Full Test Suite
```bash
pytest
```
*Expected Result: `243 passed in ~15-25s`.*

### Run Specific Test Modules
```bash
# Run security & entitlement tests
pytest tests/test_security.py -v

# Run memory & retention decay tests
pytest tests/test_memory.py -v

# Run held-out evaluation & perturbation tests
pytest tests/test_overfitting.py -v

# Run scoring & challenge tests
pytest tests/test_challenge_smoke.py -v
```

### Run Live Scenario Evaluation
```bash
# Run 16-dimension evaluation for demo scenario INC_001
python run_demo.py

# Run held-out validation suite (INC_005, INC_006, INC_007, INC_008)
python scripts/validate_held_out.py
```
