-- ============================================================================
-- MISSIONS — Chromosome 4
-- ============================================================================

CREATE TABLE missions (
    mission_id           TEXT PRIMARY KEY CHECK (mission_id ~ '^MSN-[A-Z0-9_-]{12,64}$'),
    operator_root        TEXT NOT NULL CHECK (operator_root = 'OPERATOR'),
    assignee_agent       TEXT NOT NULL REFERENCES agents(agent_id),
    objective            TEXT NOT NULL,
    desired_end_state    TEXT NOT NULL,
    priority             priority_level NOT NULL DEFAULT 'P2',
    status               mission_status NOT NULL DEFAULT 'QUEUED',
    success_criteria     TEXT[] NOT NULL DEFAULT '{}',
    open_loops           TEXT[] NOT NULL DEFAULT '{}',
    dependencies         TEXT[] NOT NULL DEFAULT '{}',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at           TIMESTAMPTZ,
    completed_at         TIMESTAMPTZ,
    mission_hash         TEXT NOT NULL CHECK (mission_hash ~ '^[a-f0-9]{64}$')
);

CREATE INDEX idx_missions_assignee ON missions (assignee_agent);
CREATE INDEX idx_missions_status ON missions (status);
CREATE INDEX idx_missions_priority ON missions (priority);