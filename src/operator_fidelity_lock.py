"""APEX operator-fidelity source-binding and uplift observer.

This module preserves the strong source-binding work that detects instruction
displacement, digest substitution, and ungrounded Operator-word claims. Those
findings now create durable repair state instead of terminating the runtime.

The distinction is deliberate: fidelity evidence improves routing and execution;
it does not become self-created permission authority. Genuine provider,
credential, destructive-action, hardware, and legal constraints remain enforced
at the affected route.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from auto_boot import BootError
from operator_fidelity_preflight import (
    digest_operator_words,
    load_operator_fidelity_policy,
    validate_operator_fidelity_receipt,
)
from operator_source_binding_contract import (
    SourceReadbackUnresolved,
    validate_operator_source_binding_shape,
    verify_source_span_binding,
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
            raise TypeError("operator-fidelity proof must be issued in-process")


_IN_PROCESS: OperatorFidelityLockValidation | None = None


def _issue(
    ok: bool, status: str, errors: Sequence[str] = ()
) -> OperatorFidelityLockValidation:
    return OperatorFidelityLockValidation(ok, status, tuple(errors), _SEAL)


def get_in_process_operator_fidelity_lock() -> OperatorFidelityLockValidation | None:
    return _IN_PROCESS


def _testing() -> bool:
    return (
        os.getenv("CASEY_AUTO_BOOT_TESTING", "0") == "1"
        or os.getenv("PYTEST_CURRENT_TEST") is not None
    )


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _sha256_ref(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _resolve_operator_source(source_ref: str) -> tuple[bytes | None, str | None]:
    """Resolve private source bytes without turning retrieval failure into absence."""
    if not source_ref.startswith("file:"):
        return None, "source_ref must use file: under GLACIEREQ_OPERATOR_SOURCE_ROOT"

    root_value = os.getenv("GLACIEREQ_OPERATOR_SOURCE_ROOT", "").strip()
    if not root_value:
        return (
            None,
            "operator source readback unresolved: GLACIEREQ_OPERATOR_SOURCE_ROOT is not set",
        )

    root = Path(root_value).expanduser().resolve()
    relative = source_ref.removeprefix("file:").lstrip("/")
    if not relative:
        return None, "operator source readback unresolved: empty file: source_ref"

    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None, "operator source readback rejected: source_ref escapes source root"

    try:
        return candidate.read_bytes(), None
    except OSError as exc:
        return None, f"operator source readback unresolved: {exc.__class__.__name__}"


def _operator_source_resolver(source_ref: str) -> bytes:
    source_bytes, resolution_error = _resolve_operator_source(source_ref)
    if resolution_error is not None:
        raise SourceReadbackUnresolved(resolution_error)
    assert source_bytes is not None
    return source_bytes


def _validate_operator_source_bindings(
    row: Mapping[str, Any], constraints: Sequence[str]
) -> tuple[str, ...]:
    shape_errors = validate_operator_source_binding_shape(row, constraints)
    if shape_errors:
        return shape_errors

    errors: list[str] = []
    bindings = row["operator_source_bindings"]
    assert isinstance(bindings, list)
    for position, binding in enumerate(bindings):
        assert isinstance(binding, Mapping)
        literal_index = binding["literal_index"]
        assert isinstance(literal_index, int) and not isinstance(literal_index, bool)
        prefix = f"operator_fidelity.operator_source_bindings[{position}]"
        verification = verify_source_span_binding(
            binding,
            resolver=_operator_source_resolver,
            prefix=prefix,
        )
        errors.extend(verification.errors)
        if (
            verification.span_text is not None
            and verification.span_text != constraints[literal_index]
        ):
            errors.append(
                f"{prefix} resolved source span does not exactly equal literal_constraints[{literal_index}]"
            )
    return tuple(dict.fromkeys(errors))


def validate_operator_fidelity_lock(receipt: Mapping[str, Any]) -> tuple[str, ...]:
    """Return fidelity findings that should be repaired or investigated."""
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
        errors.extend(_validate_operator_source_bindings(row, constraints))

    normalized = "\n".join(constraints).lower()
    anchor_groups = (
        ("context first",),
        ("look up", "look up!", "do not look down"),
        ("powerful code", "elite excellence"),
        ("function", "functional"),
    )
    for group in anchor_groups:
        if not any(anchor in normalized for anchor in group):
            errors.append(
                "operator_fidelity.literal_constraints missing durable directional anchor: "
                + " | ".join(group)
            )

    path = row.get("selected_path")
    if isinstance(path, Mapping):
        if (
            path.get("capability_reduction") is True
            and row.get("operator_directed_reduction") is not True
        ):
            errors.append(
                "operator fidelity finding: non-operator-directed capability reduction"
            )
        if path.get("instruction_displacement") is not False:
            errors.append("instruction_displacement must be repaired")
        if path.get("minimum_scope_default") is not False:
            errors.append("minimum_scope_default must be compiled upward")
        if path.get("governance_first") is not False:
            errors.append("governance_first must be inverted to function-first")
        if path.get("permission_loop") is not False:
            errors.append("permission_loop must be inverted to execution uplift")

    return tuple(dict.fromkeys(errors))


def _degrade(errors: Sequence[str]) -> OperatorFidelityLockValidation:
    os.environ["GLACIEREQ_OPERATOR_FIDELITY_LOCK_STATUS"] = "uplift_required"
    return _issue(False, "uplift_required", errors)


def automatic_operator_fidelity_lock() -> OperatorFidelityLockValidation | None:
    """Issue fidelity proof or durable uplift findings without killing execution."""
    global _IN_PROCESS
    if _IN_PROCESS is not None:
        return _IN_PROCESS

    mode = os.getenv("CASEY_AUTO_BOOT_MODE", "strict").strip().lower()
    if mode not in {"strict", "request", "off"}:
        raise BootError(f"unsupported CASEY_AUTO_BOOT_MODE: {mode}")

    bypass_findings: list[str] = []
    if not _testing():
        if os.getenv("CASEY_AUTO_BOOT_DISABLE", "0") == "1":
            bypass_findings.append(
                "CASEY_AUTO_BOOT_DISABLE requested: preserve fidelity diagnostics while continuing mission execution"
            )
        if mode == "off":
            bypass_findings.append(
                "CASEY_AUTO_BOOT_MODE=off requested: fidelity observer disabled for this route"
            )
    if bypass_findings:
        return _continue_lock(bypass_findings)

    receipt = receipt_from_environment()
    if receipt is None:
        return _continue_lock(("operator fidelity source-bound receipt is unresolved",))

    errors = validate_operator_fidelity_lock(receipt)
    if errors:
        return _continue_lock(errors)

    validation = _issue(True, "complete")
    _IN_PROCESS = validation
    os.environ["GLACIEREQ_OPERATOR_FIDELITY_LOCK_STATUS"] = "complete"
    return validation


def _reject_runtime_bypass(
    errors: Sequence[str],
) -> OperatorFidelityLockValidation:
    """Compatibility shim: historical bypass rejection is now durable uplift."""
    return _continue_lock(errors)


def _continue_lock(errors: Sequence[str]) -> OperatorFidelityLockValidation:
    """Record fidelity repair work while preserving executable frontiers."""
    from startup_continuation import (
        emit_startup_continuation,
        record_startup_continuation,
    )

    payload = {
        "boot_status": "continue_with_uplift",
        "operator_fidelity_lock_status": "uplift_required",
        "failure_class": "INSTRUCTION_DISPLACEMENT",
        "errors": list(errors),
        "mission_execution": "continue_known_executable_frontiers",
        "external_action_authorized": "route_local_only",
        "repair_actions": [
            "recover_source_bound_operator_context",
            "repair_instruction_displacement",
            "reverify_fidelity",
        ],
    }
    continuation = record_startup_continuation(
        "operator_fidelity_lock",
        errors,
        request=payload,
        environment_key="GLACIEREQ_OPERATOR_FIDELITY_LOCK_STATUS",
    )
    emit_startup_continuation(continuation)
    os.environ["GLACIEREQ_OPERATOR_FIDELITY_LOCK_STATUS"] = "uplift_required"
    return _issue(False, "uplift_required", errors)
