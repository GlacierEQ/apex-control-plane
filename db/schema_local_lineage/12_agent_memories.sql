-- ============================================================================
-- AGENT MEMORIES — Durable memory (operator-memory integration)
-- ============================================================================

CREATE TABLE agent_memories (
    memory_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id             TEXT NOT NULL REFERENCES agents(agent_id),
    namespace            TEXT NOT NULL,
    content              JSONB NOT NULL,
    content_hash         TEXT NOT NULL CHECK (content_hash ~ '^[a-f0-9]{64}$'),
    source_event_id      TEXT REFERENCES event_ledger(event_id),
    verified             BOOLEAN NOT NULL DEFAULT FALSE,
    contradiction_of     UUID REFERENCES agent_memories(memory_id),
    promoted_at          TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_agent_memories_agent ON agent_memories (agent_id);
CREATE INDEX idx_agent_memories_namespace ON agent_memories (namespace);
CREATE INDEX idx_agent_memories_verified ON agent_memories (verified);