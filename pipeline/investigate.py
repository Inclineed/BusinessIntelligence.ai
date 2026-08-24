"""
pipeline/investigate.py — Orchestrator

Runs engines E1→E7 in order:
  E1 KPI Store → E2 Signal → E3 Diagnostic →
  [Entitlement boundary] →
  E4 Evidence → E5 Hypothesis → E6 Challenge → E7 Decision

All quantitative truth (KPI values, z-scores, contributions, final scores) comes
exclusively from deterministic engines tagged SQL, STATS, or RULES.
The LLM (E5, E7) only writes hypothesis statements, evidence summaries, persona
narrative, and action explanations.  It never produces numbers.

Requirements: 5.2, 11.1, 11.6, 13.5, 16.7
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from models import (
    AnomalySignal,
    ConfidenceState,
    DimensionContribution,
    Evidence,
    Hypothesis,
    InvestigationResult,
    MethodTag,
    Persona,
    ScoredHypothesis,
    Telemetry,
)
from config.registry import SourceRegistry
from engines.kpi_store import load_kpis
from engines.signal import (
    assert_corroboration,
    build_history_from_kpis,
    detect_signals,
)
from engines.diagnostic import decompose
from engines.evidence import assemble_evidence
from engines.hypothesis import generate_hypotheses
from engines.challenge import challenge, ChallengeThresholds
from engines.decision import decide
from engines.outcome import project_outcome
from engines.memory import MemoryEngine
from security.entitlements import SecurityEngine
from pipeline.telemetry import TelemetryService
from llm.provider import LLMProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported personas
# ---------------------------------------------------------------------------

_SUPPORTED_PERSONAS: frozenset[str] = frozenset({"cfo", "analyst", "manager"})

# ---------------------------------------------------------------------------
# Quantitative-truth pattern: same regex used by hypothesis validation.
# Any digit string not preceded by 'v' (to allow version tokens).
# ---------------------------------------------------------------------------
_QUANTITATIVE_RE = re.compile(r"(?<![vV])\b\d+(\.\d+)?%?\b")


# ---------------------------------------------------------------------------
# Dependencies container
# ---------------------------------------------------------------------------


@dataclass
class Dependencies:
    """
    All external resources required by the orchestrator.

    Callers build one Dependencies instance per request and pass it to
    investigate().  This makes the orchestrator fully testable without touching
    global state.
    """

    # DB connection for SQL queries (psycopg2-compatible)
    db_conn: Any
    # ChromaDB client for unstructured evidence retrieval
    chroma_client: Any
    # LLM provider (Ollama)
    llm_provider: LLMProvider
    # Loaded and validated config dicts / lists
    kpi_contract: dict
    entitlements_config: dict
    sources_config: list
    # Scenario identifier (default matches the INC_001 demonstration scenario)
    scenario_id: str = "INC_001"
    # Anomaly detection window — defaults to last 7 days up to now
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    # Optional override for Challenge Engine thresholds
    challenge_thresholds: Optional[Any] = None
    # Optional region filter for manager persona
    region: Optional[str] = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_persona(persona_str: str) -> Persona:
    """
    Map *persona_str* (case-insensitive) to the Persona enum.

    Raises ValueError with a descriptive message when the persona is not
    among the supported set (Requirement 11.6).
    """
    normalised = persona_str.strip().lower()
    if normalised not in _SUPPORTED_PERSONAS:
        raise ValueError(
            f"Unsupported persona: {persona_str!r}. "
            f"Supported: {', '.join(sorted(_SUPPORTED_PERSONAS))}"
        )
    return Persona(normalised)


def _check_deterministic_engine_output(
    engine_name: str,
    method_tag: MethodTag,
    numeric_fields: dict[str, Any],
    violations: list[str],
) -> None:
    """
    After each deterministic engine, verify that numeric outputs are not tagged
    as LLM-produced (Requirement 13.1).

    Parameters
    ----------
    engine_name   : human-readable engine label for error messages
    method_tag    : the MethodTag declared for the engine's outputs
    numeric_fields: mapping of field_name → value to inspect
    violations    : mutable list; any violation appended here (never raises)
    """
    llm_tags = {MethodTag.LLM, MethodTag.LLM_NARRATIVE, MethodTag.RULES_LLM_NARRATIVE}
    if method_tag in llm_tags:
        for field_name, value in numeric_fields.items():
            if isinstance(value, (int, float)) and not (
                isinstance(value, bool)  # booleans are technically ints
            ):
                msg = (
                    f"[method-separation] engine='{engine_name}' "
                    f"method={method_tag.value!r}: "
                    f"numeric field '{field_name}' = {value!r} produced by an LLM-tagged "
                    "engine — violation of Requirement 13.1/13.2."
                )
                logger.error(msg)
                violations.append(msg)


def _check_hypothesis_no_numbers(
    hypotheses: list[Hypothesis],
    violations: list[str],
) -> None:
    """
    After E5, verify that hypothesis statements contain no numeric values
    (Requirement 8.4 / 13.2).  Violations are logged and recorded but the
    offending hypotheses are NOT removed here — that was already done by
    engines.hypothesis.validate_hypothesis() before they were accepted.

    This is a second-pass audit in the orchestrator.
    """
    for h in hypotheses:
        statement_clean = re.sub(r"\bv\d+(\.\d+)*\b", "", h.statement, flags=re.IGNORECASE)
        if _QUANTITATIVE_RE.search(statement_clean):
            msg = (
                f"[method-separation] hypothesis '{h.hypothesis_id}': "
                f"statement contains a quantitative-truth value after E5 validation — "
                "this hypothesis should have been rejected by E5."
            )
            logger.warning(msg)
            violations.append(msg)


def _primary_signal(
    signals: list[AnomalySignal],
    segmentable_kpi_ids: Optional[set] = None,
) -> Optional[AnomalySignal]:
    """
    Return the anomalous signal to hand to E3 for dimensional decomposition.

    Preference order:
      1. The anomalous signal with the largest |delta_pct| whose KPI HAS
         segmented data available (so E3 can actually decompose it, e.g.
         hourly_conversion has device/channel breakdown).
      2. Otherwise the anomalous signal with the largest |delta_pct|.
      3. Otherwise the first signal of any kind.
    Returns None when the list is empty.
    """
    if not signals:
        return None
    anomalous = [s for s in signals if s.is_anomaly]
    if anomalous:
        if segmentable_kpi_ids:
            seg = [s for s in anomalous if s.kpi_id in segmentable_kpi_ids]
            if seg:
                return max(seg, key=lambda s: abs(s.delta_pct))
        return max(anomalous, key=lambda s: abs(s.delta_pct))
    return signals[0]


def _build_kpi_periods(signals: list[AnomalySignal], kpi_values) -> dict[str, list[str]]:
    """
    Build the kpi_id → list[period] mapping required by assert_corroboration.

    Only aggregate (non-segmented) KPIValue entries are considered.
    """
    from collections import defaultdict
    periods: dict[str, list[str]] = defaultdict(list)
    for kv in kpi_values:
        if not kv.dimension_filters:
            periods[kv.kpi_id].append(kv.period)
    return dict(periods)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def _min_data_quality(db_conn, scenario_id: str, window_start, window_end):
    """
    Return the minimum data_quality_score recorded in the data_quality_log for
    *scenario_id* within [window_start, window_end], or None when there is no
    log for this scenario (the common case). A low value (< 0.80) triggers the
    Signal Engine data-quality guard (Requirement 3.3).
    """
    if db_conn is None:
        return None
    try:
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT MIN(data_quality_score)
                FROM data_quality_log
                WHERE scenario_id = %s AND ts >= %s AND ts <= %s
                """,
                (scenario_id, window_start, window_end),
            )
            row = cur.fetchone()
        if row and row[0] is not None:
            return float(row[0])
    except Exception as exc:  # noqa: BLE001 - table may not exist; that is fine
        logger.debug("_min_data_quality: no data_quality_log usable (%s)", exc)
        try:
            db_conn.rollback()
        except Exception:  # noqa: BLE001
            pass
    return None


