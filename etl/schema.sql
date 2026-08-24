-- BusinessIntelligence.ai — Structured Database Schema
-- PostgreSQL 15
-- All tables are scenario-scoped; scenario_id ties rows to a named incident (e.g. INC_001).

-- ---------------------------------------------------------------------------
-- Source Registry
-- Tracks every data source: grain, cadence, last refresh, SLA, and quality.
-- reliability_weight is computed at query time from staleness vs sla_minutes.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sources (
    source_id        VARCHAR(100)     PRIMARY KEY,
    name             VARCHAR(200)     NOT NULL,
    grain            VARCHAR(50)      NOT NULL,          -- e.g. "hourly", "15-min", "daily"
    cadence_minutes  INTEGER          NOT NULL,
    last_refresh     TIMESTAMPTZ      NOT NULL,
    sla_minutes      INTEGER          NOT NULL,          -- max allowed staleness
    freshness_status VARCHAR(20)      NOT NULL DEFAULT 'unknown',
    data_quality     NUMERIC(4,3)     NOT NULL DEFAULT 1.0 CHECK (data_quality BETWEEN 0 AND 1),
    lineage          JSONB            NOT NULL DEFAULT '[]',
    owner            VARCHAR(200)     NOT NULL
);

-- ---------------------------------------------------------------------------
-- KPI Values
-- One row per KPI measurement, stamped with source and method tag.
-- dimension_filters holds optional slices ({"device":"android", "region":"us-west"}).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kpi_values (
    id                SERIAL          PRIMARY KEY,
    kpi_id            VARCHAR(100)    NOT NULL,
    scenario_id       VARCHAR(100)    NOT NULL,
    period            TIMESTAMPTZ     NOT NULL,
    value             NUMERIC         NOT NULL,
    unit              VARCHAR(50)     NOT NULL,
    dimension_filters JSONB           NOT NULL DEFAULT '{}',
    source_id         VARCHAR(100)    REFERENCES sources(source_id),
    method            VARCHAR(30)     NOT NULL DEFAULT 'SQL'
);

CREATE INDEX IF NOT EXISTS idx_kpi_values_scenario  ON kpi_values (scenario_id);
CREATE INDEX IF NOT EXISTS idx_kpi_values_period     ON kpi_values (period);
CREATE INDEX IF NOT EXISTS idx_kpi_values_kpi_id     ON kpi_values (kpi_id);

-- ---------------------------------------------------------------------------
-- Orders
-- Transaction-level retail events used for revenue / conversion / AOV KPIs.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orders (
    transaction_id   VARCHAR(100)    PRIMARY KEY,
    scenario_id      VARCHAR(100)    NOT NULL,
    ts               TIMESTAMPTZ     NOT NULL,
    store_id         VARCHAR(100)    NOT NULL,
    device           VARCHAR(20)     NOT NULL,           -- "android" | "ios" | "desktop"
    channel          VARCHAR(30)     NOT NULL,           -- "app" | "web" | "in-store"
    revenue          NUMERIC         NOT NULL,
    conversion       BOOLEAN         NOT NULL,
    aov              NUMERIC         NOT NULL            -- average order value
);

CREATE INDEX IF NOT EXISTS idx_orders_scenario ON orders (scenario_id);
CREATE INDEX IF NOT EXISTS idx_orders_ts       ON orders (ts);

-- ---------------------------------------------------------------------------
-- Payment Events
-- Gateway-level success/failure with latency — feeds payment_failure_rate KPI.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS payment_events (
    event_id         VARCHAR(100)    PRIMARY KEY,
    scenario_id      VARCHAR(100)    NOT NULL,
    ts               TIMESTAMPTZ     NOT NULL,
    gateway          VARCHAR(50)     NOT NULL,
    success          BOOLEAN         NOT NULL,
    latency_ms       INTEGER         NOT NULL,
    error_code       VARCHAR(50)
);

CREATE INDEX IF NOT EXISTS idx_payment_events_scenario ON payment_events (scenario_id);
CREATE INDEX IF NOT EXISTS idx_payment_events_ts       ON payment_events (ts);

-- ---------------------------------------------------------------------------
-- Inventory Events
-- SKU-level stock snapshots — used to refute or support inventory hypotheses.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS inventory_events (
    event_id         VARCHAR(100)    PRIMARY KEY,
    scenario_id      VARCHAR(100)    NOT NULL,
    ts               TIMESTAMPTZ     NOT NULL,
    sku_id           VARCHAR(100)    NOT NULL,
    store_id         VARCHAR(100)    NOT NULL,
    in_stock         BOOLEAN         NOT NULL,
    fill_rate        NUMERIC(5,4)    CHECK (fill_rate BETWEEN 0 AND 1)
);

