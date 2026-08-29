"""
engines/decision.py — Engine E7: Decision Engine [LLM]

Consumes deterministic confidence from Engine E6 (Challenge Engine).
The LLM generates action recommendations grounded in evidence.
ABSTAIN from E6 → no recommended action (Property 6, Req 10.1).
LLM unavailability → abstain with stated reason (Req 10.5).

Key invariants
--------------
- This engine NEVER recomputes confidence.  It reads audit_verdict from
  the ChallengeResult produced by E6 and acts on it.
- If challenge_result.abstained == True  OR  the top audit_verdict == ABSTAIN,
  the Decision MUST be abstained=True and recommended_action MUST be None.
  (_verify_decision_property_6 asserts this at construction time.)
- If the LLMProvider raises LLMUnavailableError after both model attempts,
  the engine abstains with abstention_reason="provider_unavailable" while
  passing the winning_hypothesis_id through unchanged so the caller can
  record which hypothesis was under evaluation.
- The LLM is used ONLY to generate persona narrative and the recommended
  action text.  All numeric fields come from E6 and are returned untouched.

Persona invariance (Requirements 11.2, 11.3, 11.4)
---------------------------------------------------
All quantitative fields — KPI values, z-scores, dimension contributions,
final scores, and the winning hypothesis identifier — originate exclusively
from the deterministic engines E1–E6 and are threaded through this engine
WITHOUT modification regardless of the requesting persona.

The three supported personas produce STRUCTURALLY DIFFERENT narratives via
PERSONA_NARRATIVE_STYLES directives injected into the system prompt:
  • cfo      — C-suite executive summary; single most-important action; no
               technical detail.
  • analyst  — Full technical breakdown; root cause, evidence quality, method
               transparency, and monitoring plan.
  • manager  — Operational action list; specific, immediate, role-appropriate
               steps.

A field-by-field comparison of two Decision objects produced for the same
scenario under different personas will find ZERO differences in any numeric
field or in winning_hypothesis_id, while persona_narrative will differ in
textual framing.  This structural guarantee is enforced by the fact that no
numeric computation is performed here — all such values are read directly from
the ChallengeResult passed in by the Orchestrator.

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 11.2, 11.3, 11.4, 12.6
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from models import (
    AuditVerdict,
    Decision,
    MethodTag,
    Persona,
    Telemetry,
    StructuredActionRecommendation,
)
from engines.challenge import ChallengeResult
from llm.provider import LLMProvider, LLMUnavailableError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Default abstention threshold — matches Challenge Engine default (Req 10.2)
ABSTENTION_THRESHOLD: float = 0.60

# Matches OllamaProvider.DEFAULT_TIMEOUT (Req 10.6)
DEFAULT_TIMEOUT: float = 30.0

# ---------------------------------------------------------------------------
# Persona narrative style directives
# ---------------------------------------------------------------------------

PERSONA_NARRATIVE_STYLES: dict[str, str] = {
    "cfo": (
        "C-suite executive summary. Focus on business impact and the single most "
        "important action. No technical detail."
    ),
    "analyst": (
        "Full technical breakdown with root cause, evidence quality, method "
        "transparency, and monitoring plan."
    ),
    "manager": (
        "Operational action list. What to do right now. Specific, immediate, "
        "role-appropriate."
    ),
}

def _fallback_verification_metric(winning_statement: str, domain_semantics: dict) -> str:
    """Return a comma-joined verification metric string derived from domain semantics."""
    lower = winning_statement.lower()
    mechanisms = domain_semantics.get("mechanisms", {})
    
    # Try to find a matching mechanism
    matched_steps = []
    for m_id, m_data in mechanisms.items():
        if m_id == "default" or m_id == "external_factors":
             continue
        if any(kw in lower for kw in m_data.get("keywords", [])):
            matched_steps = m_data.get("verification_steps", [])
            break
            
    if not matched_steps:
        # fallback to default mechanism if any
        matched_steps = mechanisms.get("default", {}).get("verification_steps", ["kpi_primary_metric_recovery"])
        
    return ", ".join(matched_steps)


def _abstain_narrative(reason: str, verification_steps: list[str]) -> str:
    """
    Build a plain-text abstention narrative without calling the LLM
    (Req 10.3, 10.4 — no LLM call in the abstention path).
    """
    steps_text = "\n".join(f"  • {s}" for s in verification_steps)
    if reason == "provider_unavailable":
        header = (
            "The language-model provider was unavailable after the fallback attempt. "
            "No action recommendation can be generated at this time."
        )
    else:
        header = (
            "Confidence in the winning hypothesis is insufficient to support "
            "a recommended action. Verification steps are provided instead."
        )
    return header


def _build_decision_prompt(
    challenge_result: ChallengeResult,
    persona: Persona,
    evidence_summaries: list[str],
    decision_rights: dict,
    winning_statement: str,
    domain_semantics: dict,
) -> tuple[str, str]:
    """
    Build the (system_prompt, user_prompt) pair for the Decision LLM call.

    The user prompt requests a JSON object with exactly five keys:
      recommended_action, expected_impact, verification_metric,
      persona_narrative, monitoring_plan.

    For INC_001, the winning hypothesis is a checkout/payment degradation,
    so the LLM context naturally surfaces the v4.3 rollback recommendation.
    """
    top = challenge_result.scored_hypotheses[0]
    narrative_style = PERSONA_NARRATIVE_STYLES.get(
        persona.value, PERSONA_NARRATIVE_STYLES["analyst"]
    )

    levers = decision_rights.get("levers", {})
    available_levers = ", ".join(f'"{k}"' for k in levers.keys())
    if not available_levers:
        available_levers = '"Default Mitigation"'

    system_prompt = (
        f"You are a senior business-intelligence analyst writing a decision recommendation "
        f"for a {persona.value.upper()} persona.\n"
        f"Narrative style directive: {narrative_style}\n\n"
        "Rules:\n"
        "1. Base your recommendation SOLELY on the winning hypothesis and its evidence.\n"
        "2. Do NOT invent or reproduce any numeric figures — all numbers come from the "
        "   deterministic analysis already completed.\n"
        "3. Respond with ONLY valid JSON (no markdown fences, no extra commentary).\n"
        "4. The JSON MUST contain exactly these keys: "
        "   controllable_lever, recommended_action, verification_metric, "
        "   persona_narrative, monitoring_plan.\n"
        f"5. controllable_lever MUST be EXACTLY one of the following strings: {available_levers}.\n"
        "6. Keep persona_narrative under 300 words and recommended_action under 150 words."
    )

    if top:
        confidence_str = top.audit_verdict.value.upper()
    else:
        confidence_str = challenge_result.overall_verdict.value.upper()
    winning_id = challenge_result.winning_hypothesis_id or "unknown"

    # Summarise the top-ranked hypothesis rule verdicts concisely
    rule_lines = []
    for rr in top.rule_results:
        rule_lines.append(f"  {rr.rule_name}: {rr.verdict.value}")
    rules_text = "\n".join(rule_lines) if rule_lines else "  (none)"

    # Summarise up to 5 supporting evidence items for grounding
    evidence_block = ""
    if evidence_summaries:
        trimmed = evidence_summaries[:5]
        evidence_block = "\n".join(f"  [{i+1}] {s}" for i, s in enumerate(trimmed))
    else:
        evidence_block = "  (no evidence summaries available)"

    # Use domain semantics for the hypothesis generation policy / prompt
    domain_policy = domain_semantics.get("hypothesis_generation", {}).get("decision_policy", "")
    
    if not domain_policy:
        # Fallback if no domain policy is defined
        domain_policy = (
            "- Base your recommendation SOLELY on the winning hypothesis and its evidence.\n"
            "- Set verification_metric to the specific KPI(s) that should be monitored to confirm recovery."
        )

    user_prompt = (
        f"Winning hypothesis: {winning_id}\n"
        f"Hypothesis statement: {winning_statement}\n"
        f"Confidence state: {confidence_str}\n\n"
        f"Rule verdicts:\n{rules_text}\n\n"
        f"Key supporting evidence:\n{evidence_block}\n\n"
        "Based on the above analysis, produce a JSON decision recommendation.\n\n"
        "Important context for this scenario:\n"
        f"{domain_policy}\n\n"
        "Respond with ONLY the JSON object (no prose before or after)."
    )

    return system_prompt, user_prompt


def _parse_llm_json(text: str) -> dict:
    """
    Extract a JSON object from the LLM response text.

    Handles:
    - Plain JSON response.
    - JSON wrapped in markdown code fences (```json ... ```).
    - Leading/trailing whitespace.

    Returns an empty dict if parsing fails entirely.
    """
    # Strip markdown fences if present
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        text = fenced.group(1)

    text = text.strip()

    # Attempt direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find a JSON object using a simple brace-matching scan
    start = text.find("{")
    if start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break

    logger.warning("_parse_llm_json: could not extract JSON from LLM response.")
    return {}


# ---------------------------------------------------------------------------
# Property 6 invariant checker
# ---------------------------------------------------------------------------


def _verify_decision_property_6(decision: Decision) -> None:
    """
    Assert Property 6: decision.abstained == True ⇒ recommended_action is None.

    Raises AssertionError if the invariant is violated.  This is called
    immediately before every Decision is returned from decide() so no code
    path can accidentally return an abstained decision with a non-None action.
    """
    if decision.abstained and decision.recommended_action is not None:
        raise AssertionError(
            "Property 6 violated: Decision.abstained is True but "
            f"recommended_action is not None (got {decision.recommended_action!r}). "
            "The Decision_Engine must never return an abstained decision with an action."
        )


# ---------------------------------------------------------------------------
# Main entry point — Task 10.1 + 10.2
# ---------------------------------------------------------------------------


def decide(
    challenge_result: ChallengeResult,
    persona: Persona,
    provider: LLMProvider,
    *,
    evidence_summaries: Optional[list[str]] = None,
    telemetry: Optional[Telemetry] = None,
    decision_rights: Optional[dict] = None,
    winning_statement: str = "",
    domain_semantics: Optional[dict] = None,
) -> Decision:
    """
    Engine E7: Decision Engine.

    Consumes the deterministic ChallengeResult from E6 and produces a Decision
    with a persona-appropriate recommended action and verification metric, or
    abstains gracefully.

    Parameters
    ----------
    challenge_result  : ChallengeResult produced by engines.challenge.challenge().
    persona           : The investigating persona (CFO / Analyst / Manager).
    provider          : LLMProvider instance for generating the recommendation.
    evidence_summaries: Optional list of brief evidence summary strings to include
                        in the LLM prompt for grounding (improves recommendation
                        quality; does not affect any deterministic field).
    telemetry         : Optional Telemetry; updated in-place when provided.

    Returns
    -------
    Decision

    Invariants
    ----------
    - challenge_result.abstained == True  →  Decision.abstained=True,
      recommended_action=None  (Property 6, Req 10.1)
    - LLMUnavailableError after fallback  →  Decision.abstained=True,
      abstention_reason="provider_unavailable", winning_hypothesis_id preserved
      (Req 10.5)
    - This engine NEVER recomputes audit_verdict; it reads it from E6.

    Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 11.3, 12.6
    """
    if evidence_summaries is None:
        evidence_summaries = []
    if decision_rights is None:
        decision_rights = {}
    domain_semantics = domain_semantics or {}
    default_verification_steps = domain_semantics.get("mechanisms", {}).get(
        "default", {}
    ).get("verification_steps", ["kpi_primary_metric_recovery"])

    winning_id = challenge_result.winning_hypothesis_id

    # -----------------------------------------------------------------------
    # CASE A — Abstain (from E6 or empty hypothesis list)
    # -----------------------------------------------------------------------
    if challenge_result.abstained or (
        challenge_result.overall_verdict == AuditVerdict.ABSTAIN
    ):
        logger.info(
            "decide: E6 signalled ABSTAIN (abstained=%s, verdict=%s). "
            "Returning abstained Decision.",
            challenge_result.abstained,
            challenge_result.overall_verdict.value,
        )
        verification_steps = default_verification_steps
        narrative = _abstain_narrative("low_confidence", verification_steps)
        decision = Decision(
            abstained=True,
            recommended_action=None,
            verification_metric=", ".join(verification_steps),
            winning_hypothesis_id=winning_id,   # None when truly no winner
            persona_narrative=narrative,
            abstention_reason="low_confidence",
            method=MethodTag.LLM,
        )
        _verify_decision_property_6(decision)
        return decision

    # -----------------------------------------------------------------------
    # CASE B — Non-abstain: call the LLM to generate the recommendation
    # -----------------------------------------------------------------------
    system_prompt, user_prompt = _build_decision_prompt(
        challenge_result, persona, evidence_summaries, decision_rights, winning_statement, domain_semantics
    )

    try:
        response = provider.complete(
            user_prompt,
            model=getattr(provider, "model", getattr(provider, "_model", None)),
            system=system_prompt,
            temperature=0.0,
            max_tokens=600,
            format_json=True,
        )

        # Record telemetry (Req 16.2)
        if telemetry is not None:
            from llm.telemetry_wrapper import record_llm_call
            record_llm_call(
                telemetry=telemetry,
                response=response,
                engine_name="decision_engine",
            )

        parsed = _parse_llm_json(response.text)

        recommended_action: Optional[str] = (
            parsed.get("recommended_action") or None
        )
        verification_metric: Optional[str] = parsed.get("verification_metric")
        persona_narrative: str = parsed.get("persona_narrative", "")

        # Fallback: if the LLM did not provide a verification metric, derive
        # one deterministically from domain_semantics (Req 10.3)
        if not verification_metric:
            # Derive from the winning hypothesis's top scored result
            top = challenge_result.scored_hypotheses[0]
            # Use the narrative/rule context to pick the right bucket
            bucket_hint = ""
            for rr in top.rule_results:
                bucket_hint += rr.rationale + " "
            verification_metric = _fallback_verification_metric(bucket_hint, domain_semantics)

        # Fallback: if no recommended_action was extracted, use a safe default
        # (should be rare — the LLM prompt strongly requests it)
        if not recommended_action:
            logger.warning(
                "decide: LLM did not return a recommended_action; "
                "using a deterministic placeholder."
            )
            recommended_action = (
                "Review the winning hypothesis evidence and consult the relevant "
                "operations team for immediate remediation."
            )

        # Build the narrative — prefer the LLM value; fall back to monitoring_plan
        if not persona_narrative:
            persona_narrative = parsed.get("monitoring_plan", "")
        if not persona_narrative:
            persona_narrative = (
                f"Action recommended based on {challenge_result.overall_verdict.value.upper()} "
                "verdict hypothesis. Please refer to the evidence panel for full details."
            )

        # Enforce Lever Authorization (Unknown Lever Guard)
        controllable_lever = parsed.get("controllable_lever", "")
        levers = decision_rights.get("levers", {})
        if controllable_lever not in levers:
            logger.warning(
                "decide: LLM generated an unknown or unauthorized lever: %r. "
                "Abstaining to prevent execution of unauthorized action.",
                controllable_lever,
            )
            verification_steps = default_verification_steps
            narrative = (
                "The system formulated an action using an unauthorized lever. "
                "Execution is blocked pending governance review."
            )
            decision = Decision(
                abstained=True,
                recommended_action=None,
                verification_metric=", ".join(verification_steps),
                winning_hypothesis_id=winning_id,
                persona_narrative=narrative,
                abstention_reason="unauthorized_lever_selected",
                method=MethodTag.LLM,
            )
            _verify_decision_property_6(decision)
            return decision
            
        # Valid lever selected — build the StructuredActionRecommendation
        lever_cfg = levers[controllable_lever]
        monitoring_plan = parsed.get("monitoring_plan", f"Monitor {verification_metric}")
        
        structured_rec = StructuredActionRecommendation(
            driver=winning_statement or "Unknown",
            controllable_lever=controllable_lever,
            action=recommended_action,
            expected_impact="Pending E8 Simulation",
            owner=lever_cfg.get("owner", "Unknown"),
            confidence=challenge_result.scored_hypotheses[0].final_audit_score if challenge_result.scored_hypotheses else 0.0,
            monitoring_plan=monitoring_plan,
            authorized_personas=lever_cfg.get("authorized_personas", []),
        )

        decision = Decision(
            abstained=False,
            recommended_action=recommended_action,
            verification_metric=verification_metric,
            winning_hypothesis_id=winning_id,
            persona_narrative=persona_narrative,
            abstention_reason=None,
            structured_recommendation=structured_rec,
            method=MethodTag.LLM,
        )
        _verify_decision_property_6(decision)

        logger.info(
            "decide: Decision generated for persona=%s, winner=%s, verdict=%s.",
            persona.value,
            winning_id,
            challenge_result.overall_verdict.value,
        )
        return decision

    # -----------------------------------------------------------------------
    # CASE C — LLM unavailable after fallback (Req 10.5)
    # -----------------------------------------------------------------------
    except LLMUnavailableError as exc:
        logger.warning(
            "decide: LLMProvider unavailable after fallback: %s. "
            "Abstaining with reason='provider_unavailable'. "
            "Deterministic numeric outputs are preserved.",
            exc,
        )
        bucket_hint = " ".join(
            rr.rationale
            for sh in challenge_result.scored_hypotheses[:1]
            for rr in sh.rule_results
        )
        
        fallback_metric = _fallback_verification_metric(bucket_hint, domain_semantics)
        verification_steps = [s.strip() for s in fallback_metric.split(",")]
        
        narrative = _abstain_narrative("provider_unavailable", verification_steps)

        decision = Decision(
            abstained=True,
            recommended_action=None,
            verification_metric=", ".join(verification_steps),
            # Preserve winning_hypothesis_id so callers know what was being evaluated
            winning_hypothesis_id=winning_id,
            persona_narrative=narrative,
            abstention_reason="provider_unavailable",
            method=MethodTag.LLM,
        )
        _verify_decision_property_6(decision)
        return decision
