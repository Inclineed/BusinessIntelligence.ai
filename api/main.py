"""
api/main.py â€” FastAPI application for BusinessIntelligence.ai.

Exposes the /investigate endpoint with server-side entitlement enforcement,
and the /feedback endpoint for capturing analyst feedback on investigation
results.

Access-denied results are returned with HTTP 403 and no evidence content.

Requirements: 5.6, 5.7, 5.8, 17.1, 17.2, 17.3, 17.4, 17.5
"""

from __future__ import annotations

import dataclasses
import datetime
import enum
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import psycopg2
import chromadb
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config.loader import load_kpi_contract, load_entitlements, load_sources, ConfigError
from config.registry import SourceRegistry
from llm.provider import OllamaProvider
from models import Persona
from pipeline.investigate import Dependencies, investigate
from security.entitlements import SecurityEngine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration â€” read once at import time (overrideable by env)
# ---------------------------------------------------------------------------

_BASE_DIR = Path(__file__).resolve().parent.parent
_CONFIG_DIR = _BASE_DIR / "config"

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL", "postgresql://biai:biai@localhost:5432/biai"
)
CHROMA_HOST: str = os.environ.get("CHROMA_HOST", "localhost")
CHROMA_PORT: int = int(os.environ.get("CHROMA_PORT", "8000"))
OLLAMA_HOST: str = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

_SUPPORTED_PERSONAS = frozenset({"cfo", "analyst", "manager"})

# ---------------------------------------------------------------------------
# JSON serialization helpers
# ---------------------------------------------------------------------------


