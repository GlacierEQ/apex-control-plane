-- ============================================================================
-- ROW LEVEL SECURITY POLICIES (Part 2: Mission & Event Tables)
-- ============================================================================

-- MISSIONS
CREATE POLICY missions_read_assignee ON missions
    FOR SELECT USING (assignee_agent = current_agent_id() OR is_operator());

CREATE POLICY missions_write_operator ON missions
    FOR INSERT WITH CHECK (is_operator());

CREATE POLICY missions_update_assignee ON missions
    FOR UPDATE USING (assignee_agent = current_agent_id() OR is_operator())
    WITH CHECK (assignee_agent = current_agent_id() OR is_operator());

-- EVENT LEDGER
CREATE POLICY event_ledger_read_actor ON event_ledger
    FOR SELECT USING (
        authority->>'acting_agent' = current_agent_id() OR is_operator()
    );

CREATE POLICY event_ledger_write_operator ON event_ledger
    FOR INSERT WITH CHECK (is_operator());

-- EXECUTION JOURNAL
CREATE POLICY execution_journal_read_actor ON execution_journal
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM event_ledger e 
            WHERE e.event_id = execution_journal.event_id
            AND (e.authority->>'acting_agent' = current_agent_id() OR is_operator())
        )
    );

CREATE POLICY execution_journal_write_operator ON execution_journal
    FOR INSERT WITH CHECK (is_operator());

-- PROVENANCE LEDGER
CREATE POLICY provenance_read_actor ON provenance_ledger
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM event_ledger e 
            WHERE e.event_id = provenance_ledger.event_id
            AND (e.authority->>'acting_agent' = current_agent_id() OR is_operator())
        )
    );

CREATE POLICY provenance_write_operator ON provenance_ledger
    FOR INSERT WITH CHECK (is_operator());

-- RECEIPT REGISTRY
CREATE POLICY receipt_read_actor ON receipt_registry
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM event_ledger e 
            WHERE e.event_id = receipt_registry.event_id
            AND (e.authority->>'acting_agent' = current_agent_id() OR is_operator())
        )
    );

CREATE POLICY receipt_write_operator ON receipt_registry
    FOR INSERT WITH CHECK (is_operator());