def investigate(
    scenario_id: str,
    persona_str: str,
    deps: Dependencies,
) -> InvestigationResult:
    """
    Run the full E1→E7 pipeline and return a structured InvestigationResult.

    Parameters
    ----------
    scenario_id  : Identifies the scenario slice (e.g. "INC_001").
    persona_str  : One of "cfo", "analyst", "manager" (case-insensitive).
    deps         : All external resources (DB, Chroma, LLM, configs).

    Returns
    -------
    InvestigationResult with signals, contributions, evidence, hypotheses,
    scored hypotheses, decision, telemetry, and method_ownership map.

    Raises
    ------
    ValueError   : when *persona_str* is not a supported persona (Req 11.6).

    Requirements: 5.2, 11.1, 11.6, 13.5, 16.7
    """
    # ------------------------------------------------------------------
    # Step 0 — Validate persona (Requirement 11.6)
    # ------------------------------------------------------------------
    persona: Persona = _validate_persona(persona_str)

    # ------------------------------------------------------------------
    # Resolve window
    # ------------------------------------------------------------------
    # Default to the INC_001 data range (Jan 8-16 2024) so the pipeline
    # works without explicit window parameters during the demo.
    # Production deployments would pass explicit window_start/window_end.
    # Per-scenario baseline + observation windows. Baseline is the prior week;
    # the window ENDS at each scenario's incident close so the most-recent
    # aggregated period is the degraded value. Explicit deps windows override.
    _SCENARIO_WINDOWS = {
        "INC_001": (datetime(2024, 1, 8, 0, 0, 0), datetime(2024, 1, 15, 15, 0, 0)),
        "INC_002": (datetime(2024, 1, 8, 0, 0, 0), datetime(2024, 1, 15, 14, 0, 0)),
        "INC_004": (datetime(2024, 1, 8, 0, 0, 0), datetime(2024, 1, 15, 15, 0, 0)),
        "INC_005": (datetime(2024, 1, 8, 0, 0, 0), datetime(2024, 1, 15, 15, 0, 0)),
        "INC_006": (datetime(2024, 1, 8, 0, 0, 0), datetime(2024, 1, 15, 15, 0, 0)),
        "INC_007": (datetime(2024, 1, 8, 0, 0, 0), datetime(2024, 1, 16, 12, 0, 0)),
        "INC_008": (datetime(2024, 2, 2, 0, 0, 0), datetime(2024, 2, 10, 18, 0, 0)),
    }
    _ws_default, _we_default = _SCENARIO_WINDOWS.get(
        scenario_id, (datetime(2024, 1, 8, 0, 0, 0), datetime(2024, 1, 15, 15, 0, 0))
    )
    window_end: datetime   = deps.window_end   if deps.window_end   is not None else _we_default
    window_start: datetime = deps.window_start if deps.window_start is not None else _ws_default

    # ------------------------------------------------------------------
    # Shared infrastructure
    # ------------------------------------------------------------------
    registry = SourceRegistry(deps.sources_config)
    telemetry_svc = TelemetryService()
    method_ownership: dict[str, list[MethodTag]] = {}
    method_violations: list[str] = []

    provider: LLMProvider = deps.llm_provider
    p_name = getattr(provider, "provider_name", getattr(provider, "provider", "ollama"))
    p_model = getattr(provider, "DEFAULT_MODEL", getattr(provider, "model", "qwen3:8b"))
    telemetry_svc.set_provider_info(str(p_name), str(p_model))

    # Accumulators — populated in each stage; fallback to empty on failure
    kpi_values: list = []
    signals: list[AnomalySignal] = []
    contributions: list[DimensionContribution] = []
    evidence_items: list[Evidence] = []
    hypotheses: list[Hypothesis] = []
    scored_hypotheses: list[ScoredHypothesis] = []
    decision = None
    precedents: list[dict] = []

    # ------------------------------------------------------------------
    # Step 0b — Entitlement Authorization Scope (Requirements 5.1, 5.2)
    # ------------------------------------------------------------------
    logger.info("investigate: [Security] Entitlement boundary — persona=%s", persona_str)
    try:
        security_engine = SecurityEngine(deps.entitlements_config)
        scope = security_engine.authorize(persona_str, region=getattr(deps, "region", None))
        if scope.is_empty:
            logger.warning(
                "investigate: authorization scope is empty for persona '%s'; "
                "evidence assembly and precedent retrieval will proceed with no authorized sources.",
                persona_str,
            )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "investigate: entitlement resolution failed: %s — using fail-closed empty scope.",
            exc,
            exc_info=True,
        )
        scope = SecurityEngine.fail_closed().authorize(persona_str, region=getattr(deps, "region", None))

    # ------------------------------------------------------------------
    # E9 (pre-run) — Memory Engine: retrieve precedents [RETRIEVAL]
    # Filtered strictly by persona entitlement authorized_sources (Req 15.3, 5.2)
    # ------------------------------------------------------------------
    logger.info("investigate: [E9-pre] Memory Engine — retrieve precedents for scenario=%s persona=%s", scenario_id, persona_str)
    try:
        memory_engine = MemoryEngine(
            chroma_client=deps.chroma_client,
            llm_provider=provider,
        )
        precedents = memory_engine.retrieve_precedents(
            scenario_id=scenario_id,
            query_context=scenario_id,
            authorized_sources=scope.authorized_sources,
            persona=persona_str,
            region=getattr(deps, "region", None),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "investigate [E9-pre] Memory Engine retrieve failed: %s",
            exc,
            exc_info=True,
        )
        precedents = []

    # ------------------------------------------------------------------
    # E1 — KPI Store [SQL]
    # Requirement: 1.1, 1.4, 2.4, 2.5, 2.6
    # ------------------------------------------------------------------
    logger.info("investigate: [E1] KPI Store — scenario=%s persona=%s", scenario_id, persona_str)
    try:
        with telemetry_svc.measure_engine("kpi_store"):
            kpi_result = load_kpis(
                scenario_id=scenario_id,
                contract=deps.kpi_contract,
                registry=registry,
                persona=persona_str,
                db_conn=deps.db_conn,
                window_start=window_start,
                window_end=window_end,
            )
        kpi_values = kpi_result.kpi_values
        if kpi_result.errors:
            for err in kpi_result.errors:
                logger.warning("investigate [E1] error: %s", err)
        if kpi_result.access_denied:
            logger.info(
                "investigate [E1] access denied for kpi_ids: %s", kpi_result.access_denied
            )
    except Exception as exc:  # noqa: BLE001
        logger.error("investigate [E1] KPI Store failed: %s", exc, exc_info=True)
        kpi_values = []

    method_ownership["kpi_store"] = [MethodTag.SQL]

    # Verify no numeric KPI fields are LLM-tagged (Req 13.1)
    for kv in kpi_values:
        _check_deterministic_engine_output(
            "kpi_store",
            kv.method,
            {"value": kv.value},
            method_violations,
        )

    # ------------------------------------------------------------------
    # E2 — Signal [STATS]
    # Requirement: 3.1–3.6
    # ------------------------------------------------------------------
    logger.info("investigate: [E2] Signal Engine")
    try:
        with telemetry_svc.measure_engine("signal"):
            history = build_history_from_kpis(kpi_values)
            # Apply data-quality score from the data_quality_log (if present for
            # this scenario/window). A stale/gappy source (score < 0.80) makes
            # the Signal Engine raise data_quality_suspect instead of a business
            # anomaly (Req 3.3). Sources without a dq log keep the default 1.0.
            _dq = _min_data_quality(deps.db_conn, scenario_id, window_start, window_end)
            if _dq is not None:
                for _hw in history.values():
                    _hw.data_quality_score = _dq
                logger.info(
                    "investigate [E2]: applied data_quality_score=%.3f from data_quality_log "
                    "for scenario=%s window", _dq, scenario_id,
                )
            signals = detect_signals(kpi_values, history)
            kpi_periods = _build_kpi_periods(signals, kpi_values)
            signals = assert_corroboration(signals, kpi_periods)
    except Exception as exc:  # noqa: BLE001
        logger.error("investigate [E2] Signal Engine failed: %s", exc, exc_info=True)
        signals = []

    method_ownership["signal"] = [MethodTag.STATS]

    # Verify signal numeric fields are not LLM-tagged (Req 13.1)
    for sig in signals:
        _check_deterministic_engine_output(
            "signal",
            sig.method,
            {"z_score": sig.z_score, "delta_pct": sig.delta_pct},
            method_violations,
        )

    # ------------------------------------------------------------------
    # E3 — Diagnostic [SQL+STATS]
    # Requirement: 4.1–4.6
    # ------------------------------------------------------------------
    logger.info("investigate: [E3] Diagnostic Engine")
    try:
        # KPIs that have segmented (dimension_filters) rows available so E3
        # can decompose them (e.g. hourly_conversion by device/channel).
        _segmentable = {kv.kpi_id for kv in kpi_values if kv.dimension_filters}
        primary_sig = _primary_signal(signals, segmentable_kpi_ids=_segmentable)
        with telemetry_svc.measure_engine("diagnostic"):
            if primary_sig is not None:
                diagnostic_result = decompose(
                    kpi_values=kpi_values,
                    signal=primary_sig,
                    db_conn=deps.db_conn,
                    scenario_id=scenario_id,
                    window_start=window_start,
                    window_end=window_end,
                )
                contributions = diagnostic_result.contributions
                if diagnostic_result.errors:
                    for err in diagnostic_result.errors:
                        logger.warning("investigate [E3] error: %s", err)
            else:
                logger.info(
                    "investigate [E3]: no anomalous signal to decompose (expected for "
                    "sparse-history / data-quality / no-incident scenarios)."
                )
                contributions = []
    except Exception as exc:  # noqa: BLE001
        logger.error("investigate [E3] Diagnostic Engine failed: %s", exc, exc_info=True)
        contributions = []

    method_ownership["diagnostic"] = [MethodTag.SQL, MethodTag.STATS]

    # Verify contribution numeric fields are not LLM-tagged (Req 13.1)
    for contrib in contributions:
        _check_deterministic_engine_output(
            "diagnostic",
            contrib.method,
            {
                "contribution_pct": contrib.contribution_pct,
                "segment_delta_pct": contrib.segment_delta_pct,
            },
            method_violations,
        )

    # ------------------------------------------------------------------
    # E4 — Evidence [SQL+RETRIEVAL]
    # Requirement: 6.1–6.7, 7.3–7.5
    # ------------------------------------------------------------------
    logger.info("investigate: [E4] Evidence Engine (constrained by authorized_sources=%s before assembly)", scope.authorized_sources)
    try:
        with telemetry_svc.measure_engine("evidence"):
            evidence_result = assemble_evidence(
                authorized_sources=scope.authorized_sources,
                signals=signals,
                registry=registry,
                db_conn=deps.db_conn,
                chroma_client=deps.chroma_client,
                scenario_id=scenario_id,
                anomaly_window_start=window_start,
                anomaly_window_end=window_end,
                provider=provider,
                scope=scope,
                allowed_collections=frozenset({f"evidence_{scenario_id}"}),
            )
        evidence_items = evidence_result.evidence
        if evidence_result.reliability_notes:
            for note in evidence_result.reliability_notes:
                logger.debug("investigate [E4] reliability note: %s", note)
    except Exception as exc:  # noqa: BLE001
        logger.error("investigate [E4] Evidence Engine failed: %s", exc, exc_info=True)
        evidence_items = []

    method_ownership["evidence"] = [MethodTag.SQL, MethodTag.RETRIEVAL]

    # Requirement 5.4 — assert every evidence item is authorized before E5
    unauthorized_items = [
        e for e in evidence_items
        if not scope.is_empty and e.source_id not in scope.authorized_sources
    ]
    if unauthorized_items:
        for item in unauthorized_items:
            msg = (
                f"[security] evidence '{item.evidence_id}' source '{item.source_id}' "
                f"not in authorized scope for persona '{persona_str}' — dropped before LLM."
            )
            logger.error(msg)
            method_violations.append(msg)
        evidence_items = [
            e for e in evidence_items if e not in unauthorized_items
        ]

    # ------------------------------------------------------------------
    # E5 — Hypothesis [LLM] (no numbers)
    # Requirement: 8.1–8.7
    # ------------------------------------------------------------------
    logger.info("investigate: [E5] Hypothesis Engine")

    # ------------------------------------------------------------------
    # Guard — hypothesis generation requires a CONFIRMED anomaly.
    #
    # When E2's sparse-history (Req 3.2) or data-quality (Req 3.3) guard
    # suppressed the anomaly, there is no established event to explain.
    # Calling E5 anyway hands the model a prompt that literally invites
    # speculation ("No anomalies currently flagged; investigate potential
    # leading indicators"), which manufactures a cause for something that
    # never happened — the exact failure mode this system exists to prevent.
    #
    # Suppressing here keeps the pipeline aligned with the documented design
    # intent for INC_003/INC_004 ("No hypotheses should be generated",
    # etl/generate_scenarios.py), with data/ground_truth.json
    # (expected_winning_hypothesis: null), and with the evaluator's
    # hypothesis-suppression dimension. E6 then scores an empty set and E7
    # abstains via its existing empty-hypothesis path.
    # ------------------------------------------------------------------
    _anomalous_signals = [s for s in signals if s.is_anomaly]
    if not _anomalous_signals:
        if any(getattr(s, "data_quality_suspect", False) for s in signals):
            _suppression = "data-quality guard (Req 3.3)"
        elif any(getattr(s, "sparse_history", False) for s in signals):
            _suppression = "sparse-history guard (Req 3.2)"
        else:
            _suppression = "no KPI exceeded the anomaly thresholds (Req 3.5)"
        logger.info(
            "investigate [E5]: suppressed — no confirmed anomaly: %s. "
            "Skipping hypothesis generation by design; the pipeline will abstain.",
            _suppression,
        )
        hypotheses = []
    else:
        try:
            # Pass the LIVE telemetry reference (not a deepcopy) so that
            # record_llm_call() inside the engine accumulates into the service's
            # own state and shows up in the final get_telemetry() snapshot.
            with telemetry_svc.measure_engine("hypothesis"):
                hyp_result = generate_hypotheses(
                    signals=signals,
                    contributions=contributions,
                    evidence=evidence_items,
                    contract=deps.kpi_contract,
                    provider=provider,
                    telemetry=telemetry_svc.live_telemetry,
                )
            hypotheses = hyp_result.hypotheses
            if hyp_result.rejected_count > 0:
                logger.warning(
                    "investigate [E5] %d hypothesis(es) rejected: %s",
                    hyp_result.rejected_count,
                    hyp_result.rejection_reasons,
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("investigate [E5] Hypothesis Engine failed: %s", exc, exc_info=True)
            hypotheses = []

    method_ownership["hypothesis"] = [MethodTag.LLM]

    # Post-E5 audit: verify hypothesis statements contain no numbers (Req 13.2)
    _check_hypothesis_no_numbers(hypotheses, method_violations)

    # ------------------------------------------------------------------
    # E6 — Challenge [RULES + LLM_NARRATIVE]
    # Requirement: 9.1–9.8
    # ------------------------------------------------------------------
    logger.info("investigate: [E6] Challenge Engine")
    try:
        evidence_by_id: dict[str, Evidence] = {e.evidence_id: e for e in evidence_items}
        thresholds = deps.challenge_thresholds
        if thresholds is None:
            thresholds = ChallengeThresholds()

        with telemetry_svc.measure_engine("challenge"):
            challenge_result = challenge(
                hypotheses=hypotheses,
                evidence_by_id=evidence_by_id,
                signals=signals,
                contributions=contributions,
                thresholds=thresholds,
                provider=provider,
                telemetry=telemetry_svc.live_telemetry,
            )
        scored_hypotheses = challenge_result.scored_hypotheses
    except Exception as exc:  # noqa: BLE001
        logger.error("investigate [E6] Challenge Engine failed: %s", exc, exc_info=True)
        scored_hypotheses = []
        # Build a synthetic abstain result so E7 can still run
        from engines.challenge import ChallengeResult
        challenge_result = ChallengeResult(
            scored_hypotheses=[],
            winning_hypothesis_id=None,
            overall_confidence=ConfidenceState.ABSTAIN,
            abstained=True,
        )

    method_ownership["challenge"] = [MethodTag.RULES, MethodTag.LLM_NARRATIVE]

    # Verify scored hypothesis numeric fields are not LLM-tagged (Req 13.1)
    for sh in scored_hypotheses:
        _check_deterministic_engine_output(
            "challenge",
            sh.method,
            {"final_score": sh.final_score, "support_score": sh.support_score},
            method_violations,
        )

    # ------------------------------------------------------------------
    # E7 — Decision [LLM]
    # Requirement: 10.1–10.6
    # ------------------------------------------------------------------
    logger.info(
        "investigate: [E7] Decision Engine — confidence=%s abstained=%s",
        challenge_result.overall_confidence.value,
        challenge_result.abstained,
    )
    try:
        evidence_summaries = [e.summary for e in evidence_items[:5]]
        with telemetry_svc.measure_engine("decision"):
            decision = decide(
                challenge_result=challenge_result,
                persona=persona,
                provider=provider,
                evidence_summaries=evidence_summaries,
                telemetry=telemetry_svc.live_telemetry,
            )
    except Exception as exc:  # noqa: BLE001
        logger.error("investigate [E7] Decision Engine failed: %s", exc, exc_info=True)
        # Fallback to an abstained Decision so InvestigationResult is always complete
        from models import Decision
        decision = Decision(
            abstained=True,
            recommended_action=None,
            verification_metric="review_kpi_primary_metric_recovery",
            winning_hypothesis_id=challenge_result.winning_hypothesis_id,
            persona_narrative=(
                "Decision engine encountered an unexpected error. "
                "Please review the evidence and scored hypotheses manually."
            ),
            abstention_reason="provider_unavailable",
            method=MethodTag.LLM,
        )

    method_ownership["decision"] = [MethodTag.LLM]

    # ------------------------------------------------------------------
    # Log any method-separation violations (Req 13.1, 13.2)
    # ------------------------------------------------------------------
    if method_violations:
        logger.warning(
            "investigate: %d method-separation violation(s) recorded.",
            len(method_violations),
        )

    # ------------------------------------------------------------------
    # E8 — Outcome Engine [SIMULATED]
    # Requirement: 14.1–14.3, 14.5
    # ------------------------------------------------------------------
    logger.info("investigate: [E8] Outcome Engine")
    outcome = None
    try:
        if decision is not None:
            outcome = project_outcome(decision)
    except Exception as exc:  # noqa: BLE001
        logger.error("investigate [E8] Outcome Engine failed: %s", exc, exc_info=True)
        outcome = None

    method_ownership["outcome"] = [MethodTag.SIMULATED]

    # ------------------------------------------------------------------
    # Build InvestigationResult (Requirement 13.5)
    # ------------------------------------------------------------------
    logger.info(
        "investigate: pipeline complete — scenario=%s persona=%s "
        "signals=%d contributions=%d evidence=%d hypotheses=%d "
        "scored=%d decision_abstained=%s",
        scenario_id,
        persona_str,
        len(signals),
        len(contributions),
        len(evidence_items),
        len(hypotheses),
        len(scored_hypotheses),
        decision.abstained if decision else True,
    )

    investigation_result = InvestigationResult(
        scenario_id=scenario_id,
        persona=persona,
        signals=signals,
        contributions=contributions,
        evidence=evidence_items,
        hypotheses=hypotheses,
        scored=scored_hypotheses,
        decision=decision,
        outcome=outcome,
        precedents=precedents,
        telemetry=telemetry_svc.get_telemetry(),  # interim snapshot; updated below
        method_ownership=method_ownership,
    )

    # ------------------------------------------------------------------
    # E9 (post-run) — Memory Engine: store precedent [RETRIEVAL+LLM]
    # Requirement: 15.1, 15.2
    # ------------------------------------------------------------------
    logger.info("investigate: [E9-post] Memory Engine — store precedent for scenario=%s", scenario_id)
    try:
        memory_engine_store = MemoryEngine(
            chroma_client=deps.chroma_client,
            llm_provider=provider,
        )
        with telemetry_svc.measure_engine("memory"):
            stored = memory_engine_store.store_precedent(investigation_result)
        if not stored:
            logger.warning(
                "investigate [E9-post] store_precedent returned False for scenario=%s "
                "(result queued for retry or retries exhausted).",
                scenario_id,
            )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "investigate [E9-post] Memory Engine store failed: %s",
            exc,
            exc_info=True,
        )

    method_ownership["memory"] = [MethodTag.RETRIEVAL, MethodTag.LLM]

    # ------------------------------------------------------------------
    # Telemetry snapshot — taken AFTER all engines (incl. E8/E9) complete
    # so llm_calls, tokens_in, tokens_out reflect every LLM call made.
    # (Requirement 16.7)
    # ------------------------------------------------------------------
    investigation_result.telemetry = telemetry_svc.get_telemetry()

    return investigation_result
