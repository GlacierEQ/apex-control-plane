package jack_relentless

import "core:testing"

all_true_gate_state :: proc() -> Gate_State {
    return Gate_State{
        authority_valid = true,
        safety_boundary_clear = true,
        continuity_loaded = true,
        resources_invoked = true,
        existing_work_checked = true,
        canonical_owner_resolved = true,
        objective_preserved = true,
        required_sources_opened = true,
        contradictions_preserved = true,
        highest_value_delta_selected = true,
        material_action_executed = true,
        verification_passed = true,
        defects_repaired_or_exactly_blocked = true,
        persistence_written = true,
        readback_verified = true,
        next_state_resumable = true,
    }
}

@(test)
blocker_precedes_complete :: proc(t: ^testing.T) {
    g := all_true_gate_state()
    testing.expect_value(t, evaluate(g, true), Execution_Status.BLOCKED)
}

@(test)
cold_start_is_recovering :: proc(t: ^testing.T) {
    testing.expect_value(t, evaluate(Gate_State{}, false), Execution_Status.RECOVERING)
}
