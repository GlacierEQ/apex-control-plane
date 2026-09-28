-- ============================================================================
-- ROW LEVEL SECURITY POLICIES (Part 1: Core Tables)
-- ============================================================================

ALTER TABLE control_plane_continuity_spine_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE delegation_contracts ENABLE ROW LEVEL SECURITY;
ALTER TABLE missions ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE execution_journal ENABLE ROW LEVEL SECURITY;
ALTER TABLE provenance_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE receipt_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE continuity_journal ENABLE ROW LEVEL SECURITY;
ALTER TABLE provider_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE open_loops ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE verification_matrix ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION current_agent_id() RETURNS TEXT AS $$
    SELECT current_setting('app.current_agent_id', true);
$$ LANGUAGE sql STABLE;

CREATE OR REPLACE FUNCTION is_operator() RETURNS BOOLEAN AS $$
    SELECT current_setting('app.current_agent_id', true) = 'OPERATOR';
$$ LANGUAGE sql STABLE;

-- CONTINUITY SPINE
CREATE POLICY continuity_spine_read_latest ON control_plane_continuity_spine_v1
    FOR SELECT USING (
        sequence = (SELECT max(sequence) FROM control_plane_continuity_spine_v1)
        OR is_operator()
    );

CREATE POLICY continuity_spine_write_operator ON control_plane_continuity_spine_v1
    FOR INSERT WITH CHECK (is_operator());

CREATE POLICY continuity_spine_update_operator ON control_plane_continuity_spine_v1
    FOR UPDATE USING (is_operator()) WITH CHECK (is_operator());

-- AGENTS
CREATE POLICY agents_read_all ON agents FOR SELECT USING (true);

CREATE POLICY agents_write_operator ON agents
    FOR INSERT WITH CHECK (is_operator());

CREATE POLICY agents_update_operator_or_parent ON agents
    FOR UPDATE USING (
        is_operator() OR parent_agent_id = current_agent_id()
    ) WITH CHECK (
        is_operator() OR parent_agent_id = current_agent_id()
    );

-- DELEGATION CONTRACTS
CREATE POLICY delegation_read_grantee ON delegation_contracts
    FOR SELECT USING (
        grantee_agent = current_agent_id() 
        OR delegator = current_agent_id() 
        OR is_operator()
    );

CREATE POLICY delegation_write_operator ON delegation_contracts
    FOR INSERT WITH CHECK (is_operator());

CREATE POLICY delegation_revoke_delegator ON delegation_contracts
    FOR UPDATE USING (
        delegator = current_agent_id() OR is_operator()
    ) WITH CHECK (
        delegator = current_agent_id() OR is_operator()
    );