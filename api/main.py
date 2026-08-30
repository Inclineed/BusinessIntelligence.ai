"""
api/main.py — FastAPI application for BusinessIntelligence.ai.

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

from config.loader import (
    load_kpi_contract, 
    load_entitlements, 
    load_sources, 
    load_domain_semantics, 
    load_scenarios, 
    ConfigError
)
from config.registry import SourceRegistry
from llm.provider import OllamaProvider, get_llm_provider
from models import Persona
from pipeline.investigate import Dependencies, investigate
from security.entitlements import SecurityEngine

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — read once at import time (overrideable by env)
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

    - dataclass  → dict (field name → converted value)
    - Enum       → its .value
    - list/tuple → list of converted elements
    - dict       → dict with converted values
    - Everything else (str, int, float, bool, None) → pass through
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
    if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
        return obj.isoformat()
    # Sanitize non-JSON-compliant floats (NaN, Inf, -Inf)
    if isinstance(obj, float):
        import math as _math
        if _math.isnan(obj) or _math.isinf(obj):
            return None
    return obj


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
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
        logger.info("Loaded kpi_contracts.yaml — domain=%s", state.kpi_contract.get("domain"))
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
        logger.info("Loaded sources.yaml — %d source(s)", len(state.sources_config))
    except ConfigError as exc:
        logger.error("Failed to load sources.yaml: %s", exc)
        state.sources_config = []

    try:
        state.domain_semantics = load_domain_semantics(_CONFIG_DIR / "domain_semantics.yaml")
        logger.info("Loaded domain_semantics.yaml")
    except ConfigError as exc:
        logger.error("Failed to load domain_semantics.yaml: %s", exc)
        state.domain_semantics = {}

    try:
        state.scenarios_config = load_scenarios(_CONFIG_DIR / "scenarios.yaml")
        logger.info("Loaded scenarios.yaml")
    except ConfigError as exc:
        logger.error("Failed to load scenarios.yaml: %s", exc)
        state.scenarios_config = {"scenarios": []}

    # ------------------------------------------------------------------
    # Postgres connection
    # ------------------------------------------------------------------
    state.db_conn = None
    try:
        state.db_conn = psycopg2.connect(DATABASE_URL)
        logger.info("Connected to Postgres at %s", DATABASE_URL)
    except Exception as exc:  # noqa: BLE001
        logger.error("Postgres connection failed: %s — investigate will degrade gracefully.", exc)

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
        logger.error("ChromaDB connection failed: %s — investigate will degrade gracefully.", exc)

    # ------------------------------------------------------------------
    # LLM provider (Ollama / Groq)
    # ------------------------------------------------------------------
    state.llm_provider = get_llm_provider()
    logger.info("LLMProvider configured: %s", getattr(state.llm_provider, "provider_name", "unknown"))

    yield

    # ------------------------------------------------------------------
    # Shutdown — close Postgres connection
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
    scenario_id: Optional[str] = None
    scenario: Optional[str] = None
    persona: str = "analyst"   # "cfo" | "analyst" | "manager"
    region: Optional[str] = None


class FeedbackRequest(BaseModel):
    """Structured feedback submission — backward-compatible with legacy {investigation_id, content} payloads."""
    investigation_id: str
    # Legacy field (kept for backward compat — mapped to analyst_notes if no verdict)
    content: Optional[str] = None
    # Structured fields (Round 2)
    scenario_id: Optional[str] = None
    persona: Optional[str] = "analyst"
    verdict: Optional[str] = "CORRECT"  # CORRECT | INCORRECT | PARTIALLY_CORRECT | UNSURE
    corrected_hypothesis_id: Optional[str] = None
    corrected_confidence_state: Optional[str] = None
    corrected_action: Optional[str] = None
    evidence_grounding_correct: Optional[bool] = None
    analyst_notes: Optional[str] = None


class FeedbackResponse(BaseModel):
    success: bool
    feedback_id: Optional[int] = None
    validated_precedent: bool = False
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health(request: Request) -> dict:
    """
    Liveness probe. Returns status and LLM backend identifier.
    """
    provider_name = getattr(getattr(request.app.state, "llm_provider", None), "provider_name", "ollama")
    return {"status": "ok", "llm_backend": provider_name}


@app.get("/scenarios")
async def scenarios(request: Request) -> dict:
    """
    Return the complete list of available scenario identifiers with catalog metadata.
    """
    scenarios_config = request.app.state.scenarios_config
    if not scenarios_config or not scenarios_config.get("scenarios"):
        # Fallback empty list if config is missing or invalid
        return {"scenarios": []}
    return scenarios_config


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
            detail="KPI contract is not available — check server logs for config errors.",
        )
    return JSONResponse(content=_to_json(contract))


@app.post("/investigate")
async def investigate_endpoint(
    body: InvestigateRequest,
    request: Request,
) -> JSONResponse:
    """
    Run the full E1→E7 pipeline and return a structured InvestigationResult.

    Server-side entitlement enforcement (Requirements 5.6, 5.7, 5.8):

    1. Unsupported persona                → HTTP 422
    2. entitlements.yaml unresolvable     → HTTP 403, access_denied payload
    3. Empty scope after authorization    → HTTP 403, access_denied payload
    4. Authorized persona, normal run     → HTTP 200, InvestigationResult JSON
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
    entitlements_config = getattr(state, "entitlements_config", None)
    if entitlements_config is None:
        try:
            entitlements_config = load_entitlements(_CONFIG_DIR / "entitlements.yaml")
            state.entitlements_config = entitlements_config
        except Exception:
            entitlements_config = None

    if entitlements_config is None:
        # entitlements.yaml failed to load at startup — fail closed (Req 5.8)
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
    except Exception as exc:  # noqa: BLE001 — e.g. ValueError from own_only + no region
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
    try:
        from dotenv import load_dotenv
        load_dotenv(_BASE_DIR / ".env", override=True)
    except Exception:
        pass

    # Auto-reconnect to Postgres if container was started after server boot
    db_conn = getattr(state, "db_conn", None)
    if db_conn is None or getattr(db_conn, "closed", 0) != 0:
        try:
            db_conn = psycopg2.connect(DATABASE_URL)
            state.db_conn = db_conn
            print(f"\033[92m[DATABASE]\033[0m Successfully auto-connected to PostgreSQL at {DATABASE_URL}")
        except Exception as db_err:
            print(f"\033[91m[DATABASE ERROR]\033[0m PostgreSQL connection failed: {db_err}")
            db_conn = None

    # Auto-reconnect to ChromaDB if container was started after server boot
    chroma_client = getattr(state, "chroma_client", None)
    if chroma_client is None:
        try:
            chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
            state.chroma_client = chroma_client
            print(f"\033[92m[CHROMADB]\033[0m Successfully auto-connected to ChromaDB at {CHROMA_HOST}:{CHROMA_PORT}")
        except Exception as chroma_err:
            print(f"\033[93m[CHROMADB NOTICE]\033[0m ChromaDB connection failed ({chroma_err}) — continuing with metadata fallback.")
            chroma_client = None

    active_provider = get_llm_provider()
    p_name = str(getattr(active_provider, "provider_name", "unknown") or "unknown")
    p_model = str(getattr(active_provider, "model", getattr(active_provider, "_model", "default")) or "default")
    target_sc_id = str(body.scenario_id or body.scenario or "INC_001").strip()
    sc_id_str = target_sc_id
    region_str = str(getattr(body, "region", "all") or "all")
    print(f"\n\033[96m+------------------------------------------------------------------+\033[0m")
    print(f"\033[96m| STARTING INVESTIGATION: {sc_id_str:<10} | Persona: {persona_str:<8} | Region: {region_str:<5} |\033[0m")
    print(f"\033[96m| Provider: {p_name:<10} | Model: {p_model:<34} |\033[0m")
    print(f"\033[96m+------------------------------------------------------------------+\033[0m")

    try:
        kpi_contract = load_kpi_contract(_CONFIG_DIR / "kpi_contracts.yaml")
        state.kpi_contract = kpi_contract
    except Exception:
        kpi_contract = getattr(state, "kpi_contract", None)

    try:
        sources_config = load_sources(_CONFIG_DIR / "sources.yaml")
        state.sources_config = sources_config
    except Exception:
        sources_config = getattr(state, "sources_config", [])

    try:
        domain_semantics = load_domain_semantics(_CONFIG_DIR / "domain_semantics.yaml")
        state.domain_semantics = domain_semantics
    except Exception:
        domain_semantics = getattr(state, "domain_semantics", {})
            
    try:
        scenarios_config = load_scenarios(_CONFIG_DIR / "scenarios.yaml")
        state.scenarios_config = scenarios_config
    except Exception:
        scenarios_config = getattr(state, "scenarios_config", {"scenarios": []})

    deps = Dependencies(
        db_conn=db_conn,
        chroma_client=chroma_client,
        llm_provider=active_provider,
        kpi_contract=kpi_contract or entitlements_config,
        entitlements_config=entitlements_config,
        sources_config=sources_config,
        domain_semantics=domain_semantics,
        scenarios_config=scenarios_config,
        scenario_id=target_sc_id,
        region=body.region,
    )

    try:
        t_req_start = datetime.datetime.now()
        result = investigate(target_sc_id, persona_str, deps)
        elapsed_sec = (datetime.datetime.now() - t_req_start).total_seconds()
        
        d_abstained = getattr(result.decision, "abstained", False) if result.decision else True
        d_winner = str(getattr(result.decision, "winning_hypothesis_id", "None") or "None")
        tot_tok = 0
        if result.telemetry:
            tot_tok = (getattr(result.telemetry, "llm_tokens_in", 0) or 0) + (getattr(result.telemetry, "llm_tokens_out", 0) or 0)
        d_tokens = str(tot_tok)
        d_calls = str(getattr(result.telemetry, "llm_calls", 0) or 0 if result.telemetry else 0)
        
        status_color = "\033[91mABSTAINED\033[0m" if d_abstained else "\033[92mRESOLVED\033[0m"
        print(f"\033[96m+------------------------------------------------------------------+\033[0m")
        print(f"\033[96m| INVESTIGATION COMPLETE ({elapsed_sec:.2f}s) - Status: {status_color} |\033[0m")
        print(f"\033[96m| Winner: {d_winner:<8} | LLM Calls: {d_calls:<3} | Total Tokens: {d_tokens:<8} |\033[0m")
        print(f"\033[96m+------------------------------------------------------------------+\033[0m\n")
    except ValueError as exc:
        # e.g. unsupported persona surfaced from deep in the pipeline
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        logger.exception(
            "/investigate: pipeline error for scenario=%s persona=%s: %s",
            body.scenario_id, persona_str, exc,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Internal pipeline error: {exc}",
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
# POST /feedback — Structured Feedback with E9 Validation (Round 2)
# ---------------------------------------------------------------------------

_VALID_VERDICTS = frozenset({"CORRECT", "INCORRECT", "PARTIALLY_CORRECT", "UNSURE"})


@app.post("/feedback", response_model=FeedbackResponse)
async def feedback_endpoint(
    body: FeedbackRequest,
    request: Request,
) -> JSONResponse:
    """
    Persist structured analyst feedback on an investigation result.

    Round 2 behavior:
    1. Accept structured verdict (CORRECT/INCORRECT/PARTIALLY_CORRECT/UNSURE)
       or legacy {investigation_id, content} payloads for backward compat.
    2. Verify investigation_id exists and optionally validate scenario_id match.
    3. INSERT structured feedback record into PostgreSQL.
    4. If verdict == CORRECT and investigation was analyst-scoped:
       Call MemoryEngine.mark_validated() to set human_validated=True in ChromaDB.
       First-wins policy: subsequent CORRECT verdicts record feedback but do not
       re-stamp an already-validated precedent.
    5. On DB failure: no partial entry — rollback ensures atomicity.
    """
    state = request.app.state

    # ------------------------------------------------------------------
    # 0. Normalize: legacy compat — if no verdict/scenario_id, treat as
    #    legacy payload where content is the analyst_notes
    # ------------------------------------------------------------------
    verdict_str = (body.verdict or "CORRECT").upper().strip()
    analyst_notes = body.analyst_notes or body.content or None
    scenario_id = body.scenario_id  # may be None for legacy calls

    if verdict_str not in _VALID_VERDICTS:
        return JSONResponse(
            status_code=422,
            content=FeedbackResponse(
                success=False,
                error=f"Invalid verdict: {body.verdict!r}. Valid: {', '.join(sorted(_VALID_VERDICTS))}",
            ).model_dump(),
        )

    # Validate analyst_notes / content length (backward compat)
    if analyst_notes and (len(analyst_notes) < 1 or len(analyst_notes) > 5000):
        return JSONResponse(
            status_code=422,
            content=FeedbackResponse(
                success=False,
                error=f"Analyst notes / content must be 1–5000 chars (got {len(analyst_notes)}).",
            ).model_dump(),
        )

    # ------------------------------------------------------------------
    # 1. Require a live DB connection
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
    # 2. Verify investigation_id exists and resolve scenario_id/persona
    # ------------------------------------------------------------------
    inv_scenario_id: Optional[str] = None
    inv_persona: Optional[str] = None
    try:
        with state.db_conn.cursor() as cur:
            cur.execute(
                "SELECT scenario_id, persona FROM investigations WHERE investigation_id = %s",
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
            content=FeedbackResponse(success=False, error="feedback could not be saved").model_dump(),
        )

    if row is None:
        return JSONResponse(
            status_code=404,
            content=FeedbackResponse(
                success=False,
                error=f"Investigation '{body.investigation_id}' was not found.",
            ).model_dump(),
        )

    inv_scenario_id, inv_persona = row[0], row[1]

    # Use investigation's scenario_id if not provided in request
    if scenario_id is None:
        scenario_id = inv_scenario_id

    # Validate scenario_id match if explicitly provided
    if body.scenario_id and body.scenario_id != inv_scenario_id:
        return JSONResponse(
            status_code=422,
            content=FeedbackResponse(
                success=False,
                error=(
                    f"scenario_id mismatch: request={body.scenario_id!r} "
                    f"but investigation belongs to {inv_scenario_id!r}."
                ),
            ).model_dump(),
        )

    # ------------------------------------------------------------------
    # 3. Insert structured feedback record
    # ------------------------------------------------------------------
    validated_precedent = False
    feedback_id: int = 0

    try:
        with state.db_conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO feedback (
                    investigation_id, scenario_id, persona, verdict,
                    corrected_hypothesis_id, corrected_confidence_state,
                    corrected_action, evidence_grounding_correct,
                    analyst_notes, content, received_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                RETURNING feedback_id
                """,
                (
                    body.investigation_id,
                    scenario_id,
                    body.persona or inv_persona or "analyst",
                    verdict_str,
                    body.corrected_hypothesis_id,
                    body.corrected_confidence_state,
                    body.corrected_action,
                    body.evidence_grounding_correct,
                    analyst_notes,
                    body.content,
                ),
            )
            feedback_id = cur.fetchone()[0]

        # ------------------------------------------------------------------
        # 4. E9 Lifecycle Management — CORRECT, INCORRECT, PARTIALLY_CORRECT
        # ------------------------------------------------------------------
        if inv_persona == "analyst" and scenario_id:
            try:
                from engines.memory import MemoryEngine
                from models import PrecedentValidationState
                memory = MemoryEngine(chroma_client=state.chroma_client, llm_provider=state.llm_provider)

                if verdict_str == "CORRECT":
                    # First-wins check: only validate if not already validated
                    collection = memory._get_or_create_collection()
                    existing = collection.get(ids=[scenario_id], include=["metadatas"])
                    already_validated = False
                    if existing and existing.get("metadatas") and len(existing["metadatas"]) > 0:
                        meta = existing["metadatas"][0] or {}
                        val_state = meta.get("validation_state", "")
                        hv = meta.get("human_validated", False)
                        if isinstance(hv, str):
                            hv = hv.lower() in ("true", "1")
                        already_validated = (val_state == PrecedentValidationState.VALIDATED.value or bool(hv))

                    if not already_validated:
                        ok = memory.mark_validated(
                            scenario_id=scenario_id,
                            validation_feedback_id=feedback_id,
                        )
                        if ok:
                            validated_precedent = True
                            # Update the feedback record with validation linkage
                            with state.db_conn.cursor() as cur:
                                cur.execute(
                                    """
                                    UPDATE feedback
                                    SET validated_precedent = TRUE,
                                        validation_precedent_id = %s
                                    WHERE feedback_id = %s
                                    """,
                                    (scenario_id, feedback_id),
                                )
                            logger.info(
                                "/feedback: E9 precedent %s marked VALIDATED by feedback_id=%d (first-wins)",
                                scenario_id, feedback_id,
                            )
                    else:
                        logger.info(
                            "/feedback: precedent %s already validated; recording feedback_id=%d without re-stamping",
                            scenario_id, feedback_id,
                        )

                elif verdict_str == "INCORRECT":
                    # Mark precedent DISPUTED and exclude from normal retrieval
                    ok = memory.mark_disputed(
                        scenario_id=scenario_id,
                        validation_feedback_id=feedback_id,
                        dispute_notes=analyst_notes,
                    )
                    if ok:
                        logger.info(
                            "/feedback: E9 precedent %s marked DISPUTED (excluded from normal retrieval) by feedback_id=%d",
                            scenario_id, feedback_id,
                        )

                elif verdict_str == "PARTIALLY_CORRECT":
                    # Mark precedent PARTIALLY_VALIDATED (no +0.10 boost)
                    ok = memory.mark_partially_validated(
                        scenario_id=scenario_id,
                        validation_feedback_id=feedback_id,
                        notes=analyst_notes,
                    )
                    if ok:
                        logger.info(
                            "/feedback: E9 precedent %s marked PARTIALLY_VALIDATED by feedback_id=%d",
                            scenario_id, feedback_id,
                        )

            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "/feedback: E9 lifecycle transition failed for %s (feedback_id=%d): %s — feedback still saved",
                    scenario_id, feedback_id, exc,
                )

        state.db_conn.commit()
        logger.info(
            "/feedback: persisted feedback_id=%d verdict=%s for investigation=%s scenario=%s",
            feedback_id, verdict_str, body.investigation_id, scenario_id,
        )
        return JSONResponse(
            status_code=200,
            content=FeedbackResponse(
                success=True,
                feedback_id=feedback_id,
                validated_precedent=validated_precedent,
            ).model_dump(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("/feedback: DB error inserting feedback: %s", exc)
        try:
            state.db_conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return JSONResponse(
            status_code=500,
            content=FeedbackResponse(success=False, error="feedback could not be saved").model_dump(),
        )


# ---------------------------------------------------------------------------
# GET /feedback/metrics — Feedback Quality Metrics
# ---------------------------------------------------------------------------


@app.get("/feedback/metrics")
async def feedback_metrics(request: Request) -> JSONResponse:
    """
    Return aggregate feedback quality metrics across all scenarios.
    """
    state = request.app.state
    if state.db_conn is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        with state.db_conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) AS feedback_count,
                    COUNT(DISTINCT scenario_id) AS scenarios_with_feedback,
                    COUNT(*) FILTER (WHERE verdict = 'CORRECT') AS human_confirmed,
                    COUNT(*) FILTER (WHERE verdict = 'INCORRECT') AS human_rejected,
                    COUNT(*) FILTER (WHERE verdict = 'PARTIALLY_CORRECT') AS partial_corrections,
                    COUNT(*) FILTER (WHERE verdict = 'UNSURE') AS unsure_count,
                    COUNT(*) FILTER (WHERE validated_precedent = TRUE) AS validated_precedents
                FROM feedback
            """)
            row = cur.fetchone()

        feedback_count = row[0] or 0
        decisive = (row[2] or 0) + (row[3] or 0)  # CORRECT + INCORRECT
        agreement_rate = round((row[2] or 0) / decisive, 4) if decisive > 0 else None

        # Total scenarios for coverage calculation
        with state.db_conn.cursor() as cur:
            cur.execute("SELECT COUNT(DISTINCT scenario_id) FROM investigations")
            total_scenarios = (cur.fetchone()[0] or 0)

        coverage = round((row[1] or 0) / total_scenarios, 4) if total_scenarios > 0 else 0.0

        return JSONResponse(content={
            "feedback_count": feedback_count,
            "feedback_coverage": coverage,
            "scenarios_with_feedback": row[1] or 0,
            "total_scenarios": total_scenarios,
            "human_confirmed_count": row[2] or 0,
            "human_rejected_count": row[3] or 0,
            "partial_correction_count": row[4] or 0,
            "unsure_count": row[5] or 0,
            "validated_precedent_count": row[6] or 0,
            "human_agreement_rate": agreement_rate,
        })
    except Exception as exc:  # noqa: BLE001
        logger.error("/feedback/metrics: DB error: %s", exc)
        try:
            state.db_conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(status_code=500, detail="Failed to compute feedback metrics")


# ---------------------------------------------------------------------------
# GET /feedback/{scenario_id} — Retrieve Feedback for a Scenario
# ---------------------------------------------------------------------------


@app.get("/feedback/{scenario_id}")
async def get_feedback_for_scenario(scenario_id: str, request: Request) -> JSONResponse:
    """
    Retrieve all feedback records for a given scenario_id.
    """
    state = request.app.state
    if state.db_conn is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        with state.db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT feedback_id, investigation_id, scenario_id, persona,
                       verdict, corrected_hypothesis_id, corrected_confidence_state,
                       corrected_action, evidence_grounding_correct,
                       analyst_notes, validated_precedent, validation_precedent_id,
                       received_at
                FROM feedback
                WHERE scenario_id = %s
                ORDER BY received_at DESC
                """,
                (scenario_id,),
            )
            rows = cur.fetchall()

        records = []
        for r in rows:
            records.append({
                "feedback_id": r[0],
                "investigation_id": r[1],
                "scenario_id": r[2],
                "persona": r[3],
                "verdict": r[4],
                "corrected_hypothesis_id": r[5],
                "corrected_confidence_state": r[6],
                "corrected_action": r[7],
                "evidence_grounding_correct": r[8],
                "analyst_notes": r[9],
                "validated_precedent": r[10],
                "validation_precedent_id": r[11],
                "received_at": r[12].isoformat() if r[12] else None,
            })

        return JSONResponse(content={
            "scenario_id": scenario_id,
            "count": len(records),
            "records": records,
        })
    except Exception as exc:  # noqa: BLE001
        logger.error("/feedback/%s: DB error: %s", scenario_id, exc)
        try:
            state.db_conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(status_code=500, detail="Failed to retrieve feedback")


# ---------------------------------------------------------------------------
# GET /precedents/{scenario_id} — Precedent Memory Inspection & Audit
# ---------------------------------------------------------------------------


@app.get("/precedents/{scenario_id}")
async def get_precedents_for_scenario(
    scenario_id: str,
    request: Request,
    query_context: str = "",
    include_disputed: bool = False,
    include_suppressed: bool = False,
    persona: str = "analyst",
) -> JSONResponse:
    """
    Retrieve precedents matching scenario_id, with optional audit flags to include
    DISPUTED and SUPPRESSED historical records.
    """
    state = request.app.state
    if state.chroma_client is None:
        return JSONResponse(
            status_code=200,
            content={"scenario_id": scenario_id, "count": 0, "precedents": []},
        )

    try:
        from engines.memory import MemoryEngine
        from security.entitlements import SecurityEngine
        
        entitlements_config = getattr(state, "entitlements_config", None)
        auth_sources = None
        if entitlements_config:
            scope = SecurityEngine(entitlements_config).authorize(persona)
            auth_sources = scope.authorized_sources

        memory = MemoryEngine(chroma_client=state.chroma_client, llm_provider=state.llm_provider)
        precedents = memory.retrieve_precedents(
            scenario_id=scenario_id,
            query_context=query_context,
            include_disputed=include_disputed,
            include_suppressed=include_suppressed,
            authorized_sources=auth_sources,
            persona=persona,
        )

        return JSONResponse(content={
            "scenario_id": scenario_id,
            "count": len(precedents),
            "precedents": _to_json(precedents),
        })
    except Exception as exc:  # noqa: BLE001
        logger.error("/precedents/%s: error: %s", scenario_id, exc)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve precedents: {exc}")


# ---------------------------------------------------------------------------
# GET /evaluation/health — Continuous Evaluation & Drift Monitoring (Round 2)
# ---------------------------------------------------------------------------


@app.get("/evaluation/health")
async def get_system_health(request: Request) -> JSONResponse:
    """
    On-demand Continuous Evaluation & Drift Monitoring health check.

    Computes the 6 core operational health metrics across recent vs baseline
    investigation windows from PostgreSQL and reports system health status:
    HEALTHY, WATCH, DEGRADED, or INSUFFICIENT_DATA.
    """
    state = request.app.state
    if state.db_conn is None:
        raise HTTPException(status_code=503, detail="Database connection unavailable")

    try:
        from evaluation.health import HealthMonitorService
        report = HealthMonitorService.evaluate_health(state.db_conn)
        return JSONResponse(content=report.to_dict())
    except Exception as exc:  # noqa: BLE001
        logger.error("/evaluation/health: evaluation failed: %s", exc)
        try:
            state.db_conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(status_code=500, detail=f"Health evaluation failed: {exc}")



