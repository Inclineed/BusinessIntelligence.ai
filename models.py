"""
models.py — Shared data models for BusinessIntelligence.ai.

All enums, dataclasses, and helpers used across the nine-engine pipeline.
Every engine output embeds a MethodTag so provenance is inspectable end-to-end.
Numbers are NEVER produced by LLM-tagged engines; quantitative truth belongs
to SQL / STATS / RULES engines only (Requirements 7.1, 13.1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clamp(v: float, lo: float, hi: float) -> float:
    """Return v clamped to the inclusive range [lo, hi]."""
    return max(lo, min(hi, v))


def validate_weight(v: float) -> float:
    """Return v if it is in [0, 1]; raise ValueError otherwise."""
    if v < 0 or v > 1:
        raise ValueError(
            f"Weight must be in the inclusive range [0, 1]; got {v!r}"
        )
    return v


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class MethodTag(str, Enum):
    """Provenance label attached to every engine output (Requirements 7.1, 13.1)."""

    SQL = "SQL"
    STATS = "STATS"
    ETL = "ETL"
    RULES = "RULES"
    RETRIEVAL = "RETRIEVAL"
    LLM = "LLM"
    LLM_NARRATIVE = "LLM_NARRATIVE"
    RULES_LLM_NARRATIVE = "RULES+LLM_NARRATIVE"
    SIMULATED = "SIMULATED"

    # Set of tags that are permitted to produce numeric fields.
    # Any engine tagged with a value NOT in this set must never emit numbers.
    @classmethod
    def deterministic_tags(cls) -> frozenset["MethodTag"]:
        return frozenset({cls.SQL, cls.STATS, cls.RULES})


class Persona(str, Enum):
    """Presentation lens — analysis is identical across personas."""

    CFO = "cfo"
    ANALYST = "analyst"
    MANAGER = "manager"


class FreshnessStatus(str, Enum):
    """Freshness state reported by the SourceRegistry."""

    FRESH = "fresh"       # elapsed time within SLA
    STALE = "stale"       # elapsed time exceeds SLA
    UNKNOWN = "unknown"   # unavailable or SLA undefined


class AuditVerdict(str, Enum):
    """Deterministic audit result produced by the Challenge_Engine."""

    VERIFIED = "verified"
    MARGINAL = "marginal"
    REJECTED = "rejected"
    ABSTAIN = "abstain"


class EvidenceSufficiencyLevel(str, Enum):
    """Evidence sufficiency levels determined by deduplicated support sum."""

    INSUFFICIENT = "insufficient"
    LIMITED = "limited"
    SUFFICIENT = "sufficient"
    STRONG = "strong"


class RuleVerdict(str, Enum):
    """Single verdict for a Challenge_Engine rule evaluation."""

    PASS = "pass"
    PARTIAL = "partial"
    FAIL = "fail"


class OutcomeType(str, Enum):
    """Distinguishes observed data from simulated projections (Requirement 14)."""

    OBSERVED = "observed"     # from real / replayed data
    SIMULATED = "simulated"   # projected; never causal proof


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SourceRegistryEntry:
    """
    One entry in the Source_Registry, tracking grain, cadence, freshness, and
    data quality for a single data source (Requirements 1.3, 1.5, 1.6).
    """

    source_id: str
    name: str
    grain: str               # e.g. "hourly", "15-min", "daily"
    cadence_minutes: int
    last_refresh: datetime
    sla_minutes: int         # maximum allowed staleness in minutes
    freshness_status: FreshnessStatus
    data_quality: float      # 0.0 – 1.0
    lineage: list[str] = field(default_factory=list)   # upstream table/file refs
    owner: str = ""
    decay_policy: str = "linear"
    temporal_policy: str = "snapshot"

    def __post_init__(self) -> None:
        validate_weight(self.data_quality)


    @property
    def staleness_minutes(self) -> float:
        """
        Minutes elapsed since last_refresh, measured against UTC now.
        Uses datetime.utcnow() so the scenario clock is fixed at load time.
        """
        now = datetime.utcnow()
        delta = now - self.last_refresh
        return delta.total_seconds() / 60.0

    @property
    def is_within_sla(self) -> bool:
        """True when the source's staleness is within its configured SLA."""
        return self.staleness_minutes <= self.sla_minutes


