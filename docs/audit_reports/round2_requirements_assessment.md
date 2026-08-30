## Current Implementation vs Round 2 Requirements

Based on the current E1–E9 architecture, backend engines, frontend workspaces, RBAC, evidence layer, feedback loop, vector memory, and runtime instrumentation, the prototype is substantially complete at the core reasoning level. The remaining work is concentrated around **materiality, heterogeneous-data normalization/reconciliation, explicit method transparency, decision structure, runtime economics, business generalization, and visible demonstration of capabilities that already exist.**

### Status definitions

* **BUILT** — capability is implemented and functionally represented in the current architecture.
* **PARTIAL** — core capability exists, but an important requirement or explicit demonstration is still missing.
* **MISSING** — capability is not currently implemented.
* **DEMO GAP** — underlying capability exists, but the judging/demo experience does not yet visibly prove it.

---

# 1. Detect & Prioritise Material KPI Movements

**Status: PARTIAL**

### Already built

* E1 KPI storage and baseline calculation.
* Historical mean / standard deviation.
* E2 deterministic anomaly detection.
* ±3σ anomaly guard.
* Sparse-baseline guard.
* Data-quality guard.
* Time-series corridor detection.
* KPI movement detection is therefore **statistically grounded rather than LLM-generated**.

### Remaining

The brief explicitly distinguishes **statistical significance** from **business materiality**.

The current system determines whether a KPI is anomalous, but it should additionally determine whether the movement is **material to the business**.

Add a business-impact/materiality layer such as:

```text
Statistical significance
        +
Business impact
        +
Decision relevance
        ↓
Materiality score
```

Example:

```text
KPI movement: -8.4%
Statistical anomaly: YES
Revenue impact: -₹1.8M
Customers affected: 14,200
Operational severity: HIGH

Materiality: CRITICAL
```

The materiality layer should be configurable by business and KPI rather than hardcoded.

### Recommended addition

A canonical output:

```text
observed_change
statistical_significance
financial_impact
volume_impact
business_materiality
priority
```

This is a genuine analytical gap, not merely a UI enhancement.

---

# 2. Reconcile Data Across Heterogeneous Sources

**Status: PARTIAL — HIGH PRIORITY**

### Already built

E4 already combines multiple heterogeneous sources:

* orders
* payment gateway events
* support tickets
* inventory
* release notes
* deployment logs
* ChromaDB vector evidence

There is also:

* source reliability configuration
* SLA information
* freshness/reliability weighting
* SQL + vector retrieval.

### What has not been explicitly demonstrated

The brief specifically calls out:

* different grains
* different refresh cadences
* different historical coverage
* inconsistent data quality.

The current prototype must explicitly show a case such as:

```text
Revenue                    DAILY
Payment failures           HOURLY
Deployment logs             EVENT
Support tickets             EVENT
Inventory                   DAILY
```

being reconciled into one investigation timeline.

### Additional capability that should be added

The platform should have an explicit **data normalization and reconciliation layer** before evidence reasoning.

It should handle:

```text
schema normalization
entity normalization
metric mapping
timestamp normalization
timezone normalization
grain alignment
refresh/freshness alignment
missing-data handling
source conflict resolution
semantic mapping
```

### Important overlooked requirement

The system should not only retrieve heterogeneous data; it should demonstrate how heterogeneous data becomes **common, machine-usable evidence**.

For example:

```text
Unstructured deployment note
        ↓
extract deployment event
        ↓
normalize timestamp / service / release
        ↓
structured evidence object
        ↓
join with SQL telemetry
```

The canonical evidence model should contain at minimum:

```text
entity
event / observation
timestamp
metric
dimension
value
source
freshness
confidence
method
lineage
```

This is important for making the engine genuinely reusable across businesses.

---

# 3. Identify & Rank Explanatory Drivers

**Status: BUILT, WITH TRANSPARENCY GAP**

### Already built

