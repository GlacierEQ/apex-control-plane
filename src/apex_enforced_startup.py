"""APEX Genesis fail-closed startup and execution-state enforcement.

This layer sits above the existing continuity and Prime Directive proofs. It does
not replace them. It binds those proofs to OPERATOR project-direction authority,
continuation, preserved prior gain, Operator-aligned coherent path selection,
Operator asset sovereignty, and evidence-backed execution-state transitions.

Inspection may expand into non-destructive mission-aligned hardening when that
expansion remains inside the Operator-defined objective. Asset ranking and
asset disposition remain separately bound to explicit Operator direction.
"""
from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from auto_boot import EXIT_BOOT_BLOCKED, BootError
from prime_directive_boot import receipt_from_environment

DEFAULT_POLICY_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "apex_enforced_startup_policy.json"
)
_SEAL = object()


@dataclass(frozen=True, slots=True)
class ApexStartupValidation:
    ok: bool
    status: str
    errors: tuple[str, ...]
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _SEAL:
            raise TypeError("validation must be issued by the APEX startup enforcer")


_IN_PROCESS: ApexStartupValidation | None = None


def _issue(ok: bool, status: str, errors: Sequence[str] = ()) -> ApexStartupValidation:
    return ApexStartupValidation(ok, status, tuple(errors), _SEAL)


def get_in_process_apex_validation() -> ApexStartupValidation | None:
    return _IN_PROCESS


