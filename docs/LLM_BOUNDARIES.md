# Deterministic vs. LLM Boundaries

This document defines the strict operational boundaries between deterministic computational engines and Large Language Models (LLMs) in **BusinessIntelligence.ai**.

---

## 1. The Core Invariant

> **Fundamental Principle**: Quantitative truth (numbers, metric deltas, z-scores, mathematical scores, confidence thresholds, and rule verifications) belongs **exclusively** to deterministic software algorithms. LLMs are used strictly as natural-language narrative synthesizers and qualitative reasoners.

```
┌────────────────────────────────────────────────────────┐
│               DETERMINISTIC ENGINES                    │
│   • KPI values & deltas (E1)                           │
│   • Z-scores & anomaly detection (E2)                  │
│   • Dimensional contributions (E3)                     │
│   • Reliability weights & freshness decay (E4)         │
│   • Five operational rule evaluations (E6)             │
│   • Hypothesis scoring & winner selection (E6)         │
│   • Confidence threshold evaluation (E6)               │
│   • Abstention enforcement gate (E6/E7)                │
│   • Simulated trajectory curves (E8)                   │
│   • Precedent retrieval weights & TTL expiry (E9)      │
└──────────────────────────────────┬─────────────────────┘
                                   │ Constrains & Drives
                                   ▼
┌────────────────────────────────────────────────────────┐
│                  LANGUAGE MODEL ENGINES                │
│   • Long evidence text compression (E4)                │
│   • Qualitative hypothesis statement writing (E5)      │
│   • Causal reasoning narrative (E5)                    │
│   • Persona-tailored mitigation action prose (E7)      │
│   • Precedent natural-language summary (E9)            │
└────────────────────────────────────────────────────────┘
```

---

## 2. Permitted vs. Forbidden LLM Operations

| Category | Operation | Permitted? | Enforcing Mechanism |
|---|---|---|---|
| **Quantitative** | Calculate KPI delta or percentage | ❌ **FORBIDDEN** | Engine E1 / E3 pure SQL+Stats |
| **Quantitative** | Determine anomaly status ($z \ge 2.0$) | ❌ **FORBIDDEN** | Engine E2 math calculations |
| **Quantitative** | Evaluate rule pass/fail verdicts | ❌ **FORBIDDEN** | Engine E6 deterministic rule functions |
| **Quantitative** | Score hypotheses ($[0, 1]$) | ❌ **FORBIDDEN** | Engine E6 clamp and weighting math |
| **Quantitative** | Assign confidence state (HIGH/MED/LOW) | ❌ **FORBIDDEN** | Engine E6 threshold logic |
| **Security** | Filter unauthorized evidence sources | ❌ **FORBIDDEN** | `SecurityEngine` pre-retrieval scope |
| **Data Integrity** | Generate new evidence identifiers | ❌ **FORBIDDEN** | E4 SHA-256 deterministic generator |
| **Narrative** | Compress evidence text $>200$ words | ✅ **PERMITTED** | E4 `_maybe_summarize` |
| **Narrative** | Synthesize hypothesis explanation | ✅ **PERMITTED** | E5 `generate_hypotheses` (`temperature=0.0`) |
| **Narrative** | Link evidence IDs in citations | ✅ **PERMITTED** | E5 prompt schema (validated by E6 D16) |
| **Narrative** | Draft persona-tailored action steps | ✅ **PERMITTED** | E7 `decide` |
| **Narrative** | Draft 2-3 sentence precedent summary | ✅ **PERMITTED** | E9 `summarize_investigation` |

---

## 3. Engine-by-Engine LLM Prompting & Constraints

### Engine E4: Evidence Summarization
- **Purpose**: Compress raw text documents exceeding 200 words into a single sentence.
- **System Prompt**: *"You are a data analyst. Summarize evidence in one sentence. Do not include numbers or quantitative claims."*
- **Temperature**: `0.0` | **Max Tokens**: `80`
- **Fallback**: Returns original uncompressed text if LLM call fails.

### Engine E5: Hypothesis Generation
- **Purpose**: Propose candidate explanations linking metric anomalies to observed evidence.
- **System Prompt**: Enforces strict JSON schema output. Disallows generating numbers, confidence ratings, or synthetic evidence IDs.
- **Temperature**: `0.0` | **Max Tokens**: `800`
- **Validation Guard**: Hypotheses citing non-existent evidence IDs or unparseable JSON are rejected at schema validation.

### Engine E7: Decision Recommendation
- **Purpose**: Draft mitigation recommendations for the winning hypothesis.
- **Input Constraint**: E7 receives the deterministic `winning_hypothesis_id` and `confidence_state` produced by E6.
- **Abstention Gate**: If E6 confidence is `ABSTAIN`, E7 is **bypassed completely** and outputs `recommended_action = None`.
- **Temperature**: `0.0` | **Max Tokens**: `300`

### Engine E9: Precedent Summarization
- **Purpose**: Create a clean natural language summary for vector indexing in ChromaDB.
- **System Prompt**: *"You are a concise business intelligence analyst. Summarize investigations in 2-3 plain-English sentences. Do not include any numeric figures or confidence scores."*
- **Temperature**: `0.0` | **Max Tokens**: `200`
- **Fallback**: Deterministic string template (`_build_fallback_summary`).

---

## 4. Temperature & Determinism Controls

All LLM calls across the pipeline specify:
```python
temperature = 0.0
```
While temperature 0 does not guarantee bit-exact token determinism across different hardware architectures or GPU execution batches, it minimizes generation variance. More importantly, **even if LLM text varies slightly, downstream scores and decisions remain 100% deterministic conditional on the structured outputs provided to the deterministic engines**. E6 evaluates evidence IDs and rule criteria via deterministic code, not LLM token probabilities. LLM generation itself is not claimed to be bit-for-bit deterministic.

---

## 5. Failure & Unavailability Handling (`LLMUnavailableError`)

When the local Ollama daemon is offline or experiencing heavy load:
1. `OllamaProvider` attempts primary model (`qwen3:8b`).
2. On connection error or timeout (>30s), attempts fallback model (`gemma3:12b`).
3. On second failure, raises `LLMUnavailableError`.
4. **Graceful Pipeline Degradation**:
   - E5 produces 0 hypotheses $\rightarrow$ E6 sets `abstained=True` $\rightarrow$ E7 sets `recommended_action=None`.
   - E9 invokes `_build_fallback_summary` template and indexes the investigation without crashing.
