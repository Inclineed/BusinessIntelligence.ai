import { InvestigationResult } from "../types/investigation"

export interface ScenarioCatalogItem {
  id: string
  label: string
  domain: string
  description: string
  status: string
}

export const SCENARIO_CATALOG: ScenarioCatalogItem[] = [
  {
    id: "INC_001",
    label: "Payment Gateway Latency Regression",
    domain: "E-Commerce Checkout",
    description: "Checkout v4.3 deploy caused connection pool exhaustion in payment gateway client.",
    status: "live",
  },
  {
    id: "INC_002",
    label: "Simultaneous Conflicting Causes",
    domain: "E-Commerce Marketing",
    description: "Simultaneous gateway latency spike and aggressive competitor discount campaign.",
    status: "live",
  },
  {
    id: "INC_003",
    label: "Sparse Baseline History",
    domain: "E-Commerce Growth",
    description: "New Premium KPI has only 12 days of history (<14d required). Anomaly detection suppressed.",
    status: "live",
  },
  {
    id: "INC_004",
    label: "ETL Ingestion Pipeline Delay",
    domain: "Data Engineering",
    description: "Delayed batch data warehouse sync causing apparent revenue plunge.",
    status: "live",
  },
  {
    id: "INC_005",
    label: "Seasonal Demand Pattern",
    domain: "E-Commerce Demand",
    description: "Normal cyclical demand pattern within expected ±0.45σ corridor. No operational anomaly.",
    status: "live",
  },
  {
    id: "INC_006",
    label: "Compound Network & Deploy Failure",
    domain: "Platform Infrastructure",
    description: "Upstream WAN packet loss compounded by un-jittered client retry storm.",
    status: "live",
  },
  {
    id: "INC_007",
    label: "Gradual Worker Memory Leak",
    domain: "Backend Compute",
    description: "Memory buffer exhaustion drift over 48 hours across background worker cluster.",
    status: "live",
  },
  {
    id: "INC_008",
    label: "Enterprise SAML SSO Outage",
    domain: "Enterprise Security",
    description: "Identity provider certificate rotation failure blocking enterprise login.",
    status: "live",
  },
]