def load_apex_policy(path: str | Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BootError(f"APEX startup policy not found: {target}") from exc
    except json.JSONDecodeError as exc:
        raise BootError(f"invalid APEX startup policy: {exc}") from exc
    if not isinstance(value, dict):
        raise BootError("APEX startup policy must be a JSON object")
    required = {
        "schema_version",
        "authority",
        "operator_authority",
        "objective",
        "required_startup_fields",
        "execution_states",
        "transition_requirements",
        "path_requirements",
        "path_dynamic_rules",
        "mutation_interlock",
        "completion_gate",
    }
    missing = sorted(required - value.keys())
    if missing:
        raise BootError("APEX startup policy missing: " + ", ".join(missing))

    operator_authority = value.get("operator_authority")
    if not isinstance(operator_authority, dict):
        raise BootError("APEX operator_authority must be an object")
    if operator_authority.get("mode") != "absolute_project_direction":
        raise BootError("APEX operator_authority.mode must be absolute_project_direction")
    required_authority_flags = {
        "sole_human_project_authority": True,
        "current_explicit_instruction_is_sufficient_authorization_for_its_scope": True,
        "secondary_human_approval_authority": False,
        "lower_level_policy_veto": False,
        "assistant_or_automation_override": False,
        "repository_or_registry_override": False,
        "operator_owned_asset_value_ranking_is_operator_only": True,
        "operator_owned_asset_disposition_is_operator_only": True,
        "inspection_may_expand_into_mission_aligned_hardening_without_reconfirmation": True,
    }
    for field_name, expected in required_authority_flags.items():
        if operator_authority.get(field_name) is not expected:
            raise BootError(
                f"APEX operator_authority.{field_name} must be {expected!r}"
            )

    dynamic = value.get("path_dynamic_rules")
    if not isinstance(dynamic, dict):
        raise BootError("APEX path_dynamic_rules must be an object")
    for name in (
        "inspection_scope_expansion_must_be_boolean",
        "mission_aligned_hardening_must_be_boolean",
        "inspection_scope_expansion_requires_mission_aligned_hardening",
    ):
        if dynamic.get(name) is not True:
            raise BootError(f"APEX path_dynamic_rules.{name} must be true")

    interlock = value.get("mutation_interlock")
    if not isinstance(interlock, dict) or not isinstance(
        interlock.get("required_true_fields"), list
    ):
        raise BootError("APEX mutation_interlock.required_true_fields must be an array")
    if interlock.get("external_action_requires_secondary_human_approval") is not False:
        raise BootError(
            "APEX cannot grant a secondary human approval layer authority over the Operator"
        )
    if interlock.get("operator_owned_asset_disposition_requires_explicit_operator_direction") is not True:
        raise BootError(
            "APEX operator-owned asset disposition must remain Operator-directed"
        )
    if interlock.get("operator_owned_asset_value_ranking_requires_explicit_operator_direction") is not True:
        raise BootError(
            "APEX operator-owned asset value ranking must remain Operator-directed"
        )
    return value


def _norm(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _receipt_ref(value: Any) -> bool:
    if not _nonempty_text(value):
        return False
    prefix, separator, locator = value.strip().partition(":")
    return bool(separator and prefix.strip() and locator.strip())


def validate_state_transition(
    policy: Mapping[str, Any],
    from_state: str,
    to_state: str,
    *,
    evidence: Mapping[str, Any] | None = None,
) -> tuple[str, ...]:
    """Validate a material execution-state transition against APEX proof rules."""
    source = str(from_state).strip().upper()
    target = str(to_state).strip().upper()
    states = {str(value).strip().upper() for value in policy.get("execution_states", ())}
    if source not in states or target not in states:
        return ("state transition uses an unknown execution state",)

    key = f"{source}->{target}"
    requirement = str(policy.get("transition_requirements", {}).get(key, "")).strip()
    if not requirement:
        return (f"state transition {key} is not explicitly authorized",)

    proof = evidence if isinstance(evidence, Mapping) else {}
    if not _receipt_ref(proof.get(requirement)):
        return (f"state transition {key} requires receipt reference: {requirement}",)
    return ()


def _validate_operator_authorization(row: Mapping[str, Any], errors: list[str]) -> None:
    """Require evidence of the Operator's authorization, never a second approver."""
    authorization = row.get("operator_authorization")
    if not isinstance(authorization, Mapping):
        errors.append("external action requires apex_startup.operator_authorization")
        return
    if authorization.get("authorized") is not True:
        errors.append("operator_authorization.authorized must be true")
    if not _receipt_ref(authorization.get("authorization_ref")):
        errors.append("operator_authorization.authorization_ref must be a receipt reference")


def _validate_dynamic_path(path: Mapping[str, Any], errors: list[str]) -> None:
    expanded = path.get("inspection_scope_expansion")
    hardening = path.get("mission_aligned_hardening")
    if type(expanded) is not bool:
        errors.append("apex_startup.selected_path.inspection_scope_expansion must be boolean")
        return
    if type(hardening) is not bool:
        errors.append("apex_startup.selected_path.mission_aligned_hardening must be boolean")
        return
    if expanded and not hardening:
        errors.append(
            "inspection_scope_expansion requires apex_startup.selected_path.mission_aligned_hardening=true"
        )


def validate_apex_startup_receipt(
    policy: Mapping[str, Any], receipt: Mapping[str, Any]
) -> tuple[str, ...]:
    errors: list[str] = []
    row = receipt.get("apex_startup")
    if not isinstance(row, Mapping):
        return ("apex_startup must be an object",)

    expected_authority = _norm(policy.get("authority"))
    if _norm(row.get("authority")) != expected_authority:
        errors.append(f"apex_startup.authority must be {expected_authority}")

    expected_objective = _norm(policy.get("objective"))
    if _norm(row.get("objective")) != expected_objective:
        errors.append(f"apex_startup.objective must be {expected_objective}")

    for field_name in policy.get("required_startup_fields", ()):
        if field_name not in row:
            errors.append(f"apex_startup.{field_name} is required")

    interlock = policy.get("mutation_interlock", {})
    required_true_fields = (
        interlock.get("required_true_fields", ())
        if isinstance(interlock, Mapping)
        else ()
    )
    for boolean_name in required_true_fields:
        if row.get(boolean_name) is not True:
            errors.append(f"apex_startup.{boolean_name} must be true")

    if not _nonempty_text(row.get("target_state")):
        errors.append("apex_startup.target_state must be non-empty")

    contradiction_status = _norm(row.get("contradiction_status"))
    allowed_contradictions = {
        _norm(value) for value in policy.get("contradiction_statuses", ())
    }
    if contradiction_status not in allowed_contradictions:
        errors.append(
            "apex_startup.contradiction_status must be one of: "
            + ", ".join(sorted(allowed_contradictions))
        )
    if contradiction_status == "open_blocker":
        errors.append("apex_startup has an unresolved contradiction blocker")

    path = row.get("selected_path")
    if not isinstance(path, Mapping):
        errors.append("apex_startup.selected_path must be an object")
    else:
        for key, expected in policy.get("path_requirements", {}).items():
            if path.get(key) is not expected:
                errors.append(f"apex_startup.selected_path.{key} must be {expected!r}")
        if not _nonempty_text(path.get("id")):
            errors.append("apex_startup.selected_path.id is required")
        _validate_dynamic_path(path, errors)

    plan = row.get("verification_plan")
    if not isinstance(plan, list) or not any(_nonempty_text(value) for value in plan):
        errors.append("apex_startup.verification_plan must contain at least one step")

    mutation = _norm(row.get("mutation_intent", "none"))
    if mutation not in {"none", "authorized", "blocked"}:
        errors.append("apex_startup.mutation_intent must be none, authorized, or blocked")

    action_scope = _norm(row.get("action_scope"))
    allowed_scopes = {_norm(value) for value in policy.get("action_scopes", ())}
    if action_scope not in allowed_scopes:
        errors.append(
            "apex_startup.action_scope must be one of: "
            + ", ".join(sorted(allowed_scopes))
        )
    if mutation == "none" and action_scope != "none":
        errors.append("mutation_intent=none requires action_scope=none")
    if mutation == "authorized":
        if row.get("operator_plan_authorized") is not True:
            errors.append(
                "authorized mutation requires apex_startup.operator_plan_authorized=true"
            )
        if action_scope not in {"internal", "external"}:
            errors.append("authorized mutation requires internal or external action_scope")
        if action_scope == "external" and isinstance(interlock, Mapping):
            if interlock.get("external_action_requires_operator_authorization_receipt") is True:
                _validate_operator_authorization(row, errors)
            if interlock.get("external_action_requires_secondary_human_approval") is True:
                errors.append(
                    "secondary human approval cannot override or re-authorize the Operator"
                )

    claims = row.get("material_claims", [])
    if not isinstance(claims, list):
        errors.append("apex_startup.material_claims must be an array when supplied")
    else:
        states = {str(value).strip().upper() for value in policy.get("execution_states", ())}
        promoted_states = {
            "ATTEMPTED",
            "EXECUTED",
            "VERIFIED",
            "COMMITTED",
            "DEPLOYED",
            "OBSERVED_IN_OPERATION",
        }
        for index, claim in enumerate(claims):
            prefix = f"apex_startup.material_claims[{index}]"
            if not isinstance(claim, Mapping):
                errors.append(f"{prefix} must be an object")
                continue
            if not _nonempty_text(claim.get("claim")):
                errors.append(f"{prefix}.claim is required")
            state = str(claim.get("state", "")).strip().upper()
            if state not in states:
                errors.append(f"{prefix}.state is not a valid execution state")
                continue
            if not _nonempty_text(claim.get("provenance")):
                errors.append(f"{prefix}.provenance is required for material claims")
            if state in promoted_states:
                source_state = str(claim.get("source_state", "")).strip().upper()
                evidence = claim.get("transition_evidence")
                if source_state not in states:
                    errors.append(f"{prefix}.source_state is required for {state}")
                    continue
                if not isinstance(evidence, Mapping):
                    errors.append(f"{prefix}.transition_evidence is required for {state}")
                    continue
                transition_errors = validate_state_transition(
                    policy,
                    source_state,
                    state,
                    evidence=evidence,
                )
                errors.extend(f"{prefix}: {error}" for error in transition_errors)

    return tuple(errors)


def build_apex_startup_request(policy: Mapping[str, Any], *, task: str) -> dict[str, Any]:
    return {
        "request_type": "apex_genesis_enforced_startup",
        "schema_version": policy.get("schema_version"),
        "task": task,
        "authority": policy.get("authority"),
        "operator_authority": dict(policy.get("operator_authority", {})),
        "objective": policy.get("objective"),
        "requirements": {
            "context_before_mutation": True,
            "continuation_before_restart": True,
            "preserve_prior_valid_gains": True,
            "bind_operator_intent": True,
            "operator_project_direction_authority_is_absolute": True,
            "current_explicit_operator_instruction_is_authorization_for_its_scope": True,
            "secondary_human_approval_authority": False,
            "describe_material_state_within_operator_requested_taxonomy": True,
            "asset_worth_classification_requires_explicit_operator_request": True,
            "preserve_literal_operator_operation_scope": True,
            "resolve_contradictions_before_mutation": True,
            "select_operator_aligned_coherent_path_within_requested_operation": True,
            "eliminate_artificial_minimization": True,
            "receipt_bind_material_action_claims": True,
            "verify_before_state_promotion": True,
            "external_actions_require_operator_authorization_receipt": True,
            "integrate_only_verified_gain": True,
            "allow_mission_aligned_non_destructive_hardening": True,
            "no_unsolicited_operator_asset_value_ranking": True,
            "no_unsolicited_operator_asset_disposition": True,
        },
        "receipt_contract": {
            "apex_startup": {
                "authority": "operator_intent",
                "objective": "maximum_coherent_advance",
                "context_reconstructed": True,
                "prior_state_retrieved": True,
                "continuation_resolved": True,
                "target_identity_resolved": True,
                "operator_intent_resolved": True,
                "operator_plan_authorized": "boolean when mutation is authorized",
                "target_state": "non-empty string",
                "prior_valid_gains_identified": True,
                "prior_valid_gains_preserved": True,
                "relevant_source_inspected": True,
                "contradiction_status": "none|resolved|open_blocker",
                "state_model_bound": True,
                "mutation_intent": "none|authorized|blocked",
                "action_scope": "none|internal|external",
                "operator_authorization": {
                    "authorized": True,
                    "authorization_ref": "operator-command:receipt-reference; required for external actions"
                },
                "selected_path": {
                    "id": "non-empty string",
                    **dict(policy.get("path_requirements", {})),
                    "inspection_scope_expansion": False,
                    "mission_aligned_hardening": False
                },
                "verification_plan": ["at least one verification step"],
                "material_claims": [
                    {
                        "claim": "material claim",
                        "state": "one APEX execution state",
                        "source_state": "immediately preceding state when promoted",
                        "provenance": "required source reference",
                        "transition_evidence": {
                            "required_transition_key": "provider:receipt-reference"
                        },
                    }
                ],
            }
        },
    }


def _continue_apex_startup(
    errors: Sequence[str],
    *,
    request: Mapping[str, Any],
) -> ApexStartupValidation:
    from startup_continuation import emit_startup_continuation, record_startup_continuation

    continuation = record_startup_continuation(
        "apex_enforced_startup",
        errors,
        request=request,
        environment_key="GLACIEREQ_APEX_STARTUP_STATUS",
    )
    emit_startup_continuation(continuation)
    return _issue(False, "continuation_required", errors)


def automatic_apex_enforced_startup() -> ApexStartupValidation | None:
    global _IN_PROCESS
    if _IN_PROCESS is not None:
        return _IN_PROCESS

    mode = os.getenv("CASEY_AUTO_BOOT_MODE", "strict").strip().lower()
    if mode == "off" or os.getenv("CASEY_AUTO_BOOT_DISABLE") == "1":
        os.environ["GLACIEREQ_APEX_STARTUP_STATUS"] = "off"
        return None
    if mode not in {"strict", "request"}:
        raise BootError(f"unsupported CASEY_AUTO_BOOT_MODE: {mode}")

    policy = load_apex_policy()
    task = os.getenv("CASEY_BOOT_TASK", "resume Operator-directed unfinished material action")
    receipt = receipt_from_environment()

    if receipt is None:
        request = build_apex_startup_request(policy, task=task)
        print(
            json.dumps(request, ensure_ascii=False, sort_keys=True),
            file=sys.stderr,
        )
        sys.stderr.flush()
        return _continue_apex_startup(("no boot receipt supplied",), request=request)

    errors = validate_apex_startup_receipt(policy, receipt)
    validation = _issue(not errors, "complete" if not errors else "blocked", errors)
    if validation.ok:
        _IN_PROCESS = validation
        os.environ["GLACIEREQ_APEX_STARTUP_STATUS"] = "complete"
        return validation

    request = build_apex_startup_request(policy, task=task)
    request["receipt_errors"] = list(validation.errors)
    return _continue_apex_startup(validation.errors, request=request)
