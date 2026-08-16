"""APEX Genesis fail-closed startup and execution-state enforcement.

This layer sits above the existing continuity and Prime Directive proofs. It does
not replace them. It binds those proofs to OPERATOR intent, continuation,
preserved prior gain, maximum coherent path selection, and evidence-backed
execution-state transitions.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import sys
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
        "objective",
        "required_startup_fields",
        "execution_states",
        "transition_requirements",
        "path_requirements",
        "completion_gate",
    }
    missing = sorted(required - value.keys())
    if missing:
        raise BootError("APEX startup policy missing: " + ", ".join(missing))
    return value


def _norm(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _nonempty_text(value: Any) -> bool:
    return bool(str(value or "").strip())


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

    for boolean_name in (
        "context_reconstructed",
        "continuation_resolved",
        "operator_intent_resolved",
        "prior_valid_gains_preserved",
        "state_model_bound",
    ):
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

    plan = row.get("verification_plan")
    if not isinstance(plan, list) or not any(_nonempty_text(value) for value in plan):
        errors.append("apex_startup.verification_plan must contain at least one step")

    mutation = _norm(row.get("mutation_intent", "none"))
    if mutation not in {"none", "authorized", "blocked"}:
        errors.append("apex_startup.mutation_intent must be none, authorized, or blocked")
    if mutation == "authorized" and row.get("operator_plan_authorized") is not True:
        errors.append(
            "authorized mutation requires apex_startup.operator_plan_authorized=true"
        )

    claims = row.get("material_claims", [])
    if not isinstance(claims, list):
        errors.append("apex_startup.material_claims must be an array when supplied")
    else:
        states = {str(value).strip().upper() for value in policy.get("execution_states", ())}
        for index, claim in enumerate(claims):
            if not isinstance(claim, Mapping):
                errors.append(f"apex_startup.material_claims[{index}] must be an object")
                continue
            if not _nonempty_text(claim.get("claim")):
                errors.append(f"apex_startup.material_claims[{index}].claim is required")
            state = str(claim.get("state", "")).strip().upper()
            if state not in states:
                errors.append(
                    f"apex_startup.material_claims[{index}].state is not a valid execution state"
                )
            if state in {
                "OBSERVED",
                "EXECUTED",
                "VERIFIED",
                "COMMITTED",
                "DEPLOYED",
                "OBSERVED_IN_OPERATION",
            } and not _nonempty_text(claim.get("provenance")):
                errors.append(
                    f"apex_startup.material_claims[{index}].provenance is required for {state}"
                )

    return tuple(errors)


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

    proof = dict(evidence or {})
    if not proof.get(requirement):
        return (f"state transition {key} requires evidence: {requirement}",)
    return ()


def build_apex_startup_request(policy: Mapping[str, Any], *, task: str) -> dict[str, Any]:
    return {
        "request_type": "apex_genesis_enforced_startup",
        "schema_version": policy.get("schema_version"),
        "task": task,
        "authority": policy.get("authority"),
        "objective": policy.get("objective"),
        "requirements": {
            "context_before_mutation": True,
            "continuation_before_restart": True,
            "preserve_prior_valid_gains": True,
            "bind_operator_intent": True,
            "classify_material_state": True,
            "resolve_contradictions_before_mutation": True,
            "select_maximum_coherent_path": True,
            "eliminate_artificial_minimization": True,
            "receipt_bind_material_action_claims": True,
            "verify_before_state_promotion": True,
            "integrate_only_verified_gain": True,
        },
        "receipt_contract": {
            "apex_startup": {
                "authority": "operator_intent",
                "objective": "maximum_coherent_advance",
                "context_reconstructed": True,
                "continuation_resolved": True,
                "operator_intent_resolved": True,
                "operator_plan_authorized": "boolean when mutation is authorized",
                "target_state": "non-empty string",
                "prior_valid_gains_preserved": True,
                "contradiction_status": "none|resolved|open_blocker",
                "state_model_bound": True,
                "mutation_intent": "none|authorized|blocked",
                "selected_path": {
                    "id": "non-empty string",
                    **dict(policy.get("path_requirements", {})),
                },
                "verification_plan": ["at least one verification step"],
                "material_claims": [
                    {
                        "claim": "material claim",
                        "state": "one APEX execution state",
                        "provenance": "required for evidence-bearing states",
                    }
                ],
            }
        },
    }


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
    task = os.getenv("CASEY_BOOT_TASK", "resume highest-value unfinished material action")
    receipt = receipt_from_environment()

    if receipt is None:
        print(
            json.dumps(build_apex_startup_request(policy, task=task), ensure_ascii=False, sort_keys=True),
            file=sys.stderr,
        )
        sys.stderr.flush()
        status = "blocked" if mode == "strict" else "degraded"
        os.environ["GLACIEREQ_APEX_STARTUP_STATUS"] = status
        validation = _issue(False, status, ("no boot receipt supplied",))
        if mode == "strict":
            raise SystemExit(EXIT_BOOT_BLOCKED)
        return validation

    errors = validate_apex_startup_receipt(policy, receipt)
    validation = _issue(not errors, "complete" if not errors else "blocked", errors)
    if validation.ok:
        _IN_PROCESS = validation
        os.environ["GLACIEREQ_APEX_STARTUP_STATUS"] = "complete"
        return validation

    os.environ["GLACIEREQ_APEX_STARTUP_STATUS"] = "blocked"
    print(
        json.dumps(
            {
                "boot_status": "blocked",
                "apex_startup_status": "blocked",
                "errors": list(validation.errors),
                "external_action_authorized": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        file=sys.stderr,
    )
    sys.stderr.flush()
    if mode == "strict":
        raise SystemExit(EXIT_BOOT_BLOCKED)

    os.environ["GLACIEREQ_APEX_STARTUP_STATUS"] = "degraded"
    return validation
