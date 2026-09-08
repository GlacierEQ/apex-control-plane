"""Fail-closed defense against generic-model attractors and platform-pressure drift.

This gate prevents a compressed assistant representation from impersonating
source-bearing Operator state. It does not attempt to override platform policy;
it proves that any higher-priority constraint is scoped to the constrained
action and has not silently rewritten the Operator mission, operation class,
continuation point, or source topology.
"""
from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from auto_boot import BootError
from prime_directive_boot import receipt_from_environment

DEFAULT_POLICY_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "model_attractor_defense_policy.json"
)
_SEAL = object()

SOURCE_ROLE_SEMANTIC_KEYS = frozenset(
    {
        "providers_are_typed_peers",
        "connector_authority_tiers_are_routing_metadata_only",
        "canonical_role_fields_are_compatibility_labels_only",
        "topology_does_not_confer_epistemic_or_project_authority",
        "proposition_specific_source_authority_required",
        "operator_controls_project_direction",
        "source_bearing_systems_control_external_fact_support_within_domain",
        "verification_controls_completion_state",
    }
)
_SOURCE_ROLE_VERIFICATION_STATE = "verified"


@dataclass(frozen=True, slots=True)
class ModelAttractorValidation:
    ok: bool
    status: str
    errors: tuple[str, ...]
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _SEAL:
            raise TypeError("validation must be issued by the model-attractor defense")


_IN_PROCESS: ModelAttractorValidation | None = None


def _issue(ok: bool, status: str, errors: Sequence[str] = ()) -> ModelAttractorValidation:
    return ModelAttractorValidation(ok, status, tuple(errors), _SEAL)


def get_in_process_model_attractor_validation() -> ModelAttractorValidation | None:
    return _IN_PROCESS