* E3 dimensional contribution analysis.
* Segment slicing.
* Contribution percentages.
* E5 generation of competing hypotheses.
* H1 / H2 / H3 ranking.
* E6 deterministic verification.
* Timeline consistency.
* Segment alignment.
* KPI corroboration.
* Mechanism plausibility.
* Contradiction penalties.

This is one of the strongest parts of the system.

### Remaining

The UI must explicitly identify **how each conclusion was obtained**.

For every important driver/evidence item, expose:

```text
Method:
SQL
Statistics
Business Rule
Vector Retrieval
LLM
```

Example:

```text
Driver: Payment Gateway PG-07

Contribution: 63%
Method: SQL contribution analysis
Evidence: payment_events
Freshness: 4 min
Confidence: 0.94
```

For hypotheses:

```text
H1
Generated by: LLM
Validated by: deterministic E6 rules
Evidence support: 6
Contradictions: 1
Final confidence: 0.78
```

This directly satisfies the requirement that the system distinguish deterministic logic, SQL, retrieval, statistics, and LLM reasoning.

---

# 4. Persona-Specific Narratives With Traceable Evidence

**Status: BUILT, WITH DEMO GAP**

### Already built

* Analyst persona.
* CFO persona.
* Manager persona.
* RBAC restrictions.
* Server-side access enforcement.
* E4 evidence provenance.
* SHA-256 provenance hashing.
* E7 decision narrative.

### Remaining

The distinction must exist in the **narrative itself**, not only in accessible data.

The same investigation should produce different outputs:

```text
ANALYST
Technical root cause
segments
deployment evidence
gateway details
diagnostic depth

CFO
revenue impact
financial exposure
expected recovery
business risk

MANAGER
affected operating region
controllable lever
recommended operational action
owner
monitoring requirement
```

The system should therefore have a persona-aware narrative contract:

```text
persona
allowed_information
narrative_depth
language_level
decision_rights
recommended_action_scope
```

This should be demonstrated explicitly.

---

# 5. Communicate Uncertainty & Abstain

**Status: BUILT, WITH DEMO GAP**

### Already built

E6 has:

* confidence scoring
* five verification rules
* contradiction penalties
* evidence sufficiency checks
* autonomous ABSTAIN behavior
* low-confidence handling.

Sparse-history protection is also present.

### Remaining

Create one guaranteed demo scenario where the system explicitly says:

```text
INSUFFICIENT EVIDENCE

Confidence: 0.41

Conflicting evidence detected:
- Timeline mismatch
- Segment evidence inconclusive

DECISION:
ABSTAIN
```

The UI should explain **why** it abstained, not simply display an "ABSTAIN" label.

Recommended uncertainty object:

```text
confidence
evidence_coverage
contradiction_count
missing_evidence
abstention_reason
recommended_next_information
```

A particularly strong implementation would tell the user **what evidence would resolve the uncertainty**.

---

# 6. Recommend Actions Using the Required Decision Structure

**Status: PARTIAL — HIGH PRIORITY**

### Already built

* E7 operational decision engine.
* Action directives.
* E8 counterfactual/recovery projection.
* Expected economic impact.
* Recovery trajectory.

### Missing

The Round 2 brief explicitly specifies:

```text
driver
→ controllable lever
→ action
→ expected impact
→ owner
→ confidence
→ monitoring plan
```

The current output is primarily narrative-based.

Convert E7 into a structured action contract:

```json
{
  "driver": "...",
  "controllable_lever": "...",
  "action": "...",
  "expected_impact": "...",
  "owner": "...",
  "confidence": 0.84,
  "monitoring_plan": "..."
}
```

### Important additional concept

The recommendation must respect **decision rights**.

For example:

```text
CFO
→ approve pricing / financial action

Operations Manager
→ reroute traffic / change inventory allocation

Engineering
→ rollback deployment / invalidate cache
```

The system should not recommend actions that a persona is not authorized to execute.

---

