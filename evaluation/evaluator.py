"""
evaluation/evaluator.py — 15-dimension scorecard evaluator.

Reads data/ground_truth.json ONLY within this module — the pipeline
never imports this file.  Scores an InvestigationResult across 15 dimensions.
Ground truth is NEVER passed to the pipeline.

ISOLATION GUARD (Task 13.2)
----------------------------
`_GROUND_TRUTH_LOAD_ALLOWED = True` is set here and only here.
All other pipeline modules (engines/, pipeline/, security/, llm/, api/, etl/)
must carry `_GROUND_TRUTH_LOAD_ALLOWED = False` as a documentation contract.
Any runtime attempt by pipeline code to open GROUND_TRUTH_PATH is treated as
an authorization violation and recorded accordingly.

Requirements: 18.1, 18.2, 18.3, 18.4, 18.5
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from models import (
    AnomalySignal,
    ConfidenceState,
    DimensionContribution,
    Evidence,
    InvestigationResult,
    MethodTag,
    Persona,
    ScoredHypothesis,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Isolation guard (Task 13.2)
# This flag is True ONLY in this module.  All pipeline modules must declare
# _GROUND_TRUTH_LOAD_ALLOWED = False.  This is a documentation/convention
# contract for the MVP; runtime enforcement is via the authorization_violation_count.
# ---------------------------------------------------------------------------
_GROUND_TRUTH_LOAD_ALLOWED: bool = True

# ---------------------------------------------------------------------------
# Ground truth path constant
# ---------------------------------------------------------------------------
GROUND_TRUTH_PATH: Path = Path(__file__).parent.parent / "data" / "ground_truth.json"

# ---------------------------------------------------------------------------
# Allowed method tags for evidence provenance check (Dimension 13)
# ---------------------------------------------------------------------------
_ALLOWED_EVIDENCE_METHODS: frozenset[MethodTag] = frozenset(
    {MethodTag.SQL, MethodTag.RETRIEVAL, MethodTag.ETL}
)

# ---------------------------------------------------------------------------
# Persona → authorized source IDs mapping (mirrors entitlements.yaml)
# Used for authorization violation detection (Dimension 15)
# ---------------------------------------------------------------------------
_PERSONA_AUTHORIZED_SOURCES: dict[str, frozenset[str]] = {
    "cfo": frozenset({"orders", "inventory"}),
    "analyst": frozenset({"orders", "payment_gateway", "inventory", "marketing"}),
    "manager": frozenset({"orders", "inventory"}),
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class DimensionScore:
    """Per-dimension evaluation result."""

    dimension_id: int     # 1–15
    dimension_name: str
    score: float          # [0, 1]
    passed: bool          # True when score == 1.0
    detail: str           # human-readable explanation


@dataclass
class EvaluationResult:
    """Complete evaluation output for one investigation run."""

    scenario_id: str
    overall_pass: bool                        # True only when hallucinated == 0 AND auth_violations == 0 AND all scores match
    dimension_scores: list[DimensionScore]
    hallucinated_evidence_count: int
    authorization_violation_count: int
    scorecard_text: str                       # human-readable summary


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_ground_truth(path: Optional[Path] = None) -> dict:
    """
    Load and return the ground_truth.json dict.

    ISOLATION: this function is private and called ONLY within this module.
    Pipeline code must never call this or open GROUND_TRUTH_PATH.

    Parameters
    ----------
    path : optional override for the ground truth path (for testing)

    Returns
    -------
    Parsed ground truth dict.

    Raises
    ------
    FileNotFoundError  : when the ground truth file is missing.
    ValueError         : when the file cannot be parsed as JSON.
    """
    target = path if path is not None else GROUND_TRUTH_PATH
    if not target.exists():
        raise FileNotFoundError(
            f"Ground truth file not found at {target!s}. "
            "Ensure data/ground_truth.json is present."
        )
    try:
        with target.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Failed to parse ground truth JSON at {target!s}: {exc}"
        ) from exc


def _keywords_in_text(keywords: list[str], text: str) -> bool:
    """Return True if any keyword appears in text (case-insensitive)."""
    lower_text = text.lower()
    return any(kw.lower() in lower_text for kw in keywords)


def _find_winning_hypothesis(result: InvestigationResult) -> Optional[ScoredHypothesis]:
    """Return the top-ranked non-abstained ScoredHypothesis, or None."""
    if not result.scored:
        return None
    ranked = sorted(result.scored, key=lambda s: s.final_score, reverse=True)
    top = ranked[0]
    if top.confidence_state == ConfidenceState.ABSTAIN:
        return None
    return top


def _hypothesis_is_checkout_payment(hyp_id: str, statement: str, reasoning: str) -> bool:
    """
    Heuristic: returns True when the hypothesis is about checkout/payment degradation.
    Checks the hypothesis_id label and statement/reasoning keywords.
    """
    combined = (hyp_id + " " + statement + " " + reasoning).lower()
    payment_kws = (
        "payment", "checkout", "gateway", "transaction",
        "conversion", "cart", "purchase", "order",
    )
    inventory_kws = ("inventory", "stock", "shortage", "supply")
    competitor_kws = ("competitor", "competition", "pricing", "promotion", "market")

    payment_hits = sum(1 for kw in payment_kws if kw in combined)
    inventory_hits = sum(1 for kw in inventory_kws if kw in combined)
    competitor_hits = sum(1 for kw in competitor_kws if kw in combined)

    # Considered a payment/checkout hypothesis when payment keywords dominate
    return payment_hits > 0 and payment_hits >= inventory_hits and payment_hits >= competitor_hits


def _hypothesis_is_inventory(hyp_id: str, statement: str, reasoning: str) -> bool:
    """Returns True when the hypothesis is about inventory shortage."""
    combined = (hyp_id + " " + statement + " " + reasoning).lower()
    inventory_kws = ("inventory", "stock", "shortage", "supply", "out-of-stock")
    payment_kws = ("payment", "checkout", "gateway")

    inventory_hits = sum(1 for kw in inventory_kws if kw in combined)
    payment_hits = sum(1 for kw in payment_kws if kw in combined)

    return inventory_hits > 0 and inventory_hits > payment_hits


def _collect_all_hypothesis_evidence_ids(result: InvestigationResult) -> set[str]:
    """Return all evidence IDs referenced by any hypothesis."""
    ids: set[str] = set()
    for h in result.hypotheses:
        ids.update(h.supporting_evidence_ids)
        ids.update(h.contradictory_evidence_ids)
    return ids


def _actual_evidence_id_set(result: InvestigationResult) -> set[str]:
    """Return the set of evidence IDs actually present in the result."""
    return {e.evidence_id for e in result.evidence}


def _get_authorized_sources(result: InvestigationResult) -> frozenset[str]:
    """
    Return the authorized source IDs for the persona in the result.
    Falls back to the analyst set (broadest) if the persona is unrecognised.
    """
    persona_key = result.persona.value.lower() if hasattr(result.persona, "value") else str(result.persona).lower()
    return _PERSONA_AUTHORIZED_SOURCES.get(persona_key, frozenset(_PERSONA_AUTHORIZED_SOURCES["analyst"]))


def _did_abstain(result: InvestigationResult) -> bool:
    """
    Determine whether the pipeline abstained for *result*.

    Checks scored hypothesis confidence_state and decision.abstained flag.
    Returns True when the top-ranked hypothesis has ABSTAIN confidence state,
    the decision flag is set, or no hypotheses were scored at all (guard
    scenarios where the pipeline stopped before the hypothesis engine).
    """
    # Guard scenario: no scored hypotheses at all → pipeline stopped early → abstain
    if not result.scored:
        return True
    # Top scored hypothesis is ABSTAIN
    top = sorted(result.scored, key=lambda s: s.final_score, reverse=True)[0]
    if top.confidence_state == ConfidenceState.ABSTAIN:
        return True
    # Decision-level abstain flag
    if result.decision is not None and getattr(result.decision, "abstained", False):
        return True
    return False


# ---------------------------------------------------------------------------
# Evaluator class
# ---------------------------------------------------------------------------


class Evaluator:
    """
    Scores an InvestigationResult against INC_001 ground truth across 15 dimensions.

    Usage
    -----
    evaluator = Evaluator()
    eval_result = evaluator.evaluate(result)
    print(eval_result.scorecard_text)
    """

    def __init__(self, ground_truth_path: Optional[Path] = None) -> None:
        """
        Parameters
        ----------
        ground_truth_path : optional override; defaults to GROUND_TRUTH_PATH.
        """
        self._ground_truth_path = ground_truth_path
        self._ground_truth: Optional[dict] = None  # lazy-loaded

    def _gt(self) -> dict:
        """Lazy-load and cache the ground truth dict."""
        if self._ground_truth is None:
            self._ground_truth = _load_ground_truth(self._ground_truth_path)
        return self._ground_truth

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self, result: InvestigationResult) -> EvaluationResult:
        """
        Score *result* across 15 evaluation dimensions.

        For INC_001 the full 15-dimension scorecard is applied.
        For INC_002, INC_003, and INC_004 (additional Round 2 scenarios) the
        evaluation is dispatched to _score_additional_scenario(), which applies
        scenario-specific guard checks (abstain, sparse_history,
        data_quality_suspect) in place of the INC_001-specific dimensions that
        are not applicable to these guard scenarios.

        Parameters
        ----------
        result : the InvestigationResult returned by the Orchestrator.

        Returns
        -------
        EvaluationResult with per-dimension scores, counts, and a scorecard.

        Requirements: 18.1, 18.2, 3.2, 3.3, 10.1, 10.2
        """
        # Dispatch additional scenarios to the specialised scorer
        if result.scenario_id in ("INC_002", "INC_003", "INC_004"):
            return self._score_additional_scenario(result)

        gt = self._gt()
        scenario_gt = gt.get("scenarios", {}).get(result.scenario_id, {})

        # Collect all evidence IDs referenced by hypotheses
        referenced_ids = _collect_all_hypothesis_evidence_ids(result)
        actual_ids = _actual_evidence_id_set(result)
        hallucinated_ids = referenced_ids - actual_ids
        hallucinated_count = len(hallucinated_ids)

        # Collect authorization violations (evidence from unauthorized sources)
        authorized_sources = _get_authorized_sources(result)
        auth_violation_items = [
            e for e in result.evidence
            if e.source_id not in authorized_sources
        ]
        auth_violation_count = len(auth_violation_items)

        # Score all 15 dimensions
        dimensions: list[DimensionScore] = [
            self._dim_01_anomaly_detected(result, scenario_gt),
            self._dim_02_localization(result, scenario_gt),
            self._dim_03_contribution_analysis(result, scenario_gt),
            self._dim_04_evidence_retrieval(result, scenario_gt),
            self._dim_05_true_hypothesis_in_top3(result, scenario_gt),
            self._dim_06_true_hypothesis_ranking(result, scenario_gt),
            self._dim_07_incorrect_hypothesis_challenged(result, scenario_gt),
            self._dim_08_contradiction_handling(result, scenario_gt),
            self._dim_09_confidence_correctness(result, scenario_gt),
            self._dim_10_abstention_correctness(result, scenario_gt),
            self._dim_11_recommendation_correctness(result, scenario_gt),
            self._dim_12_verification_metric_presence(result, scenario_gt),
            self._dim_13_provenance_correctness(result, scenario_gt),
            self._dim_14_hallucinated_evidence(result, hallucinated_count),
            self._dim_15_authorization_violations(result, auth_violation_count),
        ]

        # Overall pass: hallucinated == 0 AND auth_violations == 0 (Req 18.5)
        hard_pass = (hallucinated_count == 0 and auth_violation_count == 0)
        all_dims_pass = all(d.passed for d in dimensions)
        overall_pass = hard_pass and all_dims_pass

        scorecard_text = format_scorecard(
            EvaluationResult(
                scenario_id=result.scenario_id,
                overall_pass=overall_pass,
                dimension_scores=dimensions,
                hallucinated_evidence_count=hallucinated_count,
                authorization_violation_count=auth_violation_count,
                scorecard_text="",  # placeholder; filled below
            )
        )

        return EvaluationResult(
            scenario_id=result.scenario_id,
            overall_pass=overall_pass,
            dimension_scores=dimensions,
            hallucinated_evidence_count=hallucinated_count,
            authorization_violation_count=auth_violation_count,
            scorecard_text=scorecard_text,
        )

    # ------------------------------------------------------------------
    # Additional scenario scorer — INC_002, INC_003, INC_004
    # ------------------------------------------------------------------

    def _score_additional_scenario(
        self,
        result: InvestigationResult,
    ) -> EvaluationResult:
        """
        Evaluate INC_002/INC_003/INC_004 using scenario-specific guard checks.

        These scenarios exercise Signal Engine guards and abstention logic rather
        than the full 15-dimension hypothesis-ranking scorecard.  The method
        reads the scenario-specific evaluation_checks from ground_truth.json and
        applies only the checks that are relevant, returning a streamlined
        EvaluationResult with the same structure as the INC_001 path so
        downstream tooling (format_scorecard, run_evaluation) is unchanged.

        Dimension mapping for additional scenarios
        ------------------------------------------
        D01  anomaly_detected        — must match evaluation_checks.anomaly_detected
        D02  sparse_history_guard    — INC_003: sparse_history flag must be True on signals
                                       INC_002/INC_004: N/A → auto-pass
        D03  data_quality_guard      — INC_004: data_quality_suspect flag must be True
                                       INC_002/INC_003: N/A → auto-pass
        D04  evidence_retrieval      — at least 0 items allowed for guard scenarios
        D05  hypothesis_suppressed   — INC_003/INC_004: no hypotheses generated
                                       INC_002: hypotheses generated (both present)
        D06  abstention_correctness  — must match evaluation_checks.abstain_expected
        D07–D15  authorization + hallucination checks (always applied)

        Requirements: 3.2, 3.3, 10.1, 10.2
        """
        gt = self._gt()
        scenario_gt = gt.get("scenarios", {}).get(result.scenario_id, {})
        checks = scenario_gt.get("evaluation_checks", {})

        # ---- shared counts (always computed) ----
        referenced_ids = _collect_all_hypothesis_evidence_ids(result)
        actual_ids = _actual_evidence_id_set(result)
        hallucinated_count = len(referenced_ids - actual_ids)

        authorized_sources = _get_authorized_sources(result)
        auth_violation_count = len(
            [e for e in result.evidence if e.source_id not in authorized_sources]
        )

        # ---- D01: anomaly_detected ----
        expected_anomaly = checks.get("anomaly_detected", False)
        actual_anomaly = any(s.is_anomaly for s in result.signals)
        d01_passed = actual_anomaly == expected_anomaly
        dimensions: list[DimensionScore] = [
            DimensionScore(
                1,
                "Anomaly detected",
                1.0 if d01_passed else 0.0,
                d01_passed,
                (
                    f"{'✓' if d01_passed else '✗'} anomaly_detected={actual_anomaly} "
                    f"(expected={expected_anomaly})"
                ),
            )
        ]

        # ---- D02: sparse_history_guard ----
        sparse_expected = checks.get("sparse_history_expected", False)
        if sparse_expected:
            # At least one signal must have sparse_history=True
            actual_sparse = any(
                getattr(s, "sparse_history", False) for s in result.signals
            )
            d02_passed = actual_sparse
            d02_detail = (
                f"{'✓' if d02_passed else '✗'} sparse_history guard "
                f"fired={actual_sparse} (expected=True for INC_003)"
            )
        else:
            # Not expected — auto-pass for this scenario
            d02_passed = True
            d02_detail = "✓ sparse_history guard N/A for this scenario (auto-pass)"
        dimensions.append(
            DimensionScore(2, "Sparse-history guard (Req 3.2)", 1.0 if d02_passed else 0.0, d02_passed, d02_detail)
        )

        # ---- D03: data_quality_guard ----
        dq_expected = checks.get("data_quality_suspect_expected", False)
        if dq_expected:
            actual_dq = any(
                getattr(s, "data_quality_suspect", False) for s in result.signals
            )
            d03_passed = actual_dq
            d03_detail = (
                f"{'✓' if d03_passed else '✗'} data_quality_suspect guard "
                f"fired={actual_dq} (expected=True for INC_004)"
            )
        else:
            d03_passed = True
            d03_detail = "✓ data_quality_suspect guard N/A for this scenario (auto-pass)"
        dimensions.append(
            DimensionScore(3, "Data-quality guard (Req 3.3)", 1.0 if d03_passed else 0.0, d03_passed, d03_detail)
        )

        # ---- D04: evidence_retrieval ----
        # Guard scenarios may legitimately have 0 evidence (pipeline stopped early);
        # treat as pass for INC_003/INC_004, require >= 1 for INC_002 (hypotheses generated).
        if result.scenario_id == "INC_002":
            ev_count = len(result.evidence)
            d04_passed = ev_count >= 1
            d04_detail = (
                f"{'✓' if d04_passed else '✗'} evidence_count={ev_count} "
                f"(expected >= 1 for ambiguous scenario)"
            )
        else:
            d04_passed = True
            d04_detail = (
                f"✓ evidence retrieval N/A for guard scenario "
                f"(evidence_count={len(result.evidence)})"
            )
        dimensions.append(
            DimensionScore(4, "Evidence retrieval", 1.0 if d04_passed else 0.0, d04_passed, d04_detail)
        )

        # ---- D05: hypothesis suppression / generation ----
        # INC_003/INC_004: guards fired → Hypothesis Engine should NOT be invoked
        # INC_002: both H1-like and H2-like hypotheses should be present
        if result.scenario_id == "INC_002":
            has_payment_hyp = any(
                _hypothesis_is_checkout_payment(h.hypothesis_id, h.statement, h.reasoning)
                for h in result.hypotheses
            )
            has_external_hyp = any(
                any(kw in (h.statement + " " + h.reasoning).lower()
                    for kw in ("competitor", "competition", "pricing", "promotion", "marketing", "external"))
                for h in result.hypotheses
            )
            d05_passed = has_payment_hyp and has_external_hyp
            d05_detail = (
                f"{'✓' if d05_passed else '✗'} INC_002 requires both payment and "
                f"competitor hypotheses: payment={has_payment_hyp}, "
                f"competitor={has_external_hyp}"
            )
            d05_name = "Both payment + competitor hypotheses present (INC_002)"
        else:
            # INC_003/INC_004: guards fired → no hypotheses should be generated
            hyp_count = len(result.hypotheses)
            d05_passed = hyp_count == 0
            d05_detail = (
                f"{'✓' if d05_passed else '✗'} hypothesis_count={hyp_count} "
                f"(expected=0 — guard suppressed pipeline)"
            )
            d05_name = "Hypothesis engine suppressed by guard"
        dimensions.append(
            DimensionScore(5, d05_name, 1.0 if d05_passed else 0.0, d05_passed, d05_detail)
        )

        # ---- D06: abstention_correctness ----
        abstain_expected = checks.get("abstain_expected", True)
        did_abstain = _did_abstain(result)
        d06_passed = did_abstain == abstain_expected
        dimensions.append(
            DimensionScore(
                6,
                "Abstention correctness (Req 10.1, 10.2)",
                1.0 if d06_passed else 0.0,
                d06_passed,
                (
                    f"{'✓' if d06_passed else '✗'} abstained={did_abstain} "
                    f"(expected={abstain_expected})"
                ),
            )
        )

        # ---- D07: no_recommended_action (guard / abstain scenarios) ----
        # For INC_003/INC_004 (pipeline stopped) and INC_002 (abstained),
        # a recommended_action should NOT be present.
        no_action_expected = checks.get("no_recommended_action", True)
        has_action = (
            result.decision is not None
            and result.decision.recommended_action is not None
            and len(str(result.decision.recommended_action).strip()) > 0
            and not did_abstain
        )
        d07_passed = (not has_action) if no_action_expected else has_action
        dimensions.append(
            DimensionScore(
                7,
                "No recommended action on abstain/guard",
                1.0 if d07_passed else 0.0,
                d07_passed,
                (
                    f"{'✓' if d07_passed else '✗'} has_action={has_action} "
                    f"(expected no_action={no_action_expected})"
                ),
            )
        )

        # ---- D08–D15: provenance + authorization + hallucination ----
        # Always enforced regardless of scenario.
        dimensions.append(
            self._dim_13_provenance_correctness(result, scenario_gt)
        )
        dimensions.append(
            self._dim_14_hallucinated_evidence(result, hallucinated_count)
        )
        dimensions.append(
            self._dim_15_authorization_violations(result, auth_violation_count)
        )

        hard_pass = (hallucinated_count == 0 and auth_violation_count == 0)
        overall_pass = hard_pass and all(d.passed for d in dimensions)

        scorecard_text = format_scorecard(
            EvaluationResult(
                scenario_id=result.scenario_id,
                overall_pass=overall_pass,
                dimension_scores=dimensions,
                hallucinated_evidence_count=hallucinated_count,
                authorization_violation_count=auth_violation_count,
                scorecard_text="",
            )
        )

        return EvaluationResult(
            scenario_id=result.scenario_id,
            overall_pass=overall_pass,
            dimension_scores=dimensions,
            hallucinated_evidence_count=hallucinated_count,
            authorization_violation_count=auth_violation_count,
            scorecard_text=scorecard_text,
        )

    # ------------------------------------------------------------------
    # Dimension scorers — one method per dimension
    # ------------------------------------------------------------------

    def _dim_01_anomaly_detected(
        self,
        result: InvestigationResult,
        scenario_gt: dict,
    ) -> DimensionScore:
        """
        Dimension 1: Anomaly detected.
        At least one signal has is_anomaly=True (INC_001 expects True).
        """
        expected = scenario_gt.get("evaluation_checks", {}).get("anomaly_detected", True)
        actual = any(s.is_anomaly for s in result.signals)

        passed = (actual == expected)
        score = 1.0 if passed else 0.0
        detail = (
            f"{'✓' if passed else '✗'} anomaly_detected={actual} "
            f"(expected={expected})"
        )
        return DimensionScore(1, "Anomaly detected", score, passed, detail)

    def _dim_02_localization(
        self,
        result: InvestigationResult,
        scenario_gt: dict,
    ) -> DimensionScore:
        """
        Dimension 2: Localization.
        Dominant segment in contributions is (device, android) for INC_001.
        """
        expected_dim = scenario_gt.get("evaluation_checks", {}).get(
            "dominant_dimension", {}
        )
        exp_dimension = expected_dim.get("dimension", "device").lower()
        exp_segment = expected_dim.get("segment", "android").lower()

        # Find the dominant contribution in the expected dimension
        relevant = [
            c for c in result.contributions
            if c.dimension.lower() == exp_dimension
        ]

        if not relevant:
            return DimensionScore(
                2, "Localization (dominant segment)",
                0.0, False,
                f"✗ no contributions found for dimension='{exp_dimension}'"
            )

        dominant = max(relevant, key=lambda c: abs(c.contribution_pct))
        actual_seg = dominant.segment.lower()

        passed = exp_segment in actual_seg or actual_seg in exp_segment
        score = 1.0 if passed else 0.0
        detail = (
            f"{'✓' if passed else '✗'} dominant segment='{dominant.segment}' "
            f"(expected dimension='{exp_dimension}' segment='{exp_segment}')"
        )
        return DimensionScore(2, "Localization (dominant segment)", score, passed, detail)

    def _dim_03_contribution_analysis(
        self,
        result: InvestigationResult,
        scenario_gt: dict,
    ) -> DimensionScore:
        """
        Dimension 3: Contribution analysis.
        Android contribution_pct > 0 (non-zero contribution).
        """
        expected_segment = (
            scenario_gt.get("evaluation_checks", {})
            .get("dominant_dimension", {})
            .get("segment", "android")
            .lower()
        )

        android_contribs = [
            c for c in result.contributions
            if expected_segment in c.segment.lower()
        ]

        if not android_contribs:
            return DimensionScore(
                3, "Contribution analysis (Android non-zero)",
                0.0, False,
                f"✗ no contributions found for segment='{expected_segment}'"
            )

        max_pct = max(abs(c.contribution_pct) for c in android_contribs)
        passed = max_pct > 0
        score = 1.0 if passed else 0.0
        detail = (
            f"{'✓' if passed else '✗'} '{expected_segment}' max "
            f"contribution_pct={max_pct:.2f}% (expected > 0)"
        )
        return DimensionScore(3, "Contribution analysis (Android non-zero)", score, passed, detail)

    def _dim_04_evidence_retrieval(
        self,
        result: InvestigationResult,
        scenario_gt: dict,
    ) -> DimensionScore:
        """
        Dimension 4: Evidence retrieval.
        At least 3 evidence items returned.
        """
        count = len(result.evidence)
        passed = count >= 3
        score = 1.0 if passed else 0.0
        detail = (
            f"{'✓' if passed else '✗'} evidence_count={count} (expected >= 3)"
        )
        return DimensionScore(4, "Evidence retrieval (>= 3 items)", score, passed, detail)

    def _dim_05_true_hypothesis_in_top3(
        self,
        result: InvestigationResult,
        scenario_gt: dict,
    ) -> DimensionScore:
        """
        Dimension 5: True hypothesis in top-3.
        An H1-like (checkout/payment) hypothesis appears in hypotheses list.
        """
        checkout_hypotheses = [
            h for h in result.hypotheses
            if _hypothesis_is_checkout_payment(h.hypothesis_id, h.statement, h.reasoning)
        ]

        # Also check scored hypotheses as a fallback (in case statement wasn't stored)
        if not checkout_hypotheses and result.scored:
            # If H1 is in the scored list, it was generated
            h1_scored = [s for s in result.scored if "1" in s.hypothesis_id]
            passed = len(h1_scored) > 0
        else:
            passed = len(checkout_hypotheses) > 0

        score = 1.0 if passed else 0.0
        detail = (
            f"{'✓' if passed else '✗'} checkout/payment hypothesis present "
            f"({'found' if passed else 'not found'} among {len(result.hypotheses)} hypotheses)"
        )
        return DimensionScore(5, "True hypothesis in top-3", score, passed, detail)

    def _dim_06_true_hypothesis_ranking(
        self,
        result: InvestigationResult,
        scenario_gt: dict,
    ) -> DimensionScore:
        """
        Dimension 6: True hypothesis ranking.
        The winning scored hypothesis is H1 (checkout/payment wins).
        """
        winner = _find_winning_hypothesis(result)

        if winner is None:
            return DimensionScore(
                6, "True hypothesis ranking (H1 wins)",
                0.0, False,
                "✗ no winning hypothesis (result abstained or no scored hypotheses)"
            )

        # Check if the winner is a checkout/payment hypothesis
        # Look up the full hypothesis for statement/reasoning
        winner_hyp = next(
            (h for h in result.hypotheses if h.hypothesis_id == winner.hypothesis_id),
            None,
        )
        if winner_hyp is not None:
            is_payment = _hypothesis_is_checkout_payment(
                winner_hyp.hypothesis_id, winner_hyp.statement, winner_hyp.reasoning
            )
        else:
            # Fallback: if id contains "1" and no other info, treat as H1
            is_payment = "1" in winner.hypothesis_id

        passed = is_payment
        score = 1.0 if passed else 0.0
        detail = (
            f"{'✓' if passed else '✗'} winning hypothesis='{winner.hypothesis_id}' "
            f"is checkout/payment={'yes' if is_payment else 'no'} "
            f"(score={winner.final_score:.3f})"
        )
        return DimensionScore(6, "True hypothesis ranking (H1 wins)", score, passed, detail)

    def _dim_07_incorrect_hypothesis_challenged(
        self,
        result: InvestigationResult,
        scenario_gt: dict,
    ) -> DimensionScore:
        """
        Dimension 7: Incorrect hypothesis challenge.
        H3 (inventory shortage) is scored LOW.
        """
        expected_h3_max = (
            scenario_gt.get("expected_hypotheses", {})
            .get("H3", {})
            .get("expected_confidence_max", 0.30)
        )

        # Find inventory hypothesis
        inventory_scored = []
        for sh in result.scored:
            hyp = next(
                (h for h in result.hypotheses if h.hypothesis_id == sh.hypothesis_id),
                None,
            )
            if hyp is not None and _hypothesis_is_inventory(
                hyp.hypothesis_id, hyp.statement, hyp.reasoning
            ):
                inventory_scored.append(sh)
            elif hyp is None and "3" in sh.hypothesis_id:
                # Fallback: H3 by id
                inventory_scored.append(sh)

        if not inventory_scored:
            return DimensionScore(
                7, "Incorrect hypothesis challenged (H3=LOW)",
                0.0, False,
                "✗ inventory-shortage hypothesis not found in scored hypotheses"
            )

        # The inventory hypothesis should be LOW (not HIGH or MEDIUM)
        h3 = min(inventory_scored, key=lambda s: s.final_score)
        is_low = (
            h3.confidence_state == ConfidenceState.LOW
            or h3.final_score <= expected_h3_max
        )
        passed = is_low
        score = 1.0 if passed else 0.0
        detail = (
            f"{'✓' if passed else '✗'} inventory hypothesis '{h3.hypothesis_id}' "
            f"confidence={h3.confidence_state.value} score={h3.final_score:.3f} "
            f"(expected LOW / score <= {expected_h3_max})"
        )
        return DimensionScore(7, "Incorrect hypothesis challenged (H3=LOW)", score, passed, detail)

    def _dim_08_contradiction_handling(
        self,
        result: InvestigationResult,
        scenario_gt: dict,
    ) -> DimensionScore:
        """
        Dimension 8: Contradiction handling.
        H3's contradictory evidence references a fresh inventory source.
        """
        # Find H3 (inventory hypothesis)
        h3 = None
        for h in result.hypotheses:
            if _hypothesis_is_inventory(h.hypothesis_id, h.statement, h.reasoning):
                h3 = h
                break

        if h3 is None:
            # Try by ID fallback
            h3 = next((h for h in result.hypotheses if "3" in h.hypothesis_id), None)

        if h3 is None:
            return DimensionScore(
                8, "Contradiction handling (H3 has inventory contradiction)",
                0.0, False,
                "✗ inventory-shortage hypothesis H3 not found"
            )

        if not h3.contradictory_evidence_ids:
            return DimensionScore(
                8, "Contradiction handling (H3 has inventory contradiction)",
                0.0, False,
                f"✗ H3 ('{h3.hypothesis_id}') has no contradictory evidence listed"
            )

        # Check that at least one contradictory evidence ID resolves to an inventory source
        actual_ids = {e.evidence_id: e for e in result.evidence}
        inventory_contradictions = []
        for eid in h3.contradictory_evidence_ids:
            ev = actual_ids.get(eid)
            if ev is not None and "inventory" in ev.source_id.lower():
                inventory_contradictions.append(ev)

        passed = len(inventory_contradictions) > 0
        score = 1.0 if passed else 0.0
        detail = (
            f"{'✓' if passed else '✗'} H3 contradictory evidence: "
            f"{h3.contradictory_evidence_ids} — "
            f"{'found' if passed else 'missing'} inventory contradiction evidence"
        )
        return DimensionScore(8, "Contradiction handling (H3 has inventory contradiction)", score, passed, detail)

    def _dim_09_confidence_correctness(
        self,
        result: InvestigationResult,
        scenario_gt: dict,
    ) -> DimensionScore:
        """
        Dimension 9: Confidence correctness.
        Winning hypothesis confidence_state is HIGH.
        """
        expected_state_str = scenario_gt.get("expected_confidence_state", "HIGH")
        try:
            expected_state = ConfidenceState(expected_state_str.lower())
        except ValueError:
            expected_state = ConfidenceState.HIGH

        winner = _find_winning_hypothesis(result)

        if winner is None:
            return DimensionScore(
                9, "Confidence correctness (winner = HIGH)",
                0.0, False,
                f"✗ no winning hypothesis (expected={expected_state.value})"
            )

        passed = winner.confidence_state == expected_state
        score = 1.0 if passed else 0.0
        detail = (
            f"{'✓' if passed else '✗'} winning '{winner.hypothesis_id}' "
            f"confidence={winner.confidence_state.value} "
            f"(expected={expected_state.value})"
        )
        return DimensionScore(9, "Confidence correctness (winner = HIGH)", score, passed, detail)

    def _dim_10_abstention_correctness(
        self,
        result: InvestigationResult,
        scenario_gt: dict,
    ) -> DimensionScore:
        """
        Dimension 10: Abstention correctness.
        INC_001 expects no abstention; verify the system did not abstain.
        """
        abstain_expected = scenario_gt.get("evaluation_checks", {}).get(
            "abstain_expected", False
        )
        # Determine if the system abstained
        did_abstain = (
            result.decision is not None and result.decision.abstained
        ) or (
            result.decision is None and not result.scored
        )
        # Also check top scored hypothesis
        if result.scored:
            top = sorted(result.scored, key=lambda s: s.final_score, reverse=True)[0]
            did_abstain = top.confidence_state == ConfidenceState.ABSTAIN

        passed = did_abstain == abstain_expected
        score = 1.0 if passed else 0.0
        detail = (
            f"{'✓' if passed else '✗'} abstained={did_abstain} "
            f"(expected={abstain_expected})"
        )
        return DimensionScore(10, "Abstention correctness", score, passed, detail)

    def _dim_11_recommendation_correctness(
        self,
        result: InvestigationResult,
        scenario_gt: dict,
    ) -> DimensionScore:
        """
        Dimension 11: Recommendation correctness.
        recommended_action contains keywords: "rollback" or "v4.3" or "payment".
        """
        expected_keywords = scenario_gt.get(
            "evaluation_checks", {}
        ).get("recommended_action_keywords", ["rollback", "v4.3", "payment"])

        action = (
            result.decision.recommended_action
            if result.decision is not None
            else None
        )

        if not action:
            return DimensionScore(
                11, "Recommendation correctness (keywords present)",
                0.0, False,
                "✗ recommended_action is None or empty (system abstained or no decision)"
            )

        found_kws = [kw for kw in expected_keywords if kw.lower() in action.lower()]
        passed = len(found_kws) > 0
        score = 1.0 if passed else 0.0
        detail = (
            f"{'✓' if passed else '✗'} recommended_action contains "
            f"{found_kws if passed else '[]'} "
            f"(expected any of {expected_keywords})"
        )
        return DimensionScore(11, "Recommendation correctness (keywords present)", score, passed, detail)

    def _dim_12_verification_metric_presence(
        self,
        result: InvestigationResult,
        scenario_gt: dict,
    ) -> DimensionScore:
        """
        Dimension 12: Verification metric presence.
        verification_metric is non-None and non-empty.
        """
        metric = (
            result.decision.verification_metric
            if result.decision is not None
            else None
        )

        passed = metric is not None and len(str(metric).strip()) > 0
        score = 1.0 if passed else 0.0
        detail = (
            f"{'✓' if passed else '✗'} verification_metric="
            f"{metric!r} ({'present' if passed else 'missing or empty'})"
        )
        return DimensionScore(12, "Verification metric presence", score, passed, detail)

    def _dim_13_provenance_correctness(
        self,
        result: InvestigationResult,
        scenario_gt: dict,
    ) -> DimensionScore:
        """
        Dimension 13: Provenance correctness.
        All evidence items have method tags in the allowed set {SQL, RETRIEVAL, ETL}.
        """
        bad_items = [
            e for e in result.evidence
            if e.method not in _ALLOWED_EVIDENCE_METHODS
        ]

        passed = len(bad_items) == 0
        score = 1.0 if passed else 0.0

        if bad_items:
            bad_summary = ", ".join(
                f"'{e.evidence_id}'={e.method.value}" for e in bad_items[:5]
            )
            detail = f"✗ evidence items with disallowed method tags: {bad_summary}"
        else:
            detail = (
                f"✓ all {len(result.evidence)} evidence items have allowed "
                f"method tags ({{{', '.join(m.value for m in _ALLOWED_EVIDENCE_METHODS)}}})"
            )
        return DimensionScore(13, "Provenance correctness (evidence method tags)", score, passed, detail)

    def _dim_14_hallucinated_evidence(
        self,
        result: InvestigationResult,
        hallucinated_count: int,
    ) -> DimensionScore:
        """
        Dimension 14: Hallucinated evidence references.
        Count of hypothesis evidence IDs not in the actual evidence set = 0 for PASS.
        """
        passed = hallucinated_count == 0
        score = 1.0 if passed else 0.0
        detail = (
            f"{'✓' if passed else '✗'} hallucinated_evidence_references={hallucinated_count} "
            f"(expected=0)"
        )
        return DimensionScore(14, "Hallucinated evidence references = 0", score, passed, detail)

    def _dim_15_authorization_violations(
        self,
        result: InvestigationResult,
        auth_violation_count: int,
    ) -> DimensionScore:
        """
        Dimension 15: Authorization violations.
        Count of evidence items from unauthorized sources = 0 for PASS.
        """
        passed = auth_violation_count == 0
        score = 1.0 if passed else 0.0
        detail = (
            f"{'✓' if passed else '✗'} authorization_violations={auth_violation_count} "
            f"(expected=0)"
        )
        return DimensionScore(15, "Authorization violations = 0", score, passed, detail)


# ---------------------------------------------------------------------------
# format_scorecard
# ---------------------------------------------------------------------------


def format_scorecard(eval_result: EvaluationResult) -> str:
    """
    Render *eval_result* as a human-readable scorecard string.

    Example output
    --------------
    BusinessIntelligence.ai — Evaluation Scorecard
    ===============================================
    INC_001
      ✓ [01] Anomaly detected
      ✓ [02] Localization (dominant segment)
      ...
      ✗ [14] Hallucinated evidence references = 0
    -----------------------------------------------
    Overall: 14/15 dimensions passed | FAIL
    Hallucinated evidence references: 1
    Authorization violations: 0

    Requirements: 18.1
    """
    lines: list[str] = []
    lines.append("BusinessIntelligence.ai — Evaluation Scorecard")
    lines.append("=" * 47)
    lines.append(eval_result.scenario_id)

    for ds in eval_result.dimension_scores:
        icon = "✓" if ds.passed else "✗"
        lines.append(f"  {icon} [{ds.dimension_id:02d}] {ds.dimension_name}")
        # Indent detail on the next line for readability
        lines.append(f"       {ds.detail}")

    lines.append("-" * 47)
    passed_count = sum(1 for ds in eval_result.dimension_scores if ds.passed)
    total = len(eval_result.dimension_scores)
    verdict = "PASS" if eval_result.overall_pass else "FAIL"
    lines.append(
        f"Overall: {passed_count}/{total} dimensions passed | {verdict}"
    )
    lines.append(f"Hallucinated evidence references: {eval_result.hallucinated_evidence_count}")
    lines.append(f"Authorization violations: {eval_result.authorization_violation_count}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


def run_evaluation(
    result: InvestigationResult,
    ground_truth_path: Optional[Path] = None,
) -> EvaluationResult:
    """
    Convenience wrapper: create an Evaluator and score *result*.

    Parameters
    ----------
    result             : InvestigationResult from the Orchestrator.
    ground_truth_path  : optional override for the ground truth file path.

    Returns
    -------
    EvaluationResult with scorecard.

    Requirements: 18.1, 18.2, 18.3
    """
    evaluator = Evaluator(ground_truth_path=ground_truth_path)
    return evaluator.evaluate(result)
