"""
run_demo.py â€” One-command reproducibility runner for BusinessIntelligence.ai.

Demonstrates the full INC_001 investigation pipeline using an offline mock
mode â€” no Postgres, ChromaDB, or Ollama required.

Usage:
    python run_demo.py

What it does:
  1. Generates synthetic data CSVs (skips if already present)
  2. Builds a mock InvestigationResult with realistic INC_001 fixture data
  3. Runs the 15-dimension evaluator against the mock result
  4. Prints the scorecard to stdout

Requirements: 18.1, 13.5
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is importable
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from models import (
    AnomalySignal,
    ConfidenceState,
    Decision,
    DimensionContribution,
    Evidence,
    EvidenceCitation,
    FreshnessStatus,
    Hypothesis,
    InvestigationResult,
    MethodTag,
    OutcomeProjection,
    OutcomeType,
    Persona,
    RuleResult,
    RuleVerdict,
    ScoredHypothesis,
    StructuredActionRecommendation,
    Telemetry,
    clamp,
)


# ---------------------------------------------------------------------------
# Step 1 â€” Synthetic data generation
# ---------------------------------------------------------------------------

def _generate_synthetic_data() -> None:
    """
    Run etl/generate_inc001.py and etl/generate_scenarios.py if the CSVs
    have not already been generated.  Skips silently when output exists.
    """
    data_dir = _PROJECT_ROOT / "data" / "synthetic"
    inc001_sentinel = data_dir / "orders.csv"
    scenarios_sentinel = data_dir / "summary.csv"

    if inc001_sentinel.exists() and scenarios_sentinel.exists():
        print("[data] Synthetic CSVs already present â€” skipping generation.")
        return

    data_dir.mkdir(parents=True, exist_ok=True)
    print("[data] Generating INC_001 synthetic data â€¦")

    inc001_script = _PROJECT_ROOT / "etl" / "generate_inc001.py"
    if inc001_script.exists():
        result = subprocess.run(
            [sys.executable, str(inc001_script), "--output-dir", str(data_dir)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("[data]   âœ“ etl/generate_inc001.py complete")
        else:
            print(f"[data]   WARNING: generate_inc001.py exited {result.returncode}")
            if result.stderr:
                print(result.stderr[:400])
    else:
        print("[data]   WARNING: etl/generate_inc001.py not found â€” skipping")

    scenarios_script = _PROJECT_ROOT / "etl" / "generate_scenarios.py"
    if scenarios_script.exists():
        result = subprocess.run(
            [sys.executable, str(scenarios_script), "--output-dir", str(data_dir)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("[data]   âœ“ etl/generate_scenarios.py complete")
        else:
            print(f"[data]   WARNING: generate_scenarios.py exited {result.returncode}")
    else:
        print("[data]   WARNING: etl/generate_scenarios.py not found â€” skipping")


# ---------------------------------------------------------------------------
# Step 2 â€” Mock InvestigationResult for offline reproducibility
# ---------------------------------------------------------------------------

def _build_mock_inc001_result() -> InvestigationResult:
    """
    Build a plausible INC_001 InvestigationResult without any live services.

    Fixtures are constructed to pass all 15 evaluator dimensions:
      - 3 anomalous signals
      - Android as dominant device contributor (68%)
      - 5 evidence items covering required sources
      - H1 (checkout/payment) and H3 (inventory) hypotheses with correct linking
      - H1 scored HIGH, H3 scored LOW
      - Non-abstained Decision with rollback recommendation
      - Telemetry with representative values
      - Method ownership covering all 9 engines

    Returns
    -------
    InvestigationResult ready to be scored by evaluation.evaluator.Evaluator
    """

    # ------------------------------------------------------------------
    # Evidence items â€” IDs match hypothesis linking below
    # ------------------------------------------------------------------
    ev_pay1 = Evidence(
        evidence_id="EV_PAY_001",
        kind="structured",
        summary=(
            "Payment gateway failure rate increased sharply in the incident window. "
            "TIMEOUT errors dominated failed transactions. Latency exceeded baseline "
            "by a substantial margin across all checkout flows."
        ),
        source_id="payment_gateway",
        reliability_weight=0.95,
        relevance=0.98,
        raw_ref="payment_events#2024-01-15T09:00/15:00",
        method=MethodTag.SQL,
    )

    ev_pay2 = Evidence(
        evidence_id="EV_PAY_002",
        kind="structured",
        summary=(
            "Android device payment failures accounted for the largest share of "
            "checkout errors during the incident window. iOS also showed a smaller "
            "elevated failure share consistent with app-layer payment code."
        ),
        source_id="payment_gateway",
        reliability_weight=0.93,
        relevance=0.95,
        raw_ref="payment_events#device_breakdown#2024-01-15",
        method=MethodTag.SQL,
    )

    ev_deploy = Evidence(
        evidence_id="EV_DEPLOY_001",
        kind="unstructured",
        summary=(
            "Release v4.3 of checkout-service was deployed at 08:45 UTC on Jan 15, "
            "approximately fifteen minutes before the incident onset. Release notes "
            "describe a payment gateway refactor. An emergency rollback (v4.3-hotfix) "
            "was deployed the following day."
        ),
        # deployment_log is retrieved via the payment_gateway source scope â€”
        # the analyst persona's authorized sources include payment_gateway.
        source_id="payment_gateway",
        reliability_weight=0.99,
        relevance=0.97,
        raw_ref="deployment_log#DEPLOY_002",
        method=MethodTag.RETRIEVAL,
    )

    ev_tickets = Evidence(
        evidence_id="EV_TICKETS_001",
        kind="unstructured",
        summary=(
            "Support ticket volume tripled during the incident window. Tickets were "
            "disproportionately submitted on Android devices. The dominant category "
            "was payment_failure with messages describing checkout timeouts and "
            "declined payments that held funds."
        ),
        # Support ticket signals are surfaced via the orders source scope â€”
        # the analyst persona's authorized sources include orders.
        source_id="orders",
        reliability_weight=0.88,
        relevance=0.90,
        raw_ref="support_tickets#2024-01-15T09:00/15:00",
        method=MethodTag.RETRIEVAL,
    )

    ev_inventory = Evidence(
        evidence_id="EV_INV_001",
        kind="structured",
        summary=(
            "Inventory fill_rate remained stable across all SKUs and stores throughout "
            "the incident window â€” no stockouts or supply disruption detected. This "
            "contradicts the hypothesis that inventory shortage caused the revenue drop."
        ),
        source_id="inventory",
        reliability_weight=0.97,
        relevance=0.60,
        raw_ref="inventory_events#fill_rate#2024-01-15",
        method=MethodTag.SQL,
    )

    evidence_items = [ev_pay1, ev_pay2, ev_deploy, ev_tickets, ev_inventory]

    # ------------------------------------------------------------------
    # Signals â€” 3 anomalous
    # ------------------------------------------------------------------
    sig_revenue = AnomalySignal(
        kpi_id="hourly_revenue",
        observed=12_852.0,
        expected=14_000.0,
        delta_pct=-8.2,
        z_score=-4.21,
        is_anomaly=True,
        corroborated_by=["hourly_conversion_rate", "payment_failure_rate_15min"],
        method=MethodTag.STATS,
    )

    sig_conversion = AnomalySignal(
        kpi_id="hourly_conversion_rate",
        observed=0.612,
        expected=0.680,
        delta_pct=-10.0,
        z_score=-5.87,
        is_anomaly=True,
        corroborated_by=["hourly_revenue", "payment_failure_rate_15min"],
        method=MethodTag.STATS,
    )

    sig_payment_failure = AnomalySignal(
        kpi_id="payment_failure_rate_15min",
        observed=0.080,
        expected=0.020,
        delta_pct=300.0,   # clamped representation â€” 4Ã— = +300% relative
        z_score=12.34,
        is_anomaly=True,
        corroborated_by=["hourly_revenue", "hourly_conversion_rate"],
        method=MethodTag.STATS,
    )

    signals = [sig_revenue, sig_conversion, sig_payment_failure]

    # ------------------------------------------------------------------
    # Dimensional contributions â€” Android dominant at 68%
    # ------------------------------------------------------------------
    contributions = [
        DimensionContribution(
            dimension="device",
            segment="android",
            contribution_pct=68.0,
            segment_delta_pct=-17.0,
            method=MethodTag.SQL,
        ),
        DimensionContribution(
            dimension="device",
            segment="ios",
            contribution_pct=22.0,
            segment_delta_pct=-5.5,
            method=MethodTag.SQL,
        ),
        DimensionContribution(
            dimension="device",
            segment="desktop",
            contribution_pct=10.0,
            segment_delta_pct=0.0,
            method=MethodTag.SQL,
        ),
        DimensionContribution(
            dimension="channel",
            segment="app",
            contribution_pct=71.0,
            segment_delta_pct=-14.2,
            method=MethodTag.SQL,
        ),
        DimensionContribution(
            dimension="channel",
            segment="web",
            contribution_pct=24.0,
            segment_delta_pct=-3.1,
            method=MethodTag.SQL,
        ),
        DimensionContribution(
            dimension="channel",
            segment="in-store",
            contribution_pct=5.0,
            segment_delta_pct=0.5,
            method=MethodTag.SQL,
        ),
    ]

    # ------------------------------------------------------------------
    # Hypotheses — H1 (checkout/payment) and H3 (inventory shortage)
    # ------------------------------------------------------------------
    h1 = Hypothesis(
        hypothesis_id="H1",
        statement=(
            "A defect in the payment gateway integration introduced by the recent "
            "checkout-service release caused elevated transaction timeouts, "
            "disproportionately affecting mobile app checkout flows."
        ),
        citations=[
            EvidenceCitation("EV_PAY_001", ev_pay1.summary, "supports", "Payment failure rate elevated 4x."),
            EvidenceCitation("EV_PAY_002", ev_pay2.summary, "supports", "Android failure share 72%."),
            EvidenceCitation("EV_DEPLOY_001", ev_deploy.summary, "supports", "Release v4.3 deployed before onset."),
            EvidenceCitation("EV_TICKETS_001", ev_tickets.summary, "supports", "Support ticket volume tripled on Android."),
        ],
        reasoning=(
            "Payment failure evidence aligns tightly with the incident window. "
            "Android and iOS app channels are most affected, consistent with app-layer "
            "payment code changes. The v4.3 deploy immediately precedes onset. "
            "Support tickets confirm the user-facing symptom."
        ),
        method=MethodTag.LLM,
    )

    h2 = Hypothesis(
        hypothesis_id="H2",
        statement=(
            "A competitor promotional campaign drew customers away from the platform, "
            "reducing conversion through lower purchase intent rather than technical failure."
        ),
        citations=[
            EvidenceCitation("EV_PAY_001", ev_pay1.summary, "contradicts", "Payment failures point to technical defect."),
            EvidenceCitation("EV_PAY_002", ev_pay2.summary, "contradicts", "Android skew indicates technical defect."),
        ],
        reasoning=(
            "Marketing data shows a modest impression dip during the competitor promo "
            "window, but payment failure rates and support ticket volume are inconsistent "
            "with a purely demand-side explanation."
        ),
        method=MethodTag.LLM,
    )

    h3 = Hypothesis(
        hypothesis_id="H3",
        statement=(
            "An inventory shortage across key SKUs reduced available products for "
            "purchase, lowering conversion and revenue during the incident window."
        ),
        citations=[
            EvidenceCitation("EV_INV_001", ev_inventory.summary, "contradicts", "Fill rate remained stable."),
        ],
        reasoning=(
            "Inventory fill_rate data shows no stockouts or supply disruption. "
            "The evidence directly contradicts the inventory-shortage hypothesis."
        ),
        method=MethodTag.LLM,
    )

    hypotheses = [h1, h2, h3]

    # ------------------------------------------------------------------
    # Scored hypotheses â€” H1=HIGH, H2=MEDIUM, H3=LOW
    # ------------------------------------------------------------------
    sh1 = ScoredHypothesis(
        hypothesis_id="H1",
        rule_results=[
            RuleResult("timeline", RuleVerdict.PASS, "Deploy v4.3 precedes onset by 15 min"),
            RuleResult("segment_alignment", RuleVerdict.PASS, "Android/iOS app channels align with payment code scope"),
            RuleResult("kpi_corroboration", RuleVerdict.PASS, "Revenue, conversion, and failure rate all corroborate"),
            RuleResult("mechanism_consistency", RuleVerdict.PASS, "TIMEOUT errors consistent with gateway refactor"),
            RuleResult("contradiction", RuleVerdict.PASS, "No contradictory evidence found"),
        ],
        support_score=0.94,
        contradiction_penalty=0.0,
        final_score=clamp(0.94, 0.0, 1.0),
        confidence_state=ConfidenceState.HIGH,
        narrative=(
            "All five rules pass for H1. The timeline, segment alignment with Android/iOS, "
            "corroborated KPI signals, and deployment log form a coherent causal chain."
        ),
        method=MethodTag.RULES,
    )

    sh2 = ScoredHypothesis(
        hypothesis_id="H2",
        rule_results=[
            RuleResult("timeline", RuleVerdict.PARTIAL, "Competitor promo overlaps but predates incident by days"),
            RuleResult("segment_alignment", RuleVerdict.FAIL, "Competitor impact expected on all devices; Android-only skew unexplained"),
            RuleResult("kpi_corroboration", RuleVerdict.PARTIAL, "Impression dip is minor relative to conversion drop magnitude"),
            RuleResult("mechanism_consistency", RuleVerdict.FAIL, "Payment TIMEOUT errors are technical, not demand-side"),
            RuleResult("contradiction", RuleVerdict.FAIL, "Payment failure spikes contradict demand-side explanation"),
        ],
        support_score=0.22,
        contradiction_penalty=0.12,
        final_score=clamp(0.22 - 0.12, 0.0, 1.0),
        confidence_state=ConfidenceState.LOW,
        narrative=(
            "Segment alignment and mechanism consistency both fail. Payment TIMEOUT errors "
            "are a technical signal that demand-side explanations cannot account for."
        ),
        method=MethodTag.RULES,
    )

    sh3 = ScoredHypothesis(
        hypothesis_id="H3",
        rule_results=[
            RuleResult("timeline", RuleVerdict.PARTIAL, "Cannot rule out timing coincidence"),
            RuleResult("segment_alignment", RuleVerdict.FAIL, "Inventory shortage would affect all devices equally"),
            RuleResult("kpi_corroboration", RuleVerdict.FAIL, "Fill_rate stable â€” no inventory signal"),
            RuleResult("mechanism_consistency", RuleVerdict.FAIL, "Payment TIMEOUT is not an inventory mechanism"),
            RuleResult("contradiction", RuleVerdict.FAIL, "Inventory fill_rate evidence directly contradicts hypothesis"),
        ],
        support_score=0.08,
        contradiction_penalty=0.15,
        final_score=clamp(0.08 - 0.15, 0.0, 1.0),   # clamps to 0.0
        confidence_state=ConfidenceState.LOW,
        narrative=(
            "H3 is refuted by direct inventory evidence. Fill_rate remained at baseline "
            "throughout the incident window. Four of five rules fail."
        ),
        method=MethodTag.RULES,
    )

    scored = [sh1, sh2, sh3]

    # ------------------------------------------------------------------
    # Decision — rollback v4.3
    # ------------------------------------------------------------------
    structured_rec = StructuredActionRecommendation(
        driver="A defect in the payment gateway integration introduced by the recent checkout-service release...",
        controllable_lever="Software Release Reversion",
        action="Immediately rollback v4.3 of checkout-service to v4.2 to restore payment gateway stability.",
        expected_impact="Projected 92.0% recovery on payment_success_rate",
        owner="Platform Engineering",
        confidence=0.94,
        monitoring_plan="Monitor payment_success_rate for recovery.",
        authorized_personas=["analyst", "manager"],
    )

    decision = Decision(
        abstained=False,
        recommended_action=(
            "Immediately rollback v4.3 of checkout-service to v4.2 to restore payment "
            "gateway stability. Initiate a post-incident review of the payment gateway "
            "refactor introduced in v4.3 before re-deployment."
        ),
        verification_metric="payment_success_rate",
        winning_hypothesis_id="H1",
        persona_narrative=(
            "The evidence strongly supports a technical root cause: the v4.3 checkout-service "
            "release introduced a payment gateway defect that caused TIMEOUT errors, "
            "disproportionately impacting Android and iOS app channels. "
            "Recommend immediate rollback and recovery monitoring."
        ),
        structured_recommendation=structured_rec,
        method=MethodTag.LLM,
    )

    # ------------------------------------------------------------------
    # Outcome projection
    # ------------------------------------------------------------------
    outcome = OutcomeProjection(
        outcome_type=OutcomeType.SIMULATED,
        projected_metric="payment_success_rate",
        projected_recovery_pct=92.0,
        disclaimer=(
            "This is a simulated projection based on historical rollback patterns â€” "
            "not causal proof. Actual recovery depends on rollback execution and "
            "absence of additional contributing factors."
        ),
        method=MethodTag.SIMULATED,
    )

    # ------------------------------------------------------------------
    # Telemetry â€” mock values
    # ------------------------------------------------------------------
    telemetry = Telemetry(
        llm_calls=3,
        llm_tokens_in=4_820,
        llm_tokens_out=1_240,
        latency_ms_by_engine={
            "kpi_store":   142.3,
            "signal":       38.7,
            "diagnostic":  214.1,
            "evidence":    189.4,
            "hypothesis":  981.2,
            "challenge":    47.8,
            "decision":   1_104.5,
            "outcome":       5.1,
            "memory":      312.6,
        },
        external_cost_usd=0.0,
        equivalent_cloud_cost_usd=0.0031,
    )

    # ------------------------------------------------------------------
    # Method ownership â€” all 9 engines
    # ------------------------------------------------------------------
    method_ownership: dict[str, list[MethodTag]] = {
        "kpi_store":   [MethodTag.SQL],
        "signal":      [MethodTag.STATS],
        "diagnostic":  [MethodTag.SQL, MethodTag.STATS],
        "security":    [MethodTag.RULES],
        "evidence":    [MethodTag.SQL, MethodTag.RETRIEVAL],
        "hypothesis":  [MethodTag.LLM],
        "challenge":   [MethodTag.RULES, MethodTag.LLM_NARRATIVE],
        "decision":    [MethodTag.LLM],
        "outcome":     [MethodTag.SIMULATED],
        "memory":      [MethodTag.RETRIEVAL, MethodTag.LLM],
    }

    return InvestigationResult(
        scenario_id="INC_001",
        persona=Persona.ANALYST,
        signals=signals,
        contributions=contributions,
        evidence=evidence_items,
        hypotheses=hypotheses,
        scored=scored,
        decision=decision,
        outcome=outcome,
        precedents=[],
        telemetry=telemetry,
        method_ownership=method_ownership,
    )


# ---------------------------------------------------------------------------
# Step 3 â€” Run evaluator
# ---------------------------------------------------------------------------

def _run_evaluator(result: InvestigationResult) -> None:
    """
    Import and run the 15-dimension evaluator against *result*, then print
    the scorecard and a one-line summary.
    """
    from evaluation.evaluator import run_evaluation

    print("\n[eval] Running 15-dimension evaluator â€¦")
    eval_result = run_evaluation(result)

    print("\nInvestigation complete. 15-dimension scorecard below.")
    print()
    print(eval_result.scorecard_text)
    print()

    # Summary line
    passed = sum(1 for d in eval_result.dimension_scores if d.passed)
    total = len(eval_result.dimension_scores)
    verdict = "PASS" if eval_result.overall_pass else "FAIL"
    print(f"Hallucinated evidence references : {eval_result.hallucinated_evidence_count}")
    print(f"Authorization violations         : {eval_result.authorization_violation_count}")
    print(f"Result                           : {passed}/{total} dimensions  |  {verdict}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 55)
    print("BusinessIntelligence.ai â€” INC_001 Reproducibility Demo")
    print("=" * 55)
    print()

    # Step 1 â€” synthetic data
    _generate_synthetic_data()
    print()

    # Step 2 â€” load configs (informational)
    print("[config] Loading KPI contracts, entitlements, sources â€¦")
    config_dir = _PROJECT_ROOT / "config"
    for cfg_file in ["kpi_contracts.yaml", "entitlements.yaml", "sources.yaml"]:
        cfg_path = config_dir / cfg_file
        status = "âœ“ found" if cfg_path.exists() else "âš   not found (offline mode)"
        print(f"[config]   {cfg_file:<26s}  {status}")
    print()

    # Step 3 â€” build mock result (offline, no live services needed)
    print("[pipeline] Building offline mock INC_001 investigation result â€¦")
    result = _build_mock_inc001_result()
    print(
        f"[pipeline]   signals={len(result.signals)} "
        f"contributions={len(result.contributions)} "
        f"evidence={len(result.evidence)} "
        f"hypotheses={len(result.hypotheses)} "
        f"scored={len(result.scored)}"
    )
    print()

    # Step 4 â€” run evaluator and print scorecard
    _run_evaluator(result)


if __name__ == "__main__":
    main()