export const DEFAULT_INC_001: InvestigationResult = {
  scenario_id: "INC_001",
  persona: "analyst",
  signals: [
    {
      kpi_id: "gateway_latency_15min",
      observed: 612,
      expected: 180,
      delta_pct: 240.0,
      z_score: 4.88,
      is_anomaly: true,
      method: "STATS",
    },
    {
      kpi_id: "hourly_conversion",
      observed: 2.1,
      expected: 3.8,
      delta_pct: -44.7,
      z_score: -3.62,
      is_anomaly: true,
      method: "STATS",
    },
    {
      kpi_id: "hourly_revenue",
      observed: 41230,
      expected: 74500,
      delta_pct: -44.6,
      z_score: -3.55,
      is_anomaly: true,
      method: "STATS",
    },
    {
      kpi_id: "payment_error_rate",
      observed: 8.4,
      expected: 0.4,
      delta_pct: 2000.0,
      z_score: 5.12,
      is_anomaly: true,
      method: "STATS",
    },
  ],
  contributions: [
    { dimension: "device", segment: "mobile_web", contribution_pct: 54.2, segment_delta_pct: 280.0, method: "STATS" },
    { dimension: "device", segment: "desktop", contribution_pct: 32.1, segment_delta_pct: 195.0, method: "STATS" },
    { dimension: "channel", segment: "direct", contribution_pct: 13.7, segment_delta_pct: 140.0, method: "STATS" },
  ],
  evidence: [
    {
      evidence_id: "EV_v43_deployment",
      source_id: "deployment_log",
      method: "RETRIEVAL",
      relevance: 0.96,
      reliability_weight: 1.0,
      summary: "Production deployment of checkout-service:v4.3 completed at 14:15 UTC. Change log indicates updated HTTP client connection timeout and connection pooling limits.",
      raw_ref: "deployments_prod.log#line-4482",
    },
    {
      evidence_id: "EV_payment_pool_exhaustion",
      source_id: "payment_gateway",
      method: "SQL",
      relevance: 0.98,
      reliability_weight: 0.99,
      summary: "Payment client active connection pool utilization reached 100% (50/50 active connections) starting at 14:18 UTC, causing HTTP 504 Gateway Timeouts.",
      raw_ref: "pg_stat_activity WHERE app_name = 'checkout_v43'",
    },
    {
      evidence_id: "EV_checkout_timeout_tickets",
      source_id: "support_tickets",
      method: "RETRIEVAL",
      relevance: 0.88,
      reliability_weight: 0.90,
      summary: "42 customer support tickets submitted between 14:20 and 14:35 UTC reporting checkout spinner freezing during the final payment confirmation step.",
      raw_ref: "zendesk_tickets_queue_tier1",
    },
  ],
  hypotheses: [
    {
      hypothesis_id: "H1",
      statement: "Payment gateway latency spike is driven by connection pool exhaustion introduced in the Checkout Service v4.3 release at 14:15 UTC.",
      supporting_evidence_ids: ["EV_v43_deployment", "EV_payment_pool_exhaustion", "EV_checkout_timeout_tickets"],
      contradictory_evidence_ids: [],
    },
    {
      hypothesis_id: "H2",
      statement: "Upstream third-party payment provider infrastructure outage is degrading global transaction response times.",
      supporting_evidence_ids: [],
      contradictory_evidence_ids: ["EV_payment_pool_exhaustion"],
    },
    {
      hypothesis_id: "H3",
      statement: "Organic seasonal traffic surge overwhelmed database read replicas during an uncoordinated flash marketing campaign.",
      supporting_evidence_ids: [],
      contradictory_evidence_ids: ["EV_v43_deployment"],
    },
  ],
  scored: [
    {
      hypothesis_id: "H1",
      support_score: 0.90,
      contradiction_penalty: 0.0,
      final_score: 0.90,
      confidence_state: "HIGH",
      rule_results: [
        { rule_name: "timeline", verdict: "pass", rationale: "Deploy at 14:15 strictly precedes 14:18 latency spike." },
        { rule_name: "segment_alignment", verdict: "pass", rationale: "Pool exhaustion affects all checkout traffic uniformly across segments." },
        { rule_name: "kpi_corroboration", verdict: "pass", rationale: "Corroborated by concurrent revenue (-44.6%) and conversion (-44.7%) plunge." },
        { rule_name: "mechanism_consistency", verdict: "pass", rationale: "Pool exhaustion directly produces 504 timeouts." },
        { rule_name: "contradiction", verdict: "pass", rationale: "No contradictory telemetry found." },
      ],
    },
    {
      hypothesis_id: "H2",
      support_score: 0.49,
      contradiction_penalty: 0.35,
      final_score: 0.14,
      confidence_state: "LOW",
      rule_results: [
        { rule_name: "timeline", verdict: "partial", rationale: "External status page reported green across all availability zones." },
        { rule_name: "contradiction", verdict: "fail", rationale: "Contradicted by local pool saturation errors." },
      ],
    },
    {
      hypothesis_id: "H3",
      support_score: 0.32,
      contradiction_penalty: 0.25,
      final_score: 0.07,
      confidence_state: "LOW",
      rule_results: [
        { rule_name: "mechanism_consistency", verdict: "fail", rationale: "Total platform order volume is flat (-1.2%) compared to expected baseline." },
      ],
    },
  ],
  decision: {
    winning_hypothesis_id: "H1",
    recommended_action: "Roll back Checkout Service from v4.3 to v4.2 immediately to restore database connection pool capacity.",
    verification_metric: "Monitor gateway latency p95: ensure drop below 200 ms within 5 minutes post-rollback.",
    persona_narrative: "Checkout v4.3 deployment at 14:15 UTC exhausted payment gateway connections, degrading conversion by 44.7%. Immediate rollback to v4.2 is recommended.",
    abstained: false,
  },
  outcome: {
    projected_recovery_pct: 88.0,
    projected_metric: "gateway_latency_15min",
    disclaimer: "Model-generated recovery projection based on historical deployment rollback rebound curves — not empirical evidence.",
  },
  precedents: [
    {
      scenario_id: "INC_001_HIST_Q3",
      relevance: 0.92,
      retrieval_score: 0.92,
      confidence_state: "HIGH",
      original_confidence_state: "HIGH",
      outcome_type: "OBSERVED",
      human_validated: true,
      summary: "Prior connection pool saturation following payment SDK upgrade resolved via pod scaling and max_connections tuning.",
      recommendation: "Scale payment-gateway-client pods from 4 to 8 and increase connection pool limit to 100.",
      evidence_ids: "EV_pool_metrics_q3,EV_db_connections_q3",
      created_at: "2025-11-14T14:30:00Z",
    },
    {
      scenario_id: "INC_003_DEGRADE_Q2",
      relevance: 0.81,
      retrieval_score: 0.486,
      confidence_state: "MEDIUM",
      original_confidence_state: "MEDIUM",
      outcome_type: "OBSERVED",
      human_validated: false,
      summary: "Connection timeout spike during holiday campaign mitigated via connection pool doubling.",
      recommendation: "Double upstream client connection pool size during peak volume spikes.",
      evidence_ids: "EV_timeout_telemetry_q2",
      created_at: "2025-08-22T09:15:00Z",
    },
  ],
  telemetry: {
    latency_ms_by_engine: {
      kpi_store: 12.4,
      signal: 4.8,
      diagnostic: 18.2,
      evidence: 45.1,
      hypothesis: 2200.0,
      challenge: 8.5,
      decision: 850.0,
      outcome: 15.0,
      memory: 32.0,
    },
    llm_calls: 3,
    llm_tokens_in: 1420,
    llm_tokens_out: 340,
    external_cost_usd: 0.00042,
    llm_provider: "groq",
    llm_model: "qwen/qwen3.6-27b",
  },
  method_ownership: {
    kpi_store: "SQL",
    signal: "STATS",
    diagnostic: "STATS",
    evidence: "SQL + RETRIEVAL",
    hypothesis: "LLM",
    challenge: "RULES",
    decision: "RULES + LLM",
    outcome: "STATS",
    memory: "CHROMA_VECTOR",
  },
}

