"""Independent authority for execution-dependency completeness basis material.

A completeness verdict is derivative unless the material from which the required
execution-claim set was derived can itself be independently resolved and bound
to exact source bytes. This module keeps that basis authority separate from the
frontier receipt so the receipt, an assistant summary, or a derived memory cannot
certify its own inputs.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

BasisResolver = Callable[[str], bytes]

_DERIVATIVE_KINDS = {
    "assistant_summary",
    "assistant_memory",
    "derived_memory",
    "frontier_receipt",
    "execution_receipt",
    "manifest",
    "checkpoint",
}
_ALLOWED_CONTRADICTION_STATES = {"active", "resolved_consistent"}


@dataclass(frozen=True, slots=True)
class DependencyBasisResult:
    authoritative: bool
    status: str
    errors: tuple[str, ...]


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_span(
    item: Mapping[str, Any], payload: bytes, *, prefix: str
) -> tuple[str, ...]:
    errors: list[str] = []
    start = item.get("span_start_byte")
    end = item.get("span_end_byte")
    if not isinstance(start, int) or isinstance(start, bool) or start < 0:
        errors.append(f"{prefix}.span_start_byte must be a non-negative integer")
        return tuple(errors)
    if not isinstance(end, int) or isinstance(end, bool) or end <= start:
        errors.append(f"{prefix}.span_end_byte must be an integer greater than span_start_byte")
        return tuple(errors)
    if end > len(payload):
        errors.append(f"{prefix}.span_end_byte exceeds independently resolved source length")
        return tuple(errors)
    span = payload[start:end]
    if item.get("span_sha256") != _sha256(span):
        errors.append(f"{prefix}.span_sha256 does not match independently resolved source span")
    return tuple(errors)


def validate_dependency_basis(
    evidence: Mapping[str, Any], *, resolver: BasisResolver
) -> DependencyBasisResult:
    """Require independently readable, exact-span-bound, non-derivative basis material."""
    errors: list[str] = []
    basis = evidence.get("dependency_basis")
    if not isinstance(basis, list) or not basis:
        return DependencyBasisResult(
            False,
            "DEPENDENCY_BASIS_UNRESOLVED",
            ("dependency_basis must be a non-empty array",),
        )

    seen_refs: set[str] = set()
    seen_ids: set[str] = set()
    for index, item in enumerate(basis):
        prefix = f"dependency_basis[{index}]"
        if not isinstance(item, Mapping):
            errors.append(f"{prefix} must be an object")
            continue

        basis_id = item.get("basis_id")
        if not _nonempty(basis_id):
            errors.append(f"{prefix}.basis_id must be non-empty")
        else:
            basis_id = str(basis_id)
            if basis_id in seen_ids:
                errors.append(f"{prefix}.basis_id must be unique")
            seen_ids.add(basis_id)

        source_ref = item.get("source_ref")
        source_kind = item.get("source_kind")
        if not _nonempty(source_ref):
            errors.append(f"{prefix}.source_ref must be non-empty")
            continue
        source_ref = str(source_ref)
        if source_ref in seen_refs:
            errors.append(f"{prefix}.source_ref must be unique")
        seen_refs.add(source_ref)

        if source_kind in _DERIVATIVE_KINDS:
            errors.append(
                f"{prefix}.source_kind is derivative and cannot establish dependency completeness"
            )
        if not _nonempty(source_kind):
            errors.append(f"{prefix}.source_kind must be non-empty")

        if not _nonempty(item.get("temporal_context")):
            errors.append(f"{prefix}.temporal_context must be non-empty")
        contradiction_state = item.get("contradiction_state")
        if contradiction_state not in _ALLOWED_CONTRADICTION_STATES:
            errors.append(
                f"{prefix}.contradiction_state must be active or resolved_consistent"
            )
        if item.get("superseded_by") is not None:
            errors.append(f"{prefix}.superseded_by must be null for authoritative basis")
        if item.get("verification_state") != "source_resolved":
            errors.append(f"{prefix}.verification_state must equal 'source_resolved'")

        try:
            payload = resolver(source_ref)
        except Exception as exc:  # noqa: BLE001 - fail closed at readback boundary
            errors.append(f"{prefix}.readback unresolved: {exc.__class__.__name__}")
            continue
        if not isinstance(payload, bytes):
            errors.append(f"{prefix}.resolver must return bytes")
            continue
        if item.get("source_sha256") != _sha256(payload):
            errors.append(
                f"{prefix}.source_sha256 does not match independently resolved bytes"
            )
        errors.extend(_validate_span(item, payload, prefix=prefix))

    verifier_ref = evidence.get("verifier_ref")
    if not _nonempty(verifier_ref):
        errors.append("verifier_ref must be non-empty")
    elif verifier_ref in {"frontier_receipt", "execution_receipt", "assistant_summary"}:
        errors.append("verifier_ref cannot self-certify dependency basis authority")

    if errors:
        return DependencyBasisResult(
            False, "DEPENDENCY_BASIS_UNRESOLVED", tuple(dict.fromkeys(errors))
        )
    return DependencyBasisResult(True, "DEPENDENCY_BASIS_VERIFIED", ())
