-- ============================================================================
-- OPEN LOOPS — Tracking unresolved obligations (Chromosome 4, Position 40)
-- ============================================================================

CREATE TABLE open_loops (
    loop_id              TEXT PRIMARY KEY,
    owner_agent          TEXT NOT NULL REFERENCES agents(agent_id),
    priority             priority_level NOT NULL,
    description          TEXT NOT NULL,
    status               open_loop_status NOT NULL DEFAULT 'PENDING',
    deadline             TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_open_loops_owner ON open_loops (owner_agent);
CREATE INDEX idx_open_loops_priority ON open_loops (priority);
CREATE INDEX idx_open_loops_status ON open_loops (status);