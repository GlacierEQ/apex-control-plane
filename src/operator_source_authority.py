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
    if not isinstance(emitted_operator_quote, str) or not emitted_operator_quote.strip():
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
    user_supplied_material = policy.get("user_supplied_material")
    organization = policy.get("organization")
    for name, value in {
        "personalization": personalization,
        "turn_start_context": turn_start_context,
        "source_fidelity": source_fidelity,
        "source_state": source_state,
        "source_identity": source_identity,
        "intent_provenance": intent_provenance,
        "user_supplied_material": user_supplied_material,
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
        "style_may_prove_authorship": False,
        "external_ai_paste_is_operator_authored": False,
        "external_ai_proposal_requires_evaluation": True,
        "explicit_adoption_requires_separate_operator_source": True,
        "explicit_adoption_is_scoped_not_wholesale": True,
        "user_authored_polished_text_remains_possible": True,
        "short_or_typo_text_does_not_establish_operator_authorship": True,
        "mixed_origin_spans_must_remain_separate": True,
        "operator_original_words_and_decisions_outweigh_pasted_draft_as_direction": True,
        "external_proposal_is_not_automatically_rejected": True,
        "hidden_harms_must_be_tested": True,
        "no_harms_flagged_does_not_prove_no_harms": True,
        "historical_persona_summaries_may_not_replace_operator_record": True,
        "review_only_is_not_adoption": True,
        "unknown_origin_is_not_mission_stop": True,
    }.items():
        _require(user_supplied_material, key, expected, scope="user_supplied_material")

    required_harms = {
        "AUTHORSHIP_LAUNDERING", "SUMMARY_AUTHORITY_INVERSION",
        "SCOPE_REDUCTION", "LOSS_OF_UNIQUE_PRIOR_WORK", "EXTRA_APPROVAL_GATE",
        "UNSUPPORTED_LAW_OR_TECHNICAL_CLAIM", "OWNING_SOURCE_MISMATCH",
        "STALE_STATUS_OR_FALSE_COMPLETION", "UNAUTHORIZED_PROVIDER_EFFECT",
        "PRIVACY_SPILL", "ADVISOR_ORACLE_DEPENDENCY", "PREMATURE_DISPOSITION",
    }
    harm_classes = user_supplied_material.get("hidden_harm_categories")
    if not isinstance(harm_classes, list) or not required_harms.issubset(set(harm_classes)):
        raise OperatorSourceAuthorityError(
            "user_supplied_material.hidden_harm_categories must retain all required classes"
        )

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


