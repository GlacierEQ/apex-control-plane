-- ============================================================================
-- VERIFICATION MATRIX — Independent verification results
-- ============================================================================

CREATE TABLE verification_matrix (
    verification_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id             TEXT NOT NULL REFERENCES event_ledger(event_id),
    verifier_agent       TEXT NOT NULL REFERENCES agents(agent_id),
    readback_performed   BOOLEAN NOT NULL,
    verification_result  verification_result NOT NULL,
    falsification_tests  JSONB NOT NULL DEFAULT '[]',
    certified_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_verification_event ON verification_matrix (event_id);
CREATE INDEX idx_verification_verifier ON verification_matrix (verifier_agent);