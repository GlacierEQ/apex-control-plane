-- ============================================================================
-- CONTINUITY JOURNAL — Layer 1 of Black Box
-- ============================================================================

CREATE TABLE continuity_journal (
    entry_id             TEXT PRIMARY KEY CHECK (entry_id ~ '^CJ-[A-Z0-9_-]{12,64}$'),
    continuity_id        TEXT NOT NULL REFERENCES control_plane_continuity_spine_v1(continuity_id),
    sequence             BIGINT NOT NULL,
    timestamp            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    transition           JSONB NOT NULL CHECK (
        transition ? 'from_head_hash' AND transition ? 'to_head_hash'
    ),
    trigger              TEXT NOT NULL,
    previous_entry_hash  TEXT CHECK (previous_entry_hash ~ '^[a-f0-9]{64}$'),
    entry_hash           TEXT NOT NULL CHECK (entry_hash ~ '^[a-f0-9]{64}$')
);

CREATE INDEX idx_continuity_journal_continuity ON continuity_journal (continuity_id);
CREATE INDEX idx_continuity_journal_sequence ON continuity_journal (sequence);