CREATE INDEX IF NOT EXISTS idx_inventory_events_scenario ON inventory_events (scenario_id);
CREATE INDEX IF NOT EXISTS idx_inventory_events_ts       ON inventory_events (ts);

-- ---------------------------------------------------------------------------
-- Marketing Events
-- Campaign spend / impressions from the marketing source.
-- source_stale flags rows loaded from a stale feed (beyond SLA).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS marketing_events (
    event_id         VARCHAR(100)    PRIMARY KEY,
    scenario_id      VARCHAR(100)    NOT NULL,
    ts               TIMESTAMPTZ     NOT NULL,
    channel          VARCHAR(50)     NOT NULL,
    spend            NUMERIC         NOT NULL,
    impressions      INTEGER         NOT NULL,
    source_stale     BOOLEAN         NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_marketing_events_scenario ON marketing_events (scenario_id);
CREATE INDEX IF NOT EXISTS idx_marketing_events_ts       ON marketing_events (ts);

-- ---------------------------------------------------------------------------
-- Support Tickets
-- Customer-reported issues — unstructured signal, also fed into ChromaDB.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS support_tickets (
    ticket_id        VARCHAR(100)    PRIMARY KEY,
    scenario_id      VARCHAR(100)    NOT NULL,
    ts               TIMESTAMPTZ     NOT NULL,
    store_id         VARCHAR(100)    NOT NULL,
    device           VARCHAR(20)     NOT NULL,
    message          TEXT            NOT NULL,
    category         VARCHAR(50)
);

CREATE INDEX IF NOT EXISTS idx_support_tickets_scenario ON support_tickets (scenario_id);
CREATE INDEX IF NOT EXISTS idx_support_tickets_ts       ON support_tickets (ts);

-- ---------------------------------------------------------------------------
-- Deployment Log
-- Software release events — timeline rule aligns anomaly onset to deploys.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS deployment_log (
    deploy_id        VARCHAR(100)    PRIMARY KEY,
    scenario_id      VARCHAR(100)    NOT NULL,
    ts               TIMESTAMPTZ     NOT NULL,
    version          VARCHAR(20)     NOT NULL,
    component        VARCHAR(50)     NOT NULL,
    notes            TEXT
);

CREATE INDEX IF NOT EXISTS idx_deployment_log_scenario ON deployment_log (scenario_id);
CREATE INDEX IF NOT EXISTS idx_deployment_log_ts       ON deployment_log (ts);

-- ---------------------------------------------------------------------------
-- Feedback
-- Analyst / manager feedback on an investigation result (for validation & learning loop).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id                 SERIAL          PRIMARY KEY,
    investigation_id            VARCHAR(100)    NOT NULL,
    scenario_id                 VARCHAR(100),
    persona                     VARCHAR(50)     DEFAULT 'analyst',
    verdict                     VARCHAR(30)     NOT NULL DEFAULT 'CORRECT',
    corrected_hypothesis_id     VARCHAR(50),
    corrected_confidence_state  VARCHAR(30),
    corrected_action            TEXT,
    evidence_grounding_correct  BOOLEAN         DEFAULT TRUE,
    analyst_notes               TEXT,
    content                     TEXT            CHECK (content IS NULL OR length(content) BETWEEN 1 AND 5000),
    validated_precedent         BOOLEAN         DEFAULT FALSE,
    validation_precedent_id     VARCHAR(100),
    received_at                 TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feedback_investigation ON feedback (investigation_id);
CREATE INDEX IF NOT EXISTS idx_feedback_scenario      ON feedback (scenario_id);
CREATE INDEX IF NOT EXISTS idx_feedback_verdict       ON feedback (verdict);

-- ---------------------------------------------------------------------------
-- Investigations
-- Persisted InvestigationResult blobs — enables E9 Memory precedent retrieval.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS investigations (
    investigation_id VARCHAR(100)    PRIMARY KEY,
    scenario_id      VARCHAR(100)    NOT NULL,
    persona          VARCHAR(20)     NOT NULL,
    result_json      JSONB           NOT NULL,
    created_at       TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_investigations_scenario   ON investigations (scenario_id);
CREATE INDEX IF NOT EXISTS idx_investigations_created_at ON investigations (created_at);