export const DEFAULT_INC_002: InvestigationResult = {
  scenario_id: "INC_002",
  persona: "analyst",
  signals: [
    {
      kpi_id: "hourly_revenue",
      observed: 52100,
      expected: 84000,
      delta_pct: -38.0,
      z_score: -3.85,
      is_anomaly: true,
      method: "STATS",
    },
    {
      kpi_id: "checkout_dropoff_rate",
      observed: 34.2,
      expected: 12.5,
      delta_pct: 173.6,
      z_score: 4.12,
      is_anomaly: true,
      method: "STATS",
    },
    {
      kpi_id: "gateway_latency_15min",
      observed: 320,
      expected: 180,
      delta_pct: 77.8,
      z_score: 2.95,
      is_anomaly: false,
      method: "STATS",
    }
  ],
  contributions: [
    { dimension: "channel", segment: "paid_search", contribution_pct: 51.0, segment_delta_pct: -65.0, method: "STATS" },
    { dimension: "channel", segment: "organic", contribution_pct: 31.2, segment_delta_pct: -28.0, method: "STATS" },
  ],
  evidence: [
    {
      evidence_id: "EV_gateway_intermittent_500",
      source_id: "payment_gateway",
      method: "SQL",
      relevance: 0.88,
      reliability_weight: 0.95,
      summary: "Intermittent HTTP 500 responses observed on checkout authorization API during third-party provider maintenance window.",
    },
    {
      evidence_id: "EV_competitor_pricing_campaign",
      source_id: "market_intelligence",
      method: "RETRIEVAL",
      relevance: 0.84,
      reliability_weight: 0.80,
      summary: "Major competitor launched an aggressive 30% sitewide flash discount targeting core categories at 12:00 UTC.",
    },
  ],
  hypotheses: [
    {
      hypothesis_id: "H1",
      statement: "Checkout revenue loss is primarily driven by intermittent payment provider HTTP 500 errors.",
      supporting_evidence_ids: ["EV_gateway_intermittent_500"],
      contradictory_evidence_ids: ["EV_competitor_pricing_campaign"],
    },
    {
      hypothesis_id: "H2",
      statement: "Checkout revenue drop is primarily caused by competitor pricing campaign diverting paid acquisition traffic.",
      supporting_evidence_ids: ["EV_competitor_pricing_campaign"],
      contradictory_evidence_ids: ["EV_gateway_intermittent_500"],
    },
  ],
  scored: [
    {
      hypothesis_id: "H1",
      support_score: 0.62,
      contradiction_penalty: 0.25,
      final_score: 0.37,
      confidence_state: "MEDIUM",
      rule_results: [
        { rule_name: "timeline", verdict: "pass", rationale: "Matches start of error elevation." },
        { rule_name: "contradiction", verdict: "partial", rationale: "Competitor campaign explains drop in add-to-cart volume." },
      ],
    },
    {
      hypothesis_id: "H2",
      support_score: 0.58,
      contradiction_penalty: 0.22,
      final_score: 0.36,
      confidence_state: "MEDIUM",
      rule_results: [
        { rule_name: "timeline", verdict: "pass", rationale: "Campaign launch at 12:00 matches traffic dip." },
        { rule_name: "contradiction", verdict: "partial", rationale: "Gateway errors are also elevated simultaneously." },
      ],
    },
  ],
  decision: {
    abstained: true,
    abstention_reason: "Ambiguous multi-causal conflict: Winning margin (0.01) is below the required 0.15 threshold. Simultaneous technical errors and competitive pricing cannot be isolated without deeper cohort telemetry.",
    recommended_action: "Abstain from singular automated mitigation. Deploy price elasticity telemetry and query secondary gateway logs to isolate primary variance driver.",
  },
  outcome: {
    disclaimer: "Simulation abstained: Insufficient causal separation to model deterministic recovery curve.",
  },
  precedents: [],
}

