from __future__ import annotations

from src.turn_context_guard import TurnContextReceipt, route_turn_context


def _receipt(**overrides):
    values = {
        "turn_id": "turn-1",
        "retrieval_attempted": True,
        "sources_consulted": ("personalization", "current_conversation"),
        "prior_corrections_checked": True,
        "material_context_found": True,
        "material_context_applied": True,
        "retrieval_available": True,
        "unresolved_conflicts": (),
    }
    values.update(overrides)
    return TurnContextReceipt(**values)


def test_skipped_retrieval_routes_to_recovery_not_mission_stop() -> None:
    decision = route_turn_context(
        _receipt(
            retrieval_attempted=False,
            sources_consulted=(),
            prior_corrections_checked=False,
            material_context_found=False,
            material_context_applied=False,
        )
    )
    assert decision.next_action == "RETRIEVE_CONTEXT_THEN_CONTINUE"
    assert decision.mission_stopped is False
    assert decision.confidence_mode == "PENDING_CONTEXT_RECOVERY"


def test_unavailable_retrieval_degrades_confidence_without_stopping_mission() -> None:
    decision = route_turn_context(
        _receipt(
            retrieval_attempted=False,
            retrieval_available=False,
            sources_consulted=(),
            prior_corrections_checked=False,
            material_context_found=False,
            material_context_applied=False,
        )
    )
    assert decision.next_action == "CONTINUE_DEGRADED_REVERSIBLE_AND_TRY_ALTERNATE_CONTEXT_SOURCES"
    assert decision.mission_stopped is False
    assert decision.confidence_mode == "DEGRADED_CONTEXT_COVERAGE"


def test_material_context_cannot_be_retrieved_then_ignored() -> None:
    decision = route_turn_context(_receipt(material_context_applied=False))
    assert decision.next_action == "APPLY_MATERIAL_CONTEXT_THEN_CONTINUE"
    assert decision.mission_stopped is False


def test_prior_corrections_are_reconciled_before_action_selection() -> None:
    decision = route_turn_context(_receipt(prior_corrections_checked=False))
    assert decision.next_action == "RECONCILE_PRIOR_CORRECTIONS_THEN_CONTINUE"
    assert decision.mission_stopped is False


def test_unresolved_conflict_changes_route_not_mission() -> None:
    decision = route_turn_context(_receipt(unresolved_conflicts=("source-a vs source-b",)))
    assert decision.next_action == "CONTINUE_WITH_CONFLICT_AWARE_RETRIEVAL_AND_REVERSIBLE_WORK"
    assert decision.mission_stopped is False


def test_context_applied_allows_operator_aligned_execution() -> None:
    decision = route_turn_context(_receipt())
    assert decision.next_action == "EXECUTE_OPERATOR_ALIGNED_TURN"
    assert decision.mission_stopped is False
    assert decision.confidence_mode == "CONTEXT_APPLIED"
    assert len(decision.receipt_sha256) == 64