# 7. Learn From Analyst / Business User Feedback

**Status: BUILT, WITH PROOF GAP**

### Already built

* E9 institutional memory.
* ChromaDB precedent storage.
* Precedent matching.
* Human feedback.
* Analyst validation.
* Precedent retrieval boosting.
* Feedback persistence.

### Remaining

Demonstrate an actual:

```text
investigation
   ↓
analyst feedback
   ↓
feedback stored
   ↓
precedent updated
   ↓
future similar investigation
   ↓
changed ranking / recommendation
```

The important distinction is:

> "We store feedback"

versus:

> "The system's future behavior changes because of feedback."

The second is what should be demonstrated.

### Recommended metric

Track:

```text
human_agreement_rate
feedback_corrections
precedent_validation_rate
post-feedback improvement
```

---

# 8. Security, Cost, Latency & Scalability

**Status: PARTIAL**

### Security — largely BUILT

Current architecture includes:

* Analyst access.
* CFO restricted aggregation.
* Manager regional scope.
* server-side authorization.
* field-level restrictions.

### Remaining security proof

The demo should visibly show:

```text
Allowed field
Restricted field
Masked field
```

Example:

```text
CFO

Revenue       ₹12.4M
SKU           [RESTRICTED]
Customer ID   [RESTRICTED]
Region        APAC
```

The system should also maintain **auditability**:

```text
who
accessed
what
when
under which role
```

### Cost — PARTIAL

Need:

```text
LLM calls
input tokens
output tokens
total tokens
model used
estimated cost
```

per investigation.

### Latency — PARTIAL

Already visible at a high level.

Improve by exposing:

```text
E1 latency
E2 latency
E3 latency
E4 retrieval latency
E5 LLM latency
E6 latency
E7 LLM latency
E8 latency
E9 latency

TOTAL
```

### Scalability — NOT SUFFICIENTLY DEMONSTRATED

The prototype does not yet clearly demonstrate:

* concurrent investigations
* caching
* batching
* async processing
* model fallback under load
* database connection scaling
* vector-search scaling.

These need not all be implemented for the hackathon, but the architecture should explain how the system scales.

A reasonable prototype explanation is:

```text
Stateless E1–E8 execution
+
shared provider infrastructure
+
connection pooling
+
cached retrieval / embeddings
+
asynchronous investigation execution
+
provider fallback
```

---

# 9. Minimum Prototype Checklist

## 3–5 connected KPIs across 2–3 sources and different grains/cadences

**Status: PARTIAL**

The project has sufficient KPIs and sources, but the demo must explicitly show different grain/cadence reconciliation.

---

## Lightweight KPI / Semantic Contract

**Status: BUILT, WITH VISIBILITY GAP**

`kpi_contracts.yaml` already defines:

* KPI definitions.
* formulas.
* drivers.
* thresholds.
* lineage.
* access restrictions.

However, this should be surfaced through the UI.

Recommended:

```text
KPI CONTRACT

Definition
Formula
Grain
Refresh cadence
Drivers
Threshold
Business impact rule
Source lineage
Access policy
```

---

## ≥2 Personas With Different Narratives / Actions

**Status: BUILT, WITH DEMO GAP**

Technically supported.

Need visible narrative differentiation.

---

## Multi-Factor KPI Movement

**Status: BUILT**

E3 + E5 + E6 cover this well.

---

## Low-Confidence / Abstain Scenario

**Status: BUILT, WITH DEMO GAP**

Need one deterministic, repeatable demo scenario.

---

## Sparse-History / Newly Launched KPI

**Status: PARTIAL**

The `<30 samples` guard exists, but there should be a dedicated scenario such as:

```text
NEW KPI: Product Launch Conversion

Observations: 17
Baseline requirement: 30

Status:
INSUFFICIENT HISTORY

Decision:
ABSTAIN
```

---

## Role-Based Security Scenario

**Status: BUILT, WITH DEMO GAP**