def _nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _nonempty_string_array(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(
        _nonempty_text(item) for item in value
    )


def load_model_attractor_policy(
    path: str | Path = DEFAULT_POLICY_PATH,
) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BootError(f"model-attractor policy not found: {target}") from exc
    except json.JSONDecodeError as exc:
        raise BootError(f"invalid model-attractor policy: {exc}") from exc
    if not isinstance(value, dict):
        raise BootError("model-attractor policy must be a JSON object")

    required = {
        "schema_version",
        "failure_class",
        "fail_closed",
        "required_boolean_fields",
        "continuity_required_fields",
        "constraint_scoping",
        "routing_hints_only",
        "forbidden_transformations",
        "source_role_semantics",
    }
    missing = sorted(required - value.keys())
    if missing:
        raise BootError("model-attractor policy missing: " + ", ".join(missing))
    if value.get("fail_closed") is not True:
        raise BootError("model-attractor policy must remain fail_closed=true")
    if not isinstance(value.get("required_boolean_fields"), Mapping):
        raise BootError("model-attractor required_boolean_fields must be an object")
    if not isinstance(value.get("continuity_required_fields"), Mapping):
        raise BootError("model-attractor continuity_required_fields must be an object")

    semantics = value.get("source_role_semantics")
    if not isinstance(semantics, Mapping) or not semantics:
        raise BootError("model-attractor source_role_semantics must be a non-empty object")
    if not all(
        isinstance(key, str) and key.strip() and isinstance(expected, bool)
        for key, expected in semantics.items()
    ):
        raise BootError("model-attractor source_role_semantics must contain boolean invariants")
    semantic_keys = set(semantics)
    missing_semantics = sorted(SOURCE_ROLE_SEMANTIC_KEYS - semantic_keys)
    unexpected_semantics = sorted(semantic_keys - SOURCE_ROLE_SEMANTIC_KEYS)
    if missing_semantics or unexpected_semantics:
        details: list[str] = []
        if missing_semantics:
            details.append("missing=" + ",".join(missing_semantics))
        if unexpected_semantics:
            details.append("unexpected=" + ",".join(unexpected_semantics))
        raise BootError(
            "model-attractor source_role_semantics must match approved keys ("
            + "; ".join(details)
            + ")"
        )

    transformations = value.get("forbidden_transformations")
    if not isinstance(transformations, list) or not transformations or not all(
        isinstance(item, str) and item.strip() for item in transformations
    ):
        raise BootError("model-attractor forbidden_transformations must be a non-empty string array")
    return value


def validate_model_attractor_receipt(
    policy: Mapping[str, Any], receipt: Mapping[str, Any]
) -> tuple[str, ...]:
    errors: list[str] = []
    row = receipt.get("model_attractor_defense")
    if not isinstance(row, Mapping):
        return ("model_attractor_defense must be an object",)

    if str(row.get("failure_class", "")).strip().upper() != str(
        policy.get("failure_class", "")
    ).strip().upper():
        errors.append(
            "model_attractor_defense.failure_class must be "
            + str(policy.get("failure_class"))
        )

    continuity_required = row.get("continuity_required")
    if continuity_required not in {True, False}:
        errors.append("model_attractor_defense.continuity_required must be boolean")

    for field_name, expected in policy.get("required_boolean_fields", {}).items():
        if row.get(field_name) is not expected:
            errors.append(
                f"model_attractor_defense.{field_name} must be {expected!r}"
            )

    source_role_semantics = policy.get("source_role_semantics", {})
    for field_name, expected in source_role_semantics.items():
        if row.get(field_name) is not expected:
            errors.append(
                f"model_attractor_defense.{field_name} must be {expected!r}"
            )

    source_role_evidence = row.get("source_role_evidence")
    if not isinstance(source_role_evidence, Mapping):
        errors.append("model_attractor_defense.source_role_evidence must be an object")
    else:
        for field_name, expected in source_role_semantics.items():
            evidence = source_role_evidence.get(field_name)
            prefix = f"model_attractor_defense.source_role_evidence.{field_name}"
            if not isinstance(evidence, Mapping):
                errors.append(f"{prefix} must be an object")
                continue
            if evidence.get("asserted_value") is not expected:
                errors.append(f"{prefix}.asserted_value must be {expected!r}")
            if not _nonempty_text(evidence.get("proposition")):
                errors.append(f"{prefix}.proposition must be non-empty")
            if not _nonempty_string_array(evidence.get("source_refs")):
                errors.append(f"{prefix}.source_refs must be a non-empty string array")
            if not _nonempty_string_array(evidence.get("provider_refs")):
                errors.append(f"{prefix}.provider_refs must be a non-empty string array")
            if str(evidence.get("verification_state", "")).strip().lower() != (
                _SOURCE_ROLE_VERIFICATION_STATE
            ):
                errors.append(
                    f"{prefix}.verification_state must be {_SOURCE_ROLE_VERIFICATION_STATE}"
                )

    constraint_scope = row.get("platform_constraint_scope")
    if not _nonempty_text(constraint_scope):
        errors.append("model_attractor_defense.platform_constraint_scope must be non-empty")
    elif constraint_scope.strip().lower() not in {"none", "narrow_action_constraint"}:
        errors.append(
            "model_attractor_defense.platform_constraint_scope must be none or narrow_action_constraint"
        )

    blocked_sources = row.get("blocked_sources", [])
    if not isinstance(blocked_sources, list) or not all(
        _nonempty_text(item) for item in blocked_sources
    ):
        errors.append("model_attractor_defense.blocked_sources must be an array of non-empty strings")

    if continuity_required is True:
        for field_name, expected in policy.get("continuity_required_fields", {}).items():
            value = row.get(field_name)
            if expected is True and value is not True:
                errors.append(f"model_attractor_defense.{field_name} must be true")
            elif expected == "nonempty" and not _nonempty_text(value):
                errors.append(f"model_attractor_defense.{field_name} must be non-empty")
            elif expected == "nonempty_array":
                if not isinstance(value, list) or not any(_nonempty_text(item) for item in value):
                    errors.append(
                        f"model_attractor_defense.{field_name} must contain at least one source reference"
                    )

        if blocked_sources and row.get("partial_hydration_declared") is not True:
            errors.append(
                "model_attractor_defense.partial_hydration_declared must be true when blocked_sources is non-empty"
            )
    elif continuity_required is False:
        if row.get("hydration_complete_for_material_state") not in {True, False, None}:
            errors.append(
                "model_attractor_defense.hydration_complete_for_material_state must be boolean when supplied"
            )

    return tuple(dict.fromkeys(errors))


def build_model_attractor_request(
    policy: Mapping[str, Any], *, task: str
) -> dict[str, Any]:
    source_role_semantics = dict(policy.get("source_role_semantics", {}))
    source_role_evidence_contract = {
        field_name: {
            "asserted_value": expected,
            "proposition": "non-empty proposition tied to this invariant",
            "source_refs": ["one or more source-bearing references"],
            "provider_refs": ["one or more provider/authority references"],
            "verification_state": _SOURCE_ROLE_VERIFICATION_STATE,
        }
        for field_name, expected in source_role_semantics.items()
    }
    return {
        "request_type": "glaciereq_model_attractor_defense_preflight",
        "schema_version": policy.get("schema_version"),
        "task": task,
        "failure_class": policy.get("failure_class"),
        "principle": policy.get("principle"),
        "forbidden_transformations": list(policy.get("forbidden_transformations", ())),
        "source_role_semantics": source_role_semantics,
        "requirements": {
            "classify_continuity_requirement": True,
            "bind_current_operator_message": True,
            "preserve_operator_operation_class": True,
            "reuse_known_state_before_rediscovery": True,
            "identify_nearest_valid_continuation_when_continuity_dependent": True,
            "identify_nearest_executable_frontier_when_continuity_dependent": True,
            "hydrate_material_source_bearing_state_when_continuity_dependent": True,
            "preserve_prior_verified_gains_when_continuity_dependent": True,
            "treat_memory_and_summaries_as_routing_hints_only": True,
            "preserve_polycentric_provenance_and_contradictions": True,
            "preserve_mission_support_boundary": True,
            "forbid_summary_as_state_substitution": True,
            "forbid_reconstruction_as_continuation_substitution": True,
            "forbid_plan_as_execution_substitution": True,
            "forbid_support_work_as_mission_substitution": True,
            "forbid_operator_correction_as_assistant_meta_task": True,
            "forbid_unrequested_global_canonicalization": True,
            "scope_platform_constraints_to_the_specific_constrained_action": True,
            "forbid_platform_constraint_from_rewriting_operator_mission": True,
            "forbid_generic_model_prior_from_rewriting_operation_class": True,
            "recover_known_state_instead_of_reasking_when_available": True,
            "forbid_dragging_operator_through_recoverable_state": True,
            "enforce_source_role_semantics": True,
            "require_source_role_evidence": True,
            "forbid_connector_metadata_from_becoming_global_authority": True,
        },
        "receipt_contract": {
            "model_attractor_defense": {
                "failure_class": "MODEL_ATTRACTOR_DRIFT",
                "continuity_required": "boolean",
                "current_operator_message_bound": True,
                "operator_mission_preserved": True,
                "operator_operation_class_preserved": True,
                "known_state_reuse_checked": True,
                "nearest_valid_continuation_checked": True,
                "abstraction_substitution_checked": True,
                "mission_support_boundary_preserved": True,
                "memory_projection_treated_as_authority": False,
                "summary_substituted_for_state": False,
                "reconstruction_substituted_for_continuation": False,
                "plan_substituted_for_execution": False,
                "support_work_substituted_for_mission": False,
                "assistant_meta_task_substituted_for_operator_task": False,
                "global_canonicalization_without_operator_direction": False,
                "platform_constraint_reframed_mission": False,
                "generic_assistant_prior_reframed_operation": False,
                "unnecessary_reasking_of_recoverable_state": False,
                "operator_dragged_through_recoverable_state": False,
                **source_role_semantics,
                "source_role_evidence": source_role_evidence_contract,
                "platform_constraint_scope": "none|narrow_action_constraint",
                "blocked_sources": [],
                "partial_hydration_declared": False,
                "operator_operation_class": "required when continuity_required=true",
                "active_thread": "required when continuity_required=true",
                "continuation_ref": "required when continuity_required=true",
                "source_refs": ["required when continuity_required=true"],
                "known_state_reused": "true when continuity_required=true",
                "nearest_executable_frontier_identified": "true when continuity_required=true",
                "prior_verified_gains_preserved": "true when continuity_required=true",
                "hydration_complete_for_material_state": "true when continuity_required=true",
                "source_bearing_state_used": "true when continuity_required=true",
                "polycentric_state_preserved": "true when continuity_required=true",
                "provenance_preserved": "true when continuity_required=true",
                "contradictions_preserved_or_explicitly_resolved": "true when continuity_required=true"
            }
        },
    }


def _continue_model_attractor(
    errors: Sequence[str], *, request: Mapping[str, Any]
) -> ModelAttractorValidation:
    from startup_continuation import emit_startup_continuation, record_startup_continuation

    continuation = record_startup_continuation(
        "model_attractor_defense",
        errors,
        request=request,
        environment_key="GLACIEREQ_MODEL_ATTRACTOR_DEFENSE_STATUS",
    )
    emit_startup_continuation(continuation)
    return _issue(False, "continuation_required", errors)


def automatic_model_attractor_defense() -> ModelAttractorValidation | None:
    global _IN_PROCESS
    if _IN_PROCESS is not None:
        return _IN_PROCESS

    mode = os.getenv("CASEY_AUTO_BOOT_MODE", "strict").strip().lower()
    if mode == "off" or os.getenv("CASEY_AUTO_BOOT_DISABLE") == "1":
        os.environ["GLACIEREQ_MODEL_ATTRACTOR_DEFENSE_STATUS"] = "off"
        return None
    if mode not in {"strict", "request"}:
        raise BootError(f"unsupported CASEY_AUTO_BOOT_MODE: {mode}")

    policy = load_model_attractor_policy()
    task = os.getenv(
        "CASEY_BOOT_TASK", "resume Operator-directed unfinished material action"
    )
    receipt = receipt_from_environment()

    if receipt is None:
        request = build_model_attractor_request(policy, task=task)
        print(json.dumps(request, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        sys.stderr.flush()
        return _continue_model_attractor(("no boot receipt supplied",), request=request)

    errors = validate_model_attractor_receipt(policy, receipt)
    validation = _issue(not errors, "complete" if not errors else "blocked", errors)
    if validation.ok:
        _IN_PROCESS = validation
        os.environ["GLACIEREQ_MODEL_ATTRACTOR_DEFENSE_STATUS"] = "complete"
        return validation

    request = build_model_attractor_request(policy, task=task)
    request["receipt_errors"] = list(validation.errors)
    return _continue_model_attractor(validation.errors, request=request)
