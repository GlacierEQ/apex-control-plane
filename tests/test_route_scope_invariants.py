import pytest

from route_scope_invariants import (
    MissionRoutingState,
    RouteEventKind,
    ScopeInvariantViolation,
    apply_route_event,
    assert_scope_transition,
)


def _state() -> MissionRoutingState:
    return MissionRoutingState(
        mission_id="telecom-capabilities",
        objective="finish Telecom capability work",
        scope_items=("repair lockfile", "advance CALL-E runtime"),
        active_route="desktop-commander",
    )


def test_broken_tool_changes_route_not_objective_or_scope() -> None:
    before = _state()
    after = apply_route_event(
        before,
        kind=RouteEventKind.TOOL_FAILURE,
        route="desktop-commander",
        replacement_route="supabase-control-plane",
    )

    assert after.objective == before.objective
    assert after.scope_items == before.scope_items
    assert after.active_route == "supabase-control-plane"
    assert after.unavailable_routes == ("desktop-commander",)


def test_skip_for_now_is_sequencing_not_scope_removal() -> None:
    before = _state()
    after = apply_route_event(
        before,
        kind=RouteEventKind.TEMPORARY_SKIP,
        subject="desktop-commander-dependent step",
        replacement_route="supabase-control-plane",
    )

    assert after.objective == before.objective
    assert after.scope_items == before.scope_items
    assert after.temporarily_deferred == ("desktop-commander-dependent step",)


def test_route_failure_cannot_silently_drop_lockfile_work() -> None:
    before = _state()
    illegal = MissionRoutingState(
        mission_id=before.mission_id,
        objective=before.objective,
        scope_items=("advance CALL-E runtime",),
        active_route="supabase-control-plane",
    )

    with pytest.raises(ScopeInvariantViolation, match="mutate Operator scope"):
        assert_scope_transition(before, illegal)


def test_route_failure_cannot_silently_replace_objective() -> None:
    before = _state()
    illegal = MissionRoutingState(
        mission_id=before.mission_id,
        objective="do only CALL-E work",
        scope_items=before.scope_items,
        active_route="supabase-control-plane",
    )

    with pytest.raises(ScopeInvariantViolation, match="mutate the Operator objective"):
        assert_scope_transition(before, illegal)


def test_scope_change_requires_explicit_operator_authority() -> None:
    before = _state()

    with pytest.raises(ScopeInvariantViolation, match="explicit Operator"):
        apply_route_event(
            before,
            kind=RouteEventKind.EXPLICIT_SCOPE_CHANGE,
            new_scope_items=("advance CALL-E runtime",),
        )

    after = apply_route_event(
        before,
        kind=RouteEventKind.EXPLICIT_SCOPE_CHANGE,
        explicit_operator_scope_change=True,
        new_scope_items=("advance CALL-E runtime",),
    )
    assert after.scope_items == ("advance CALL-E runtime",)
