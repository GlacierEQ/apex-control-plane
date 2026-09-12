"""Fail-closed authority for enumerating execution dependencies.

Dependency completeness cannot be established by a verifier merely asserting that
its own declared set is complete. This boundary requires a separately resolved,
hashed enumeration artifact whose inputs and candidate claim identities are bound
to the executable frontier. The enumerator is therefore an explicit authority
surface rather than an uninspectable semantic judgment embedded in a receipt.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

SourceResolver = Callable[[str], bytes]


@dataclass(frozen=True, slots=True)
class DependencyEnumerationResult:
    ok: bool
    status: str
    required_execution_claim_ids: tuple[str, ...]
    errors: tuple[str, ...]


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _resolve(resolver: SourceResolver, ref: Any, *, prefix: str) -> tuple[bytes | None, str | None]:
    if not _nonempty(ref):
        return None, f"{prefix}.source_ref must be non-empty"
    try:
        payload = resolver(str(ref))
    except Exception as exc:  # noqa: BLE001 - fail-closed provider/source boundary
        return None, f"{prefix}.source readback unresolved: {exc.__class__.__name__}"
    if not isinstance(payload, bytes):
        return None, f"{prefix}.resolver must return bytes"
    return payload, None


def validate_dependency_enumeration(
    artifact: Mapping[str, Any],
    *,
    resolver: SourceResolver,
    expected_frontier_id: str,
    declared_execution_claim_ids: Sequence[str],
) -> DependencyEnumerationResult:
    """Validate an independently materialized execution-dependency enumeration."""
    errors: list[str] = []
    prefix = "frontier_authority.dependency_enumeration"

    source_bytes, resolution_error = _resolve(
        resolver, artifact.get("evidence_ref"), prefix=prefix
    )
    if resolution_error:
        return DependencyEnumerationResult(
            False, "DEPENDENCY_ENUMERATION_READBACK_UNRESOLVED", (), (resolution_error,)
        )
    assert source_bytes is not None

    if artifact.get("evidence_sha256") != _sha256(source_bytes):
        errors.append(f"{prefix}.evidence_sha256 does not match independently resolved bytes")

    try:
        evidence = json.loads(source_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return DependencyEnumerationResult(
            False,
            "DEPENDENCY_ENUMERATION_INVALID",
            (),
            tuple(errors + [f"{prefix}.evidence_ref must resolve to UTF-8 JSON"]),
        )
    if not isinstance(evidence, Mapping):
        return DependencyEnumerationResult(
            False,
            "DEPENDENCY_ENUMERATION_INVALID",
            (),
            tuple(errors + [f"{prefix}.evidence must be an object"]),
        )

    if evidence.get("frontier_id") != expected_frontier_id:
        errors.append(f"{prefix}.evidence.frontier_id must equal the derived frontier_id")

    enumerator_ref = evidence.get("enumerator_ref")
    if not _nonempty(enumerator_ref):
        errors.append(f"{prefix}.evidence.enumerator_ref must be non-empty")
    if enumerator_ref in {
        "frontier_receipt",
        "execution_receipt",
        "assistant_summary",
        "dependency_completeness_verification",
    }:
        errors.append(f"{prefix}.evidence.enumerator_ref cannot self-certify dependency discovery")

    enumerator_version = evidence.get("enumerator_version")
    if not _nonempty(enumerator_version):
        errors.append(f"{prefix}.evidence.enumerator_version must be non-empty")

    input_refs = evidence.get("input_refs")
    input_hashes = evidence.get("input_sha256")
    if not isinstance(input_refs, list) or not input_refs or not all(_nonempty(item) for item in input_refs):
        errors.append(f"{prefix}.evidence.input_refs must be a non-empty array of source refs")
    elif len(input_refs) != len(set(input_refs)):
        errors.append(f"{prefix}.evidence.input_refs must be unique")

    if not isinstance(input_hashes, Mapping):
        errors.append(f"{prefix}.evidence.input_sha256 must map every input ref to its hash")
    elif isinstance(input_refs, list):
        if set(input_hashes) != set(input_refs):
            errors.append(f"{prefix}.evidence.input_sha256 must exactly cover input_refs")
        for ref in input_refs:
            if not _nonempty(ref):
                continue
            payload, input_error = _resolve(resolver, ref, prefix=f"{prefix}.input[{ref}]")
            if input_error:
                errors.append(input_error)
                continue
            assert payload is not None
            if input_hashes.get(ref) != _sha256(payload):
                errors.append(f"{prefix}.evidence.input_sha256[{ref!r}] does not match resolved bytes")

    candidates = evidence.get("candidate_execution_claim_ids")
    required: tuple[str, ...] = ()
    if not isinstance(candidates, list) or not all(_nonempty(item) for item in candidates):
        errors.append(
            f"{prefix}.evidence.candidate_execution_claim_ids must be an array of non-empty strings"
        )
    else:
        normalized = [str(item) for item in candidates]
        if len(normalized) != len(set(normalized)):
            errors.append(f"{prefix}.evidence.candidate_execution_claim_ids must be unique")
        required = tuple(sorted(normalized))
        if sorted(declared_execution_claim_ids) != list(required):
            errors.append(
                f"{prefix}.evidence.candidate_execution_claim_ids proves declared execution_claim_ids are incomplete or substituted"
            )

    if errors:
        return DependencyEnumerationResult(
            False, "DEPENDENCY_ENUMERATION_UNRESOLVED", required, tuple(dict.fromkeys(errors))
        )
    return DependencyEnumerationResult(True, "DEPENDENCY_ENUMERATION_VERIFIED", required, ())
