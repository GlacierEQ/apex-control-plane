-- ============================================================================
-- PROVIDER RECEIPTS — Canonical receipts
-- ============================================================================

CREATE TABLE provider_receipts (
    receipt_id           TEXT PRIMARY KEY CHECK (receipt_id ~ '^RCP-[A-Z0-9_-]{12,64}$'),
    provider             TEXT NOT NULL CHECK (provider IN ('Gmail', 'GitHub', 'Supabase', 'Telecom', 'DecoVault', 'AWS', 'Stripe', 'LocalRuntime')),
    provider_native_id   TEXT NOT NULL,
    acting_agent         TEXT NOT NULL REFERENCES agents(agent_id) CHECK (acting_agent ~ '^OA\.[A-Z0-9_]+(\.[A-Z0-9_]+)*$'),
    mission_id           TEXT NOT NULL REFERENCES missions(mission_id),
    action_type          TEXT NOT NULL,
    acquired_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    readback_verified    BOOLEAN NOT NULL DEFAULT FALSE,
    readback_at          TIMESTAMPTZ,
    raw_response_metadata JSONB NOT NULL DEFAULT '{}',
    receipt_payload_hash TEXT NOT NULL CHECK (receipt_payload_hash ~ '^[a-f0-9]{64}$')
);

CREATE INDEX idx_provider_receipts_agent ON provider_receipts (acting_agent);
CREATE INDEX idx_provider_receipts_mission ON provider_receipts (mission_id);
CREATE INDEX idx_provider_receipts_provider ON provider_receipts (provider);