@dataclass
class KPIValue:
    """
    A single connected KPI value stamped with source provenance and freshness
    (Requirements 1.1, 1.4, 2.4).  Method is always SQL — LLMs never compute KPIs.
    """

    kpi_id: str
    name: str
    value: float
    unit: str
    period: str
    dimension_filters: dict[str, str] = field(default_factory=dict)
    source_id: str = ""
    freshness: Optional[FreshnessStatus] = None
    method: MethodTag = MethodTag.SQL


@dataclass
class AnomalySignal:
    """
    Anomaly detection output from the Signal_Engine (Requirements 3.1 – 3.6).
    Guards prevent false alarms from thin history or degraded data quality.
    """

    kpi_id: str
    observed: float
    expected: float
    delta_pct: float          # clamped to [-100.00, 100.00], 2 dp
    z_score: float            # clamped to [-1000.00, 1000.00], 2 dp
    is_anomaly: bool
    corroborated_by: list[str] = field(default_factory=list)   # kpi_ids
    sparse_history: bool = False          # guard: baseline samples < 30
    data_quality_suspect: bool = False    # guard: data-quality score < 0.80
    method: MethodTag = MethodTag.STATS


class BusinessMateriality(str, Enum):
    """
    Business materiality tier distinguishing statistical significance from business impact.
    """
    NEGLIGIBLE = "NEGLIGIBLE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class MaterialityAssessment:
    """
    Translates a statistical AnomalySignal into domain-specific business impact and priority rank.
    """

    kpi_id: str
    observed_value: float
    baseline_mean: float
    z_score: float
    delta_pct: float
    is_statistical_anomaly: bool
    financial_impact: Optional[float] = None
    volume_impact: Optional[float] = None
    business_materiality: BusinessMateriality = BusinessMateriality.NEGLIGIBLE
    priority_rank: int = 0


@dataclass
class DimensionContribution:
    """
    Contribution of a segment within a dimension to a KPI movement
    (Requirements 4.1 – 4.6).  contribution_pct is in [0, 100].
    """

    dimension: str          # "device" | "region" | "channel"
    segment: str            # "android" | "web" | ...
    contribution_pct: float  # share of total movement, [0, 100]
    segment_delta_pct: float
    method: MethodTag = MethodTag.SQL


class TemporalAlignmentPolicy(str, Enum):
    """
    Temporal semantics governing observation normalization over the investigation window.
    Cadence (e.g. hourly, daily) is defined separately.
    No automatic proportional allocation is applied to any grain or semantic type.
    """
    SNAPSHOT = "snapshot"
    PERIOD_TOTAL = "period_total"
    AVERAGE = "average"
    RATE = "rate"
    LAST_KNOWN_VALUE = "last_known_value"


def calculate_reliability_decay(
    base_quality: float,
    staleness_minutes: float,
    sla_minutes: float,
) -> float:
    """
    Continuous linear decay.
    If staleness <= SLA: weight = base_quality
    If staleness > SLA: decays linearly to 0 over the duration of (2 * SLA).

    Note on Replay / Temporal Context:
    staleness_minutes is measured relative to the ingestion clock. When replaying
    historical ExtractionResult fixtures or logs in a different temporal context,
    ensure the reference clock is pinned (e.g. via SourceRegistry.update_last_refresh)
    to avoid artificial decay drift against wall-clock time.
    """
    if sla_minutes <= 0 or base_quality <= 0:
        return 0.0
    if staleness_minutes <= sla_minutes:
        return clamp(base_quality, 0.0, 1.0)

    # Linear decay reaching 0 at 2 * SLA
    staleness_beyond_ratio = (staleness_minutes - sla_minutes) / sla_minutes
    decay_factor = max(0.0, 1.0 - staleness_beyond_ratio)
    return clamp(base_quality * decay_factor, 0.0, 1.0)


@dataclass
class ExtractionResult:
    """Intermediate payload from raw sources before normalization."""
    raw_payload: Any               # SQL row (tuple/dict), JSON (dict), plain text (str)
    source_type: str               # "sql", "vector", "api"
    extracted_at: datetime         # Ingestion timestamp
    raw_identifier: str            # Original PK or chunk ID


