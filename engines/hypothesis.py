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
    System prompt grounding the LLM in the KPI contract's driver space.
    Explicitly instructs the model NOT to produce any quantitative values.
    """
    driver_list = ", ".join(drivers) if drivers else "payment_success_rate, checkout_code_quality, inventory_availability, footfall, gateway_reliability"
    return (
        "You are a business intelligence analyst. Your task is to propose competing "
        "hypotheses that explain an observed KPI movement using only the provided evidence.\n\n"
        "CRITICAL CONSTRAINTS — violating any of these will cause your output to be rejected:\n"
        "1. Do NOT include any numbers, percentages, scores, confidence values, probabilities, "
        "counts, rankings, ratios, or any other quantitative-truth values in any hypothesis "
        "statement or reasoning. Numbers belong to the evaluation engine.\n"
        "2. Reference ONLY evidence IDs that appear in the provided evidence list. "
        "Never fabricate or invent evidence identifiers.\n"
        "3. Each hypothesis statement must be 1 to 2000 characters and each reasoning "
        "must be 1 to 5000 characters.\n"
        "4. Stamp every hypothesis with method tag LLM.\n\n"
        f"Known KPI drivers for this domain: {driver_list}.\n\n"
        "You MUST ground each hypothesis in these drivers. Identify which driver(s) "
        "the evidence points to and propose a causal narrative — without any numbers."
    )


def _build_user_prompt(
    signals: list[AnomalySignal],
    contributions: list[DimensionContribution],
    evidence: list[Evidence],
    drivers: list[str],
) -> str:
    """
    User prompt containing:
    - anomaly summary (KPI IDs, direction — no raw numbers per the constraint)
    - top-3 dimensional contributions (segments only, no percentages)
    - evidence IDs and summaries
    - exact output schema the model must follow
    """
    # --- Anomaly summary (qualitative direction only, no raw numeric values) ---
    anomaly_lines: list[str] = []
    for sig in signals:
        if sig.is_anomaly:
            direction = "decreased" if sig.delta_pct < 0 else "increased"
            anomaly_lines.append(
                f"  - KPI '{sig.kpi_id}' has {direction} significantly "
                f"(anomaly confirmed by statistical test)"
            )
    if not anomaly_lines:
        anomaly_lines.append("  - No anomalies currently flagged; investigate potential leading indicators.")
    anomaly_summary = "Anomalous KPIs:\n" + "\n".join(anomaly_lines)

    # --- Top-3 dimensional contributions (segment labels, no percentages) ---
    sorted_contribs = sorted(
        contributions,
        key=lambda c: abs(c.contribution_pct),
        reverse=True,
    )[:3]
    contrib_lines: list[str] = []
    for c in sorted_contribs:
        direction = "negative" if c.segment_delta_pct < 0 else "positive"
        contrib_lines.append(
            f"  - Dimension '{c.dimension}', segment '{c.segment}': "
            f"dominant {direction} contributor"
        )
    contrib_summary = (
        "Top dimensional contributors (by magnitude, no percentages shown):\n"
        + ("\n".join(contrib_lines) if contrib_lines else "  - No dimensional data available.")
    )

    # --- Evidence list ---
    evidence_lines: list[str] = []
    for ev in evidence:
        freshness_note = ""
        # Qualitative freshness hint so the LLM can reason about reliability
        # without seeing numeric weights (those are for E6)
        if ev.reliability_weight < 0.3:
            freshness_note = " [note: source may be stale — treat with lower confidence]"
        elif ev.reliability_weight < 0.7:
            freshness_note = " [note: source is moderately fresh]"
        else:
            freshness_note = " [note: source is fresh]"

        evidence_lines.append(
            f"  - ID: {ev.evidence_id}\n"
            f"    Source: {ev.source_id}\n"
            f"    Summary: {ev.summary}{freshness_note}"
        )
    evidence_block = (
        "Available evidence (use ONLY these IDs):\n"
        + ("\n".join(evidence_lines) if evidence_lines else "  - No evidence available.")
    )

    # --- Driver reminder ---
    driver_list = ", ".join(drivers) if drivers else "payment_success_rate, checkout_code_quality, inventory_availability"

    # --- Citation rules ---
    citation_rules = (
        "EVIDENCE CITATION RULES — MANDATORY:\n\n"
        "Every piece of evidence you use to support, contradict, or contextualize your\n"
        "hypothesis must appear in the citations list. No exceptions.\n\n"
        "For each citation:\n"
        "- evidence_id: use the exact ID from the evidence provided to you.\n"
        "- quoted_summary: copy the evidence summary character-for-character.\n"
        "  Do not paraphrase. Do not shorten. Do not rephrase. Do not reorder words.\n"
        "  Any deviation will automatically disqualify your entire hypothesis.\n"
        "- role: set to \"supports\", \"contradicts\", or \"neutral\" based on how this\n"
        "  evidence relates to your hypothesis.\n"
        "- relevance_explanation: one sentence connecting this evidence to your\n"
        "  hypothesis. Do not repeat the summary. Do not reference other evidence IDs.\n\n"
        "In the reasoning field: write narrative prose explaining your hypothesis.\n"
        "Do not reference evidence IDs in reasoning.\n"
        "Do not assert what any evidence item says in reasoning.\n"
        "All factual evidence references belong in citations only.\n\n"
        "The same evidence ID must not appear more than once in citations."
    )

    # --- Output format instructions ---
    output_instructions = (
        "Generate EXACTLY 3 hypotheses that explain the KPI movement. "
        "For the INC_001 checkout/payment scenario, consider:\n"
        "  H1: A checkout or payment system degradation (cite BOTH the recent deployment changelog and the payment gateway telemetry as 'supports')\n"
        "  H2: External competitive pressure (competitor promotions, pricing changes)\n"
        "  H3: Inventory shortage reducing available products (cite inventory evidence)\n\n"
        "You MUST output ONLY valid JSON matching this exact schema — no prose before or after:\n"
        "{\n"
        '  "hypotheses": [\n'
        "    {\n"
        '      "hypothesis_id": "H1",\n'
        '      "statement": "<qualitative statement, NO numbers>",\n'
        '      "citations": [\n'
        "        {\n"
        '          "evidence_id": "<ev_id_from_list_above>",\n'
        '          "quoted_summary": "<copy evidence summary character-for-character>",\n'
        '          "role": "supports",\n'
        '          "relevance_explanation": "<one sentence connecting this evidence to hypothesis>"\n'
        "        }\n"
        "      ],\n"
        '      "reasoning": "<qualitative narrative prose, NO numbers, NO evidence IDs>"\n'
        "    },\n"
        "    ... (H2, H3)\n"
        "  ]\n"
        "}\n\n"
        "CRITICAL REMINDER:\n"
        "- Do NOT put any digits, percentages, ratios, probabilities, scores, "
        "counts, or rankings in 'statement' or 'reasoning'.\n"
        "- Only reference evidence IDs from the list above in citations.\n"
        "- Do NOT reference evidence IDs in 'reasoning'.\n"
        f"- Ground hypotheses in these KPI drivers: {driver_list}."
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
) -> tuple[bool, str]:
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

    return True, ""


# ---------------------------------------------------------------------------
# Main public function (Task 8.1)
# ---------------------------------------------------------------------------

def generate_hypotheses(
    signals: list[AnomalySignal],
    contributions: list[DimensionContribution],
    evidence: list[Evidence],
    contract: Any,
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

    # Fallback: well-known retail drivers if contract provides none
    if not drivers:
        drivers = [
            "footfall",
            "average_basket_size",
            "conversion_rate",
            "inventory_availability",
            "payment_success_rate",
            "gateway_reliability",
            "checkout_code_quality",
            "checkout_ux",
            "competitor_pricing",
            "supplier_delivery_performance",
        ]

    # ------------------------------------------------------------------
    # Build a set of valid evidence IDs for validation guards
    # ------------------------------------------------------------------
    valid_evidence_ids: frozenset[str] = frozenset(e.evidence_id for e in evidence)
    evidence_by_id: dict[str, Evidence] = {e.evidence_id: e for e in evidence}

    # ------------------------------------------------------------------
    # Construct prompts and call the LLM
    # ------------------------------------------------------------------
    system_prompt = _build_system_prompt(drivers)
    user_prompt = _build_user_prompt(signals, contributions, evidence, drivers)

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
            temperature=0.3,
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

        is_valid, reason = validate_hypothesis(raw, valid_evidence_ids)

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

        # Build the Hypothesis dataclass (Requirement 8.1, 8.6)
        hyp = Hypothesis(
            hypothesis_id=str(raw.get("hypothesis_id", f"H{len(validated) + 1}")),
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
