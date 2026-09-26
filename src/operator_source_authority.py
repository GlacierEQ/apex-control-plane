"""Fail-closed validation for Operator personalization and source authority.

Static contract validation is intentionally strict because malformed authority
configuration should never silently become runtime doctrine. Per-turn context
recovery is different: missing or unavailable context must auto-route to recovery
or degraded continuation rather than becoming a generalized mission stop.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from operator_source_binding_contract import SourceResolver, verify_source_span_binding

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "operator_source_authority_contract.json"


class OperatorSourceAuthorityError(RuntimeError):
    pass


def _require(mapping: Mapping[str, Any], key: str, expected: Any, *, scope: str) -> None:
    if mapping.get(key) != expected:
        raise OperatorSourceAuthorityError(
            f"{scope}.{key} must be {expected!r}; got {mapping.get(key)!r}"
        )


def enforce_verbatim_response_fidelity(
    *,
    requested_verbatim: bool,
    source_binding: Mapping[str, Any] | None,
    source_resolver: SourceResolver | None,
    emitted_operator_quote: str | None,
) -> None:
    """Require an exact, independently resolved Operator source span."""
    if not requested_verbatim:
        return

    policy = enforce_operator_source_authority()
    source_fidelity = policy["source_fidelity"]
    if (
        source_fidelity.get("verbatim_request_requires_source_rehydration_before_response")
        is not True
        or source_fidelity.get("verbatim_request_forbids_paraphrase_as_substitute")
        is not True
        or source_fidelity.get("verbatim_quote_must_be_exact_source_span") is not True
    ):
        raise OperatorSourceAuthorityError(
            "verbatim response fidelity policy is not fully enforced"
        )

    if not isinstance(source_binding, Mapping) or source_resolver is None:
        raise OperatorSourceAuthorityError(
            "verbatim response requires an independently resolved source binding"
        )
    if not isinstance(emitted_operator_quote, str) or not emitted_operator_quote:
        raise OperatorSourceAuthorityError(
            "verbatim response requires a non-empty exact Operator quote"
        )

    verification = verify_source_span_binding(
        source_binding,
        resolver=source_resolver,
        prefix="verbatim_response",
        require_unsuperseded=True,
    )
    if verification.errors or verification.span_text is None:
        detail = verification.errors[0] if verification.errors else "source span unresolved"
        raise OperatorSourceAuthorityError(
            "verbatim source verification failed: " + detail
        )
    if emitted_operator_quote != verification.span_text:
        raise OperatorSourceAuthorityError(
            "verbatim response must exactly equal the exact requested source span"
        )


def enforce_operator_source_authority() -> dict[str, Any]:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if policy.get("fail_closed") is not True:
        raise OperatorSourceAuthorityError("operator source authority must fail closed")

    personalization = policy.get("personalization")
    turn_start_context = policy.get("turn_start_context")
    source_fidelity = policy.get("source_fidelity")
    source_state = policy.get("source_state")
    source_identity = policy.get("source_identity")
    intent_provenance = policy.get("intent_provenance")
    organization = policy.get("organization")
    for name, value in {
        "personalization": personalization,
        "turn_start_context": turn_start_context,
        "source_fidelity": source_fidelity,
        "source_state": source_state,
        "source_identity": source_identity,
        "intent_provenance": intent_provenance,
        "organization": organization,
    }.items():
        if not isinstance(value, Mapping):
            raise OperatorSourceAuthorityError(f"{name} policy missing")

    for key, expected in {
        "status": "mandatory_user_authority_input",
        "highest_user_authority_layer": True,
        "load_before_task_interpretation": True,
        "optional_context": False,
        "summary_may_override": False,
        "memory_gap_may_demote": False,
        "tool_or_widget_may_redefine_mission": False,
        "fresh_model_inference_may_supersede": False,
    }.items():
        _require(personalization, key, expected, scope="personalization")

    for key, expected in {
        "scope": "every_operator_turn",
        "retrieval_attempt_required": True,
        "model_may_skip_due_to_apparent_sufficiency": False,
        "current_conversation_is_not_complete_personalization": True,
        "prior_corrections_checked_before_action_selection": True,
        "retrieved_context_must_causally_affect_action_when_material": True,
        "context_application_receipt_required": True,
        "missing_context_response": "AUTO_RECOVER_THEN_CONTINUE",
        "retrieval_failure_response": "CONTINUE_DEGRADED_AND_TRY_ALTERNATE_SOURCES",
        "retrieval_failure_is_mission_stop": False,
        "support_mechanism_may_not_gain_veto": True,
        "unknown_context_reduces_confidence_not_effort": True,
    }.items():
        _require(turn_start_context, key, expected, scope="turn_start_context")

    for key, expected in {
        "verbatim_operator_source_is_controlling": True,
        "summary_role": "INDEX_AND_ROUTING_ONLY",
        "summary_may_be_governing_source": False,
        "summary_may_replace_verbatim_source": False,
        "summary_may_normalize_operator_meaning": False,
        "controlling_decision_requires_source_rehydration_when_available": True,
        "summary_conflict_resolution": "VERBATIM_OPERATOR_SOURCE_WINS",
        "compression_must_preserve_qualifiers_distinctions_scope_and_corrections": True,
        "summary_without_source_lineage_is_non_authoritative": True,
        "repeated_summary_does_not_gain_authority": True,
        "assistant_interpretation_must_remain_separate_from_operator_words": True,
        "verbatim_request_requires_source_rehydration_before_response": True,
        "verbatim_request_forbids_paraphrase_as_substitute": True,
        "verbatim_quote_must_be_exact_source_span": True,
    }.items():
        _require(source_fidelity, key, expected, scope="source_fidelity")

    for key, expected in {
        "operator_words_are_source_state": True,
        "source_layer_verbatim": True,
        "summaries_are_derived_only": True,
        "summaries_may_impersonate_source": False,
        "summaries_may_replace_operator_words": False,
        "derived_state_requires_source_lineage": True,
        "contradictions_must_be_preserved": True,
        "compression_may_erase_distinctions": False,
        "compression_may_merge_actors_events_or_truth_states": False,
        "historical_wording_may_be_normalized": False,
    }.items():
        _require(source_state, key, expected, scope="source_state")

    for key, expected in {
        "operator_designation": "OPERATOR",
        "operator_designation_semantics": "proper_name",
        "operator_source_class": "KNOWLEDGE_USE_DIRECTION",
        "knowledge_system_source_class": "KNOWLEDGE_STATE",
        "agent_source_class": "INFERENCE",
        "evidence_source_class": "EVIDENCE",
        "source_classes_never_collapse": True,
        "knowledge_state_is_not_use_direction": True,
        "use_direction_is_not_knowledge_state": True,
        "knowledge_state_alone_does_not_choose_use": True,
        "operator_direction_does_not_rewrite_evidence_or_knowledge_state": True,
        "framework_material_never_becomes_operator_words_by_retrieval": True,
    }.items():
        _require(source_identity, key, expected, scope="source_identity")

    expected_classes = [
        "USER_ORIGINATED",
        "ASSISTANT_PROPOSED_USER_ACCEPTED",
        "ASSISTANT_ORIGINATED_UNCONTESTED",
        "UNKNOWN",
    ]
    expected_authority_classes = ["USER_ORIGINATED", "ASSISTANT_PROPOSED_USER_ACCEPTED"]
    _require(intent_provenance, "allowed_classes", expected_classes, scope="intent_provenance")
    _require(intent_provenance, "project_direction_authority_classes", expected_authority_classes, scope="intent_provenance")
    for key, expected in {
        "operator_adoption_requires_explicit_evidence": True,
        "assistant_originated_uncontested_does_not_become_operator_intent": True,
        "unknown_provenance_does_not_gain_direction_authority": True,
        "absence_of_operator_objection_is_not_adoption": True,
    }.items():
        _require(intent_provenance, key, expected, scope="intent_provenance")

    for key, expected in {
        "evidence_integrity_controls": True,
        "beneficial_reorganization_allowed": True,
        "old_path_is_not_immutable_authority": True,
        "location_changes_require_lineage_preservation": True,
        "empty_scaffolding_is_not_organization": True,
        "decorative_directories_are_not_progress": True,
    }.items():
        _require(organization, key, expected, scope="organization")

    return policy
