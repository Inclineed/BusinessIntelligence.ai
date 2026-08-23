# BusinessIntelligence.ai — Setup & Run Guide

Domain-agnostic, evidence-backed KPI decision engine.  
Nine-engine pipeline with deterministic confidence and local LLM inference.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| **Python 3.11** | Other 3.x versions may work but are untested |
| **Docker Desktop** | Must be running before you start |
| **Ollama** | Installed and running locally on port 11434 |
| **Git** | For cloning / version control |

### Required Ollama models

Pull these once before first run:

```powershell
ollama pull qwen3:8b       # primary reasoning model (~5 GB)
ollama pull gemma3:12b     # fallback model (~8 GB)
ollama pull bge-m3         # embedding model for ChromaDB (~1 GB)
```

Confirm they are available:

```powershell
ollama list
# Should show: qwen3:8b, gemma3:12b, bge-m3
```

---

## First-Time Setup

### 1. Clone / open the project

```powershell
cd e:\accenture
```

### 2. Install Python dependencies

```powershell
pip install -r requirements.txt
```

### 3. Configure environment variables

```powershell
copy .env.example .env
```

The defaults in `.env` work out of the box for a local setup:

```
DATABASE_URL=postgresql://biai:biai@localhost:5432/biai
CHROMA_HOST=localhost
CHROMA_PORT=8000
OLLAMA_HOST=http://localhost:11434
```

Edit `.env` only if your ports differ.

### 4. Start the databases

```powershell
docker compose up postgres chromadb -d
```

Wait ~10 seconds for Postgres to become healthy:

```powershell
docker compose ps
# postgres should show: (healthy)
```

### 5. Generate synthetic scenario data

```powershell
$env:PYTHONIOENCODING = "utf-8"
python etl/generate_inc001.py
python etl/generate_scenarios.py
```

This writes CSVs to `data/synthetic/`.

### 6. Load structured data into Postgres

```powershell
python etl/load_fast.py
```

Expected output:
```
OK  orders                 43,359 rows
OK  payment_events        345,286 rows
OK  inventory_events        2,250 rows
OK  marketing_events           27 rows
OK  support_tickets         1,238 rows
OK  deployment_log              3 rows
Done. 392,163 rows loaded.
```

### 7. Embed unstructured evidence into ChromaDB

```powershell
python etl/load_unstructured.py `
  --chroma-host localhost `
  --chroma-port 8000 `
  --ollama-host http://localhost:11434
```

Expected output:
```
support_tickets   1238 document(s)
deployment_log       3 document(s)
release_notes        3 document(s)
TOTAL             1244 document(s)
```

> **Note:** This step embeds documents using `bge-m3` via Ollama. It takes ~60–90 seconds.

---

## Daily Run

Every time you want to use the app, you need three things running: Docker containers, the FastAPI backend, and the Streamlit frontend.

### Step 1 — Start Docker containers (if not already running)

```powershell
cd e:\accenture
docker compose up postgres chromadb -d
```

Check they are healthy:

```powershell
docker compose ps
```

### Step 2 — Warm the LLM (recommended)

The first Ollama inference after a cold start can be slow (2–5 min).  
Warm the model first to avoid a timeout on your first investigation:

```powershell
ollama run qwen3:8b "hi"
# Wait for the response, then Ctrl+C
```

### Step 3 — Start the API backend

Open **Terminal 1**:

```powershell
cd e:\accenture
$env:PYTHONIOENCODING = "utf-8"
$env:DATABASE_URL     = "postgresql://biai:biai@localhost:5432/biai"
$env:CHROMA_HOST      = "localhost"
$env:CHROMA_PORT      = "8000"
$env:OLLAMA_HOST      = "http://localhost:11434"
python -m uvicorn api.main:app --host 0.0.0.0 --port 8080
```

You should see:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080
```

### Step 4 — Start the Streamlit frontend

Open **Terminal 2**:

```powershell
cd e:\accenture
$env:PYTHONIOENCODING = "utf-8"
$env:API_URL          = "http://localhost:8080"
python -m streamlit run frontend/app.py
```

You should see:
```
  You can now view your Streamlit app in your browser.
  Local URL: http://localhost:8501
```

### Step 5 — Open the browser

Go to **http://localhost:8501**

1. Select persona in the sidebar: **Analyst** (full access), **CFO** (aggregate only), or **Manager** (own region — demonstrates access-denied)
2. Select scenario: **INC_001** (live full investigation), **INC_002**, or **INC_004**
3. Click **🚀 Run Investigation**

> **Expected run time:** 2–4 minutes for the first run (LLM generating hypotheses + decision locally).  
> Subsequent runs on the same scenario are faster once the model is warm.

---

## Scenarios