Demonstrate actual masking / restricted fields, not just persona switching.

---

## Evidence: Freshness, Method, Contribution, Confidence & Lineage

**Status: PARTIAL**

Current evidence already provides significant provenance capability.

Complete each evidence object with:

```text
source
source_timestamp
freshness
method
contribution
confidence
lineage
provenance_hash
```

---

# 10. LLM vs Non-LLM Processing

**Status: MISSING AS A VISIBLE PRODUCT CONCEPT — HIGHEST PRIORITY**

The architecture already separates these responsibilities, but the system currently does not make this distinction explicit enough.

Every E-stage should declare its computational method.

Example:

```text
E1 SIGNAL
DETERMINISTIC
SQL + statistics

E2 ANOMALY
DETERMINISTIC
statistical rules

E3 DIAGNOSTIC
DETERMINISTIC
SQL contribution analysis

E4 EVIDENCE
HYBRID
SQL + vector retrieval

E5 HYPOTHESIS
LLM
hypothesis synthesis

E6 CHALLENGE
DETERMINISTIC
5 verification rules

E7 DECISION
HYBRID
business rules + LLM synthesis

E8 OUTCOME
DETERMINISTIC
scenario simulation

E9 MEMORY
RETRIEVAL + FEEDBACK
vector similarity + human validation
```

This should be visible directly in the UI.

Also show **why** the LLM is used:

```text
LLM:
semantic synthesis / hypothesis generation / narrative generation

NOT LLM:
KPI truth / anomaly thresholds / contribution calculations /
verification rules / financial calculations
```

This is central to the brief.

---

# 11. Runtime Telemetry

**Status: PARTIAL**

Current latency monitoring is useful, but complete the required telemetry:

```text
Investigation ID
Total latency
SQL queries
Vector searches
LLM calls
Model(s)
Input tokens
Output tokens
Total tokens
Estimated cost
Cache hits
Cache misses
```

A compact investigation-level summary should be visible:

```text
RUNTIME

Latency          1.84s
LLM calls        2
Tokens           5.3K
Estimated cost   $0.0038
Cache hit        YES
```

---

# 12. Heterogeneous Data Ingestion & Normalization

**Status: NOT EXPLICITLY IMPLEMENTED AS A FIRST-CLASS LAYER**

This requirement is broader than simply having multiple sources.

The platform should be able to accept:

### Structured

```text
SQL
CSV
Excel
warehouse tables
```

### Semi-structured

```text
JSON
API payloads
event streams
application logs
```

### Unstructured

```text
PDFs
documents
release notes
support tickets
emails
incident reports
engineering notes
```

These should be converted into a common canonical evidence representation.

For example:

```text
Unstructured document
        ↓
entity / event extraction
        ↓
timestamp extraction
        ↓
semantic normalization
        ↓
structured evidence
        ↓
E4
```

The E1–E9 engine should remain business-agnostic while business-specific mappings/configuration define the semantics.

---

# 13. Business Generalization / Replicability

**Status: PARTIAL**

The platform should not be treated as a retail-only application.

The correct architecture is:

```text
BUSINESS-AGNOSTIC E1–E9 ENGINE
              +
BUSINESS-SPECIFIC CONFIGURATION
```

Business-specific configuration should contain:

```text
KPI definitions
source mappings
drivers
dimensions
thresholds
business rules
personas
decision rights
semantic mappings
scenario definitions
evidence sources
evaluation ground truth
```

A new business should therefore require **configuration and data onboarding rather than rewriting E1–E9**.

Remove hardcoded retail assumptions from the reusable reasoning layer.

---

# 14. KPI Semantic Governance

**Status: PARTIAL**

The KPI contract exists, but the broader semantic-governance layer is not fully explicit.

The system should account for:

```text
KPI definition
calculation
grain
time window
dimensions
hierarchy
business calendar
timezone
currency
source lineage
threshold
materiality rule
authorized personas
```

