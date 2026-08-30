# BusinessIntelligence.ai — Setup & Operations Guide

Evidence-backed KPI decision engine with a 9-stage causal investigation pipeline, deterministic constraint auditing (E6), role-based data governance (E7), and an enterprise React/Vite analytical console.

---

## 1. System Requirements & Prerequisites

| Requirement | Supported Version | Notes |
|---|---|---|
| **Operating System** | Windows 10/11, macOS, Linux | PowerShell or Bash terminal |
| **Python** | `Python 3.11.x` | Primary backend runtime |
| **Node.js & npm** | `Node.js >= 18.0.0`, `npm >= 9.0.0` | Required for React 19 / Vite operations console |
| **Docker Desktop** | `Docker >= 24.0.0` | Required for PostgreSQL and ChromaDB containers |
| **LLM Inference** | **Groq**, **OpenAI**, **Anthropic**, or **Ollama** | Cloud API or Local offline inference |

---

## 2. LLM Provider Configuration

### Option A: Groq Cloud API (Recommended for Ultra-Low Latency)
1. Obtain an API key from [console.groq.com](https://console.groq.com).
2. Configure `.env`:
   ```ini
   LLM_PROVIDER=groq
   GROQ_API_KEY=gsk_your_actual_api_key_here
   GROQ_MODEL=llama-3.3-70b-versatile
   ```

### Option B: OpenAI API
1. Obtain an API key from [platform.openai.com](https://platform.openai.com).
2. Configure `.env`:
   ```ini
   LLM_PROVIDER=openai
   OPENAI_API_KEY=sk-your_openai_api_key_here
   OPENAI_MODEL=gpt-4o-mini
   ```

### Option C: Anthropic API
1. Obtain an API key from [console.anthropic.com](https://console.anthropic.com).
2. Configure `.env`:
   ```ini
   LLM_PROVIDER=anthropic
   ANTHROPIC_API_KEY=sk-ant-your_anthropic_api_key_here
   ANTHROPIC_MODEL=claude-3-5-haiku-20241022
   ```

### Option D: Local Offline Inference (Ollama)
1. Install and start Ollama (`http://localhost:11434`):
   ```powershell
   ollama pull qwen3:8b
   ollama pull bge-m3         # Embedding model for ChromaDB vector store
   ```
2. Configure `.env`:
   ```ini
   LLM_PROVIDER=ollama
   OLLAMA_HOST=http://localhost:11434
   ```

---

## 3. First-Time Installation

### Step 1 — Clone / Open Repository
```powershell
cd e:\accenture
```

### Step 2 — Python Virtual Environment & Backend Dependencies
```powershell
# Create virtual environment (if not present)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install backend dependencies
pip install -r requirements.txt
```

### Step 3 — Frontend Dependencies
```powershell
# Navigate to web frontend and install npm packages
cd web
npm install
cd ..
```

### Step 4 — Configure Environment Variables
```powershell
copy .env.example .env
```
Ensure your `.env` contains the correct database and service parameters:
```ini
DATABASE_URL=postgresql://biai:biai@localhost:5432/biai
CHROMA_HOST=localhost
CHROMA_PORT=8000
API_PORT=8085
API_HOST=0.0.0.0
LLM_BACKEND=groq
GROQ_API_KEY=your_key_here
GROQ_MODEL=qwen/qwen3.8-27b
```

---

## 4. Infrastructure & Database Initialization

### Step 1 — Start PostgreSQL & ChromaDB
```powershell
docker compose up -d
```
Verify container health:
```powershell
docker compose ps
# postgres should report (healthy), chromadb should report Up
```

### Step 2 — Generate Synthetic Scenario Telemetry & Load PostgreSQL
```powershell
$env:PYTHONIOENCODING = "utf-8"
python etl/generate_scenarios.py
python etl/load_synthetic.py
```
Expected output:
```text
OK  orders                 43,359 rows
OK  payment_events        345,286 rows
OK  inventory_events        2,250 rows
OK  marketing_events           27 rows
OK  support_tickets         1,238 rows
OK  deployment_log              3 rows
Done. 392,163 rows loaded.
```

### Step 3 — Embed & Populate ChromaDB Evidence Collections
```powershell
# 1. Embed and load core unstructured evidence records (INC_001)
python etl/load_unstructured.py --scenario-id INC_001 --chroma-host localhost --chroma-port 8000

# 2. Seed multi-scenario evidence collections (INC_002, INC_004, etc.)
python etl/seed_scenario_evidence.py --chroma-host localhost --chroma-port 8000
```
Expected output:
```text
support_tickets   1238 document(s)
deployment_log       3 document(s)
release_notes        3 document(s)
TOTAL             1244 document(s) loaded into ChromaDB.
```

---

## 5. Daily Execution & Running the Platform

### Terminal 1 — Start the FastAPI Backend
```powershell
cd e:\accenture
.\.venv\Scripts\Activate.ps1
uvicorn api.main:app --host 0.0.0.0 --port 8085 --reload
```
* Interactive Swagger API documentation: `http://localhost:8085/docs`
* Health check endpoint: `http://localhost:8085/health`

### Terminal 2 — Start the React Operations Console
```powershell
cd e:\accenture\web
npm run dev
```
* Operations Console URL: `http://localhost:5173`

---

## 6. Running Investigations

### 1. Via Operations Console (Web UI)
1. Open `http://localhost:5173` in your browser.
2. Select a scenario from the top bar (e.g. `INC_001 Payment Gateway Latency`).
3. Select an Analyst Persona (`Analyst`, `CFO`, `Manager`) and Region Scope (`Global`, `US-East`, `Asia-Pacific`, etc.).
4. Click **Run Investigation** to watch the 9-stage pipeline execute with live streaming cards.
5. Review the E6 Rule Scorecard, Root-Cause Evidence Gate, and E7 Governed Action Directive.

### 2. Via Command Line / API (cURL / PowerShell)
```powershell
curl -X POST "http://localhost:8085/investigate" `
  -H "Content-Type: application/json" `
  -d '{\"scenario_id\":\"INC_001\",\"persona\":\"analyst\",\"region\":\"all\"}'
```

---

## 7. Verification & Automated Test Suites

### 1. Backend Pytest Suite
```powershell
cd e:\accenture
pytest -v --tb=short
```

### 2. Frontend Vitest Suite
```powershell
cd e:\accenture\web
npm test
```
*Runs all 12 Vitest suites and 35 React Testing Library component tests.*

### 3. Frontend Production Build Verification
```powershell
cd e:\accenture\web
npm run build
```
*Compiles TypeScript bundle and verifies zero bundle errors.*

### 4. Multi-Scenario Matrix Verification Suite
```powershell
cd e:\accenture
python scratch/run_full_matrix_verification.py
```
*Executes all 26 scenario and persona permutations with 60s rate-limit protection.*

---

## 8. Service Port Reference

| Service | Port | Description |
|---|---|---|
| **PostgreSQL** | `5432` | Relational telemetry store (`biai / biai / biai`) |
| **ChromaDB** | `8000` | Vector evidence and precedent memory store |
| **FastAPI Backend** | `8085` | Primary REST API server (`uvicorn api.main:app`) |
| **React Console** | `5173` | Vite development server (`web/`) |
| **Ollama** (Optional) | `11434` | Local LLM inference server (when `LLM_BACKEND=ollama`) |

---

## 9. Troubleshooting & FAQ

### Port `8085` already in use
Check for lingering Python background processes:
```powershell
Get-Process python* | Stop-Process
```

### `ChromaDB connection failed: Could not connect to tenant default_tenant`
Ensure Docker container is running:
```powershell
docker compose restart chromadb
```

### LLM Rate Limits (429 Too Many Requests on Groq)
The test runner `scratch/run_full_matrix_verification.py` automatically incorporates a 60-second cooldown between tests. If hitting rate limits in manual use, switch model to `groq/llama-3.3-70b-versatile` or run locally via `LLM_BACKEND=ollama`.
