-- Connector Registry + Audit Schema
-- apex-control-plane
-- Apply via: psql $NEON_DATABASE_URL -f migrations/001_connectors.sql

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Connector registry — all registered external integrations
CREATE TABLE IF NOT EXISTS connectors (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT        UNIQUE NOT NULL,
    kind                TEXT        NOT NULL,  -- github, notion, supabase, sentry, neon, supermemory, clickup, pinecone, qdrant, motherduck
    config              JSONB       NOT NULL DEFAULT '{}',
    enabled             BOOLEAN     NOT NULL DEFAULT true,
    last_health_at      TIMESTAMPTZ,
    last_health_status  TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_connectors_kind    ON connectors (kind);
CREATE INDEX IF NOT EXISTS idx_connectors_enabled ON connectors (enabled);

-- Per-connector health log
CREATE TABLE IF NOT EXISTS connector_health_log (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    connector_id    UUID        NOT NULL REFERENCES connectors (id) ON DELETE CASCADE,
    status          TEXT        NOT NULL CHECK (status IN ('healthy', 'degraded', 'down', 'unknown')),
    details         JSONB       NOT NULL DEFAULT '{}',
    checked_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_health_connector_id ON connector_health_log (connector_id);
CREATE INDEX IF NOT EXISTS idx_health_checked_at   ON connector_health_log (checked_at DESC);

-- Seed: register all 9 services from the integration targets
INSERT INTO connectors (name, kind, config) VALUES
    ('github',      'github',      '{"token": ""}'),
    ('notion',      'notion',      '{"api_key": ""}'),
    ('supabase',    'supabase',    '{"url": "", "service_key": ""}'),
    ('pinecone',    'pinecone',    '{"api_key": "", "environment": ""}'),
    ('qdrant',      'qdrant',      '{"url": "http://localhost:6333"}'),
    ('sentry',      'sentry',      '{"dsn": ""}'),
    ('motherduck',  'motherduck',  '{"token": ""}'),
    ('clickup',     'clickup',     '{"api_key": ""}'),
    ('neon',        'neon',        '{"dsn": ""}'),
    ('supermemory', 'supermemory', '{"api_key": ""}')
ON CONFLICT (name) DO NOTHING;
