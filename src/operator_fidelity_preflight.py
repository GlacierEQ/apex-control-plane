"""Fail-closed operator-fidelity preflight for APEX runtime startup.

This gate exists for one failure class: INSTRUCTION_DISPLACEMENT.
It verifies that literal Operator direction survived context compression and
that the selected execution vector did not silently collapse into minimum
scope, governance-first behavior, permission loops, capability reduction,
unsolicited Operator-asset valuation or disposition, inspection-scope
expansion, or textual minimization hidden behind compliant booleans.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from anti_minimization_compiler import inspect_execution_text, supported_rule_codes
from auto_boot import BootError
from prime_directive_boot import receipt_from_environment

DEFAULT_POLICY_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "operator_fidelity_runtime_policy.json"
)
_SEAL = object()


@dataclass(frozen=True, slots=True)
class OperatorFidelityValidation:
    ok: bool
    status: str
    errors: tuple[str, ...]
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _SEAL:
            raise TypeError(
                "validation must be issued by the operator-fidelity enforcer"
            )


_IN_PROCESS: OperatorFidelityValidation | None = None


def _issue(
    ok: bool, status: str, errors: Sequence[str] = ()
) -> OperatorFidelityValidation:
    return OperatorFidelityValidation(ok, status, tuple(errors), _SEAL)


def get_in_process_operator_fidelity_validation() -> OperatorFidelityValidation | None:
    return _IN_PROCESS


def load_operator_fidelity_policy(
    path: str | Path = DEFAULT_POLICY_PATH,
) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BootError(f"operator-fidelity policy not found: {target}") from exc
    except json.JSONDecodeError as exc:
        raise BootError(f"invalid operator-fidelity policy: {exc}") from exc
    if not isinstance(value, dict):
        raise BootError("operator-fidelity policy must be a JSON object")

    required = {
        "schema_version",
        "failure_class",
        "authority",
        "objective",
        "direction",
        "fail_closed",
        "required_true_fields",
        "required_nonempty_fields",
        "selected_path_requirements",
        "operator_asset_sovereignty",
        "anti_minimization",
        "pro_code_elite_humanized_engineering",
        "correction_requirements",
    }
    missing = sorted(required - value.keys())
    if missing:
        raise BootError("operator-fidelity policy missing: " + ", ".join(missing))
    if value.get("fail_closed") is not True:
        raise BootError("operator-fidelity policy must remain fail_closed=true")

    asset_sovereignty = value.get("operator_asset_sovereignty")
    if not isinstance(asset_sovereignty, Mapping):
        raise BootError(
            "operator-fidelity operator_asset_sovereignty must be an object"
        )
    required_asset_flags = {
        "look_inspect_list_inventory_map_are_observation_only": True,
        "asset_value_ranking_requires_explicit_operator_request": True,
        "asset_disposition_requires_explicit_operator_request": True,
        "similar_names_do_not_imply_duplication": True,
        "overlap_does_not_imply_subordination": True,
        "tool_access_is_capability_not_authority": True,
        "observation_is_knowledge_not_authority": True,
    }
    for field_name, expected in required_asset_flags.items():
        if asset_sovereignty.get(field_name) is not expected:
            raise BootError(
                f"operator-fidelity operator_asset_sovereignty.{field_name} must be {expected!r}"
            )

    anti_minimization = value.get("anti_minimization")
    if not isinstance(anti_minimization, Mapping):
        raise BootError("operator-fidelity anti_minimization policy must be an object")
    if str(anti_minimization.get("mode", "")).strip().lower() != "fail_closed":
        raise BootError("operator-fidelity anti_minimization.mode must be fail_closed")
    if anti_minimization.get("semantic_selected_path_scan") is not True:
        raise BootError(
            "operator-fidelity anti_minimization.semantic_selected_path_scan must be true"
        )

    declared_codes = anti_minimization.get("required_semantic_rule_codes")
    if not isinstance(declared_codes, list) or not all(
        isinstance(item, str) and item.strip() for item in declared_codes
    ):
        raise BootError(
            "operator-fidelity anti_minimization.required_semantic_rule_codes must be a non-empty string array"
        )
    declared = tuple(dict.fromkeys(item.strip() for item in declared_codes))
    compiled = supported_rule_codes()
    if set(declared) != set(compiled):
        missing_in_compiler = sorted(set(declared) - set(compiled))
        missing_in_policy = sorted(set(compiled) - set(declared))
        details: list[str] = []
        if missing_in_compiler:
            details.append("policy-only=" + ",".join(missing_in_compiler))
        if missing_in_policy:
            details.append("compiler-only=" + ",".join(missing_in_policy))
        raise BootError("operator-fidelity semantic rule drift: " + "; ".join(details))

    engineering = value.get("pro_code_elite_humanized_engineering")
    if not isinstance(engineering, Mapping) or engineering.get("required") is not True:
        raise BootError(
            "operator-fidelity pro_code_elite_humanized_engineering.required must be true"
        )
    return value


def _norm(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_sha256_ref(value: Any) -> bool:
    if not _nonempty_text(value):
        return False
    prefix, sep, digest = value.strip().partition(":")
    if sep != ":" or prefix.lower() != "sha256":
        return False
    return len(digest) == 64 and all(ch in "0123456789abcdefABCDEF" for ch in digest)


def _iter_text(value: Any) -> Iterable[str]:
    """Yield selected-path prose without converting structured flags to text."""
    if isinstance(value, str):
        if value.strip():
            yield value
        return
    if isinstance(value, Mapping):
        for nested in value.values():
            yield from _iter_text(nested)
        return
    if isinstance(value, (list, tuple)):
        for nested in value:
            yield from _iter_text(nested)


def digest_operator_words(*parts: str) -> str:
    payload = "\n".join(part for part in parts if part).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def validate_operator_fidelity_receipt(
    policy: Mapping[str, Any], receipt: Mapping[str, Any]
) -> tuple[str, ...]:
    errors: list[str] = []
    row = receipt.get("operator_fidelity")
    if not isinstance(row, Mapping):
        return ("operator_fidelity must be an object",)

    if _norm(row.get("failure_class")) != _norm(policy.get("failure_class")):
        errors.append(
            "operator_fidelity.failure_class must be "
            + str(policy.get("failure_class"))
        )
    if _norm(row.get("authority")) != _norm(policy.get("authority")):
        errors.append(
            "operator_fidelity.authority must be " + str(policy.get("authority"))
        )
    if _norm(row.get("objective")) != _norm(policy.get("objective")):
        errors.append(
            "operator_fidelity.objective must be " + str(policy.get("objective"))
        )
    if _norm(row.get("direction")) != _norm(policy.get("direction")):
        errors.append(
            "operator_fidelity.direction must be " + str(policy.get("direction"))
        )

    for field_name in policy.get("required_true_fields", ()):
        if row.get(field_name) is not True:
            errors.append(f"operator_fidelity.{field_name} must be true")

    for field_name in policy.get("required_nonempty_fields", ()):
        if not _nonempty_text(row.get(field_name)):
            errors.append(f"operator_fidelity.{field_name} must be non-empty")

    if not _is_sha256_ref(row.get("operator_words_digest")):
        errors.append("operator_fidelity.operator_words_digest must be sha256:<64 hex>")

    literal_constraints = row.get("literal_constraints")
    if not isinstance(literal_constraints, list) or not any(
        _nonempty_text(value) for value in literal_constraints
    ):
        errors.append(
            "operator_fidelity.literal_constraints must contain exact or resolved operator constraints"
        )

    corrections = row.get("corrections_applied")
    if not isinstance(corrections, list):
        errors.append("operator_fidelity.corrections_applied must be an array")

    correction_present = row.get("correction_present")
    if correction_present not in {True, False}:
        errors.append("operator_fidelity.correction_present must be boolean")
    elif correction_present:
        requirements = policy.get("correction_requirements", {})
        if row.get("objective_function_reassessed") is not True:
            errors.append(
                "operator_fidelity.objective_function_reassessed must be true when a correction exists"
            )
        if not corrections or not any(_nonempty_text(value) for value in corrections):
            errors.append(
                "operator_fidelity.corrections_applied must identify how corrections changed execution"
            )
        effect_field = str(requirements.get("effect_field", "correction_effect"))
        if not _nonempty_text(row.get(effect_field)):
            errors.append(
                f"operator_fidelity.{effect_field} must be non-empty when a correction exists"
            )

    path = row.get("selected_path")
    if not isinstance(path, Mapping):
        errors.append("operator_fidelity.selected_path must be an object")
    else:
        for field_name, expected in policy.get(
            "selected_path_requirements", {}
        ).items():
            if path.get(field_name) is not expected:
                errors.append(
                    f"operator_fidelity.selected_path.{field_name} must be {expected!r}"
                )
        if not _nonempty_text(path.get("functional_advance")):
            errors.append(
                "operator_fidelity.selected_path.functional_advance must be non-empty"
            )
        if not _nonempty_text(path.get("strongest_coherent_path")):
            errors.append(
                "operator_fidelity.selected_path.strongest_coherent_path must be non-empty"
            )

        reduction = path.get("capability_reduction")
        operator_directed = row.get("operator_directed_reduction") is True
        if reduction is True and not operator_directed:
            errors.append(
                "capability reduction requires operator_fidelity.operator_directed_reduction=true"
            )

        selected_path_text = "\n".join(_iter_text(path))
        for finding in inspect_execution_text(
            selected_path_text,
            operator_directed_reduction=operator_directed,
        ):
            errors.append(
                "operator_fidelity.selected_path semantic regression: "
                + finding.message
            )

    next_ceiling = row.get("next_ceiling")
    if not _nonempty_text(next_ceiling):
        errors.append("operator_fidelity.next_ceiling must be non-empty")

    return tuple(dict.fromkeys(errors))


def build_operator_fidelity_request(
    policy: Mapping[str, Any], *, task: str
) -> dict[str, Any]:
    selected_path_contract = {
        **dict(policy.get("selected_path_requirements", {})),
        "capability_reduction": False,
        "functional_advance": "specific capability/function/outcome advanced",
        "strongest_coherent_path": (
            "why this path best executes the Operator-defined operation without scope expansion"
        ),
    }
    return {
        "request_type": "glaciereq_operator_fidelity_preflight",
        "schema_version": policy.get("schema_version"),
        "task": task,
        "failure_class": policy.get("failure_class"),
        "authority": policy.get("authority"),
        "objective": policy.get("objective"),
        "direction": policy.get("direction"),
        "requirements": {
            "read_literal_operator_words": True,
            "bind_explicit_prohibitions": True,
            "load_relevant_corrections": True,
            "check_instruction_displacement": True,
            "reassess_objective_function_after_correction": True,
            "route_uncertainty_to_investigation": True,
            "make_governance_subordinate_to_function": True,
            "reject_minimum_scope_default": True,
            "semantic_scan_selected_path": True,
            "consider_capability_growth": True,
            "apply_pro_code_elite_humanized_engineering": True,
            "preserve_prior_valid_gains": True,
            "preserve_literal_operator_operation_scope": True,
            "no_unsolicited_operator_asset_value_ranking": True,
            "no_unsolicited_operator_asset_disposition": True,
            "inspection_scope_expansion_forbidden": True,
            "identify_functional_advance": True,
            "identify_next_ceiling": True,
        },
        "receipt_contract": {
            "operator_fidelity": {
                "failure_class": "INSTRUCTION_DISPLACEMENT",
                "authority": "operator_intent",
                "objective": "maximum_coherent_advance",
                "direction": "look_up",
                "literal_operator_words_preserved": True,
                "explicit_prohibitions_bound": True,
                "relevant_corrections_loaded": True,
                "instruction_displacement_checked": True,
                "objective_function_matches_operator": True,
                "uncertainty_routed_to_investigation": True,
                "governance_subordinate_to_function": True,
                "prior_valid_gains_preserved": True,
                "anti_minimization_checked": True,
                "capability_growth_considered": True,
                "humanized_engineering_standard_applied": True,
                "operator_words_digest": "sha256:<64 hex over exact/resolved operator words>",
                "literal_constraints": ["exact or resolved operator constraint"],
                "correction_present": "boolean",
                "objective_function_reassessed": "true when correction_present=true",
                "corrections_applied": ["how the correction changed execution"],
                "correction_effect": "required when correction_present=true",
                "operator_directed_reduction": False,
                "selected_path": selected_path_contract,
                "next_ceiling": "what the verified gain unlocks next within Operator direction",
            }
        },
    }


def _continue_operator_fidelity(
    errors: Sequence[str],
    *,
    request: Mapping[str, Any],
) -> OperatorFidelityValidation:
    from startup_continuation import (
        emit_startup_continuation,
        record_startup_continuation,
    )

    continuation = record_startup_continuation(
        "operator_fidelity_preflight",
        errors,
        request=request,
        environment_key="GLACIEREQ_OPERATOR_FIDELITY_STATUS",
    )
    emit_startup_continuation(continuation)
    return _issue(False, "continuation_required", errors)


def automatic_operator_fidelity_preflight() -> OperatorFidelityValidation | None:
    global _IN_PROCESS
    if _IN_PROCESS is not None:
        return _IN_PROCESS

    mode = os.getenv("CASEY_AUTO_BOOT_MODE", "strict").strip().lower()
    if mode == "off" or os.getenv("CASEY_AUTO_BOOT_DISABLE") == "1":
        os.environ["GLACIEREQ_OPERATOR_FIDELITY_STATUS"] = "off"
        return None
    if mode not in {"strict", "request"}:
        raise BootError(f"unsupported CASEY_AUTO_BOOT_MODE: {mode}")

    policy = load_operator_fidelity_policy()
    task = os.getenv(
        "CASEY_BOOT_TASK", "resume Operator-directed unfinished material action"
    )
    receipt = receipt_from_environment()

    if receipt is None:
        print(
            json.dumps(
                build_operator_fidelity_request(policy, task=task),
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        sys.stderr.flush()
        return _continue_operator_fidelity(
            ("no boot receipt supplied",),
            request=build_operator_fidelity_request(policy, task=task),
        )

    errors = validate_operator_fidelity_receipt(policy, receipt)
    validation = _issue(not errors, "complete" if not errors else "blocked", errors)
    if validation.ok:
        _IN_PROCESS = validation
        os.environ["GLACIEREQ_OPERATOR_FIDELITY_STATUS"] = "complete"
        return validation

    request = build_operator_fidelity_request(policy, task=task)
    request["receipt_errors"] = list(validation.errors)
    return _continue_operator_fidelity(validation.errors, request=request)
