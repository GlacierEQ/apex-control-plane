-- ============================================================================
-- AGENT REGISTRY — Administrative topology (Chromosome 12)
-- ============================================================================

CREATE TABLE agents (
    agent_id             TEXT PRIMARY KEY CHECK (agent_id ~ '^OA\.[A-Z0-9_]+(\.[A-Z0-9_]+)*$'),
    human_name           TEXT NOT NULL,
    domain               TEXT NOT NULL,
    version              TEXT NOT NULL CHECK (version ~ '^\d+\.\d+\.\d+$'),
    operator_root        TEXT NOT NULL CHECK (operator_root = 'OPERATOR'),
    lifecycle_state      lifecycle_state NOT NULL DEFAULT 'SEED',
    genome               JSONB NOT NULL,
    genome_hash          TEXT NOT NULL CHECK (genome_hash ~ '^[a-f0-9]{64}$'),
    parent_agent_id      TEXT REFERENCES agents(agent_id),
    generation           INT NOT NULL DEFAULT 0 CHECK (generation >= 0),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    retired_at           TIMESTAMPTZ,
    CONSTRAINT genome_has_required_chromosomes CHECK (
        genome ? 'c01_continuity' AND genome ? 'c02_authority' 
        AND genome ? 'c03_identity_and_lineage' AND genome ? 'c04_mission'
        AND genome ? 'c05_cognition' AND genome ? 'c06_knowledge_and_memory'
        AND genome ? 'c07_capability' AND genome ? 'c08_execution'
        AND genome ? 'c09_evidence_and_provenance' AND genome ? 'c10_verification'
        AND genome ? 'c11_integrity_and_security' AND genome ? 'c12_administration_and_observability'
    )
);

CREATE INDEX idx_agents_domain ON agents (domain);
CREATE INDEX idx_agents_lifecycle ON agents (lifecycle_state);
CREATE INDEX idx_agents_parent ON agents (parent_agent_id);