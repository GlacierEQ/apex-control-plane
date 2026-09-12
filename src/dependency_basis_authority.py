"""Independent authority for execution-dependency completeness basis material.

A completeness verdict is derivative unless the material from which the required
execution-claim set was derived can itself be independently resolved and hashed.
This module keeps that basis authority separate from the frontier receipt so the
receipt, an assistant summary, or a derived memory cannot certify its own inputs.
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


@dataclass(frozen=True, slots=True)
class DependencyBasisResult:
    authoritative: bool
    status: str
    errors: tuple[str, ...]


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_dependency_basis(
    evidence: Mapping[str, Any], *, resolver: BasisResolver
) -> DependencyBasisResult:
    """Require independently readable, hashed, non-derivative basis material."""
    errors: list[str] = []
    basis = evidence.get("dependency_basis")
    if not isinstance(basis, list) or not basis:
        return DependencyBasisResult(
            False,
            "DEPENDENCY_BASIS_UNRESOLVED",
            ("dependency_basis must be a non-empty array",),
        )

    seen_refs: set[str] = set()
    for index, item in enumerate(basis):
        prefix = f"dependency_basis[{index}]"
        if not isinstance(item, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
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
            errors.append(f"{prefix}.source_kind is derivative and cannot establish dependency completeness")
        if not _nonempty(source_kind):
            errors.append(f"{prefix}.source_kind must be non-empty")
        try:
            payload = resolver(source_ref)
        except Exception as exc:  # noqa: BLE001 - fail closed at readback boundary
            errors.append(f"{prefix}.readback unresolved: {exc.__class__.__name__}")
            continue
        if not isinstance(payload, bytes):
            errors.append(f"{prefix}.resolver must return bytes")
            continue
        if item.get("source_sha256") != _sha256(payload):
            errors.append(f"{prefix}.source_sha256 does not match independently resolved bytes")

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
