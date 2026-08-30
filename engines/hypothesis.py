"""
engines/hypothesis.py — Engine E5: Hypothesis Engine [LLM]

Generates candidate hypotheses grounded in the KPI contract's driver space.
The LLM outputs: statement (NO numbers), supporting_evidence_ids,
contradictory_evidence_ids, and reasoning.

Numbers (confidence, scores) are NEVER produced here — that is Engine E6's job.

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, NamedTuple, Optional

from models import (
    AnomalySignal,
    DimensionContribution,
    Evidence,
    EvidenceCitation,
    Hypothesis,
    MethodTag,
    Telemetry,
)
from llm.provider import LLMProvider
from llm.telemetry_wrapper import record_llm_call

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

class HypothesisGenerationResult(NamedTuple):
    """
    Return type for generate_hypotheses().

    hypotheses        : validated Hypothesis objects ready for Engine E6
    rejected_count    : number of hypotheses rejected by validation guards
    rejection_reasons : one string per rejected hypothesis (Reqs 8.3, 8.4, 8.5)
    llm_response_text : raw LLM output for debugging / audit
    """

    hypotheses: list[Hypothesis]
    rejected_count: int
    rejection_reasons: list[str]
    llm_response_text: str


# ---------------------------------------------------------------------------
# Prompt construction helpers
# ---------------------------------------------------------------------------

def _build_system_prompt(drivers: list[str]) -> str:
    """
    System prompt grounding the LLM in the KPI contract's driver space and causal discrimination principles.
    Explicitly instructs the model NOT to produce any quantitative values and to enforce causal hierarchy.
    """
    driver_list = ", ".join(drivers) if drivers else "payment_success_rate, checkout_code_quality, inventory_availability, footfall"
    return (
        "You are a business intelligence analyst. Propose up to 3 competing, falsifiable hypotheses explaining an observed KPI movement using ONLY provided evidence.\n\n"
        "CRITICAL RULES:\n"
        "1. NO numbers, percentages, scores, counts, ratios, or probabilities in statement or reasoning.\n"
        "2. Reference ONLY provided evidence IDs in citations. Never invent IDs.\n"
        "3. Distinguish canonical causal layers:\n"
        "   - ROOT_CAUSE: initiating cause (INTERNAL_RELEASE, EXTERNAL_PROVIDER, MACRO_EXTERNAL, RESOURCE_EXHAUSTION, INVENTORY_SHORTAGE, UNKNOWN).\n"
        "   - AFFECTED_SUBSYSTEM: technical pathway (payment_gateway, inventory_system, marketing_channel, device_client, auth_service).\n"
        "   - PROXIMAL_MECHANISM: immediate mechanism (latency_spike_and_timeout, connection_pool_exhaustion, stockout, crash_loop).\n"
        "   - SYMPTOM_KPIS: downstream observed KPIs.\n"
        "4. Do NOT confuse affected subsystem with root cause: payment gateway telemetry proves gateway degradation, not automatically an external provider or deployment. If upstream cause is unobserved, set root_cause_type='UNKNOWN'.\n"
        "5. Do NOT duplicate hypotheses on the same causal chain.\n"
        "6. In citations, mark role as 'supports', 'contradicts', or 'neutral'. Mark downstream symptoms as 'neutral' unless discriminating.\n"
        "7. Stamp every hypothesis with method tag LLM. Output valid JSON only.\n"
        f"Domain KPI drivers: {driver_list}."
    )


def _build_user_prompt(
    signals: list[AnomalySignal],
    contributions: list[DimensionContribution],
    evidence: list[Evidence],
    drivers: list[str],
    domain_semantics: dict,
) -> str:
    """
    User prompt containing:
    - anomaly summary (KPI IDs, direction — no raw numbers)
    - top-3 dimensional contributions (segments only)
    - evidence IDs and summaries
    - exact output schema
    """
    anomaly_lines: list[str] = []
    for sig in signals:
        if sig.is_anomaly:
            direction = "decreased" if sig.delta_pct < 0 else "increased"
            anomaly_lines.append(f"  - KPI '{sig.kpi_id}' has {direction} significantly")
    if not anomaly_lines:
        anomaly_lines.append("  - No anomalies currently flagged.")
    anomaly_summary = "Anomalous KPIs:\n" + "\n".join(anomaly_lines)

    sorted_contribs = sorted(contributions, key=lambda c: abs(c.contribution_pct), reverse=True)[:3]
    contrib_lines = [f"  - Dimension '{c.dimension}', segment '{c.segment}': dominant contributor" for c in sorted_contribs]
    contrib_summary = "Top dimensional contributors:\n" + ("\n".join(contrib_lines) if contrib_lines else "  - None")

    sorted_evidence = sorted(evidence, key=lambda e: (e.source_reliability * getattr(e, "confidence", 0.9)), reverse=True)[:10]
    evidence_lines = [f"  - ID: {ev.evidence_id} | Source: {ev.source_id} | Summary: {ev.summary}" for ev in sorted_evidence]
    evidence_block = "Available evidence (use ONLY these IDs):\n" + ("\n".join(evidence_lines) if evidence_lines else "  - None")

    valid_mechanisms = [m for m in domain_semantics.get("mechanisms", {}).keys() if m != "default"]
    valid_mechanisms_str = ", ".join(f'"{m}"' for m in valid_mechanisms) + ', or "UNKNOWN"'
    valid_subsystems = [s for s in domain_semantics.get("subsystems", {}).keys() if s != "default"]
    valid_subsystems_str = ", ".join(f'"{s}"' for s in valid_subsystems) + ', or "UNKNOWN"'
    valid_archetypes = list(domain_semantics.get("root_cause_archetypes", {}).keys())
    valid_archetypes_str = ", ".join(f'"{a}"' for a in valid_archetypes)

    citation_rules = (
        "CITATION RULES:\n"
        "- evidence_id: exact ID from list above.\n"
        "- quoted_summary: copy evidence summary verbatim.\n"
        "- role: 'supports' (specifically corroborates this mechanism), 'contradicts', or 'neutral'.\n"
        "- relevance_explanation: one sentence connecting evidence to hypothesis."
    )

    output_instructions = (
        f"Output valid JSON schema:\n"
        "{\n"
        '  "hypotheses": [\n'
        "    {\n"
        '      "hypothesis_id": "H1",\n'
        f'      "mechanism_tag": "<one of: {valid_mechanisms_str}>",\n'
        f'      "root_cause_type": "<one of: {valid_archetypes_str}>",\n'
        f'      "affected_subsystem": "<one of: {valid_subsystems_str}>",\n'
        '      "proximal_mechanism": "<e.g. latency_spike_and_timeout, connection_pool_exhaustion, stockout, UNKNOWN>",\n'
        '      "symptom_kpis": ["<anomalous KPI 1>"],\n'
        '      "statement": "<qualitative causal statement, NO numbers>",\n'
        '      "citations": [\n'
        '        {"evidence_id": "<id1>", "quoted_summary": "<exact summary>", "role": "supports", "relevance_explanation": "<exp>"},\n'
        '        {"evidence_id": "<id2>", "quoted_summary": "<exact summary>", "role": "supports", "relevance_explanation": "<exp>"}\n'
        "      ],\n"
        '      "reasoning": "<qualitative narrative prose, NO numbers, NO evidence IDs>"\n'
        "    }\n"
        "  ]\n"
        "}"
    )

    return "\n\n".join([anomaly_summary, contrib_summary, evidence_block, citation_rules, output_instructions])


# ---------------------------------------------------------------------------
# Internal JSON parser
# ---------------------------------------------------------------------------

def _parse_llm_hypotheses(response_text: str) -> list[dict]:
    """
    Parse the LLM response text into a list of raw hypothesis dicts.

    Strategy:
    1. Try parsing the whole response as JSON, looking for a `hypotheses` array.
    2. Try to extract a JSON object from the text (handles preamble/postamble).
    3. Try to find individual hypothesis-like JSON objects with regex.
    4. Return [] if all strategies fail; caller handles gracefully.
    """
    # Strategy 1: direct JSON parse
    try:
        data = json.loads(response_text.strip())
        if isinstance(data, dict) and "hypotheses" in data:
            hyps = data["hypotheses"]
            if isinstance(hyps, list):
                return hyps
        # Maybe the model returned a list directly
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 1.5: extract from markdown json code block if present
    fence_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.DOTALL)
    for m in fence_pattern.finditer(response_text):
        try:
            data = json.loads(m.group(1).strip())
            if isinstance(data, dict) and "hypotheses" in data:
                hyps = data["hypotheses"]
                if isinstance(hyps, list):
                    return hyps
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, ValueError):
            pass

    # Strategy 2: find outermost JSON object containing "hypotheses"
    start_idx = response_text.find("{")
    end_idx = response_text.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        try:
            data = json.loads(response_text[start_idx:end_idx + 1])
            if isinstance(data, dict) and "hypotheses" in data:
                hyps = data["hypotheses"]
                if isinstance(hyps, list):
                    return hyps
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, ValueError):
            pass

    # Strategy 2.5: Brace matching scan starting from first '{'
    if start_idx != -1:
        depth = 0
        in_string = False
        escape = False
        for i in range(start_idx, len(response_text)):
            ch = response_text[i]
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if not in_string:
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            candidate_str = response_text[start_idx:i + 1]
                            data = json.loads(candidate_str)
                            if isinstance(data, dict) and "hypotheses" in data:
                                hyps = data["hypotheses"]
                                if isinstance(hyps, list):
                                    return hyps
                        except (json.JSONDecodeError, ValueError):
                            pass

    # Strategy 2.8: Clean trailing commas and try parsing
    clean_text = re.sub(r',\s*([}\]])', r'\1', response_text)
    try:
        data = json.loads(clean_text)
        if isinstance(data, dict) and "hypotheses" in data and isinstance(data["hypotheses"], list):
            return data["hypotheses"]
        if isinstance(data, list):
            return data
    except Exception:
        pass

    # Strategy 3: find individual hypothesis objects with nested support
    candidates: list[dict] = []
    for match in re.finditer(r'"hypothesis_id"\s*:', response_text):
        pos = match.start()
        obj_start = response_text.rfind('{', 0, pos)
        if obj_start != -1:
            depth = 0
            in_string = False
            escape = False
            for j in range(obj_start, len(response_text)):
                ch = response_text[j]
                if escape:
                    escape = False
                    continue
                if ch == '\\':
                    escape = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if not in_string:
                    if ch == '{':
                        depth += 1
                    elif ch == '}':
                        depth -= 1
                        if depth == 0:
                            raw_chunk = response_text[obj_start:j + 1]
                            clean_chunk = re.sub(r',\s*([}\]])', r'\1', raw_chunk)
                            try:
                                obj = json.loads(clean_chunk)
                                if isinstance(obj, dict) and "hypothesis_id" in obj:
                                    if obj not in candidates:
                                        candidates.append(obj)
                            except (json.JSONDecodeError, ValueError):
                                pass
                            break
    if candidates:
        return candidates

    # Strategy 4: Relaxed Regex Field Extractor for fallback recovery
    recovered: list[dict] = []
    hyp_blocks = re.split(r'(?=\bH[1-9]\b|"(?:hypothesis_id|statement)"\s*:\s*"H[1-9]")', response_text)
    for block in hyp_blocks:
        id_match = re.search(r'"?hypothesis_id"?\s*:\s*"?(H[1-9])"?', block, re.IGNORECASE)
        stmt_match = re.search(r'"?statement"?\s*:\s*"([^"]+)"', block)
        if not id_match and not stmt_match:
            continue
        h_id = id_match.group(1).upper() if id_match else f"H{len(recovered)+1}"
        stmt = stmt_match.group(1) if stmt_match else "Causal hypothesis under evaluation"
        # Extract mechanism_tag
        mech_match = re.search(r'"?mechanism_tag"?\s*:\s*"([^"]+)"', block)
        m_tag = mech_match.group(1) if mech_match else "UNKNOWN"
        
        # Extract citations
        cits = []
        for cit_match in re.finditer(r'"?evidence_id"?\s*:\s*"([a-f0-9]{8,16}|deploy_[^"]+|release_[^"]+|payment_[^"]+)"', block, re.IGNORECASE):
            cits.append({
                "evidence_id": cit_match.group(1),
                "quoted_summary": "Extracted supporting evidence",
                "role": "supports",
                "relevance_explanation": "Supporting evidence link",
            })
        
        # Extract reasoning
        rsn_match = re.search(r'"?reasoning"?\s*:\s*"([^"]+)"', block)
        rsn = rsn_match.group(1) if rsn_match else "Evaluated causal explanation."
        
        recovered.append({
            "hypothesis_id": h_id,
            "mechanism_tag": m_tag,
            "statement": stmt,
            "citations": cits,
            "reasoning": rsn,
        })
    if recovered:
        return recovered

    logger.warning(
        "_parse_llm_hypotheses: all parsing strategies failed for response of "
        "%d chars. Returning empty list.",
        len(response_text),
    )
    return []


# ---------------------------------------------------------------------------
# Validation guard (Task 8.2)
# ---------------------------------------------------------------------------

# Regex that matches number tokens that constitute quantitative-truth values:
#   - integers: 42
#   - decimals: 3.14
#   - percentages: 10%, 0.5%
# Uses word-boundary anchors so sub-word contexts (e.g., H1, v4.3) are not caught.
# "v4.3" is matched separately: we exclude version-like tokens (v\d) explicitly.
_QUANTITATIVE_RE = re.compile(r'(?<![vV])\b\d+(\.\d+)?%?\b')


def validate_hypothesis(
    raw_hyp: dict,
    valid_evidence_ids: frozenset[str],
    domain_semantics: Optional[dict] = None,
) -> tuple[bool, str]:
    domain_semantics = domain_semantics or {}
    """
    Validate a raw hypothesis dict produced by the LLM.

    Returns (is_valid, rejection_reason).

    Rejects when (Requirements 8.3, 8.4, 8.5 & Citation Security Boundary):
    (a) Any evidence ID in citations, supporting, or contradictory lists is not in
        valid_evidence_ids  → "hallucinated evidence ID: {id}"
    (b) The statement contains a quantitative-truth value  → "statement contains quantitative-truth value"
    (c) statement length < 1 or > 2000 chars
    (d) reasoning length < 1 or > 5000 chars
    (e) citations is missing, not a list, or contains malformed citation objects / invalid roles
    (f) reasoning contains evidence ID references
    (g) zero citations when evidence is available
    """
    statement = raw_hyp.get("statement", "")
    reasoning = raw_hyp.get("reasoning", "")
    supporting = raw_hyp.get("supporting_evidence_ids", [])
    contradictory = raw_hyp.get("contradictory_evidence_ids", [])
    citations_raw = raw_hyp.get("citations", None)

    # (c) Statement length
    if not isinstance(statement, str) or len(statement) < 1:
        return False, "statement is empty or not a string"
    if len(statement) > 2000:
        return False, f"statement length {len(statement)} exceeds 2000 characters"

    # (d) Reasoning length
    if not isinstance(reasoning, str) or len(reasoning) < 1:
        return False, "reasoning is empty or not a string"
    if len(reasoning) > 5000:
        return False, f"reasoning length {len(reasoning)} exceeds 5000 characters"

    # (e) Citations structure and malformed object validation
    parsed_citations_count = 0
    if citations_raw is not None:
        if not isinstance(citations_raw, list):
            return False, "citations field is present but not a list"

        for idx, item in enumerate(citations_raw):
            if not isinstance(item, dict):
                return False, f"citation item at index {idx} is not a dict"

            eid = item.get("evidence_id")
            if not isinstance(eid, str) or not eid.strip():
                return False, f"citation at index {idx} missing valid evidence_id string"

            summary_quote = item.get("quoted_summary")
            if summary_quote is not None and not isinstance(summary_quote, str):
                return False, f"citation '{eid}' quoted_summary must be a string if provided"

            role = item.get("role")
            if role not in ("supports", "contradicts", "neutral"):
                return False, f"citation '{eid}' has invalid role {role!r} (must be supports, contradicts, or neutral)"

            parsed_citations_count += 1
    else:
        parsed_citations_count = len(supporting) + len(contradictory)

    # (g) Zero citations policy: when evidence is available, hypothesis must cite at least one item
    if valid_evidence_ids and parsed_citations_count == 0:
        return False, "hypothesis contains zero citations when evidence is available"

    # (f) Reasoning evidence ID prohibition check
    if isinstance(reasoning, str):
        for eid in valid_evidence_ids:
            pattern = r'\b' + re.escape(eid) + r'\b'
            if re.search(pattern, reasoning, re.IGNORECASE):
                return False, f"reasoning contains prohibited evidence ID reference: '{eid}'"

    # (a) Hallucinated evidence IDs
    all_referenced: list[str] = list(supporting) + list(contradictory)
    if isinstance(citations_raw, list):
        for c in citations_raw:
            if isinstance(c, dict) and "evidence_id" in c:
                all_referenced.append(c["evidence_id"])

    for eid in all_referenced:
        if not isinstance(eid, str):
            return False, f"evidence ID {eid!r} is not a string"
        if eid not in valid_evidence_ids:
            return False, f"hallucinated evidence ID: {eid!r}"

    # (b) Quantitative-truth values in the statement
    # We allow version strings like "v4.3" by stripping them first
    # to avoid false positives when the LLM mentions a deployment version.
    # Strip version-like tokens (e.g., v4.3, v3) before checking
    statement_for_check = re.sub(r'\bv\d+(\.\d+)*\b', '', statement, flags=re.IGNORECASE)
    if _QUANTITATIVE_RE.search(statement_for_check):
        return False, "statement contains quantitative-truth value"

    # (h) Mechanism tag validation
    mechanism_tag = raw_hyp.get("mechanism_tag")
    if not mechanism_tag:
        return False, "missing mechanism_tag"
    if not isinstance(mechanism_tag, str):
        return False, "mechanism_tag is not a string"
    valid_mechanisms = [m for m in domain_semantics.get("mechanisms", {}).keys() if m != "default"]
    if mechanism_tag != "UNKNOWN" and mechanism_tag not in valid_mechanisms:
        return False, f"invalid mechanism_tag: {mechanism_tag!r}"

    return True, ""


# ---------------------------------------------------------------------------
# Main public function (Task 8.1)
# ---------------------------------------------------------------------------

def generate_hypotheses(
    signals: list[AnomalySignal],
    contributions: list[DimensionContribution],
    evidence: list[Evidence],
    contract: Any,
    domain_semantics: dict,
    provider: LLMProvider,
    telemetry: Optional[Telemetry] = None,
) -> HypothesisGenerationResult:
    """
    Generate candidate hypotheses for observed KPI anomalies (Engine E5).

    Pre-condition: *evidence* has already been entitlement-filtered by the
    Security_Engine before this function is called.  This function never
    widens or re-filters the evidence set (Requirement 8.7).

    Parameters
    ----------
    signals       : AnomalySignal list from Engine E2.
    contributions : DimensionContribution list from Engine E3.
    evidence      : Entitlement-filtered Evidence list from Engine E4.
    contract      : KPI contract object (or dict) that exposes a `drivers`
                    attribute/key so the prompt is grounded in domain drivers.
    provider      : LLMProvider for generating hypotheses.
    telemetry     : Optional Telemetry instance; updated in-place when provided.

    Returns
    -------
    HypothesisGenerationResult with:
    - validated Hypothesis objects (method=LLM, no numbers)
    - rejected_count and rejection_reasons for the validation guards
    - raw LLM response text for audit / debugging

    Requirements: 8.1, 8.2, 8.6, 8.7
    """
    # ------------------------------------------------------------------
    # Extract drivers from the contract for prompt grounding
    # ------------------------------------------------------------------
    drivers: list[str] = []
    if contract is not None:
        if hasattr(contract, "drivers"):
            raw_drivers = contract.drivers
        elif isinstance(contract, dict):
            raw_drivers = contract.get("drivers", [])
        else:
            raw_drivers = []

        if isinstance(raw_drivers, list):
            drivers = [str(d) for d in raw_drivers]
        elif isinstance(raw_drivers, dict):
            # Some contract shapes nest drivers per KPI; flatten them
            seen: set[str] = set()
            for kpi_drivers in raw_drivers.values():
                if isinstance(kpi_drivers, list):
                    for d in kpi_drivers:
                        if d not in seen:
                            drivers.append(str(d))
                            seen.add(d)

    # Fallback: use domain_semantics drivers if contract provides none
    if not drivers:
        drivers = domain_semantics.get("hypothesis_generation", {}).get("drivers", [])
    if not drivers:
        drivers = ["technical degradation", "external factors", "inventory disruptions"]

    # ------------------------------------------------------------------
    # Build a set of valid evidence IDs for validation guards
    # ------------------------------------------------------------------
    valid_evidence_ids: frozenset[str] = frozenset(e.evidence_id for e in evidence)
    evidence_by_id: dict[str, Evidence] = {e.evidence_id: e for e in evidence}

    # ------------------------------------------------------------------
    # Construct prompts and call the LLM
    # ------------------------------------------------------------------
    system_prompt = _build_system_prompt(drivers)
    user_prompt = _build_user_prompt(signals, contributions, evidence, drivers, domain_semantics)

    logger.debug(
        "generate_hypotheses: calling LLM with %d signals, %d contributions, "
        "%d evidence items.",
        len(signals),
        len(contributions),
        len(evidence),
    )

    llm_response_text = ""
    try:
        response = provider.complete(
            user_prompt,
            model=getattr(provider, "model", getattr(provider, "_model", None)),
            system=system_prompt,
            temperature=0.0,
            max_tokens=3500,
            format_json=True,
        )
        llm_response_text = response.text

        # Record telemetry if provided (Requirement 16.2)
        if telemetry is not None:
            record_llm_call(
                telemetry=telemetry,
                response=response,
                engine_name="hypothesis_engine",
            )

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "generate_hypotheses: LLM call failed: %s. Returning empty result.",
            exc,
        )
        return HypothesisGenerationResult(
            hypotheses=[],
            rejected_count=0,
            rejection_reasons=[f"LLM call failed: {exc}"],
            llm_response_text="",
        )

    # ------------------------------------------------------------------
    # Parse the LLM response
    # ------------------------------------------------------------------
    raw_hypotheses = _parse_llm_hypotheses(llm_response_text)

    if not raw_hypotheses:
        logger.warning(
            "generate_hypotheses: LLM response could not be parsed into hypotheses. "
            "Raw response length: %d chars.",
            len(llm_response_text),
        )

    # ------------------------------------------------------------------
    # Validate each raw hypothesis (Tasks 8.1 + 8.2)
    # ------------------------------------------------------------------
    validated: list[Hypothesis] = []
    rejected_count = 0
    rejection_reasons: list[str] = []

    for raw in raw_hypotheses:
        if not isinstance(raw, dict):
            rejected_count += 1
            rejection_reasons.append(
                f"raw hypothesis is not a dict: {type(raw).__name__!r}"
            )
            continue

        is_valid, reason = validate_hypothesis(raw, valid_evidence_ids, domain_semantics)

        if not is_valid:
            rejected_count += 1
            hyp_id = raw.get("hypothesis_id", "<unknown>")
            rejection_reasons.append(
                f"hypothesis {hyp_id!r} rejected: {reason}"
            )
            logger.warning(
                "generate_hypotheses: rejected hypothesis %r — %s",
                hyp_id,
                reason,
            )
            continue

        # Extract citations
        citations_raw = raw.get("citations", [])
        citations: list[EvidenceCitation] = []
        if isinstance(citations_raw, list):
            for c in citations_raw:
                if isinstance(c, dict):
                    role_val = str(c.get("role", "supports")).lower()
                    if role_val not in ("supports", "contradicts", "neutral"):
                        role_val = "supports"
                    
                    eid = str(c.get("evidence_id", ""))
                    if eid in evidence_by_id:
                        quoted_summary = evidence_by_id[eid].summary
                    else:
                        quoted_summary = str(c.get("quoted_summary", ""))

                    citations.append(
                        EvidenceCitation(
                            evidence_id=eid,
                            quoted_summary=quoted_summary,
                            role=role_val,  # type: ignore[arg-type]
                            relevance_explanation=str(c.get("relevance_explanation", "")),
                        )
                    )

        if not citations:
            # Fallback for legacy format if any
            for eid in raw.get("supporting_evidence_ids", []):
                citations.append(EvidenceCitation(evidence_id=str(eid), quoted_summary="", role="supports", relevance_explanation=""))
            for eid in raw.get("contradictory_evidence_ids", []):
                citations.append(EvidenceCitation(evidence_id=str(eid), quoted_summary="", role="contradicts", relevance_explanation=""))

        # Build the Hypothesis dataclass with structured causal ontology
        raw_root = str(raw.get("root_cause_type", "UNKNOWN")).strip().upper()
        if raw_root not in ("INTERNAL_RELEASE", "EXTERNAL_PROVIDER", "MACRO_EXTERNAL", "RESOURCE_EXHAUSTION", "INVENTORY_SHORTAGE", "UNKNOWN"):
            raw_root = "UNKNOWN"

        raw_sub = str(raw.get("affected_subsystem", "UNKNOWN")).strip().lower()
        if not raw_sub or raw_sub in ("unknown", "none"):
            raw_sub = str(raw.get("mechanism_tag", "UNKNOWN")).strip().lower()

        raw_prox = str(raw.get("proximal_mechanism", "UNKNOWN")).strip()
        
        raw_symptom_kpis = raw.get("symptom_kpis", [])
        symptom_kpis = [str(k) for k in raw_symptom_kpis] if isinstance(raw_symptom_kpis, list) else []

        mech_tag = str(raw.get("mechanism_tag", raw_sub or "UNKNOWN"))

        hyp = Hypothesis(
            hypothesis_id=str(raw.get("hypothesis_id", f"H{len(validated) + 1}")),
            mechanism_tag=mech_tag,
            root_cause_type=raw_root,
            affected_subsystem=raw_sub,
            proximal_mechanism=raw_prox,
            symptom_kpis=symptom_kpis,
            statement=raw["statement"],
            citations=citations,
            reasoning=raw["reasoning"],
            method=MethodTag.LLM,  # Requirement 8.6
        )
        validated.append(hyp)

    logger.info(
        "generate_hypotheses: produced %d hypothesis(es), rejected %d.",
        len(validated),
        rejected_count,
    )

    return HypothesisGenerationResult(
        hypotheses=validated,
        rejected_count=rejected_count,
        rejection_reasons=rejection_reasons,
        llm_response_text=llm_response_text,
    )
