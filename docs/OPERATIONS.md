# Operations & Deployment Handbook

This document provides step-by-step procedures for initializing infrastructure, loading synthetic data, configuring LLM providers (Ollama vs. Groq), running investigations, managing vector memory, and troubleshooting operational issues in **BusinessIntelligence.ai**.

---

## 1. System Requirements & Prerequisites

- **Operating System**: Linux, macOS, or Windows (WSL2 / PowerShell).
- **Python**: Version 3.11+.
- **Docker & Docker Compose**: For PostgreSQL and ChromaDB containers.
- **LLM Provider Options**:
  - **Local Ollama**: Local server running on `http://localhost:11434` with models `qwen3:8b` (reasoning) and `bge-m3` (embeddings).
  - **Groq Cloud**: API key with access to `llama-3.3-70b-versatile` (or other supported models). Embeddings automatically delegate to local `bge-m3`.

---

## 2. Step-by-Step Environment Initialization

### Step 1: Clone & Install Python Dependencies
```bash
git clone https://github.com/Inclineed/BusinessIntelligence.ai.git
cd BusinessIntelligence.ai

python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Step 2: Start Infrastructure Containers
```bash
docker compose up -d postgres chromadb
```
- **PostgreSQL 15**: Listening on `localhost:5432` (`user: biai`, `pass: biai`, `db: biai`).
- **ChromaDB 0.5.7**: Listening on `localhost:8000`.

### Step 3: Initialize Ollama Models (Required for Local Inference & Embeddings)
```bash
# Pull primary inference model
ollama pull qwen3:8b

# Pull secondary fallback model
ollama pull gemma3:12b

# Pull embedding model (1024 dimensions)
ollama pull bge-m3
```

---

## 3. LLM Provider Management

### Selecting Local Ollama Provider (Default)
In `.env` or shell:
```bash
LLM_PROVIDER=ollama
OLLAMA_HOST=http://localhost:11434
```

### Selecting Groq Cloud Provider
In untracked `.env` or shell:
```bash
LLM_PROVIDER=groq
GROQ_API_KEY=<your_provisioned_groq_api_key>
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_CREDENTIAL_MODE=single
```

For local testing / hackathon concurrency pooling (untracked `.env` only):
```bash
GROQ_CREDENTIAL_MODE=local_pool
GROQ_API_KEYS=<key1>,<key2>,<key3>
```

### Running the Live Groq Smoke Test
Verify connectivity, model response, latency, and cost calculation without starting the full app:
```bash
python scripts/test_groq.py
# Or test structured JSON output:
python scripts/test_groq.py --json
```

---

## 4. Data Generation & Ingestion (ETL)

Generate synthetic baseline datasets and held-out scenarios (`INC_001` through `INC_008`) across PostgreSQL tables and ChromaDB vector collections:

```bash
# Ingest PostgreSQL seed data and seed ChromaDB collections
python etl/generate_held_out.py
```
This script initializes:
- `kpi_values` table with conversion, latency, and payment metrics.
- Relational event tables (`payment_events`, `inventory_events`, `deployment_log`).
- ChromaDB collections: `support_tickets`, `release_notes`, `deployment_log`.

---

## 5. Execution Workflows

### Option A: Run Live Investigation Demo (CLI)
Executes the full E1→E9 pipeline for `INC_001` and evaluates against ground truth:
```bash
python run_demo.py
```

### Option B: Run Held-Out Scenario Validation
Validates all held-out scenarios (`INC_005`, `INC_006`, `INC_007`, `INC_008`):
```bash
python scripts/validate_held_out.py
```

### Option C: Run Full Pytest Suite
```bash
pytest
```

### Option D: Run REST API & React Dashboard
```bash
# Terminal 1: Start FastAPI backend (port 8080)
uvicorn api.main:app --host 0.0.0.0 --port 8080

# Terminal 2: Start web frontend (port 5173)
cd web
npm run dev
```

---

## 6. Precedent Memory Maintenance & Rebuild

> [!WARNING]
> This operation deletes the existing `investigation_precedents` collection. Run only when intentionally rebuilding E9 memory.

To reset ChromaDB precedent memory and index clean baseline investigations:
```bash
python scripts/rebuild_memory.py
```

---

## 7. Troubleshooting Matrix

| Issue / Symptom | Probable Cause | Resolution |
|---|---|---|
| `ChromaDB: Dimension mismatch (got 384, expected 1024)` | Query was executed using ChromaDB default embedding model instead of `bge-m3`. | Ensure `llm_provider.embed(..., model="bge-m3")` pre-computes embeddings before querying ChromaDB. |
| `LLMUnavailableError: Connection refused (localhost:11434)` | Ollama daemon is not running. | Run `ollama serve` in a terminal window. |
| `ValueError: GROQ_API_KEY is required for GroqProvider` | `LLM_PROVIDER=groq` is set but `GROQ_API_KEY` is missing or empty. | Set `GROQ_API_KEY` in `.env` or export in environment. |
| `GroqAPIError: Groq rate limit (HTTP 429) exceeded` | Groq tier rate limit exhausted. | `GroqProvider` automatically retries with backoff. Check dashboard quotas or upgrade tier. |
| `psycopg2.OperationalError: could not connect to server` | PostgreSQL container is stopped or starting. | Run `docker compose ps` and verify `postgres` container is healthy on port 5432. |
| `Evaluation Failure: D16 Citation Mismatch` | Quoted summary in hypothesis was altered by LLM text generation. | Ensure E5 canonicalizes `quoted_summary` directly from `evidence_by_id[eid].summary`. |
