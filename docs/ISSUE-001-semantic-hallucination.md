# ISSUE-001: Semantic Hallucination — LLM Misrepresentation of Evidence Content

**Severity**: 🔴 Critical — Structural / Correctness  
**Status**: Resolved (Fixed in Commit `bef715c`, Hardened in Commit `PR-001-fix`)  
**Affects**: `models.py`, `engines/hypothesis.py` (E5), `engines/challenge.py` (E6), `evaluation/evaluator.py`

---

## Resolution & Implementation Summary

The structural solution chosen was a **verbatim citation contract** with deterministic string matching (`quoted_summary.strip() == actual.strip()`). This avoids fuzzy similarity thresholds and eliminates semantic paraphrase hallucination entirely.

### Core Architectural Fixes

1. **`EvidenceCitation` Schema & Derived Properties** ([`models.py`](file:///e:/accenture/models.py#L235))
   - Introduced `EvidenceCitation(evidence_id, quoted_summary, role, relevance_explanation)`.
   - `supporting_evidence_ids` and `contradictory_evidence_ids` are now derived `@property` methods on `Hypothesis.citations`. They cannot be written independently.
   - `reasoning` is strictly scoped to narrative prose and prohibited from referencing evidence IDs or asserting evidence content.

2. **Deterministic Citation Hard Gate** ([`engines/challenge.py`](file:///e:/accenture/engines/challenge.py#L831))
   - Implemented `validate_citations(hypothesis, evidence_by_id)`.
   - Checks for `duplicate_citation`, `phantom_id`, and exact `summary_mismatch`.
   - `score_hypothesis()` hard-gates on any citation violation before evaluating rules: immediately returns `final_score=0.0`, `confidence_state=ABSTAIN`, and logs violations.

3. **E5 Prompt & Parser Security Boundary** ([`engines/hypothesis.py`](file:///e:/accenture/engines/hypothesis.py))
   - Added mandatory verbatim quote rules in E5 prompts.
   - **Malformed schema handling**: `validate_hypothesis` rejects malformed citation objects, invalid roles outside `{"supports", "contradicts", "neutral"}`, or non-string summaries.
   - **Reasoning isolation check**: `validate_hypothesis` rejects any hypothesis where `reasoning` contains evidence ID tokens (e.g. `ev_001`).
   - **Zero-citation policy**: When `valid_evidence_ids` is non-empty, `validate_hypothesis` rejects hypotheses that provide zero citations, preventing evidence-free hypotheses from bypassing validation.

4. **Dimension 16 Scorecard Integration** ([`evaluation/evaluator.py`](file:///e:/accenture/evaluation/evaluator.py#L1084))
   - Added **D16: Citation Fidelity** to the evaluator scorecard.
   - Explicitly configured D14, D15, and D16 as **Hard Requirements**: failing D16 forces `overall_pass = False`.
   - **Scope Distinction Documented**: A 16/16 pass proves structural quotation fidelity, schema compliance, and authorization safety. It does not certify LLM semantic interpretation correctness (which requires human review).

5. **Test Suite Verification** ([`tests/test_fidelity.py`](file:///e:/accenture/tests/test_fidelity.py))
   - 13 dedicated unit and integration tests covering exact matches, mismatch violations, phantom IDs, duplicate IDs, hard-gate disqualifications, derived fields, neutral citations, malformed JSON structures, invalid roles, reasoning ID references, zero-citation policy, and D16 evaluator hard pass.
   - **Test Results**: 200/200 passed cleanly in pytest; `run_demo.py` achieves 16/16 PASS.

## Problem Statement

The hallucination check in E6 (`engines/challenge.py`) validates that evidence IDs exist in the `evidence_by_id` dictionary. A hallucinated ID like `FAKE_ID_999` is dropped and scores `0.0` — this is tested in `tests/test_challenge_smoke.py::TestHallucinatedIds`.

**This is the easy form of hallucination.**

The dangerous, unmitigated form is: the LLM cites `ev_inventory_001` accurately by ID, but then describes it in the hypothesis `reasoning` field as saying _"inventory levels are critically low"_ — when the actual `Evidence.summary` says _"Inventory fill rate is normal and stable."_ The LLM has inverted the meaning of the evidence.

### Why This Is Dangerous

E6's five rules (`timeline`, `segment_alignment`, `kpi_corroboration`, `mechanism_consistency`, `contradiction`) operate on **hypothesis-level keywords and evidence metadata** (source IDs, reliability weights, relevance scores). They do **not** compare the LLM's textual characterization of each evidence item against the actual `Evidence.summary` field.

This means:
1. A hypothesis can reference valid evidence IDs.
2. The LLM can describe what the evidence "says" in a way that is the **opposite** of the actual content.
3. E6 will score the hypothesis based on rule verdicts that do not catch the misrepresentation.
4. The 15-dimension evaluator checks for hallucinated IDs (D14) but **not** for semantic fidelity.
5. A semantically hallucinated hypothesis can score `HIGH` and pass all 15 evaluation dimensions.

### Current Code Gap

In [`engines/challenge.py`](file:///e:/accenture/engines/challenge.py):
- `score_hypothesis()` calculates `support_score` by iterating `h.supporting_evidence_ids` and summing `ev.reliability_weight * ev.relevance` — it never reads `ev.summary`.
- `evaluate_rule()` dispatches to `_rule_timeline`, `_rule_segment_alignment`, etc. These functions check keywords in `hypothesis.statement` and `hypothesis.reasoning`, but never cross-reference those claims against the underlying `Evidence.summary`.

In [`evaluation/evaluator.py`](file:///e:/accenture/evaluation/evaluator.py):
- `_dim_14_hallucinated_evidence()` checks `referenced_ids - actual_ids`. It counts phantom IDs. It does **not** verify that the LLM's use of a real ID is semantically faithful.

---

## Remediation Plan

### Phase 1: Evidence Fidelity Checker (New Module)

Create `engines/fidelity.py` — a deterministic post-processing step that runs **between E5 and E6**:

```python
def check_evidence_fidelity(
    hypotheses: list[Hypothesis],
    evidence_by_id: dict[str, Evidence],
    provider: LLMProvider,
) -> list[FidelityResult]:
    """
    For each hypothesis, compare the LLM's reasoning text against
    the actual Evidence.summary for every referenced evidence ID.
    
    Uses embedding cosine similarity (bge-m3) between:
      - The LLM's claim about the evidence (extracted from reasoning)
      - The actual Evidence.summary
    
    If cosine similarity < FIDELITY_THRESHOLD (e.g. 0.55), flag
    the evidence reference as a semantic misrepresentation.
    """
```

**Logic**:
1. For each evidence ID in `supporting_evidence_ids` and `contradictory_evidence_ids`:
   - Extract the sentence(s) in `hypothesis.reasoning` that mention the evidence ID or its source keywords.
   - Embed both the extracted claim and the actual `evidence.summary` using `bge-m3`.
   - Compute cosine similarity.
   - If similarity is below `FIDELITY_THRESHOLD`, mark the reference as `misrepresented`.
2. Return a `FidelityResult` per hypothesis containing a list of flagged references.

### Phase 2: Integrate Into E6 Scoring

Modify `engines/challenge.py`:
- Add a new rule: `evidence_fidelity` to the `RULE_NAMES` list.
- The rule evaluates to `PASS` if zero references are flagged, `PARTIAL` if one is flagged, `FAIL` if multiple are flagged.
- This mechanically penalizes hypotheses built on misrepresented evidence.

### Phase 3: New Evaluation Dimension

Add **D16: Semantic Fidelity** to the evaluator:
- For each hypothesis, verify that no evidence reference has a fidelity score below threshold.
- Score 1.0 if zero semantic misrepresentations, 0.0 otherwise.

### Phase 4: Adversarial Test Case

Add a test in `tests/test_fidelity.py`:
- Construct a hypothesis where `reasoning` says "inventory levels are dangerously low" but `ev_inventory_001.summary` says "inventory levels are normal and stable".
- Assert the fidelity checker flags this.
- Assert E6 penalizes the hypothesis score accordingly.

---

## Impact Assessment

- **Risk if unfixed**: A semantically hallucinated hypothesis can receive a `HIGH` confidence score, trigger an automated action recommendation, and pass all 15 evaluation dimensions undetected. This is the most dangerous unmitigated failure mode in the system.
- **Remediation complexity**: Medium. The fidelity checker is a new module but reuses existing embedding infrastructure (`bge-m3` via `LLMProvider.embed`).
- **Performance impact**: One additional embedding call per evidence reference per hypothesis. For 3 hypotheses × 3 evidence references = ~9 embedding calls. Latency: ~2-3 seconds total.
