"""Fail-closed authority for enumerating execution dependencies.

Dependency completeness cannot be established by a verifier merely asserting that
its own declared set is complete. This boundary requires separately resolved,
hashed input artifacts and deterministically derives execution-claim identities
from those bytes. The enumerator's candidate list is checked against that derived
set, so an AI-generated enumeration cannot silently omit or invent dependencies.

The input universe is separately authority-bound: the enumeration must resolve a
hashed manifest whose input_refs exactly match the enumerator inputs. This keeps
the enumerator from silently deleting an entire material input before dependency
derivation begins.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

SourceResolver = Callable[[str], bytes]
_EXECUTION_CLAIM_PREFIX = "execution:"
_FORBIDDEN_COLLECTOR_REFS = {
    "frontier_receipt",
    "execution_receipt",
    "assistant_summary",
    "dependency_completeness_verification",
    "dependency_enumeration",
}


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


def _resolve(
    resolver: SourceResolver, ref: Any, *, prefix: str
) -> tuple[bytes | None, str | None]:
    if not _nonempty(ref):
        return None, f"{prefix}.source_ref must be non-empty"
    try:
        payload = resolver(str(ref))
    except Exception as exc:  # noqa: BLE001 - fail-closed provider/source boundary
        return None, f"{prefix}.source readback unresolved: {exc.__class__.__name__}"
    if not isinstance(payload, bytes):
        return None, f"{prefix}.resolver must return bytes"
    return payload, None


def _collect_execution_claim_ids(value: Any, found: set[str]) -> None:
    """Recursively collect execution claim identities from structured source data."""
    if isinstance(value, str):
        if value.startswith(_EXECUTION_CLAIM_PREFIX) and value.strip() == value:
            found.add(value)
        return
    if isinstance(value, Mapping):
        for nested in value.values():
            _collect_execution_claim_ids(nested, found)
        return
    if isinstance(value, list):
        for nested in value:
            _collect_execution_claim_ids(nested, found)


def _derive_claim_ids_from_input_bytes(
    payload: bytes, *, prefix: str
) -> tuple[set[str], str | None]:
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return set(), f"{prefix} must resolve to UTF-8 JSON for deterministic dependency derivation"
    found: set[str] = set()
    _collect_execution_claim_ids(parsed, found)
    return found, None


def _validate_input_manifest(
    evidence: Mapping[str, Any],
    *,
    resolver: SourceResolver,
    expected_frontier_id: str,
    input_refs: Sequence[str],
    enumeration_evidence_ref: str,
) -> tuple[str, ...]:
    errors: list[str] = []
    prefix = "frontier_authority.dependency_enumeration.input_manifest"
    manifest_ref = evidence.get("input_manifest_ref")
    manifest_sha256 = evidence.get("input_manifest_sha256")
    payload, resolution_error = _resolve(resolver, manifest_ref, prefix=prefix)
    if resolution_error:
        return (resolution_error,)
    assert payload is not None

    if manifest_ref == enumeration_evidence_ref:
        errors.append(f"{prefix}.source_ref cannot equal dependency enumeration evidence_ref")
    if manifest_sha256 != _sha256(payload):
        errors.append(f"{prefix}.input_manifest_sha256 does not match resolved bytes")

    try:
        manifest = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return tuple(errors + [f"{prefix}.source_ref must resolve to UTF-8 JSON"])
    if not isinstance(manifest, Mapping):
        return tuple(errors + [f"{prefix} must resolve to an object"])

    if manifest.get("frontier_id") != expected_frontier_id:
        errors.append(f"{prefix}.frontier_id must equal the derived frontier_id")

    collector_ref = manifest.get("collector_ref")
    if not _nonempty(collector_ref):
        errors.append(f"{prefix}.collector_ref must be non-empty")
    if collector_ref in _FORBIDDEN_COLLECTOR_REFS:
        errors.append(f"{prefix}.collector_ref cannot self-certify material input discovery")

    manifest_refs = manifest.get("input_refs")
    if (
        not isinstance(manifest_refs, list)
        or not manifest_refs
        or not all(_nonempty(item) for item in manifest_refs)
    ):
        errors.append(f"{prefix}.input_refs must be a non-empty array of source refs")
    else:
        normalized = [str(item) for item in manifest_refs]
        if len(normalized) != len(set(normalized)):
            errors.append(f"{prefix}.input_refs must be unique")
        if sorted(normalized) != sorted(input_refs):
            errors.append(
                f"{prefix}.input_refs must exactly match dependency enumeration input_refs"
            )

    return tuple(dict.fromkeys(errors))


def validate_dependency_enumeration(
    artifact: Mapping[str, Any],
    *,
    resolver: SourceResolver,
    expected_frontier_id: str,
    declared_execution_claim_ids: Sequence[str],
) -> DependencyEnumerationResult:
    """Validate enumeration against dependencies derived from independently read inputs."""
    errors: list[str] = []
    prefix = "frontier_authority.dependency_enumeration"

    evidence_ref = artifact.get("evidence_ref")
    source_bytes, resolution_error = _resolve(
        resolver, evidence_ref, prefix=prefix
    )
    if resolution_error:
        return DependencyEnumerationResult(
            False,
            "DEPENDENCY_ENUMERATION_READBACK_UNRESOLVED",
            (),
            (resolution_error,),
        )
    assert source_bytes is not None

    if artifact.get("evidence_sha256") != _sha256(source_bytes):
        errors.append(
            f"{prefix}.evidence_sha256 does not match independently resolved bytes"
        )

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
        errors.append(
            f"{prefix}.evidence.frontier_id must equal the derived frontier_id"
        )

    enumerator_ref = evidence.get("enumerator_ref")
    if not _nonempty(enumerator_ref):
        errors.append(f"{prefix}.evidence.enumerator_ref must be non-empty")
    if enumerator_ref in _FORBIDDEN_COLLECTOR_REFS:
        errors.append(
            f"{prefix}.evidence.enumerator_ref cannot self-certify dependency discovery"
        )

    enumerator_version = evidence.get("enumerator_version")
    if not _nonempty(enumerator_version):
        errors.append(f"{prefix}.evidence.enumerator_version must be non-empty")

    input_refs = evidence.get("input_refs")
    input_hashes = evidence.get("input_sha256")
    deterministic_required: set[str] = set()
    normalized_input_refs: list[str] = []
    if (
        not isinstance(input_refs, list)
        or not input_refs
        or not all(_nonempty(item) for item in input_refs)
    ):
        errors.append(
            f"{prefix}.evidence.input_refs must be a non-empty array of source refs"
        )
    elif len(input_refs) != len(set(input_refs)):
        errors.append(f"{prefix}.evidence.input_refs must be unique")
        normalized_input_refs = [str(item) for item in input_refs]
    else:
        normalized_input_refs = [str(item) for item in input_refs]

    if normalized_input_refs and _nonempty(evidence_ref):
        errors.extend(
            _validate_input_manifest(
                evidence,
                resolver=resolver,
                expected_frontier_id=expected_frontier_id,
                input_refs=normalized_input_refs,
                enumeration_evidence_ref=str(evidence_ref),
            )
        )

    if not isinstance(input_hashes, Mapping):
        errors.append(
            f"{prefix}.evidence.input_sha256 must map every input ref to its hash"
        )
    elif isinstance(input_refs, list):
        if set(input_hashes) != set(input_refs):
            errors.append(f"{prefix}.evidence.input_sha256 must exactly cover input_refs")
        for ref in input_refs:
            if not _nonempty(ref):
                continue
            input_prefix = f"{prefix}.input[{ref}]"
            payload, input_error = _resolve(resolver, ref, prefix=input_prefix)
            if input_error:
                errors.append(input_error)
                continue
            assert payload is not None
            if input_hashes.get(ref) != _sha256(payload):
                errors.append(
                    f"{prefix}.evidence.input_sha256[{ref!r}] does not match resolved bytes"
                )
            derived, derivation_error = _derive_claim_ids_from_input_bytes(
                payload, prefix=input_prefix
            )
            if derivation_error:
                errors.append(derivation_error)
            deterministic_required.update(derived)

    candidates = evidence.get("candidate_execution_claim_ids")
    candidate_required: tuple[str, ...] = ()
    if not isinstance(candidates, list) or not all(_nonempty(item) for item in candidates):
        errors.append(
            f"{prefix}.evidence.candidate_execution_claim_ids must be an array of non-empty strings"
        )
    else:
        normalized = [str(item) for item in candidates]
        if len(normalized) != len(set(normalized)):
            errors.append(
                f"{prefix}.evidence.candidate_execution_claim_ids must be unique"
            )
        candidate_required = tuple(sorted(normalized))
        derived_required = tuple(sorted(deterministic_required))
        if candidate_required != derived_required:
            errors.append(
                f"{prefix}.evidence.candidate_execution_claim_ids must exactly equal dependencies deterministically derived from resolved inputs"
            )

    required = tuple(sorted(deterministic_required))
    if sorted(declared_execution_claim_ids) != list(required):
        errors.append(
            f"{prefix}.resolved inputs prove declared execution_claim_ids are incomplete or substituted"
        )

    if errors:
        return DependencyEnumerationResult(
            False,
            "DEPENDENCY_ENUMERATION_UNRESOLVED",
            required,
            tuple(dict.fromkeys(errors)),
        )
    return DependencyEnumerationResult(
        True, "DEPENDENCY_ENUMERATION_VERIFIED", required, ()
    )