def _to_json(obj: Any) -> Any:
    """
    Recursively convert dataclasses, enums, and nested structures into
    JSON-serializable primitives.

    - dataclass  â†’ dict (field name â†’ converted value)
    - Enum       â†’ its .value
    - list/tuple â†’ list of converted elements
    - dict       â†’ dict with converted values
    - Everything else (str, int, float, bool, None) â†’ pass through
    """
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        d = {
            f.name: _to_json(getattr(obj, f.name))
            for f in dataclasses.fields(obj)
        }
        if hasattr(obj, "supporting_evidence_ids"):
            d["supporting_evidence_ids"] = _to_json(obj.supporting_evidence_ids)
        if hasattr(obj, "contradictory_evidence_ids"):
            d["contradictory_evidence_ids"] = _to_json(obj.contradictory_evidence_ids)
        return d
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, (list, tuple)):
        return [_to_json(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _to_json(v) for k, v in obj.items()}
    # Sanitize non-JSON-compliant floats (NaN, Inf, -Inf)
    if isinstance(obj, float):
        import math as _math
        if _math.isnan(obj) or _math.isinf(obj):
            return None
    return obj


# ---------------------------------------------------------------------------
# Lifespan â€” startup / shutdown
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.

    On startup:
      1. Load and validate config artifacts (kpi_contracts, entitlements, sources).
      2. Connect to Postgres.
      3. Connect to ChromaDB.
      4. Build OllamaProvider.

    All resources are stored on app.state so request handlers can read them.
    Startup errors are logged; individual failures are non-fatal where possible
    so a partial environment can still serve /health.
    """
    state = app.state

    # ------------------------------------------------------------------
    # Config artifacts
    # ------------------------------------------------------------------
    try:
        state.kpi_contract = load_kpi_contract(_CONFIG_DIR / "kpi_contracts.yaml")
        logger.info("Loaded kpi_contracts.yaml â€” domain=%s", state.kpi_contract.get("domain"))
    except ConfigError as exc:
        logger.error("Failed to load kpi_contracts.yaml: %s", exc)
        state.kpi_contract = None

    try:
        state.entitlements_config = load_entitlements(_CONFIG_DIR / "entitlements.yaml")
        logger.info("Loaded entitlements.yaml")
    except ConfigError as exc:
        logger.error("Failed to load entitlements.yaml: %s", exc)
        state.entitlements_config = None

    try:
        state.sources_config = load_sources(_CONFIG_DIR / "sources.yaml")
        logger.info("Loaded sources.yaml â€” %d source(s)", len(state.sources_config))
    except ConfigError as exc:
        logger.error("Failed to load sources.yaml: %s", exc)
        state.sources_config = []

    # ------------------------------------------------------------------
    # Postgres connection
    # ------------------------------------------------------------------
    state.db_conn = None
    try:
        state.db_conn = psycopg2.connect(DATABASE_URL)
        logger.info("Connected to Postgres at %s", DATABASE_URL)
    except Exception as exc:  # noqa: BLE001
        logger.error("Postgres connection failed: %s â€” investigate will degrade gracefully.", exc)

    # ------------------------------------------------------------------
    # ChromaDB client
    # ------------------------------------------------------------------
    state.chroma_client = None
    try:
        state.chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        # Heartbeat to confirm connectivity
        state.chroma_client.get_collection  # lightweight check
        logger.info("Connected to ChromaDB at %s:%s", CHROMA_HOST, CHROMA_PORT)
    except Exception as exc:  # noqa: BLE001
        logger.error("ChromaDB connection failed: %s â€” investigate will degrade gracefully.", exc)

    # ------------------------------------------------------------------
    # LLM provider (Ollama)
    # ------------------------------------------------------------------
    state.llm_provider = OllamaProvider(base_url=OLLAMA_HOST)
    logger.info("OllamaProvider configured at %s", OLLAMA_HOST)

    yield

    # ------------------------------------------------------------------
    # Shutdown â€” close Postgres connection
    # ------------------------------------------------------------------
    if state.db_conn is not None:
        try:
            state.db_conn.close()
            logger.info("Postgres connection closed.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error closing Postgres connection: %s", exc)


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="BusinessIntelligence.ai",
    version="1.0.0",
    description=(
        "Evidence-backed KPI decision engine. "
        "Nine-engine pipeline with deterministic confidence and LLM narrative."
    ),
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class InvestigateRequest(BaseModel):
    scenario_id: str = "INC_001"
    persona: str = "analyst"   # "cfo" | "analyst" | "manager"
    region: Optional[str] = None


class FeedbackRequest(BaseModel):
    investigation_id: str
    content: str   # 1 to 5000 characters


class FeedbackResponse(BaseModel):
    success: bool
    feedback_id: Optional[int] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    """
    Liveness probe.  Returns status and LLM backend identifier.
    """
    return {"status": "ok", "llm_backend": "ollama"}


@app.get("/scenarios")
async def scenarios() -> dict:
    """
    Return the complete list of available scenario identifiers with catalog metadata.
    """
    return {
        "scenarios": [
            {"id": "INC_001", "status": "live", "label": "Payment Gateway Latency Regression", "domain": "E-Commerce Checkout"},
            {"id": "INC_002", "status": "live", "label": "Simultaneous Conflicting Causes", "domain": "E-Commerce Marketing"},
            {"id": "INC_003", "status": "live", "label": "Sparse Baseline History", "domain": "E-Commerce Growth"},
            {"id": "INC_004", "status": "live", "label": "ETL Ingestion Pipeline Delay", "domain": "Data Engineering"},
            {"id": "INC_005", "status": "live", "label": "Seasonal Demand Pattern", "domain": "E-Commerce Demand"},
            {"id": "INC_006", "status": "live", "label": "Compound Network & Deploy Failure", "domain": "Platform Infrastructure"},
            {"id": "INC_007", "status": "live", "label": "Gradual Worker Memory Leak", "domain": "Backend Compute"},
            {"id": "INC_008", "status": "live", "label": "Enterprise SAML SSO Outage", "domain": "Enterprise Security"},
        ]
    }


@app.get("/kpi-contract")
async def kpi_contract(request: Request) -> JSONResponse:
    """
    Return the loaded KPI contract as JSON.
    HTTP 503 when the contract was not loaded at startup.
    """
    contract = request.app.state.kpi_contract
    if contract is None:
        raise HTTPException(
            status_code=503,
            detail="KPI contract is not available â€” check server logs for config errors.",
        )
    return JSONResponse(content=_to_json(contract))


@app.post("/investigate")
async def investigate_endpoint(
    body: InvestigateRequest,
    request: Request,
) -> JSONResponse:
    """
    Run the full E1â†’E7 pipeline and return a structured InvestigationResult.

    Server-side entitlement enforcement (Requirements 5.6, 5.7, 5.8):

    1. Unsupported persona                â†’ HTTP 422
    2. entitlements.yaml unresolvable     â†’ HTTP 403, access_denied payload
    3. Empty scope after authorization    â†’ HTTP 403, access_denied payload
    4. Authorized persona, normal run     â†’ HTTP 200, InvestigationResult JSON
    """
    state = request.app.state
    persona_str = body.persona.strip().lower()

    # ------------------------------------------------------------------
    # 1. Validate persona (Requirement 11.6)
    # ------------------------------------------------------------------
    if persona_str not in _SUPPORTED_PERSONAS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unsupported persona: {body.persona!r}. "
                f"Supported: {', '.join(sorted(_SUPPORTED_PERSONAS))}"
            ),
        )

    # ------------------------------------------------------------------
    # 2. Resolve entitlements (Requirement 5.8)
    # ------------------------------------------------------------------
    entitlements_config = state.entitlements_config
    if entitlements_config is None:
        # entitlements.yaml failed to load at startup â€” fail closed (Req 5.8)
        logger.warning(
            "/investigate: entitlements_config unavailable for persona=%s scenario=%s",
            persona_str, body.scenario_id,
        )
        return JSONResponse(
            status_code=403,
            content={
                "access_denied": True,
                "reason": "entitlements could not be resolved",
                "persona": persona_str,
            },
        )

    security_engine = SecurityEngine(entitlements_config)
    try:
        scope = security_engine.authorize(persona_str, region=body.region)
    except Exception as exc:  # noqa: BLE001 â€” e.g. ValueError from own_only + no region
        logger.error(
            "/investigate: entitlement authorization error for persona=%s: %s",
            persona_str, exc,
        )
        return JSONResponse(
            status_code=403,
            content={
                "access_denied": True,
                "reason": "entitlements could not be resolved",
                "persona": persona_str,
            },
        )

    # ------------------------------------------------------------------
    # 3. Empty-scope check (Requirement 5.6)
    # ------------------------------------------------------------------
    if scope.is_empty:
        logger.warning(
            "/investigate: empty authorization scope for persona=%s scenario=%s",
            persona_str, body.scenario_id,
        )
        access_denied = security_engine.get_access_denied_result(scope, denied_sources=[])
        return JSONResponse(status_code=403, content=access_denied)

    # ------------------------------------------------------------------
    # 4. Build Dependencies and run the pipeline
    # ------------------------------------------------------------------
    deps = Dependencies(
        db_conn=state.db_conn,
        chroma_client=state.chroma_client,
        llm_provider=state.llm_provider,
        kpi_contract=entitlements_config if state.kpi_contract is None else state.kpi_contract,
        entitlements_config=entitlements_config,
        sources_config=state.sources_config,
        scenario_id=body.scenario_id,
    )

    try:
        result = investigate(body.scenario_id, persona_str, deps)
    except ValueError as exc:
        # e.g. unsupported persona surfaced from deep in the pipeline
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "/investigate: pipeline error for scenario=%s persona=%s: %s",
            body.scenario_id, persona_str, exc,
        )
        raise HTTPException(
            status_code=500,
            detail="Internal pipeline error â€” see server logs for details.",
        ) from exc

    # ------------------------------------------------------------------
    # 5. Persist the investigation result to the investigations table
    #    investigation_id = "{scenario_id}_{persona}_{timestamp}" (Req 17.4)
    # ------------------------------------------------------------------
    investigation_id: Optional[str] = None
    if state.db_conn is not None:
        try:
            ts_tag = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            investigation_id = f"{body.scenario_id}_{persona_str}_{ts_tag}"
            result_json_str = json.dumps(_to_json(result))
            with state.db_conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO investigations
                        (investigation_id, scenario_id, persona, result_json, created_at)
                    VALUES (%s, %s, %s, %s::jsonb, now())
                    ON CONFLICT (investigation_id) DO NOTHING
                    """,
                    (investigation_id, body.scenario_id, persona_str, result_json_str),
                )
            state.db_conn.commit()
            logger.info(
                "/investigate: persisted investigation_id=%s", investigation_id
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "/investigate: failed to persist investigation result: %s", exc
            )
            try:
                state.db_conn.rollback()
            except Exception:  # noqa: BLE001
                pass
            investigation_id = None
    else:
        logger.debug("/investigate: no DB connection; skipping investigation persistence.")

    result_payload = _to_json(result)
    if investigation_id is not None:
        result_payload["investigation_id"] = investigation_id

    return JSONResponse(content=result_payload)