export const DEFAULT_INC_003: InvestigationResult = {
  scenario_id: "INC_003",
  persona: "analyst",
  signals: [
    {
      kpi_id: "premium_subscription_checkout",
      observed: 48,
      expected: 150,
      delta_pct: -68.0,
      z_score: -1.82,
      is_anomaly: false,
      sparse_history: true,
      method: "STATS",
    },
  ],
  contributions: [],
  evidence: [],
  hypotheses: [],
  scored: [],
  decision: {
    abstained: true,
    abstention_reason: "SPARSE BASELINE GUARD: Minimum 14-day history required for statistical anomaly scoring (12 days available for KPI 'premium_subscription_checkout'). Anomaly scoring suppressed to prevent false positive alert fatigue.",
    recommended_action: "Accumulate additional baseline history. Re-evaluate once 14-day observation window is satisfied.",
  },
  outcome: {
    disclaimer: "No simulation executed: Anomaly suppressed under sparse baseline history guardrail.",
  },
  precedents: [],
}

export const DEFAULT_INC_004: InvestigationResult = {
  scenario_id: "INC_004",
  persona: "analyst",
  signals: [
    {
      kpi_id: "hourly_revenue",
      observed: 11400,
      expected: 78500,
      delta_pct: -85.5,
      z_score: -5.40,
      is_anomaly: true,
      data_quality_suspect: true,
      method: "STATS",
    },
  ],
  contributions: [],
  evidence: [],
  hypotheses: [],
  scored: [],
  decision: {
    abstained: true,
    abstention_reason: "DATA-QUALITY GUARD: Ingestion pipeline delay detected. Data warehouse batch sync job 'orders_batch_sync_v2' is 72 minutes behind schedule; apparent revenue plunge is an artifact of incomplete table partitions.",
    recommended_action: "Hold operational changes. Monitor ETL pipeline job 'orders_batch_sync_v2' and re-evaluate signals once synchronization catch-up completes.",
  },
  outcome: {
    disclaimer: "No recovery simulation executed: Apparent anomaly is suppressed under data-quality verification guardrail.",
  },
  precedents: [],
}

export const DEFAULT_INC_005: InvestigationResult = {
  scenario_id: "INC_005",
  persona: "analyst",
  signals: [
    {
      kpi_id: "daily_active_users",
      observed: 14200,
      expected: 15100,
      delta_pct: -6.0,
      z_score: -0.45,
      is_anomaly: false,
      method: "STATS",
    },
    {
      kpi_id: "order_conversion_rate",
      observed: 3.4,
      expected: 3.5,
      delta_pct: -2.8,
      z_score: -0.32,
      is_anomaly: false,
      method: "STATS",
    },
  ],
  contributions: [],
  evidence: [],
  hypotheses: [],
  scored: [],
  decision: {
    abstained: true,
    abstention_reason: "NO ANOMALY DETECTED: Observed variance is within normal seasonal corridor (-0.45σ). Platform metrics reflect standard weekly cyclical demand variations.",
    recommended_action: "No operational remediation required. Demand patterns follow expected seasonal baseline.",
  },
  outcome: {
    disclaimer: "No simulation needed: Baseline operations are nominal.",
  },
  precedents: [],
}

