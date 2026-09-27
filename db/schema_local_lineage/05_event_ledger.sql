-- ============================================================================
-- EVENT LEDGER — Layer 2 of Black Box (5-layer recorder)
-- ============================================================================

CREATE TABLE event_ledger (
    event_id             TEXT PRIMARY KEY CHECK (event_id ~ '^EVT-[A-Z0-9_-]{12,64}$'),
    sequence             BIGINT NOT NULL UNIQUE,
    timestamp            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    continuity           JSONB NOT NULL CHECK (
        continuity ? 'previous_event_hash'
        AND continuity ? 'resulting_continuity_head_hash'
    ),
    authority            JSONB NOT NULL CHECK (
        authority @> '{"operator_id": "OPERATOR"}'::jsonb
        AND authority ? 'acting_agent'
        AND authority ? 'genome_version'
        AND authority ? 'genome_hash'
    ),
    mission              JSONB NOT NULL CHECK (
        mission ? 'mission_id'
        AND mission ? 'objective_id'
    ),
    context              JSONB NOT NULL DEFAULT '{}',
    decision             JSONB,
    execution            JSONB NOT NULL CHECK (
        execution ? 'capability'
        AND execution ? 'provider'
        AND execution ? 'operation'
        AND execution ? 'action_hash'
    ),
    result               JSONB NOT NULL CHECK (
        result ? 'success_claimed'
        AND result ? 'output_hash'
    ),
    verification         JSONB NOT NULL CHECK (
        verification ? 'readback_performed'
        AND verification ? 'verification_result'
    ),
    integrity            JSONB NOT NULL CHECK (
        integrity ? 'parent_event_hash'
        AND integrity ? 'event_hash'
    ),
    CONSTRAINT integrity_event_hash_format CHECK (integrity->>'event_hash' ~ '^[a-f0-9]{64}$'),
    CONSTRAINT integrity_parent_event_hash_format CHECK (
        integrity->>'parent_event_hash' IS NULL 
        OR integrity->>'parent_event_hash' ~ '^[a-f0-9]{64}$'
    )
);

CREATE INDEX idx_event_ledger_sequence ON event_ledger (sequence);
CREATE INDEX idx_event_ledger_timestamp ON event_ledger (timestamp);
CREATE INDEX idx_event_ledger_acting_agent ON event_ledger ((authority->>'acting_agent'));
CREATE INDEX idx_event_ledger_mission ON event_ledger ((mission->>'mission_id'));
CREATE INDEX idx_event_ledger_continuity_head ON event_ledger ((continuity->>'resulting_continuity_head_hash'));