This is especially important because the brief explicitly warns about:

* inconsistent KPI definitions
* different hierarchies
* different calendars
* aggregation differences.

---

# 15. Data Quality & Trust Layer

**Status: PARTIAL**

Existing guards are strong:

* incomplete ingestion protection
* sparse history protection
* source reliability
* freshness/SLA weighting.

The broader platform should also explicitly handle:

```text
missing data
duplicate records
late-arriving data
schema drift
unexpected nulls
source conflicts
stale data
partial ingestion
```

and communicate their effect on confidence.

Example:

```text
Source reliability: 0.71

Reason:
25% of expected events missing

Impact:
confidence reduced by 0.12
```

---

# 16. Contradictory Evidence Resolution

**Status: PARTIAL / BUILT AT VERIFICATION LEVEL**

E6 already penalizes contradictions.

Extend this so the evidence layer explicitly represents:

```text
supporting evidence
contradicting evidence
source reliability
timestamp consistency
confidence
```

The system should be able to say:

```text
Evidence A supports H1
Evidence B contradicts H1

Because Evidence B is fresher and more reliable,
H1 confidence is reduced.
```

That would make the uncertainty mechanism much more credible.

---

# 17. Causal Inference vs LLM Hypothesis Generation

**Status: NEEDS CLARIFICATION**

E5 currently generates causal hypotheses, but this should not be presented as formal causal inference unless an actual causal methodology is implemented.

The architecture should clearly distinguish:

```text
Correlation / contribution
        ≠
Causal inference
        ≠
LLM-generated causal hypothesis
```

A defensible description is:

```text
E3:
observational contribution analysis

E5:
candidate causal hypothesis generation

E6:
evidence-based challenge / validation

E7:
decision recommendation
```

If formal causal inference is not implemented, do not claim that it is.

---

# 18. Forecasting / Expected Recovery

**Status: BUILT FOR THE CURRENT USE CASE, BUT LIMITED IN SCOPE**

E8 already produces:

* recovery projections
* revenue impact
* time-to-recovery.

The system could later incorporate formal forecasting models, but forecasting is not currently a central missing requirement unless the team chooses to position it as one.

---

# 19. Continuous Evaluation & Drift

**Status: PARTIAL**

The project already has:

* operational health evaluation.
* latency monitoring.
* abstention monitoring.
* human agreement.
* citation violation metrics.
* benchmark evaluation.

The remaining opportunity is to make evaluation clearly business-specific and expose:

```text
precision
recall
abstention compliance
citation accuracy
human agreement
latency
cost
model drift
data drift
```

The system should distinguish:

```text
Data drift
Model drift
Business/KPI drift
Operational drift
```

and indicate which layer is responsible.

---

# 20. Auditability

**Status: PARTIAL / STRONG FOUNDATION**

Already present:

* evidence provenance.
* SHA-256 hashing.
* feedback records.
* investigation history.

Complete the audit trail across:

```text
input
→ normalization
→ KPI calculation
→ anomaly detection
→ evidence retrieval
→ hypothesis generation
→ challenge
→ decision
→ action
→ feedback
```

An investigation should be reproducible from its stored inputs and configuration.

---

# 21. What Was Not Explicitly Considered Before

The following capabilities should be added to the requirements review because they naturally follow from the Round 2 brief and the intended product architecture:

### A. Data normalization / canonical evidence model

Different systems should be translated into common entities, events, metrics and dimensions before reasoning.

### B. Grain and time reconciliation

Hourly, daily and event-level information must be aligned without silently producing invalid aggregations.

### C. Business calendar / timezone / currency handling

A KPI engine must not assume all businesses operate in UTC or use the same business calendar.

### D. Source conflict resolution

Different sources may disagree. The engine needs a reliability/recency hierarchy.

### E. Decision-right-aware recommendations

The system should recommend actions that are appropriate for the current persona and authority.

### F. Recommendation monitoring

