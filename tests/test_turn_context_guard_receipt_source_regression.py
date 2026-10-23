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

def test_no_material_hit_is_not_misreported_as_applied_context():
    decision = route_turn_context(_receipt(
        sources_consulted=("provider:source",),
        prior_corrections_checked=True,
        material_context_found=False,
        material_context_applied=False,
    ))
    assert decision.next_action == "EXECUTE_OPERATOR_ALIGNED_TURN"
    assert decision.confidence_mode == "CONTEXT_CHECKED_NO_MATERIAL_HIT"
    assert "no material context" in decision.reason
    assert not decision.mission_stopped


def test_no_material_hit_without_correction_check_must_reconcile_before_execution():
    decision = route_turn_context(_receipt(
        sources_consulted=("provider:source",),
        prior_corrections_checked=False,
        material_context_found=False,
        material_context_applied=False,
    ))
    assert decision.next_action == "RECONCILE_PRIOR_CORRECTIONS_THEN_CONTINUE"
    assert decision.confidence_mode == "PENDING_CORRECTION_RECONCILIATION"
    assert not decision.mission_stopped


def test_material_hit_still_requires_applied_context_receipt():
    decision = route_turn_context(_receipt())
    assert decision.confidence_mode == "CONTEXT_APPLIED"


def test_malformed_source_shape_cannot_self_certify_context():
    # JSON/deserialization can violate the dataclass type annotation at runtime.
    # Bare strings and mappings iterate as source names in the old any() gate.
    for sources in ("provider:source", {"provider:source": True},
                    ("provider:source", ""), ("provider:source", 42)):
        decision = route_turn_context(_receipt(sources_consulted=sources))
        assert decision.next_action == "RETRIEVE_CONTEXT_THEN_CONTINUE"
        assert decision.confidence_mode == "PENDING_CONTEXT_RECOVERY"
        assert not decision.mission_stopped


def test_missing_source_field_routes_to_recovery_instead_of_typeerror():
    decision = route_turn_context(_receipt(sources_consulted=None))
    assert decision.next_action == "RETRIEVE_CONTEXT_THEN_CONTINUE"
    assert not decision.mission_stopped


def test_valid_sequence_sources_preserve_context_application():
    for sources in (("provider:source",), ["provider:source"]):
        decision = route_turn_context(_receipt(sources_consulted=sources))
        assert decision.confidence_mode == "CONTEXT_APPLIED"
        assert decision.next_action == "EXECUTE_OPERATOR_ALIGNED_TURN"


def test_malformed_source_unavailable_retrieval_preserves_reversible_progress():
    decision = route_turn_context(_receipt(
        sources_consulted="provider:source", retrieval_available=False))
    assert decision.next_action == "CONTINUE_DEGRADED_REVERSIBLE_AND_TRY_ALTERNATE_CONTEXT_SOURCES"
    assert not decision.mission_stopped
