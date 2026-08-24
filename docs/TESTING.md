# Testing Architecture & Verification Guide

This document details the automated test suite, verification layers, regression suites, and reproduction commands for **BusinessIntelligence.ai**.

---

## 1. Test Architecture Overview

The repository features an automated test suite comprising **288+ passing tests** across 12 test modules in `tests/`, ensuring coverage of mathematical logic, security boundaries, vector memory, candidate oversampling policies, multi-key LLM rotation, adversarial perturbations, and end-to-end pipeline execution.

```
tests/
├── test_kpi_store.py             # E1 KPI loading & SQL contract checks
├── test_signal.py                # E2 Z-score detection & partial bucket guards
├── test_diagnostic.py            # E3 Dimensional decomposition & dominance
├── test_evidence.py              # E4 SLA reliability decay & query pre-filters
├── test_challenge_smoke.py       # E6 Operational rules & deterministic score math
├── test_citation_validation.py   # D16 Citation fidelity & phantom ID guards
├── test_security.py              # Authorization boundaries & fail-closed scopes
├── test_memory.py                # E9 ChromaDB storage, weighting, TTL & candidate oversampling
├── test_overfitting.py           # Held-out evaluation & adversarial perturbations
├── test_fidelity.py              # Text normalization & citation fidelity
├── test_feedback.py              # Human analyst validation feedback loop & API
└── test_llm_provider.py          # Pluggable Ollama/Groq providers, multi-key rotation, sanitization
```

---

## 2. Testing Strategy & Layers

The testing strategy is organized into ten specific layers, each designed to catch a different class of failure:

### 1. Deterministic Unit Tests
- **Target**: E1, E2, E3, E4, E6 deterministic functions.
- **Catches**: Mathematical errors in z-score calculation, dimensional contribution scaling, SLA decay weights, and pure-function rule evaluation. 

### 2. Engine Integration Tests
- **Target**: End-to-end deterministic flow from E1 through E6 (mocking LLM calls).
- **Catches**: Contract mismatches between engines (e.g., E2 producing signals that E3 cannot decompose, or E6 rejecting E5's hypothesis schema).

### 3. Security Boundary Tests
- **Target**: `SecurityEngine` and E4 pre-query filters.
- **Catches**: Fail-closed authorization bypasses, entitlement leakage where restricted personas might retrieve technical evidence, and invalid regional configurations.

### 4. Provenance & Citation Integrity Tests
- **Target**: E6 citation validation logic.
- **Catches**: Hypotheses attempting to pass off hallucinated evidence IDs, duplicate citations to inflate scores, and LLM-altered quotes (material summary mismatches). Note: formatting and whitespace drift are tested to ensure they do not cause false-positive disqualifications.

### 5. Memory Contamination & Candidate Oversampling Tests
- **Target**: E9 ChromaDB storage and Search $\to$ Oversample $\to$ Filter pipeline.
- **Catches**: Simulated or unverified legacy records polluting observed operational precedents. Tests candidate multiplier application ($n\_results = \text{MAX\_RESULTS} \times \text{multiplier}$), absence of slow ChromaDB `where` filters, and recall under controlled adversarial noise fixtures.

### 6. Adversarial Perturbation & Monotonicity Tests
- **Target**: E6 Scoring constraints.
- **Catches**: Non-monotonic scoring behavior. Ensures that deleting supporting evidence always decreases a score, and injecting high-reliability contradictory evidence always suppresses a score below the abstention threshold.

### 7. Held-Out Evaluation
- **Target**: E1-E9 pipeline via `validate_held_out.py`.
- **Catches**: Pipeline overfitting to the primary demo scenario (`INC_001`). Tests edge cases like partial-bucket starvation (`INC_005`), compound failures (`INC_006`), and gradual degradation (`INC_007`).

### 8. Cross-Domain Evaluation
- **Target**: `INC_008` (B2B SaaS SAML SSO outage).
- **Catches**: E-commerce domain overfitting. Ensures the pipeline structure, evaluator, and prompts generalize to entirely different dimensional schemas and evidence sources without hardcoded assumptions.

### 9. Pluggable LLM Provider & Multi-Key Rotation Tests
- **Target**: `llm/provider.py` (`OllamaProvider`, `GroqProvider`).
- **Catches**: HTTP 429 rate limit backoff failures, zero-delay multi-key rotation, production single-credential isolation, secret-safe logging, and token sanitization.

### 10. Live Integration Validation
- **Target**: `run_demo.py` and `validate_held_out.py` with live containers.
- **Catches**: Infrastructure configuration drift, broken DB connections, missing Ollama models, and timeout issues when interacting with the real database and vector store.

---

## 3. Reproduction & Execution Commands

### Run Full Test Suite
```bash
pytest
```
*Expected Result: `288+ passed in ~20-25s`.*

### Run Specific Test Modules
```bash
# Run security & entitlement tests
pytest tests/test_security.py -v

# Run memory & candidate oversampling tests
pytest tests/test_memory.py -v

# Run LLM provider & multi-key rotation tests
pytest tests/test_llm_provider.py -v

# Run held-out evaluation & perturbation tests
pytest tests/test_overfitting.py -v

# Run scoring & challenge tests
pytest tests/test_challenge_smoke.py -v
```

### Run Benchmarks
```bash
# Run E9 candidate oversampling & scale benchmark
python benchmarks/run_oversampling_benchmark.py

# Run provider latency & concurrency comparison (Ollama vs Groq)
python benchmarks/run_provider_comparison.py
```
