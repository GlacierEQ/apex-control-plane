-- ============================================================================
-- DELEGATION CONTRACTS — Authority chains (Chromosome 2)
-- ============================================================================

CREATE TABLE delegation_contracts (
    contract_id          TEXT PRIMARY KEY CHECK (contract_id ~ '^DC-[A-Z0-9_-]{12,64}$'),
    root_authority       TEXT NOT NULL CHECK (root_authority = 'OPERATOR'),
    parent_contract_id   TEXT REFERENCES delegation_contracts(contract_id),
    delegator            TEXT NOT NULL,
    grantee_agent        TEXT NOT NULL REFERENCES agents(agent_id) CHECK (grantee_agent ~ '^OA\.[A-Z0-9_]+(\.[A-Z0-9_]+)*$'),
    jurisdiction         TEXT NOT NULL,
    permitted_scopes     TEXT[] NOT NULL DEFAULT '{}',
    prohibited_scopes    TEXT[] NOT NULL DEFAULT '{}',
    approval_required_scopes TEXT[] NOT NULL DEFAULT '{}',
    effective_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at           TIMESTAMPTZ,
    revocation_status    delegation_status NOT NULL DEFAULT 'ACTIVE',
    signature            TEXT,
    contract_hash        TEXT NOT NULL CHECK (contract_hash ~ '^[a-f0-9]{64}$'),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_delegation_grantee ON delegation_contracts (grantee_agent);
CREATE INDEX idx_delegation_parent ON delegation_contracts (parent_contract_id);
CREATE INDEX idx_delegation_status ON delegation_contracts (revocation_status);