package jack_relentless

Execution_Status :: enum {
    RECOVERING,
    EXECUTING,
    BLOCKED,
    COMPLETE,
}

Gate_State :: struct {
    authority_valid: bool,
    safety_boundary_clear: bool,
    continuity_loaded: bool,
    resources_invoked: bool,
    existing_work_checked: bool,
    canonical_owner_resolved: bool,
    objective_preserved: bool,
    required_sources_opened: bool,
    contradictions_preserved: bool,
    highest_value_delta_selected: bool,
    material_action_executed: bool,
    verification_passed: bool,
    defects_repaired_or_exactly_blocked: bool,
    persistence_written: bool,
    readback_verified: bool,
    next_state_resumable: bool,
}

execution_ready :: proc(g: Gate_State) -> bool {
    return g.authority_valid &&
           g.safety_boundary_clear &&
           g.continuity_loaded &&
           g.resources_invoked &&
           g.existing_work_checked &&
           g.canonical_owner_resolved &&
           g.objective_preserved &&
           g.required_sources_opened
}

completion_ready :: proc(g: Gate_State) -> bool {
    return execution_ready(g) &&
           g.contradictions_preserved &&
           g.highest_value_delta_selected &&
           g.material_action_executed &&
           g.verification_passed &&
           g.defects_repaired_or_exactly_blocked &&
           g.persistence_written &&
           g.readback_verified &&
           g.next_state_resumable
}

resume_ready :: proc(g: Gate_State) -> bool {
    return g.continuity_loaded &&
           g.canonical_owner_resolved &&
           g.persistence_written &&
           g.readback_verified &&
           g.next_state_resumable
}

evaluate :: proc(g: Gate_State, exact_blocker_present: bool) -> Execution_Status {
    if exact_blocker_present {
        return .BLOCKED
    }
    if completion_ready(g) {
        return .COMPLETE
    }
    if !execution_ready(g) {
        return .RECOVERING
    }
    return .EXECUTING
}
