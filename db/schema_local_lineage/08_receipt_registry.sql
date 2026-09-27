-- ============================================================================
-- RECEIPT REGISTRY — Layer 5 of Black Box
-- ============================================================================

CREATE TABLE receipt_registry (
    entry_id             TEXT PRIMARY KEY CHECK (entry_id ~ '^RRE-[A-Z0-9_-]{12,64}$'),
    receipt_id           TEXT NOT NULL CHECK (receipt_id ~ '^RCP-[A-Z0-9_-]{12,64}$'),
    event_id             TEXT NOT NULL REFERENCES event_ledger(event_id),
    sequence             BIGINT NOT NULL,
    registered_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    provider             TEXT NOT NULL CHECK (provider IN ('Gmail', 'GitHub', 'Supabase', 'Telecom', 'DecoVault', 'AWS', 'Stripe', 'LocalRuntime')),
    provider_native_id   TEXT NOT NULL,
    receipt_payload_hash TEXT NOT NULL CHECK (receipt_payload_hash ~ '^[a-f0-9]{64}$'),
    readback_verified    BOOLEAN NOT NULL DEFAULT FALSE,
    previous_entry_hash  TEXT CHECK (previous_entry_hash ~ '^[a-f0-9]{64}$'),
    entry_hash           TEXT NOT NULL CHECK (entry_hash ~ '^[a-f0-9]{64}$')
);

CREATE INDEX idx_receipt_event ON receipt_registry (event_id);
CREATE INDEX idx_receipt_sequence ON receipt_registry (sequence);
CREATE INDEX idx_receipt_provider ON receipt_registry (provider);