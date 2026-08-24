# Operations & Deployment Handbook

This document provides step-by-step procedures for initializing infrastructure, loading synthetic data, running investigations, managing vector memory, and troubleshooting operational issues in **BusinessIntelligence.ai**.

---

## 1. System Requirements & Prerequisites

- **Operating System**: Linux, macOS, or Windows (WSL2 / PowerShell).
- **Python**: Version 3.11+.
- **Docker & Docker Compose**: For PostgreSQL and ChromaDB containers.
- **Ollama**: Local LLM server running on `http://localhost:11434`.
  - Required Models: `qwen3:8b` (inference) and `bge-m3` (embeddings).

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

### Step 3: Initialize Ollama Models
```bash
# Pull primary inference model
ollama pull qwen3:8b

# Pull secondary fallback model
ollama pull gemma3:12b

# Pull embedding model (1024 dimensions)
ollama pull bge-m3
```

---

## 3. Data Generation & Ingestion (ETL)

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

## 4. Execution Workflows

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

### Option D: Run REST API & Streamlit Dashboard
```bash
# Terminal 1: Start FastAPI backend (port 8080)
uvicorn api.main:app --host 0.0.0.0 --port 8080

# Terminal 2: Start Streamlit operational console (port 8501)
streamlit run frontend/app.py --server.port 8501
```
Open **`http://localhost:8501`** in a browser to use the operational terminal.

---

## 5. Precedent Memory Maintenance & Rebuild

> [!WARNING]
> This operation deletes the existing `investigation_precedents` collection. Run only when intentionally rebuilding E9 memory.

To reset ChromaDB precedent memory and index clean baseline investigations:
```bash
python scripts/rebuild_memory.py
```
This drops the `investigation_precedents` collection and re-inserts clean provenance-complete precedents for `INC_001`–`INC_008` with human-validation fields initialized to unvalidated.

---

## 6. Troubleshooting Matrix

| Issue / Symptom | Probable Cause | Resolution |
|---|---|---|
| `ChromaDB: Dimension mismatch (got 384, expected 1024)` | Query was executed using ChromaDB default embedding model instead of `bge-m3`. | Ensure `llm_provider.embed(..., model="bge-m3")` pre-computes embeddings before querying ChromaDB. |
| `LLMUnavailableError: Connection refused (localhost:11434)` | Ollama daemon is not running. | Run `ollama serve` in a terminal window. |
| `psycopg2.OperationalError: could not connect to server` | PostgreSQL container is stopped or starting. | Run `docker compose ps` and verify `postgres` container is healthy on port 5432. |
| `Streamlit: Port 8501 is already in use` | Previous Streamlit instance still active. | Kill existing process or specify another port: `--server.port 8502`. |
| `Evaluation Failure: D16 Citation Mismatch` | Quoted summary in hypothesis was altered by LLM text generation. | Ensure E5 canonicalizes `quoted_summary` directly from `evidence_by_id[eid].summary`. |