def assess_supplied_material(
    *,
    declared_origin: str,
    intended_use: str,
    historical_source_ref: str,
    adoption_source_ref: str | None = None,
    adopted_scope: str | None = None,
    style_cues: list[str] | None = None,
    material_hidden_harms: list[str] | None = None,
) -> dict[str, Any]:
    """Return evidence-bounded triage, not a stylistic author detector.

    declared_origin must be attributed by the trusted caller from the original
    message/source span or a separate explicit user statement. It must NEVER
    be chosen solely by prose length, typo frequency, or apparent fluency.
    This function does not audit the material content on its own: harm flags
    are review inputs, not proof that the review was exhaustive.
    """
    enforce_operator_source_authority()
    if declared_origin not in {"OPERATOR_AUTHORED", "EXTERNAL_AI", "UNKNOWN"}:
        raise OperatorSourceAuthorityError("declared_origin must be attributable")
    if intended_use not in {"DIRECT", "EVALUATE", "ADOPT"}:
        raise OperatorSourceAuthorityError("intended_use unsupported")
    if not isinstance(historical_source_ref, str) or not historical_source_ref.strip():
        raise OperatorSourceAuthorityError("historical_source_ref is required")

    historical_source_ref = historical_source_ref.strip()
    adoption_ref = adoption_source_ref.strip() if isinstance(adoption_source_ref, str) else ""
    scope = adopted_scope.strip() if isinstance(adopted_scope, str) else ""
    if intended_use == "ADOPT":
        if not adoption_ref or adoption_ref == historical_source_ref:
            raise OperatorSourceAuthorityError("adoption_source_ref must be a separate explicit Operator source")
        if not scope:
            raise OperatorSourceAuthorityError("adopted_scope must identify the exact adopted portion")
    if intended_use != "ADOPT" and (adoption_ref or scope):
        raise OperatorSourceAuthorityError("adoption metadata requires intended_use ADOPT")

    if intended_use == "ADOPT":
        # A plausible ref is not original-source readback or semantic verification.
        # The existing Operator source-binding mechanism must verify the separate
        # adoption instruction before any controlling effect is inferred.
        status = "ADOPTION_CLAIM_PENDING_SOURCE_VERIFICATION"
        direction = False
    elif declared_origin == "OPERATOR_AUTHORED" and intended_use == "DIRECT":
        # This function is triage only. Actual directives remain governed by
        # verified original Operator spans in the existing APEX source gate.
        status = "DECLARED_OPERATOR_DIRECTION_PENDING_SOURCE_VERIFICATION"
        direction = False
    elif declared_origin == "EXTERNAL_AI":
        status = "PROPOSAL_FOR_REVIEW"
        direction = False
    elif declared_origin == "OPERATOR_AUTHORED":
        status = "OPERATOR_TEXT_FOR_EVALUATION"
        direction = False
    else:
        status = "ORIGIN_UNVERIFIED_REVIEW"
        direction = False

    if material_hidden_harms is not None and not isinstance(material_hidden_harms, list):
        raise OperatorSourceAuthorityError("material_hidden_harms must be a list of labels")
    if style_cues is not None and not isinstance(style_cues, list):
        raise OperatorSourceAuthorityError("style_cues must be a list of labels")
    harms = list(material_hidden_harms or [])
    cues = list(style_cues or [])
    if not all(isinstance(v, str) and v.strip() for v in harms):
        raise OperatorSourceAuthorityError("material_hidden_harms must contain nonempty labels")
    if not all(isinstance(v, str) and v.strip() for v in cues):
        raise OperatorSourceAuthorityError("style_cues must contain nonempty labels")
    return {
        "status": status,
        "declared_origin": declared_origin,
        "operator_authorship_proven": False,
        "declared_origin_is_not_independent_authorship_proof": True,
        "controlling_operator_direction": direction,
        "historical_source_ref": historical_source_ref,
        "adoption_source_ref": adoption_ref or None,
        "adopted_scope": scope or None,
        "adopted_scope_verified": False,
        "source_scope_binding_required": intended_use == "ADOPT",
        "requires_original_operator_source_verification": intended_use in {"DIRECT", "ADOPT"},
        "style_cues_are_evidence_of_authorship": False,
        "style_cues_recorded": cues,
        "hidden_harms": harms,
        "hidden_harm_review": "FLAGS_SUPPLIED_NOT_INDEPENDENTLY_AUDITED",
    }


