"""Regression: source-free retrieval cannot self-certify applied context."""
from __future__ import annotations

from src.turn_context_guard import TurnContextReceipt, route_turn_context


def _receipt(**changes):
    values = dict(
        turn_id="turn-source-bound",
        retrieval_attempted=True,
        sources_consulted=("provider:source",),
        prior_corrections_checked=True,
        material_context_found=True,
        material_context_applied=True,
        retrieval_available=True,
        unresolved_conflicts=(),
    )
    values.update(changes)
    return TurnContextReceipt(**values)


def test_attempted_without_consulted_source_routes_to_recovery():
    for sources in ((), ("",), (" ",), ("", "   ")):
        decision = route_turn_context(_receipt(
            sources_consulted=sources,
            material_context_found=False,
            material_context_applied=False,
        ))
        assert decision.next_action == "RETRIEVE_CONTEXT_THEN_CONTINUE"
        assert decision.confidence_mode == "PENDING_CONTEXT_RECOVERY"
        assert not decision.mission_stopped


def test_no_consulted_source_with_unavailable_retrieval_keeps_reversible_work():
    decision = route_turn_context(_receipt(
        retrieval_available=False,
        sources_consulted=(),
        material_context_found=False,
        material_context_applied=False,
    ))
    assert decision.next_action == "CONTINUE_DEGRADED_REVERSIBLE_AND_TRY_ALTERNATE_CONTEXT_SOURCES"
    assert not decision.mission_stopped


def test_applied_flag_without_found_context_is_not_accepted():
    decision = route_turn_context(_receipt(
        material_context_found=False, material_context_applied=True,
    ))
    assert decision.next_action == "RETRIEVE_CONTEXT_THEN_CONTINUE"
    assert not decision.mission_stopped


def test_real_consulted_source_without_material_hit_is_not_a_global_stop():
    decision = route_turn_context(_receipt(
        material_context_found=False, material_context_applied=False,
    ))
    assert decision.next_action == "EXECUTE_OPERATOR_ALIGNED_TURN"
    assert not decision.mission_stopped


def test_real_applied_context_preserves_operator_aligned_execution():
    decision = route_turn_context(_receipt())
    assert decision.next_action == "EXECUTE_OPERATOR_ALIGNED_TURN"
    assert decision.confidence_mode == "CONTEXT_APPLIED"