export const DEFAULT_INC_006: InvestigationResult = {
  scenario_id: "INC_006",
  persona: "analyst",
  signals: [
    {
      kpi_id: "platform_error_rate",
      observed: 12.8,
      expected: 0.5,
      delta_pct: 2460.0,
      z_score: 5.60,
      is_anomaly: true,
      method: "STATS",
    },
    {
      kpi_id: "api_gateway_latency",
      observed: 480,
      expected: 110,
      delta_pct: 336.4,
      z_score: 4.90,
      is_anomaly: true,
      method: "STATS",
    },
  ],
  contributions: [
    { dimension: "service", segment: "checkout_api", contribution_pct: 62.0, segment_delta_pct: 420.0, method: "STATS" },
    { dimension: "service", segment: "auth_proxy", contribution_pct: 38.0, segment_delta_pct: 180.0, method: "STATS" },
  ],
  evidence: [
    {
      evidence_id: "EV_upstream_packet_loss",
      source_id: "network_telemetry",
      method: "SQL",
      relevance: 0.94,
      reliability_weight: 0.98,
      summary: "Upstream WAN provider experienced 18% packet loss between US-East edge nodes and primary compute cluster starting at 10:05 UTC.",
    },
    {
      evidence_id: "EV_auth_retry_storm",
      source_id: "service_mesh",
      method: "RETRIEVAL",
      relevance: 0.91,
      reliability_weight: 0.95,
      summary: "Client retry storm amplified by un-jittered exponential backoff, causing cascading auth-proxy thread pool saturation.",
    },
  ],
  hypotheses: [
    {
      hypothesis_id: "H1",
      statement: "Compound failure: Upstream WAN packet loss triggered an un-jittered client retry storm that saturated the internal auth-proxy service mesh.",
      supporting_evidence_ids: ["EV_upstream_packet_loss", "EV_auth_retry_storm"],
      contradictory_evidence_ids: [],
    },
  ],
  scored: [
    {
      hypothesis_id: "H1",
      support_score: 0.92,
      contradiction_penalty: 0.0,
      final_score: 0.92,
      confidence_state: "HIGH",
      rule_results: [
        { rule_name: "timeline", verdict: "pass", rationale: "WAN drop at 10:05 preceded auth retry storm at 10:08." },
        { rule_name: "mechanism_consistency", verdict: "pass", rationale: "Corroborated by thread pool saturation logs." },
      ],
    },
  ],
  decision: {
    winning_hypothesis_id: "H1",
    recommended_action: "Enable circuit breaker on auth-proxy ingress and apply jittered backoff configuration to client gateway.",
    verification_metric: "Verify auth-proxy queue length drops below 50 requests and error rate normalizes < 1%.",
    abstained: false,
  },
  outcome: {
    projected_recovery_pct: 94.0,
    projected_metric: "platform_error_rate",
    disclaimer: "Simulated recovery projection based on circuit-breaker shedding profile.",
  },
  precedents: [],
}

export const DEFAULT_INC_007: InvestigationResult = {
  scenario_id: "INC_007",
  persona: "analyst",
  signals: [
    {
      kpi_id: "worker_memory_utilization",
      observed: 94.2,
      expected: 42.0,
      delta_pct: 124.3,
      z_score: 4.60,
      is_anomaly: true,
      method: "STATS",
    },
    {
      kpi_id: "job_processing_latency",
      observed: 3200,
      expected: 450,
      delta_pct: 611.1,
      z_score: 5.10,
      is_anomaly: true,
      method: "STATS",
    },
  ],
  contributions: [
    { dimension: "queue", segment: "event_ingest_worker", contribution_pct: 82.0, segment_delta_pct: 140.0, method: "STATS" },
    { dimension: "queue", segment: "email_notification_worker", contribution_pct: 18.0, segment_delta_pct: 35.0, method: "STATS" },
  ],
  evidence: [
    {
      evidence_id: "EV_buffer_leak_telemetry",
      source_id: "runtime_profiler",
      method: "SQL",
      relevance: 0.97,
      reliability_weight: 0.99,
      summary: "Gradual memory leak in event_ingest_worker unreleased byte buffer handler accumulating +1.2GB every 6 hours.",
      raw_ref: "profiler_heap_dump_worker_04.hprof",
    },
  ],
  hypotheses: [
    {
      hypothesis_id: "H1",
      statement: "Worker memory exhaustion is driven by an unreleased byte buffer leak in the background event ingestion pipeline.",
      supporting_evidence_ids: ["EV_buffer_leak_telemetry"],
      contradictory_evidence_ids: [],
    },
  ],
  scored: [
    {
      hypothesis_id: "H1",
      support_score: 0.95,
      contradiction_penalty: 0.0,
      final_score: 0.95,
      confidence_state: "HIGH",
      rule_results: [
        { rule_name: "timeline", verdict: "pass", rationale: "Steady heap growth over 48 hours matches unreleased buffer leak profile." },
        { rule_name: "mechanism_consistency", verdict: "pass", rationale: "GC thrashing directly produces worker execution slowdown." },
      ],
    },
  ],
  decision: {
    winning_hypothesis_id: "H1",
    recommended_action: "Restart event ingestion worker pool and deploy buffer release patch v2.1.4.",
    verification_metric: "Confirm worker cluster memory utilization stabilizes below 50% for 60 consecutive minutes.",
    abstained: false,
  },
  outcome: {
    projected_recovery_pct: 96.0,
    projected_metric: "worker_memory_utilization",
    disclaimer: "Deterministic process restart recovery curve.",
  },
  precedents: [],
}