@dataclass
class CanonicalEvidenceRecord:
    """
    Canonical evidence record standardizing structured, semi-structured,
    and unstructured data across heterogeneous sources into a unified contract.
    """

    schema_version: str = "1.0"
    id: str = ""
    source_id: str = "test_source"
    source_name: str = ""
    entity: str = ""
    observation: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metric: Optional[str] = None
    dimension: dict[str, str] = field(default_factory=dict)
    value: Optional[float] = None
    # Computed at ingestion time relative to SourceRegistry last_refresh.
    # Note: will drift if replayed without anchoring the scenario clock.
    freshness_minutes: float = 0.0

    source_reliability: float = 1.0   # [0, 1] — freshness-decayed
    confidence: float = 1.0          # [0, 1] — extraction or retrieval relevance
    method: MethodTag = MethodTag.SQL
    lineage: list[str] = field(default_factory=list)
    provenance_hash: str = ""
    raw_ref: str = "raw_ref"
    kind: str = "structured"          # "structured" | "unstructured"

    def __init__(
        self,
        evidence_id: str = "",
        kind: str = "structured",
        summary: str = "",
        source_id: str = "test_source",
        source_name: str = "",
        reliability_weight: Optional[float] = None,
        relevance: Optional[float] = None,
        raw_ref: str = "raw_ref",
        method: MethodTag = MethodTag.SQL,
        id: Optional[str] = None,
        schema_version: str = "1.0",
        entity: str = "",
        observation: str = "",
        timestamp: Optional[datetime] = None,
        metric: Optional[str] = None,
        dimension: Optional[dict[str, str]] = None,
        value: Optional[float] = None,
        freshness_minutes: float = 0.0,
        source_reliability: Optional[float] = None,
        confidence: Optional[float] = None,
        lineage: Optional[list[str]] = None,
        provenance_hash: str = "",
    ) -> None:
        self.schema_version = schema_version
        self.source_id = source_id
        self.source_name = source_name or source_id
        self.entity = entity or source_id
        self.observation = observation or summary
        self.timestamp = timestamp if timestamp is not None else datetime.utcnow()
        self.metric = metric
        self.dimension = dimension or {}
        self.value = value
        self.freshness_minutes = freshness_minutes
        self.kind = kind
        self.raw_ref = raw_ref
        self.method = method
        self.lineage = lineage or []

        # Resolve reliability
        resolved_rel = source_reliability if source_reliability is not None else (
            reliability_weight if reliability_weight is not None else 1.0
        )
        self.source_reliability = validate_weight(clamp(float(resolved_rel), 0.0, 1.0))

        # Resolve confidence
        resolved_conf = confidence if confidence is not None else (
            relevance if relevance is not None else 1.0
        )
        self.confidence = validate_weight(clamp(float(resolved_conf), 0.0, 1.0))

        # Resolve ID
        resolved_id = id if id is not None else (evidence_id if evidence_id else "")
        if resolved_id:
            self.id = resolved_id
        else:
            import hashlib
            raw_id_input = f"{self.raw_ref}:{self.source_id}:{self.timestamp.isoformat()}:{self.entity}:{self.observation}"
            self.id = hashlib.sha256(raw_id_input.encode()).hexdigest()[:16]

        # Resolve Provenance Hash
        if provenance_hash:
            self.provenance_hash = provenance_hash
        else:
            import hashlib
            raw_prov_input = f"{self.schema_version}:{self.source_id}:{self.entity}:{self.observation}:{self.timestamp.isoformat()}:{self.raw_ref}"
            self.provenance_hash = hashlib.sha256(raw_prov_input.encode()).hexdigest()

    @property
    def evidence_id(self) -> str:
        return self.id

    @evidence_id.setter
    def evidence_id(self, val: str) -> None:
        self.id = val

    @property
    def summary(self) -> str:
        return self.observation

    @summary.setter
    def summary(self, val: str) -> None:
        self.observation = val

    @property
    def reliability_weight(self) -> float:
        return self.source_reliability

    @reliability_weight.setter
    def reliability_weight(self, val: float) -> None:
        self.source_reliability = validate_weight(clamp(float(val), 0.0, 1.0))

    @property
    def relevance(self) -> float:
        return self.confidence

    @relevance.setter
    def relevance(self, val: float) -> None:
        self.confidence = validate_weight(clamp(float(val), 0.0, 1.0))