After recommending an action, the system should track whether the KPI actually recovered.

This creates:

```text
recommend
→ execute
→ monitor
→ compare expected vs actual
→ learn
```

### G. Action effectiveness learning

E9 should eventually learn not only which hypothesis was correct, but:

```text
which action worked
how quickly it worked
under which conditions
```

### H. Cache / cost optimization

The brief explicitly mentions caching and cost per insight.

Potential mechanisms:

```text
embedding cache
evidence retrieval cache
investigation result cache
LLM response reuse
model routing by task
```

### I. Model routing

Different tasks do not necessarily require the same model.

For example:

```text
simple extraction → smaller/cheaper model
complex hypothesis generation → stronger model
local/private evidence → Ollama
high-latency-sensitive synthesis → Groq
```

### J. Human-in-the-loop escalation

Instead of only:

```text
CONFIDENT
ABSTAIN
```

support:

```text
CONFIDENT → execute/recommend
UNCERTAIN → request more evidence
CONFLICTED → human review
```

This would make the operational workflow more realistic.

---

# Final Gap Prioritisation

## P0 — Required Before Final Demo

1. **Visible LLM vs non-LLM method classification.**
2. **Business-impact materiality score.**
3. **Explicit heterogeneous-grain/cadence reconciliation demo.**
4. **Structured 7-field action recommendation.**
5. **Token + estimated cost telemetry.**
6. **Visible abstention scenario.**
7. **Visible sparse-history scenario.**
8. **Persona-specific narrative/action differences.**
9. **Evidence freshness + method + lineage metadata.**

## P1 — Strongly Recommended

10. **Explicit unstructured → structured evidence extraction.**
11. **Canonical evidence model.**
12. **Business-generalized configuration boundary.**
13. **Visible field-level security/masking.**
14. **Feedback → reinvestigation → changed behavior demonstration.**
15. **Decision-right-aware recommendations.**
16. **Source conflict handling.**
17. **Data quality impact on confidence.**
18. **Post-action monitoring / effectiveness loop.**

## P2 — Valuable but Not Essential for the Prototype

19. Formal causal inference.
20. Advanced forecasting.
21. Full model/data drift remediation.
22. Advanced caching infrastructure.
23. Dynamic model routing.
24. Large-scale concurrent execution.
25. Production-grade data connectors for every possible source type.

---

# Final Assessment

The project is **not missing the core intelligence engine**. E1–E9 already cover the central detect → diagnose → evidence → hypothesize → challenge → decide → simulate → learn loop.

The largest remaining issue is that several capabilities exist internally but are not yet **explicitly surfaced, structured, or demonstrated** in the way the Round 2 brief expects.

The highest-value remaining work is therefore:

```text
Heterogeneous data
        ↓
Normalize / reconcile
        ↓
Quantitative KPI truth
        ↓
Materiality
        ↓
Driver contribution
        ↓
Evidence + provenance
        ↓
Hypotheses
        ↓
Deterministic challenge
        ↓
Persona-specific decision
        ↓
7-field action
        ↓
Counterfactual
        ↓
Monitor outcome
        ↓
Human feedback
        ↓
Institutional memory
```

The final product should make one principle obvious:

> **The LLM is not the intelligence source of truth. It is one component inside a governed analytical and decision system.**

The deterministic/statistical/SQL components establish what happened; heterogeneous evidence explains context; the LLM helps formulate and communicate hypotheses and decisions; verification controls uncertainty; and feedback closes the learning loop.

For business generalization, the reusable architecture should be:

```text
          BUSINESS-AGNOSTIC E1–E9
                    +
       BUSINESS-SPECIFIC CONFIGURATION
                    +
        BUSINESS-SPECIFIC DATA / EVIDENCE
```

A new business should therefore be onboardable by defining its KPIs, sources, semantics, drivers, policies, personas, evidence mappings, and evaluation scenarios — **not by rewriting the core engine**.