export const DEFAULT_INC_008: InvestigationResult = {
  scenario_id: "INC_008",
  persona: "analyst",
  signals: [
    {
      kpi_id: "sso_auth_failure_rate",
      observed: 98.4,
      expected: 0.2,
      delta_pct: 49100.0,
      z_score: 7.20,
      is_anomaly: true,
      method: "STATS",
    },
    {
      kpi_id: "enterprise_active_sessions",
      observed: 420,
      expected: 12500,
      delta_pct: -96.6,
      z_score: -6.80,
      is_anomaly: true,
      method: "STATS",
    },
  ],
  contributions: [
    { dimension: "identity_provider", segment: "okta_saml", contribution_pct: 88.0, segment_delta_pct: 99.0, method: "STATS" },
    { dimension: "identity_provider", segment: "azure_ad", contribution_pct: 12.0, segment_delta_pct: 10.0, method: "STATS" },
  ],
  evidence: [
    {
      evidence_id: "EV_saml_cert_expiry",
      source_id: "security_audit_log",
      method: "SQL",
      relevance: 0.99,
      reliability_weight: 1.0,
      summary: "SAML signing x509 certificate expired at 00:00 UTC. Inbound SAML assertions from primary Okta IdP rejected by SP validator.",
      raw_ref: "saml_keystore_audit.log#line-102",
    },
  ],
  hypotheses: [
    {
      hypothesis_id: "H1",
      statement: "Enterprise SSO outage is caused by an expired SAML signing certificate on the service provider assertion consumer endpoint.",
      supporting_evidence_ids: ["EV_saml_cert_expiry"],
      contradictory_evidence_ids: [],
    },
  ],
  scored: [
    {
      hypothesis_id: "H1",
      support_score: 0.98,
      contradiction_penalty: 0.0,
      final_score: 0.98,
      confidence_state: "HIGH",
      rule_results: [
        { rule_name: "timeline", verdict: "pass", rationale: "Certificate expiry at 00:00 matches immediate 100% rejection." },
        { rule_name: "mechanism_consistency", verdict: "pass", rationale: "Crypto verification failure halts token issuance." },
      ],
    },
  ],
  decision: {
    winning_hypothesis_id: "H1",
    recommended_action: "Rotate expired SAML x509 certificate in production keystore and reload IdP metadata bundle.",
    verification_metric: "Confirm test SAML assertion returns HTTP 200 OK and active sessions climb > 5,000.",
    abstained: false,
  },
  outcome: {
    projected_recovery_pct: 99.0,
    projected_metric: "sso_auth_failure_rate",
    disclaimer: "Deterministic certificate reload recovery curve.",
  },
  precedents: [],
}

export const SCENARIO_PREVIEWS: Record<string, InvestigationResult> = {
  INC_001: DEFAULT_INC_001,
  INC_002: DEFAULT_INC_002,
  INC_003: DEFAULT_INC_003,
  INC_004: DEFAULT_INC_004,
  INC_005: DEFAULT_INC_005,
  INC_006: DEFAULT_INC_006,
  INC_007: DEFAULT_INC_007,
  INC_008: DEFAULT_INC_008,
}
