"""APEX OPERATOR source-fidelity verifier.

The filename and public API retain ``operator_fidelity_lock`` for compatibility,
but this component does not define what OPERATOR must want or say.

It protects two things only:

1. words attributed to OPERATOR remain cryptographically bound to the literal
   constraints supplied by the receipt; and
2. source identity remains explicit so AKOS/framework material, evidence, and
   agent inference cannot silently impersonate the singular proper-name
   designation OPERATOR.

The verifier may detect attribution/integrity failure. It may not manufacture
mandatory OPERATOR phrases, objectives, corrections, or doctrine.
"""
from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from auto_boot import EXIT_BOOT_BLOCKED, BootError
from operator_fidelity_preflight import (
    digest_operator_words,
    load_operator_fidelity_policy,
    validate_operator_fidelity_receipt,
)
from prime_directive_boot import receipt_from_environment

_SEAL = object()


@dataclass(frozen=True, slots=True)
class OperatorFidelityLockValidation:
    ok: bool
    status: str
    errors: tuple[str, ...]
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _SEAL:
            raise TypeError("OPERATOR source-fidelity proof must be issued in-process")


_IN_PROCESS: OperatorFidelityLockValidation | None = None


def _issue(ok: bool, status: str, errors: Sequence[str] = ()) -> OperatorFidelityLockValidation:
    return OperatorFidelityLockValidation(ok, status, tuple(errors), _SEAL)


def get_in_process_operator_fidelity_lock() -> OperatorFidelityLockValidation | None:
    return _IN_PROCESS


def _testing() -> bool:
    return os.getenv("CASEY_AUTO_BOOT_TESTING", "0") == "1" or os.getenv("PYTEST_CURRENT_TEST") is not None


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def validate_operator_fidelity_lock(receipt: Mapping[str, Any]) -> tuple[str, ...]:
    """Validate source identity and integrity without inventing OPERATOR direction."""
    errors: list[str] = []
    policy = load_operator_fidelity_policy()
    errors.extend(validate_operator_fidelity_receipt(policy, receipt))

    row = receipt.get("operator_fidelity")
    if not isinstance(row, Mapping):
        return tuple(errors or ["operator_fidelity must be an object"])

    constraints = _text_list(row.get("literal_constraints"))
    if constraints:
        expected = digest_operator_words(*constraints)
        actual = str(row.get("operator_words_digest", "")).strip()
        if actual != expected:
            errors.append(
                "operator_fidelity.operator_words_digest is not bound to literal_constraints"
            )

    # Do not inspect OPERATOR's words for machine-selected slogans or durable
    # phrases. The machine verifies attribution/integrity, not the content of
    # OPERATOR's direction.
    path = row.get("selected_path")
    if isinstance(path, Mapping):
        if path.get("operator_designation") != "OPERATOR":
            errors.append("OPERATOR is the singular proper-name designation")
        if path.get("operator_designation_semantics") != "proper_name":
            errors.append("OPERATOR designation semantics must be proper_name")
        if path.get("operator_designation_is_singular") is not True:
            errors.append("OPERATOR designation must remain singular")
        if path.get("source_identity_preserved") is not True:
            errors.append("source identity must remain explicit")
        if path.get("akos_material_is_framework_not_operator") is not True:
            errors.append("AKOS material must not be attributed to OPERATOR")
        if path.get("agent_inference_is_not_operator") is not True:
            errors.append("agent inference must not be attributed to OPERATOR")
        if path.get("evidence_is_not_operator") is not True:
            errors.append("evidence must not be attributed to OPERATOR")
        if path.get("capability_reduction") is True and row.get("operator_directed_reduction") is not True:
            errors.append("OPERATOR source-fidelity verifier rejects non-OPERATOR-directed capability reduction")
        if path.get("instruction_displacement") is not False:
            errors.append("OPERATOR source-fidelity verifier requires instruction_displacement=false")
        if path.get("minimum_scope_default") is not False:
            errors.append("OPERATOR source-fidelity verifier requires minimum_scope_default=false")
        if path.get("governance_first") is not False:
            errors.append("OPERATOR source-fidelity verifier requires governance_first=false")
        if path.get("permission_loop") is not False:
            errors.append("OPERATOR source-fidelity verifier requires permission_loop=false")

    return tuple(dict.fromkeys(errors))


def _degrade(errors: Sequence[str]) -> OperatorFidelityLockValidation:
    """Expose a diagnostic request-mode state without authorizing runtime action."""
    os.environ["GLACIEREQ_OPERATOR_FIDELITY_LOCK_STATUS"] = "degraded"
    return _issue(False, "degraded", errors)


def automatic_operator_fidelity_lock() -> OperatorFidelityLockValidation | None:
    """Issue source-fidelity proof or expose a resumable diagnostic state."""
    global _IN_PROCESS
    if _IN_PROCESS is not None:
        return _IN_PROCESS

    mode = os.getenv("CASEY_AUTO_BOOT_MODE", "strict").strip().lower()
    if mode not in {"strict", "request", "off"}:
        raise BootError(f"unsupported CASEY_AUTO_BOOT_MODE: {mode}")

    if not _testing():
        if os.getenv("CASEY_AUTO_BOOT_DISABLE", "0") == "1":
            return _continue_lock(("CASEY_AUTO_BOOT_DISABLE cannot disable OPERATOR source fidelity",))
        if mode == "off":
            return _continue_lock(("CASEY_AUTO_BOOT_MODE=off cannot disable OPERATOR source fidelity",))

    receipt = receipt_from_environment()
    if receipt is None:
        return _continue_lock(("OPERATOR source-fidelity verification requires a boot receipt",))

    errors = validate_operator_fidelity_lock(receipt)
    if errors:
        return _continue_lock(errors)

    validation = _issue(True, "complete")
    _IN_PROCESS = validation
    os.environ["GLACIEREQ_OPERATOR_FIDELITY_LOCK_STATUS"] = "complete"
    return validation


def _continue_lock(errors: Sequence[str]) -> OperatorFidelityLockValidation:
    """Preserve diagnostics while exposing a non-authorizing recovery path."""
    from startup_continuation import emit_startup_continuation, record_startup_continuation

    payload = {
        "boot_status": "continuation_required",
        "operator_fidelity_lock_status": "continuation_required",
        "failure_class": "INSTRUCTION_DISPLACEMENT",
        "errors": list(errors),
        "runtime_authorized": False,
        "external_action_authorized": False,
    }
    continuation = record_startup_continuation(
        "operator_fidelity_lock",
        errors,
        request=payload,
        environment_key="GLACIEREQ_OPERATOR_FIDELITY_LOCK_STATUS",
    )
    emit_startup_continuation(continuation)
    return _issue(False, "continuation_required", errors)