# Alias for backward compatibility
Evidence = CanonicalEvidenceRecord



@dataclass
class EvidenceCitation:
    evidence_id: str
    quoted_summary: str        # copied verbatim from Evidence.summary
    role: Literal["supports", "contradicts", "neutral"]
    relevance_explanation: str # one sentence — must not reference evidence IDs
                               # or assert factual claims about evidence content


@dataclass
class CitationViolation:
    evidence_id: str
    violation_type: Literal[
        "phantom_id",
        "summary_mismatch",
        "duplicate_citation",
    ]
    detail: str = ""


@dataclass
class Hypothesis:
    """
    A hypothesis proposed by the Hypothesis_Engine (LLM), with NO quantitative
    truth in the statement (Requirements 8.1 – 8.7).
    """

    hypothesis_id: str = "H1"                 # e.g. "H1"
    statement: str = ""                       # LLM prose, 1–2000 chars, NO numbers
    mechanism_tag: str = ""                   # explicit structured mechanism tag
    citations: list[EvidenceCitation] = field(default_factory=list)
    reasoning: str = ""                       # 1–5000 chars
    # Narrative prose only. Must not reference evidence IDs or assert
    # what any evidence item says. All evidence references belong in citations.
    method: MethodTag = MethodTag.LLM

    @property
    def supporting_evidence_ids(self) -> list[str]:
        return [c.evidence_id for c in self.citations if c.role == "supports"]

    @property
    def contradictory_evidence_ids(self) -> list[str]:
        return [c.evidence_id for c in self.citations if c.role == "contradicts"]


@dataclass
class RuleResult:
    """
    Outcome of a single rule evaluation inside the Challenge_Engine
    (Requirement 9.1).
    """

    rule_name: str     # "timeline" | "segment_alignment" | "kpi_corroboration" |
                       # "mechanism_consistency" | "contradiction"
    verdict: RuleVerdict
    rationale: str


@dataclass
class ScoredHypothesis:
    """
    A hypothesis after deterministic constraint auditing by the Challenge_Engine
    (Requirements 9.1 – 9.8).  final_audit_score is clamped to [0, 1].
    narrative (LLM_NARRATIVE) never mutates final_audit_score or audit_verdict.
    """

    hypothesis_id: str
    rule_results: list[RuleResult] = field(default_factory=list)
    support_score: float = 0.0
    contradiction_score: float = 0.0
    rule_score: float = 0.0
    final_audit_score: float = 0.0          # clamped [0, 1]
    audit_verdict: AuditVerdict = AuditVerdict.REJECTED
    evidence_sufficiency_score: float = 0.0
    evidence_sufficiency_level: EvidenceSufficiencyLevel = EvidenceSufficiencyLevel.INSUFFICIENT
    narrative: str = ""               # optional LLM_NARRATIVE; never alters score
    method: MethodTag = MethodTag.RULES
    disqualification_reason: Optional[str] = None
    violations: list[CitationViolation] = field(default_factory=list)
    unaligned_evidence_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.final_audit_score = clamp(self.final_audit_score, 0.0, 1.0)

    @property
    def verdict(self) -> AuditVerdict:
        return self.audit_verdict

    @property
    def confidence(self) -> AuditVerdict:
        return self.audit_verdict



# Alias for backward/test compatibility
HypothesisScore = ScoredHypothesis


@dataclass(frozen=True)
class StructuredActionRecommendation:
    """
    Deterministic, structured operational decision record (Requirement 10.x).
    Enforces strict provenance for all governance fields.
    """
    driver: str
    controllable_lever: str
    action: str
    expected_impact: str
    owner: str
    confidence: float
    monitoring_plan: str
    authorized_personas: list[str]


