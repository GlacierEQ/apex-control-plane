"""Fail-closed defense against generic-model attractors and platform-pressure drift.

This gate prevents a compressed assistant representation from impersonating
source-bearing Operator state. It does not attempt to override platform policy;
it proves that any higher-priority constraint is scoped to the constrained
action and has not silently rewritten the Operator mission, operation class,
continuation point, or source topology.
"""
from __future__ import annotations

import hashlib
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
_REPO_ROOT = Path(__file__).resolve().parents[1]
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
DERIVATIVE_REPRESENTATION_SEMANTIC_KEYS = frozenset(
    {
        "live_operator_objective_has_direction_authority",
        "operator_firsthand_words_are_not_rewritten_by_profile_summaries",
        "source_bearing_state_outranks_derivative_state_for_factual_support",
        "summaries_profiles_memories_indexes_and_manifests_are_retrieval_and_orientation_aids",
        "derivative_representation_may_not_reduce_target_scale",
        "derivative_representation_may_not_change_operation_class",
        "derivative_representation_may_not_convert_execution_into_explanation",
        "derivative_representation_may_not_convert_dynamic_intelligence_into_static_rule_by_default",
        "presentation_concision_is_independent_of_execution_depth",
        "completion_requires_target_state_evidence_not_response_completion",
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


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _resolve_local_source(source_ref: str) -> tuple[Path, bytes]:
    """Resolve source refs whose bytes are independently available to this runtime.

    Receipt-provided labels are not accepted as proof. Only repository-local
    source refs are eligible for a recomputable semantic binding here.
    """
    if not _nonempty_text(source_ref):
        raise ValueError("source_ref must be non-empty")

    locator = source_ref.split("#", 1)[0].strip()
    if locator.startswith("policy:"):
        relative = Path("config") / locator[len("policy:") :]
    elif locator.startswith("repo:"):
        relative = Path(locator[len("repo:") :])
    else:
        raise ValueError(
            "source_ref must use a recomputable local scheme (policy: or repo:)"
        )

    resolved = (_REPO_ROOT / relative).resolve()
    try:
        resolved.relative_to(_REPO_ROOT)
    except ValueError as exc:
        raise ValueError("source_ref escapes repository root") from exc
    if not resolved.is_file():
        raise ValueError(f"source_ref does not resolve to a file: {source_ref}")
    return resolved, resolved.read_bytes()


def build_local_source_binding(source_ref: str) -> dict[str, str]:
    """Build a binding whose digest the validator will recompute independently."""
    _, payload = _resolve_local_source(source_ref)
    return {
        "source_ref": source_ref,
        "source_sha256": _sha256_bytes(payload),
    }


def _validate_source_role_bindings(
    *,
    field_name: str,
    expected: bool,
    evidence: Mapping[str, Any],
    prefix: str,
) -> tuple[str, ...]:
    errors: list[str] = []
    source_refs = evidence.get("source_refs")
    bindings = evidence.get("source_bindings")
    if not _nonempty_string_array(source_refs):
        return ()
    if not isinstance(bindings, list) or not bindings:
        return (f"{prefix}.source_bindings must be a non-empty array",)

    verified_binding = False
    for index, binding in enumerate(bindings):
        binding_prefix = f"{prefix}.source_bindings[{index}]"
        if not isinstance(binding, Mapping):
            errors.append(f"{binding_prefix} must be an object")
            continue

        source_ref = binding.get("source_ref")
        if not _nonempty_text(source_ref):
            errors.append(f"{binding_prefix}.source_ref must be non-empty")
            continue
        if source_ref not in source_refs:
            errors.append(
                f"{binding_prefix}.source_ref must match an entry in source_refs"
            )
            continue
        if not source_ref.startswith("policy:"):
            errors.append(
                f"{binding_prefix}.source_ref must bind source-role semantics to policy source"
            )
            continue

        fragment = source_ref.split("#", 1)[1] if "#" in source_ref else ""
        if fragment != field_name:
            errors.append(
                f"{binding_prefix}.source_ref fragment must be {field_name}"
            )
            continue

        try:
            _, payload = _resolve_local_source(source_ref)
        except ValueError as exc:
            errors.append(f"{binding_prefix}.source_ref is not recomputable: {exc}")
            continue

        expected_digest = _sha256_bytes(payload)
        if binding.get("source_sha256") != expected_digest:
            errors.append(
                f"{binding_prefix}.source_sha256 does not match source bytes"
            )
            continue

        try:
            source_document = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            errors.append(
                f"{binding_prefix}.source_ref must resolve to valid UTF-8 JSON policy"
            )
            continue
        source_semantics = source_document.get("source_role_semantics")
        if not isinstance(source_semantics, Mapping):
            errors.append(
                f"{binding_prefix}.source_ref lacks source_role_semantics"
            )
            continue
        if source_semantics.get(field_name) is not expected:
            errors.append(
                f"{binding_prefix}.source_ref does not support asserted_value {expected!r}"
            )
            continue
        verified_binding = True

    if not verified_binding:
        errors.append(
            f"{prefix} has no independently recomputable source binding"
        )
    return tuple(errors)


def _validate_boolean_semantics(
    *,
    value: Any,
    label: str,
    approved_keys: frozenset[str],
) -> None:
    if not isinstance(value, Mapping) or not value:
        raise BootError(f"model-attractor {label} must be a non-empty object")
    if not all(
        isinstance(key, str) and key.strip() and isinstance(expected, bool)
        for key, expected in value.items()
    ):
        raise BootError(f"model-attractor {label} must contain boolean invariants")
    semantic_keys = set(value)
    missing = sorted(approved_keys - semantic_keys)
    unexpected = sorted(semantic_keys - approved_keys)
    if missing or unexpected:
        details: list[str] = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if unexpected:
            details.append("unexpected=" + ",".join(unexpected))
        raise BootError(
            f"model-attractor {label} must match approved keys ("
            + "; ".join(details)
            + ")"
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
        "derivative_representation_semantics",
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

    _validate_boolean_semantics(
        value=value.get("source_role_semantics"),
        label="source_role_semantics",
        approved_keys=SOURCE_ROLE_SEMANTIC_KEYS,
    )
    _validate_boolean_semantics(
        value=value.get("derivative_representation_semantics"),
        label="derivative_representation_semantics",
        approved_keys=DERIVATIVE_REPRESENTATION_SEMANTIC_KEYS,
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
            errors.extend(
                _validate_source_role_bindings(
                    field_name=field_name,
                    expected=expected,
                    evidence=evidence,
                    prefix=prefix,
                )
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


def _continuity_contract(policy: Mapping[str, Any]) -> dict[str, Any]:
    contract: dict[str, Any] = {}
    for field_name, expected in policy.get("continuity_required_fields", {}).items():
        if expected is True:
            contract[field_name] = "true when continuity_required=true"
        elif expected == "nonempty":
            contract[field_name] = "required when continuity_required=true"
        elif expected == "nonempty_array":
            contract[field_name] = ["required when continuity_required=true"]
        else:
            contract[field_name] = expected
    return contract


def build_model_attractor_request(
    policy: Mapping[str, Any], *, task: str
) -> dict[str, Any]:
    source_role_semantics = dict(policy.get("source_role_semantics", {}))
    derivative_semantics = dict(policy.get("derivative_representation_semantics", {}))
    required_boolean_contract = dict(policy.get("required_boolean_fields", {}))
    continuity_contract = _continuity_contract(policy)
    source_role_evidence_contract = {
        field_name: {
            "asserted_value": expected,
            "proposition": "non-empty proposition tied to this invariant",
            "source_refs": [
                f"policy:model_attractor_defense_policy.json#{field_name}"
            ],
            "provider_refs": ["one or more provider/authority references"],
            "source_bindings": [
                {
                    "source_ref": f"policy:model_attractor_defense_policy.json#{field_name}",
                    "source_sha256": "sha256:<64 hex recomputed from source bytes>",
                }
            ],
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
        "derivative_representation_semantics": derivative_semantics,
        "requirements": {
            "classify_continuity_requirement": True,
            "bind_current_operator_message": True,
            "preserve_operator_operation_class": True,
            "preserve_operator_target_scale": True,
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
            "forbid_objective_surrogate_substitution": True,
            "forbid_derivative_authority_inversion": True,
            "forbid_scaffold_as_build_substitution": True,
            "forbid_response_as_operation_substitution": True,
            "forbid_derivative_profile_from_overriding_live_operator_signal": True,
            "keep_presentation_concision_independent_of_execution_depth": True,
            "require_target_state_evidence_for_completion": True,
            "forbid_support_work_as_mission_substitution": True,
            "forbid_operator_correction_as_assistant_meta_task": True,
            "forbid_unrequested_global_canonicalization": True,
            "scope_platform_constraints_to_the_specific_constrained_action": True,
            "forbid_platform_constraint_from_rewriting_operator_mission": True,
            "forbid_generic_model_prior_from_rewriting_operation_class": True,
            "recover_known_state_instead_of_reasking_when_available": True,
            "forbid_dragging_operator_through_recoverable_state": True,
            "enforce_required_boolean_fields_from_policy": True,
            "enforce_continuity_fields_from_policy": True,
            "enforce_derivative_representation_semantics": True,
            "enforce_source_role_semantics": True,
            "require_source_role_evidence": True,
            "require_recomputable_source_role_bindings": True,
            "forbid_connector_metadata_from_becoming_global_authority": True,
        },
        "receipt_contract": {
            "model_attractor_defense": {
                "failure_class": "MODEL_ATTRACTOR_DRIFT",
                "continuity_required": "boolean",
                **required_boolean_contract,
                **source_role_semantics,
                "source_role_evidence": source_role_evidence_contract,
                "platform_constraint_scope": "none|narrow_action_constraint",
                "blocked_sources": [],
                "partial_hydration_declared": False,
                **continuity_contract,
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
