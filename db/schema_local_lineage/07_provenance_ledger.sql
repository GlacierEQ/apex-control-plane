-- ============================================================================
-- PROVENANCE LEDGER — Layer 4 of Black Box
-- ============================================================================

CREATE TABLE provenance_ledger (
    entry_id             TEXT PRIMARY KEY CHECK (entry_id ~ '^PRV-[A-Z0-9_-]{12,64}$'),
    event_id             TEXT NOT NULL REFERENCES event_ledger(event_id),
    sequence             BIGINT NOT NULL,
    timestamp            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_type          TEXT NOT NULL CHECK (source_type IN ('DOCUMENT', 'PROVIDER_API', 'TESTIMONY', 'MEMORY', 'DERIVATION', 'EXTERNAL')),
    source_ref           TEXT NOT NULL,
    source_hash          TEXT NOT NULL CHECK (source_hash ~ '^[a-f0-9]{64}$'),
    transform            TEXT NOT NULL CHECK (transform IN ('SOURCE', 'DERIVATIVE')),
    lineage              TEXT[] NOT NULL DEFAULT '{}',
    previous_entry_hash  TEXT CHECK (previous_entry_hash ~ '^[a-f0-9]{64}$'),
    entry_hash           TEXT NOT NULL CHECK (entry_hash ~ '^[a-f0-9]{64}$')
);

CREATE INDEX idx_provenance_event ON provenance_ledger (event_id);
CREATE INDEX idx_provenance_sequence ON provenance_ledger (sequence);