from operator_fidelity_preflight import load_operator_fidelity_policy


def test_operator_fidelity_requires_route_scope_preservation() -> None:
    policy = load_operator_fidelity_policy()
    selected = policy["selected_path_requirements"]
    assert selected["route_failure_preserves_objective"] is True
    assert selected["route_failure_preserves_scope"] is True
    assert selected["temporary_skip_is_sequencing_only"] is True
    assert selected["scope_change_requires_explicit_operator_instruction"] is True

    invariants = policy["route_scope_invariants"]
    assert invariants["route_is_not_scope"] is True
    assert invariants["tool_failure_is_routing_data_only"] is True
    assert invariants["tool_unavailability_may_change_route"] is True
    assert invariants["tool_unavailability_may_not_change_objective"] is True
    assert invariants["tool_unavailability_may_not_remove_scope"] is True
    assert invariants["temporary_skip_preserves_scope"] is True
    assert invariants["temporary_skip_changes_sequence_only"] is True
    assert invariants["scope_removal_requires_explicit_operator_instruction"] is True
