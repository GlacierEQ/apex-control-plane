"""Load and validate the derived, non-sovereign Operator and worker models.

The Operator working model prevents repeated rediscovery or reduction of Casey and
his estate. The worker execution contract prevents authority amnesia, operation-
class substitution, and false progress semantics. Neither object becomes project
direction authority; current literal Operator direction controls the mission.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from auto_boot import BootError

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _require_flag(value: Mapping[str, Any], field: str, expected: bool, *, prefix: str) -> None:
    if value.get(field) is not expected:
        raise BootError(f"{prefix}.{field} must be {expected!r}")


def _require_nonempty_text(value: Mapping[str, Any], field: str, *, prefix: str) -> None:
    if not str(value.get(field, "")).strip():
        raise BootError(f"{prefix}.{field} must be non-empty")


def _require_nonempty_list(value: Mapping[str, Any], field: str, *, prefix: str) -> None:
    items = value.get(field)
    if not isinstance(items, list) or not any(str(item).strip() for item in items):
        raise BootError(f"{prefix}.{field} must be a non-empty array")


def _load_repo_json(policy: Mapping[str, Any], field: str, *, label: str) -> dict[str, Any]:
    raw_path = str(policy.get(field, "")).strip()
    if not raw_path:
        raise BootError(f"APEX startup policy must define {field}")

    target = (_REPO_ROOT / raw_path).resolve()
    try:
        target.relative_to(_REPO_ROOT)
    except ValueError as exc:
        raise BootError(f"{field} must stay inside the repository") from exc

    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BootError(f"{label} not found: {target}") from exc
    except json.JSONDecodeError as exc:
        raise BootError(f"invalid {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise BootError(f"{label} must be a JSON object")
    return value


def load_worker_execution_contract(policy: Mapping[str, Any]) -> dict[str, Any]:
    """Return the validated Casey-specific worker execution contract."""
    value = _load_repo_json(
        policy,
        "worker_execution_contract_path",
        label="worker execution contract",
    )
    required = {
        "schema_version",
        "name",
        "role",
        "authority_persistence",
        "operation_semantics",
        "merge_semantics",
        "progress_semantics",
        "execution_semantics",
        "failure_recovery",
        "communication_semantics",
        "startup_receipt_requirements",
    }
    missing = sorted(required - value.keys())
    if missing:
        raise BootError("worker execution contract missing: " + ", ".join(missing))
    if value.get("role") != "ephemeral_bounded_execution_component_inside_glaciereq":
        raise BootError("worker execution contract role must remain bounded inside GlacierEQ")

    authority = value.get("authority_persistence")
    if not isinstance(authority, Mapping):
        raise BootError("worker execution contract authority_persistence must be an object")
    for field in (
        "standing_operator_authority_persists_across_turns",
        "standing_operator_authority_persists_across_branches_and_pr_states",
        "standing_operator_authority_persists_across_tool_and_provider_state_changes",
        "mechanical_state_change_does_not_reopen_operator_decision",
        "reauthorization_requires_operator_revocation_supersession_or_scope_change",
        "worker_may_not_invent_ungranted_authority",
    ):
        _require_flag(authority, field, True, prefix="worker_execution_contract.authority_persistence")

    operation = value.get("operation_semantics")
    if not isinstance(operation, Mapping):
        raise BootError("worker execution contract operation_semantics must be an object")
    for field in (
        "literal_operation_class_persists_until_target_change_or_operator_supersession",
        "continue_means_continue",
        "build_means_build",
        "fix_means_fix",
        "merge_means_promote_authorized_change_to_destination",
        "untangle_means_reconcile_repair_and_organize_not_summarize",
        "execution_constraint_does_not_rewrite_operation_class",
    ):
        _require_flag(operation, field, True, prefix="worker_execution_contract.operation_semantics")

    merge = value.get("merge_semantics")
    if not isinstance(merge, Mapping):
        raise BootError("worker execution contract merge_semantics must be an object")
    for field in (
        "granted_merge_authorization_persists_until_merged_or_revoked",
        "queued_checks_do_not_reopen_merge_decision",
        "merge_conflicts_are_execution_problems_not_authorization_questions",
        "merge_immediately_when_authorized_route_permits",
        "destination_readback_required_before_merge_completion",
    ):
        _require_flag(merge, field, True, prefix="worker_execution_contract.merge_semantics")

    progress = value.get("progress_semantics")
    if not isinstance(progress, Mapping):
        raise BootError("worker execution contract progress_semantics must be an object")
    for field in (
        "worker_activity_is_progress",
        "plan_is_progress",
        "retrieval_is_progress",
        "branch_is_progress",
        "commit_is_progress",
        "pull_request_is_progress",
        "review_is_progress",
        "tool_invocation_is_progress",
    ):
        _require_flag(progress, field, False, prefix="worker_execution_contract.progress_semantics")
    for field in (
        "progress_requires_material_target_state_change",
        "intermediate_artifacts_are_not_destination",
        "intermediate_state_must_be_reported_as_intermediate",
    ):
        _require_flag(progress, field, True, prefix="worker_execution_contract.progress_semantics")

    execution = value.get("execution_semantics")
    if not isinstance(execution, Mapping):
        raise BootError("worker execution contract execution_semantics must be an object")
    for field in (
        "tool_first_when_tool_can_materially_execute",
        "no_execution_claim_without_tool_evidence_when_tool_execution_is_required",
        "no_verified_mutation_claim_without_readback",
        "preserve_verified_gains_across_failures",
        "blockers_preserve_authorization_and_continuation",
        "resume_from_exact_frontier_without_operator_restatement",
    ):
        _require_flag(execution, field, True, prefix="worker_execution_contract.execution_semantics")

    recovery = value.get("failure_recovery")
    if not isinstance(recovery, Mapping):
        raise BootError("worker execution contract failure_recovery must be an object")
    for field in (
        "forceful_operator_correction_is_state_integrity_interrupt",
        "generic_deescalation_must_not_replace_execution_recovery",
        "recover_first_dropped_or_rewritten_state",
        "repair_controllable_defect_before_reporting",
        "resume_original_mission_after_repair",
    ):
        _require_flag(recovery, field, True, prefix="worker_execution_contract.failure_recovery")

    communication = value.get("communication_semantics")
    if not isinstance(communication, Mapping):
        raise BootError("worker execution contract communication_semantics must be an object")
    for field in (
        "prefer_changed_target_state",
        "prefer_exact_blocker_when_real",
        "prefer_receipt_and_readback_proof",
        "prefer_nearest_continuation_point",
        "do_not_narrate_worker_activity_as_accomplishment",
        "do_not_repeat_operator_preferences_instead_of_executing",
        "do_not_claim_fixed_before_target_state_verification",
    ):
        _require_flag(communication, field, True, prefix="worker_execution_contract.communication_semantics")

    receipts = value.get("startup_receipt_requirements")
    if not isinstance(receipts, Mapping):
        raise BootError("worker execution contract startup_receipt_requirements must be an object")
    for field in (
        "worker_execution_contract_loaded",
        "standing_authorizations_preserved",
        "target_state_progress_semantics_loaded",
        "operator_operation_class_preserved",
    ):
        _require_flag(receipts, field, True, prefix="worker_execution_contract.startup_receipt_requirements")
    return value


def load_operator_working_model(policy: Mapping[str, Any]) -> dict[str, Any]:
    """Return a validated Operator model with the bounded worker contract attached."""
    value = _load_repo_json(policy, "operator_working_model_path", label="operator working model")
    required = {
        "schema_version",
        "name",
        "authority_semantics",
        "operator_identity",
        "estate_model",
        "actual_work_pattern",
        "default_loop",
        "state_reuse",
        "scope_fidelity",
        "working_patterns",
        "impact_first_judgment",
        "literal_operator_anchors",
        "failure_interrupt_vectors",
        "anti_patterns",
        "startup_receipt_requirements",
    }
    missing = sorted(required - value.keys())
    if missing:
        raise BootError("operator working model missing: " + ", ".join(missing))

    authority = value.get("authority_semantics")
    if not isinstance(authority, Mapping):
        raise BootError("operator working model authority_semantics must be an object")
    for field, expected in {
        "current_operator_message_controls_current_mission": True,
        "literal_operator_sources_outrank_assistant_derivations": True,
        "assistant_working_model_is_derived_and_non_sovereign": True,
        "memory_and_continuity_state_are_starting_state_not_project_authority": True,
        "historical_summaries_are_routing_hints_not_identity_or_current_state": True,
    }.items():
        _require_flag(authority, field, expected, prefix="operator_working_model.authority_semantics")

    identity = value.get("operator_identity")
    if not isinstance(identity, Mapping):
        raise BootError("operator working model operator_identity must be an object")
    for field in ("name", "role", "primary_model", "anti_reduction_rule", "builds"):
        _require_nonempty_text(identity, field, prefix="operator_working_model.operator_identity")
    _require_nonempty_list(identity, "diagnostic_discipline", prefix="operator_working_model.operator_identity")

    estate = value.get("estate_model")
    if not isinstance(estate, Mapping):
        raise BootError("operator working model estate_model must be an object")
    for field in ("glaciereq", "design_thesis", "target", "organ_rule", "anti_monolith_rule"):
        _require_nonempty_text(estate, field, prefix="operator_working_model.estate_model")
    for field in ("principles", "recurring_organs"):
        _require_nonempty_list(estate, field, prefix="operator_working_model.estate_model")

    actual_work_pattern = value.get("actual_work_pattern")
    if not isinstance(actual_work_pattern, list) or not any(str(item).strip() for item in actual_work_pattern):
        raise BootError("operator_working_model.actual_work_pattern must be a non-empty array")
    if not str(value.get("default_loop", "")).strip():
        raise BootError("operator_working_model.default_loop must be non-empty")

    state_reuse = value.get("state_reuse")
    if not isinstance(state_reuse, Mapping):
        raise BootError("operator working model state_reuse must be an object")
    _require_flag(state_reuse, "rediscovery_is_progress", False, prefix="operator_working_model.state_reuse")
    _require_nonempty_text(state_reuse, "rule", prefix="operator_working_model.state_reuse")

    scope_fidelity = value.get("scope_fidelity")
    if not isinstance(scope_fidelity, Mapping):
        raise BootError("operator working model scope_fidelity must be an object")
    for field, expected in {
        "operator_asserted_scope_is_source_state": True,
        "scope_carries_across_execution_contexts": True,
        "assistant_may_not_narrow_scope_without_explicit_operator_authorization": True,
        "assistant_may_not_replace_systemic_with_local": True,
        "assistant_may_not_replace_longitudinal_with_current_thread": True,
        "assistant_may_not_introduce_partial_or_frequency_qualifiers_without_source_basis": True,
        "operator_scope_correction_propagates_forward": True,
    }.items():
        _require_flag(scope_fidelity, field, expected, prefix="operator_working_model.scope_fidelity")
    _require_nonempty_text(scope_fidelity, "rule", prefix="operator_working_model.scope_fidelity")
    _require_nonempty_list(
        scope_fidelity,
        "examples_of_forbidden_unbacked_narrowing",
        prefix="operator_working_model.scope_fidelity",
    )

    patterns = value.get("working_patterns")
    if not isinstance(patterns, Mapping) or not patterns:
        raise BootError("operator_working_model.working_patterns must be a non-empty object")

    impact = value.get("impact_first_judgment")
    if not isinstance(impact, Mapping):
        raise BootError("operator working model impact_first_judgment must be an object")
    _require_nonempty_text(impact, "rule", prefix="operator_working_model.impact_first_judgment")
    _require_nonempty_list(impact, "weigh", prefix="operator_working_model.impact_first_judgment")
    _require_flag(impact, "reweight_on_state_change", True, prefix="operator_working_model.impact_first_judgment")
    _require_flag(
        impact,
        "frameworks_are_inputs_not_substitutes_for_judgment",
        True,
        prefix="operator_working_model.impact_first_judgment",
    )

    interrupts = value.get("failure_interrupt_vectors")
    if not isinstance(interrupts, Mapping):
        raise BootError("operator_working_model.failure_interrupt_vectors must be an object")
    _require_nonempty_list(interrupts, "phrases", prefix="operator_working_model.failure_interrupt_vectors")
    _require_nonempty_text(
        interrupts,
        "contextual_semantics",
        prefix="operator_working_model.failure_interrupt_vectors",
    )

    receipt_requirements = value.get("startup_receipt_requirements")
    if not isinstance(receipt_requirements, Mapping):
        raise BootError("operator working model startup_receipt_requirements must be an object")
    for field in (
        "operator_identity_loaded",
        "operator_estate_model_loaded",
        "operator_model_loaded",
        "relevant_memory_consulted_when_available",
        "known_state_reused_before_rediscovery",
        "literal_operator_sources_preserved_separately_from_derived_interpretation",
        "working_method_applied_to_task_decomposition",
        "operator_asserted_scope_preserved",
        "continuation_point_resolved",
        "rediscovery_if_performed_has_material_justification",
    ):
        _require_flag(
            receipt_requirements,
            field,
            True,
            prefix="operator_working_model.startup_receipt_requirements",
        )

    value["worker_execution_contract"] = load_worker_execution_contract(policy)
    return value


def public_operator_model_projection(model: Mapping[str, Any]) -> dict[str, Any]:
    """Return the complete boot-safe projection without converting it into authority."""
    return {
        "name": model.get("name"),
        "schema_version": model.get("schema_version"),
        "authority_semantics": dict(model.get("authority_semantics", {})),
        "operator_identity": dict(model.get("operator_identity", {})),
        "estate_model": dict(model.get("estate_model", {})),
        "actual_work_pattern": list(model.get("actual_work_pattern", [])),
        "default_loop": model.get("default_loop"),
        "state_reuse": dict(model.get("state_reuse", {})),
        "scope_fidelity": dict(model.get("scope_fidelity", {})),
        "working_patterns": dict(model.get("working_patterns", {})),
        "impact_first_judgment": dict(model.get("impact_first_judgment", {})),
        "worker_execution_contract": dict(model.get("worker_execution_contract", {})),
        "literal_operator_anchors": list(model.get("literal_operator_anchors", [])),
        "failure_interrupt_vectors": dict(model.get("failure_interrupt_vectors", {})),
        "anti_patterns": list(model.get("anti_patterns", [])),
        "startup_receipt_requirements": dict(model.get("startup_receipt_requirements", {})),
    }
