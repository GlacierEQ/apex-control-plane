from __future__ import annotations

from prime_established_state_guard import (
    dimension_effect,
    evaluate_conflict,
    should_reopen_established_state,
)


def test_generic_open_blocker_is_not_a_veto() -> None:
    decision = evaluate_conflict(status="open_blocker")
    assert decision.blocks is False
    assert should_reopen_established_state(established=True, conflict=decision) is False


def test_missing_fresh_verification_does_not_reopen_established_state() -> None:
    decision = evaluate_conflict(
        status="positive_conflict_blocker",
        positive_conflict={
            "positive_conflict": False,
            "source_ref": "",
            "conflicts_with_source_ref": "",
            "material_to_current_action": False,
            "affected_dimensions": [],
        },
    )
    assert decision.blocks is False
    assert should_reopen_established_state(established=True, conflict=decision) is False


def test_positive_source_bearing_material_conflict_can_block() -> None:
    decision = evaluate_conflict(
        status="positive_conflict_blocker",
        positive_conflict={
            "positive_conflict": True,
            "source_ref": "provider:new-record",
            "conflicts_with_source_ref": "case:established-proposition",
            "material_to_current_action": True,
            "affected_dimensions": ["offense_time"],
        },
    )
    assert decision.blocks is True
    assert decision.affected_dimensions == ("offense_time",)
    assert should_reopen_established_state(established=True, conflict=decision) is True


def test_conflict_reopens_only_affected_dimension() -> None:
    decision = evaluate_conflict(
        status="positive_conflict_blocker",
        positive_conflict={
            "positive_conflict": True,
            "source_ref": "provider:new-record",
            "conflicts_with_source_ref": "case:established-proposition",
            "material_to_current_action": True,
            "affected_dimensions": ["document_creation_time"],
        },
    )
    state = dimension_effect(
        established_dimensions={
            "detention_occurred": True,
            "document_creation_time": "after 21:00",
            "paid_transaction": "$165.15",
        },
        conflict=decision,
    )
    assert state["document_creation_time"]["state"] == "REOPEN_FOR_CONFLICT_RESOLUTION"
    assert state["detention_occurred"]["state"] == "PRESERVE"
    assert state["paid_transaction"]["state"] == "PRESERVE"


def test_operator_can_direct_reexamination_without_erasing_prior_state() -> None:
    assert should_reopen_established_state(
        established=True,
        operator_directed_reexamination=True,
    ) is True
