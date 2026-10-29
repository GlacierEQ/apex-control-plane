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
        "applied_context_refs": ("current_conversation",),
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


def test_previously_consulted_context_reused_without_retrieval_ritual() -> None:
    decision = route_turn_context(_receipt(
        retrieval_attempted=False,
        sources_consulted=("source:existing-work",),
        reused_context_refs=("source:existing-work",),
        applied_context_refs=("source:existing-work",),
    ))
    assert decision.next_action == "EXECUTE_OPERATOR_ALIGNED_TURN"
    assert decision.confidence_mode == "CONTEXT_APPLIED"


def test_unconsulted_reuse_claim_cannot_skip_understanding() -> None:
    decision = route_turn_context(_receipt(
        retrieval_attempted=False,
        sources_consulted=("source:known",),
        reused_context_refs=("source:invented",),
        material_context_found=False,
        material_context_applied=False,
        applied_context_refs=(),
    ))
    assert decision.next_action == "RETRIEVE_CONTEXT_THEN_CONTINUE"
    assert decision.mission_stopped is False


def test_retrieval_attempt_without_consulted_source_is_not_understanding() -> None:
    decision = route_turn_context(_receipt(
        retrieval_attempted=True,
        sources_consulted=(),
        material_context_found=False,
        material_context_applied=False,
        applied_context_refs=(),
    ))
    assert decision.next_action == "RETRIEVE_CONTEXT_THEN_CONTINUE"


def test_context_application_flag_without_consulted_source_is_not_enough() -> None:
    decision = route_turn_context(_receipt(applied_context_refs=()))
    assert decision.next_action == "APPLY_MATERIAL_CONTEXT_THEN_CONTINUE"


def test_context_application_cannot_use_unconsulted_reference() -> None:
    decision = route_turn_context(_receipt(applied_context_refs=("source:other-mission",)))
    assert decision.next_action == "APPLY_MATERIAL_CONTEXT_THEN_CONTINUE"


def test_research_question_before_action_routes_to_study_not_false_completion() -> None:
    decision = route_turn_context(_receipt(
        research_questions=("What does the current API contract guarantee?",),
    ))
    assert decision.next_action == "RESEARCH_STUDY_MAXIMIZE_QUALITY_THEN_CONTINUE"
    assert decision.mission_stopped is False


def test_bare_research_applied_flag_is_not_scientific_evidence() -> None:
    decision = route_turn_context(_receipt(
        research_questions=("Find strongest repair approach",),
        research_applied=True,
    ))
    assert decision.next_action == "RESEARCH_STUDY_MAXIMIZE_QUALITY_THEN_CONTINUE"


def test_research_sources_must_be_consulted_and_applied() -> None:
    bad = [
        {"research_source_refs": ("source:unknown",), "research_applied_refs": ("source:unknown",)},
        {"research_source_refs": ("current_conversation",), "research_applied_refs": ("source:unknown",)},
        {"research_source_refs": ("current_conversation",), "research_applied_refs": ()},
    ]
    for variant in bad:
        decision = route_turn_context(_receipt(
            research_questions=("Compare safe approaches",),
            research_applied=True,
            **variant,
        ))
        assert decision.next_action == "RESEARCH_STUDY_MAXIMIZE_QUALITY_THEN_CONTINUE"


def test_source_bound_research_can_advance_operator_aligned_work() -> None:
    decision = route_turn_context(_receipt(
        research_questions=("Study source-supported alternative",),
        research_applied=True,
        research_source_refs=("current_conversation",),
        research_applied_refs=("current_conversation",),
    ))
    assert decision.next_action == "EXECUTE_OPERATOR_ALIGNED_TURN"
    assert decision.mission_stopped is False


def test_existing_understanding_avoids_unnecessary_research_gate() -> None:
    decision = route_turn_context(_receipt(
        research_questions=(),
        research_applied=False,
    ))
    assert decision.next_action == "EXECUTE_OPERATOR_ALIGNED_TURN"


def test_study_provenance_changes_receipt_digest() -> None:
    base = route_turn_context(_receipt())
    studied = route_turn_context(_receipt(
        research_questions=("Study provider semantics",),
        research_applied=True,
        research_source_refs=("current_conversation",),
        research_applied_refs=("current_conversation",),
    ))
    assert base.receipt_sha256 != studied.receipt_sha256


def test_absent_context_cannot_be_marked_applied() -> None:
    decision = route_turn_context(_receipt(
        material_context_found=False,
        material_context_applied=True,
    ))
    assert decision.next_action == "RECONCILE_CONTEXT_CLAIMS_THEN_CONTINUE"
    assert decision.mission_stopped is False


def test_unexpected_source_type_is_not_trusted_as_consulted_evidence() -> None:
    decision = route_turn_context(_receipt(
        sources_consulted=(["unhashable-source"],),
        retrieval_attempted=True,
        material_context_found=False,
        material_context_applied=False,
        applied_context_refs=(),
    ))
    assert decision.next_action == "RETRIEVE_CONTEXT_THEN_CONTINUE"