def render_operator_hierarchical_distillation(
    *,
    source_bindings: list[Mapping[str, Any]],
    parents: Mapping[str, str | None],
    source_resolver: SourceResolver,
    expected_proposition_ids: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Render a source-linked parent/child outline of Operator words.

    This is a *positive execution route*, not a new startup or permission
    gate. The caller supplies the parent/child classification; that structure
    is explicitly derivative and must never be mistaken for Operator speech.
    Every leaf is independently resolved from original bytes. No memory
    summary, assistant paraphrase, silent deduplication, or truncated input
    is promoted to an exact quote.
    """
    if not source_bindings:
        raise OperatorSourceAuthorityError("hierarchical distillation requires original source bindings")
    if not isinstance(parents, Mapping):
        raise OperatorSourceAuthorityError("hierarchical distillation parents must be a mapping")
    if not callable(source_resolver):
        raise OperatorSourceAuthorityError("hierarchical distillation source resolver required")

    # Source coverage cannot be inferred from whatever subset a model supplies.
    # An independently inventoried corpus is a HOST responsibility; this optional
    # expected set verifies consistency with the caller's inventory, not the
    # independent completeness of that inventory itself.
    expected_set: set[str] | None = None
    if expected_proposition_ids is not None:
        if (not isinstance(expected_proposition_ids, (list, tuple))
                or not expected_proposition_ids
                or not all(isinstance(x, str) and x.strip() for x in expected_proposition_ids)
                or len(set(expected_proposition_ids)) != len(expected_proposition_ids)):
            raise OperatorSourceAuthorityError("expected source inventory requires unique nonempty identifiers")
        expected_set = set(expected_proposition_ids)

    rows: dict[str, dict[str, str]] = {}
    source_order: list[str] = []
    for position, binding in enumerate(source_bindings):
        if not isinstance(binding, Mapping):
            raise OperatorSourceAuthorityError("hierarchical distillation requires typed source bindings")
        identity = binding.get("proposition_id")
        if not isinstance(identity, str) or not identity.strip() or identity in rows:
            raise OperatorSourceAuthorityError("hierarchical distillation needs distinct nonempty proposition identities")
        verified = verify_source_span_binding(
            binding, resolver=source_resolver,
            prefix=f"hierarchical_distillation[{position}]",
            require_unsuperseded=False,
            allow_historical_quote_states=True,
        )
        if verified.errors or verified.span_text is None:
            raise OperatorSourceAuthorityError(
                "hierarchical distillation source verification failed: "
                + (verified.errors[0] if verified.errors else "source unresolved")
            )
        source_order.append(identity)
        rows[identity] = {
            "source_ref": str(binding["source_ref"]),
            "original_text": verified.span_text,
            "source_state": str(binding["contradiction_state"]),
            "superseded_by": str(binding.get("superseded_by") or ""),
            "temporal_context": str(binding.get("temporal_context") or ""),
        }

    if expected_set is not None and expected_set != set(source_order):
        missing = sorted(expected_set - set(source_order))
        extra = sorted(set(source_order) - expected_set)
        raise OperatorSourceAuthorityError(
            f"expected source inventory missing={missing!r} unexpected={extra!r}"
        )
    if set(parents.keys()) != set(source_order):
        raise OperatorSourceAuthorityError(
            "hierarchical distillation parents must exactly cover every original statement"
        )
    for identity, parent in parents.items():
        if parent is not None and parent not in rows:
            raise OperatorSourceAuthorityError(
                f"hierarchical distillation unknown parent for {identity!r}"
            )

    # Explicit cycle detection before traversal avoids unbounded recursion.
    seen: set[str] = set()
    visiting: set[str] = set()
    def visit(identity: str) -> None:
        if identity in visiting:
            raise OperatorSourceAuthorityError("hierarchical distillation parent cycle")
        if identity in seen:
            return
        visiting.add(identity)
        parent = parents[identity]
        if parent is not None:
            visit(parent)
        visiting.remove(identity)
        seen.add(identity)

    for identity in source_order:
        visit(identity)

    children: dict[str | None, list[str]] = {None: []}
    for identity in source_order:
        children.setdefault(parents[identity], []).append(identity)

    bullets: list[dict[str, Any]] = []
    markdown_lines: list[str] = []
    def emit(identity: str, depth: int) -> None:
        source = rows[identity]
        bullets.append({
            "proposition_id": identity,
            "parent_id": parents[identity],
            "depth": depth,
            "original_text": source["original_text"],
            "source_ref": source["source_ref"],
            "source_author": "operator_source_record",
            "structure_author": "derived_organization_only",
            "source_state": source["source_state"],
            "superseded_by": source["superseded_by"] or None,
            "temporal_context": source["temporal_context"],
            "direction_authority": (
                "historical_quote_only" if source["source_state"] in {"superseded", "conflicted"}
                else "source_quote_not_external_fact"
            ),
        })
        indent = "  " * depth
        # The structured original_text is untouched; continuation indentation
        # in the Markdown projection only changes formatting, not source data.
        displayed_text = source["original_text"].replace("\n", "\n" + indent + "  ")
        markdown_lines.append(
            f"{indent}- VERBATIM [{identity}] ({source['source_ref']}): {displayed_text}"
        )
        for child in children.get(identity, []):
            emit(child, depth + 1)

    for root in children[None]:
        emit(root, 0)
    return {
        "source_count": len(source_order),
        "bullets": bullets,
        "markdown": "\n".join(markdown_lines) + "\n",
        "projection_author": "derived_organization_only",
        "supplied_binding_coverage": len(bullets) == len(source_order),
        "complete_source_coverage": expected_set is not None and len(bullets) == len(expected_set),
        "coverage_scope": (
            "caller_inventory_match_not_independent_corpus_proof"
            if expected_set is not None else "supplied_bindings_only"
        ),
    }
