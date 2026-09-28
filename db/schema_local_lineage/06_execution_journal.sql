-- ============================================================================
-- EXECUTION JOURNAL — Layer 3 of Black Box
-- ============================================================================

CREATE TABLE execution_journal (
    entry_id             TEXT PRIMARY KEY CHECK (entry_id ~ '^XJ-[A-Z0-9_-]{12,64}$'),
    event_id             TEXT NOT NULL REFERENCES event_ledger(event_id),
    sequence             BIGINT NOT NULL,
    timestamp            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    capability           TEXT NOT NULL,
    operation            TEXT NOT NULL,
    command_digest       TEXT NOT NULL CHECK (command_digest ~ '^[a-f0-9]{64}$'),
    exit_code            INT,
    before_state_hash    TEXT CHECK (before_state_hash ~ '^[a-f0-9]{64}$'),
    after_state_hash     TEXT CHECK (after_state_hash ~ '^[a-f0-9]{64}$'),
    duration_ms          NUMERIC NOT NULL DEFAULT 0 CHECK (duration_ms >= 0),
    previous_entry_hash  TEXT CHECK (previous_entry_hash ~ '^[a-f0-9]{64}$'),
    entry_hash           TEXT NOT NULL CHECK (entry_hash ~ '^[a-f0-9]{64}$')
);

CREATE INDEX idx_execution_journal_event ON execution_journal (event_id);
CREATE INDEX idx_execution_journal_sequence ON execution_journal (sequence);