@dataclass(frozen=True)
class Decision:
    """
    Recommended action (or abstention) produced by the Decision_Engine
    (Requirements 10.1 – 10.6, 11.3, 12.6).
    When abstained=True, recommended_action MUST be None.
    """

    abstained: bool
    recommended_action: Optional[str]
    verification_metric: Optional[str]
    winning_hypothesis_id: Optional[str]
    persona_narrative: str
    abstention_reason: Optional[str] = None   # "low_confidence" | "provider_unavailable" | "unauthorized_lever_selected" | "persona_not_authorized_for_lever"
    structured_recommendation: Optional[StructuredActionRecommendation] = None
    method: MethodTag = MethodTag.LLM

    def __post_init__(self) -> None:
        if self.abstained and self.recommended_action is not None:
            raise ValueError(
                "Decision.recommended_action must be None when abstained=True "
                "(Property 6 / Requirement 10.1)"
            )


@dataclass
class OutcomeProjection:
    """
    A SIMULATED outcome projection produced by the Outcome_Engine
    (Requirements 14.1 – 14.6).  outcome_type MUST be SIMULATED for the MVP.
    """

    outcome_type: OutcomeType       # SIMULATED for MVP
    projected_metric: str
    projected_recovery_pct: float
    disclaimer: str                 # "not causal proof"
    recovery_window_hours: Optional[float] = None
    mean_time_to_normalcy: Optional[str] = None
    assumptions: list[str] = field(default_factory=list)
    method: MethodTag = MethodTag.SIMULATED

    def __post_init__(self) -> None:
        if self.method != MethodTag.SIMULATED:
            raise ValueError(
                "OutcomeProjection.method must be MethodTag.SIMULATED "
                "(Requirement 14.1)"
            )


@dataclass
class Telemetry:
    """
    Per-investigation runtime telemetry captured by the Telemetry_Service
    (Requirements 16.1 – 16.7).
    external_cost_usd is always 0.00 for local Ollama execution.
    equivalent_cloud_cost_usd is None when the rate table lacks the model.
    """

    llm_calls: int = 0
    llm_tokens_in: int = 0
    llm_tokens_out: int = 0
    latency_ms_by_engine: dict[str, float] = field(default_factory=dict)
    external_cost_usd: float = 0.0
    equivalent_cloud_cost_usd: Optional[float] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    rate_limit_events: int = 0



@dataclass
class InvestigationResult:
    """
    The complete output of one pipeline run, returned by the Orchestrator
    (Requirements 13.5, 16.7).
    method_ownership maps each engine name to its MethodTag(s).
    """

    scenario_id: str
    persona: Persona
    signals: list[AnomalySignal] = field(default_factory=list)
    materiality: list[MaterialityAssessment] = field(default_factory=list)
    contributions: list[DimensionContribution] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    scored: list[ScoredHypothesis] = field(default_factory=list)
    decision: Optional[Decision] = None
    outcome: Optional[OutcomeProjection] = None
    precedents: list[Any] = field(default_factory=list)
    telemetry: Telemetry = field(default_factory=Telemetry)
    method_ownership: dict[str, list[MethodTag]] = field(default_factory=dict)


class FeedbackVerdict(str, Enum):
    CORRECT = "CORRECT"                      # Root cause, confidence, and action fully verified
    INCORRECT = "INCORRECT"                  # Root cause or mechanism is erroneous
    PARTIALLY_CORRECT = "PARTIALLY_CORRECT"  # Mechanism plausible but action/confidence requires adjustment
    UNSURE = "UNSURE"                        # Insufficient domain context to confirm or refute


@dataclass
class StructuredFeedbackSubmission:
    """Input submission payload for analyst/user feedback on an investigation."""

    investigation_id: str
    scenario_id: str
    verdict: FeedbackVerdict
    persona: str = "analyst"
    corrected_hypothesis_id: Optional[str] = None
    corrected_audit_verdict: Optional[str] = None
    corrected_action: Optional[str] = None
    evidence_grounding_correct: Optional[bool] = None
    analyst_notes: Optional[str] = None


@dataclass
class StructuredFeedbackRecord(StructuredFeedbackSubmission):
    """Persisted feedback record with database metadata and validation state."""

    feedback_id: int = 0
    received_at: str = ""
    validated_precedent: bool = False
    validation_precedent_id: Optional[str] = None