| Scenario | Status | What it demonstrates |
|---|---|---|
| 🟢 **INC_001** | Live | Full investigation — checkout/payment degradation, H1 wins HIGH, Android dominant, rollback recommended |
| 🟢 **INC_002** | Live | Simultaneous causes — pipeline abstains (gap too small between H1 and H2) |
| 🧪 **INC_003** | Evaluation-only | Sparse history — 12 days < 30-sample threshold, anomaly suppressed. Run via `python run_demo.py` |
| 🟢 **INC_004** | Live | Data-quality false anomaly — ETL gap creates apparent revenue drop, pipeline flags it as data issue not business issue |

---

## Offline Verification (no servers needed)

Runs a mock INC_001 investigation using pre-built fixtures and prints the 15-dimension evaluation scorecard. Requires no running Postgres, ChromaDB, or Ollama:

```powershell
$env:PYTHONIOENCODING = "utf-8"
python run_demo.py
```

Expected output:
```
Overall: 15/15 dimensions passed | PASS
Hallucinated evidence references: 0
Authorization violations: 0
```

---

## API Endpoints

The FastAPI backend exposes these endpoints once running on port 8080:

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `GET` | `/scenarios` | List available scenarios with status |
| `GET` | `/kpi-contract` | Loaded KPI semantic contract as JSON |
| `POST` | `/investigate` | Run a full investigation |
| `POST` | `/feedback` | Submit analyst feedback on an investigation |

Quick test:

```powershell
# Health check
curl http://localhost:8080/health

# Run INC_001 as analyst
curl -X POST http://localhost:8080/investigate `
  -H "Content-Type: application/json" `
  -d '{\"scenario_id\":\"INC_001\",\"persona\":\"analyst\"}'
```

---

## Personas

| Persona | Authorized sources | Narrative style |
|---|---|---|
| `analyst` | orders, payment_gateway, inventory, marketing, deployment_log, support_tickets, release_notes | Full technical breakdown |
| `cfo` | orders, inventory (aggregate only) | C-suite executive summary — single most important action |
| `manager` | orders, inventory (own region only) | Operational action list — demonstrates access-denied for payment_gateway |

---

## Troubleshooting

### `streamlit: command not found`

Use the module form instead:
```powershell
python -m streamlit run frontend/app.py
```

### `ChromaDB connection failed: Could not connect to tenant default_tenant`

The Docker image version is pinned to `0.5.7` to match the Python client (`chromadb==0.5.0`). If you see this after pulling a new image, check `docker-compose.yml` — it should read `chromadb/chroma:0.5.7`.

### Investigation times out in the UI (`Request timed out after 600s`)

The LLM is running cold or the machine is under heavy load. Steps:
1. Stop the `ra-*` containers if running: `docker stop ra-tei-reranker ra-searxng ra-qdrant`
2. Warm the model: `ollama run qwen3:8b "hi"` then Ctrl+C
3. Retry the investigation

### `tuple index out of range` on payment KPIs

This was a fixed bug (modulo operator in SQL). If you see it, confirm you have the latest `engines/kpi_store.py` where `% 15` is written as `%% 15`.

### `llm_calls=0` in telemetry

This was a fixed bug (deepcopy snapshot). Confirm you have the latest `pipeline/telemetry.py` with the `live_telemetry` property and `pipeline/investigate.py` passing `telemetry_svc.live_telemetry` to the LLM engines.

### H1 shows MEDIUM instead of HIGH

This was a fixed bug in the challenge rules. Confirm:
- `engines/challenge.py` — `_rule_timeline` accepts `payment_gateway` as deployment-adjacent evidence
- `engines/challenge.py` — `_rule_segment_alignment` passes for payment/checkout hypotheses with payment_gateway evidence
- `config/entitlements.yaml` — analyst `authorized_sources` includes `deployment_log`, `support_tickets`, `release_notes`
- ChromaDB `evidence_INC_001` collection was rebuilt after the entitlement change (1244 documents)

---

## Data Architecture

```
data/
  synthetic/
    orders.csv                  # INC_001 — hourly orders with incident window
    payment_events.csv          # INC_001 — 15-min gateway events
    inventory_events.csv        # INC_001 — daily SKU snapshots (normal throughout)
    marketing_events.csv        # INC_001 — daily campaigns (intentionally stale)
    support_tickets.csv         # INC_001 — customer tickets (3x spike in window)
    deployment_log.csv          # INC_001 — v4.3 deploy at 08:45, 15 min before incident
    INC_002/                    # Abstain scenario data
    INC_003/                    # Sparse history data
    INC_004/                    # ETL gap / data-quality scenario data
  release_notes/
    v4.2.txt                    # Routine maintenance
    v4.3.txt                    # Performance optimisation (root cause)
    v4.3-hotfix.txt             # Emergency rollback
  ground_truth.json             # Hidden — evaluator only, never read by pipeline
```

---

## Service Ports

| Service | Port | Notes |
|---|---|---|
| Postgres | 5432 | Credentials: `biai / biai / biai` |
| ChromaDB | 8000 | Pinned to `0.5.7` |
| Ollama | 11434 | Must be started manually |
| FastAPI | 8080 | Started by you in Terminal 1 |
| Streamlit | 8501 | Started by you in Terminal 2 |
