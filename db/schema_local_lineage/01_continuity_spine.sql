-- ============================================================================
-- CONTINUITY SPINE — Position #1
-- ============================================================================

CREATE TABLE control_plane_continuity_spine_v1 (
    continuity_id        TEXT PRIMARY KEY CHECK (continuity_id ~ '^cnt_[a-zA-Z0-9_-]{12,64}$'),
    sequence             BIGINT NOT NULL CHECK (sequence >= 1),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    operator_authority   JSONB NOT NULL CHECK (
        operator_authority @> '{"root_operator": "OPERATOR"}'::jsonb
        AND operator_authority ? 'authority_hash'
        AND operator_authority ? 'override_state'
    ),
    active_missions      TEXT[] NOT NULL DEFAULT '{}',
    active_agents        TEXT[] NOT NULL DEFAULT '{}',
    open_loops           JSONB NOT NULL DEFAULT '[]',
    commitments          JSONB NOT NULL DEFAULT '[]',
    deadlines            JSONB NOT NULL DEFAULT '[]',
    evidence_heads       JSONB NOT NULL DEFAULT '{}',
    provider_state_heads JSONB NOT NULL DEFAULT '{}',
    memory_head          TEXT CHECK (memory_head ~ '^[a-f0-9]{64}$'),
    genome_heads         JSONB NOT NULL DEFAULT '{}',
    environment_state    JSONB NOT NULL CHECK (
        environment_state ? 'active_mounts'
        AND environment_state ? 'node_id'
        AND environment_state ? 'platform'
    ),
    last_verified_event  JSONB NOT NULL CHECK (
        last_verified_event ? 'event_id'
        AND last_verified_event ? 'event_hash'
    ),
    last_verified_receipt JSONB,
    recovery_instructions TEXT NOT NULL,
    integrity            JSONB NOT NULL CHECK (
        integrity ? 'payload_hash'
        AND integrity ? 'previous_head_hash'
    ),
    CONSTRAINT integrity_payload_hash_format CHECK (integrity->>'payload_hash' ~ '^[a-f0-9]{64}$'),
    CONSTRAINT integrity_previous_head_hash_format CHECK (
        integrity->>'previous_head_hash' IS NULL 
        OR integrity->>'previous_head_hash' ~ '^[a-f0-9]{64}$'
    )
);

CREATE INDEX idx_continuity_spine_sequence ON control_plane_continuity_spine_v1 (sequence);
CREATE INDEX idx_continuity_spine_created_at ON control_plane_continuity_spine_v1 (created_at);