# ---------------------------------------------------------------------------
# POST /feedback
# ---------------------------------------------------------------------------


@app.post("/feedback", response_model=FeedbackResponse)
async def feedback_endpoint(
    body: FeedbackRequest,
    request: Request,
) -> JSONResponse:
    """
    Persist analyst feedback on an investigation result.

    Validation rules (Requirements 17.1 â€“ 17.5):
    1. content length must be 1â€“5000 chars   â†’ HTTP 422 on failure
    2. investigation_id must exist in DB     â†’ HTTP 404 if not found
    3. INSERT into feedback table            â†’ HTTP 200 with feedback_id
    4. On DB failure: no partial entry       â†’ HTTP 500
    5. No DB connection available            â†’ HTTP 500
    """
    state = request.app.state

    # ------------------------------------------------------------------
    # 1. Validate content length (Requirement 17.3)
    # ------------------------------------------------------------------
    content_len = len(body.content)
    if content_len < 1 or content_len > 5000:
        return JSONResponse(
            status_code=422,
            content=FeedbackResponse(
                success=False,
                error=(
                    f"Feedback content must be between 1 and 5000 characters "
                    f"(got {content_len})."
                ),
            ).model_dump(),
        )

    # ------------------------------------------------------------------
    # 2. Require a live DB connection
    # ------------------------------------------------------------------
    if state.db_conn is None:
        logger.error("/feedback: no database connection available.")
        return JSONResponse(
            status_code=500,
            content=FeedbackResponse(
                success=False,
                error="feedback could not be saved",
            ).model_dump(),
        )

    # ------------------------------------------------------------------
    # 3. Verify investigation_id exists (Requirement 17.4)
    # ------------------------------------------------------------------
    try:
        with state.db_conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM investigations WHERE investigation_id = %s",
                (body.investigation_id,),
            )
            row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        logger.error("/feedback: DB error checking investigation_id: %s", exc)
        try:
            state.db_conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return JSONResponse(
            status_code=500,
            content=FeedbackResponse(
                success=False,
                error="feedback could not be saved",
            ).model_dump(),
        )

    if row is None:
        return JSONResponse(
            status_code=404,
            content=FeedbackResponse(
                success=False,
                error=f"Investigation '{body.investigation_id}' was not found.",
            ).model_dump(),
        )

    # ------------------------------------------------------------------
    # 4. Insert feedback (Requirements 17.1, 17.2, 17.5)
    # ------------------------------------------------------------------
    try:
        with state.db_conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO feedback (investigation_id, content, received_at)
                VALUES (%s, %s, now())
                RETURNING feedback_id
                """,
                (body.investigation_id, body.content),
            )
            feedback_id: int = cur.fetchone()[0]
        state.db_conn.commit()
        logger.info(
            "/feedback: persisted feedback_id=%d for investigation_id=%s",
            feedback_id,
            body.investigation_id,
        )
        return JSONResponse(
            status_code=200,
            content=FeedbackResponse(success=True, feedback_id=feedback_id).model_dump(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("/feedback: DB error inserting feedback: %s", exc)
        try:
            state.db_conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        # Requirement 17.5 â€” no partial entry; rollback ensures atomicity
        return JSONResponse(
            status_code=500,
            content=FeedbackResponse(
                success=False,
                error="feedback could not be saved",
            ).model_dump(),
        )

