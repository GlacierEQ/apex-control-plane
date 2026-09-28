-- ============================================================================
-- ROW LEVEL SECURITY POLICIES (Part 3: Continuity, Provider, Memory, Verification)
-- ============================================================================

-- CONTINUITY JOURNAL
CREATE POLICY continuity_journal_read_actor ON continuity_journal
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM control_plane_continuity_spine_v1 c
            WHERE c.continuity_id = continuity_journal.continuity_id
            AND (c.sequence = (SELECT max(sequence) FROM control_plane_continuity_spine_v1 WHERE continuity_id = c.continuity_id) OR is_operator())
        )
    );

CREATE POLICY continuity_journal_write_operator ON continuity_journal
    FOR INSERT WITH CHECK (is_operator());

-- PROVIDER RECEIPTS
CREATE POLICY provider_receipts_read_actor ON provider_receipts
    FOR SELECT USING (acting_agent = current_agent_id() OR is_operator());

CREATE POLICY provider_receipts_write_operator ON provider_receipts
    FOR INSERT WITH CHECK (is_operator());

-- OPEN LOOPS
CREATE POLICY open_loops_read_owner ON open_loops
    FOR SELECT USING (owner_agent = current_agent_id() OR is_operator());

CREATE POLICY open_loops_write_operator ON open_loops
    FOR INSERT WITH CHECK (is_operator());

CREATE POLICY open_loops_update_owner ON open_loops
    FOR UPDATE USING (owner_agent = current_agent_id() OR is_operator())
    WITH CHECK (owner_agent = current_agent_id() OR is_operator());

-- AGENT MEMORIES
CREATE POLICY agent_memories_read_owner ON agent_memories
    FOR SELECT USING (agent_id = current_agent_id() OR is_operator());

CREATE POLICY agent_memories_write_owner ON agent_memories
    FOR INSERT WITH CHECK (agent_id = current_agent_id() OR is_operator());

CREATE POLICY agent_memories_update_owner ON agent_memories
    FOR UPDATE USING (agent_id = current_agent_id() OR is_operator())
    WITH CHECK (agent_id = current_agent_id() OR is_operator());

-- VERIFICATION MATRIX
CREATE POLICY verification_read_involved ON verification_matrix
    FOR SELECT USING (
        verifier_agent = current_agent_id() 
        OR EXISTS (
            SELECT 1 FROM event_ledger e 
            WHERE e.event_id = verification_matrix.event_id
            AND e.authority->>'acting_agent' = current_agent_id()
        )
        OR is_operator()
    );

CREATE POLICY verification_write_operator ON verification_matrix
    FOR INSERT WITH CHECK (is_operator());