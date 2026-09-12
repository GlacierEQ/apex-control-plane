"""Independent authority for material-input collector identity.

A material-input manifest cannot establish its own collector authority merely by
naming a collector_ref. This boundary resolves the dependency enumeration, its
hashed manifest, and a separate collector attestation, then binds all three to
the same frontier, manifest bytes, collector identity, and input universe.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

SourceResolver = Callable[[str], bytes]
_FORBIDDEN_VERIFIER_REFS = {
    "frontier_receipt",
    "execution_receipt",
    "assistant_summary",
    "dependency_completeness_verification",
    "dependency_enumeration",
    "material_input_manifest",
    "material_input_collector_attestation",
}


@dataclass(frozen=True, slots=True)
class CollectorAuthorityResult:
    ok: bool
    status: str
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
    except Exception as exc:  # noqa: BLE001 - fail-closed source boundary
        return None, f"{prefix}.source readback unresolved: {exc.__class__.__name__}"
    if not isinstance(payload, bytes):
        return None, f"{prefix}.resolver must return bytes"
    return payload, None


def _json_object(payload: bytes, *, prefix: str) -> tuple[Mapping[str, Any] | None, str | None]:
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, f"{prefix} must resolve to UTF-8 JSON"
    if not isinstance(parsed, Mapping):
        return None, f"{prefix} must resolve to an object"
    return parsed, None


def _input_refs_digest(input_refs: Any) -> str | None:
    if not isinstance(input_refs, list) or not input_refs or not all(_nonempty(item) for item in input_refs):
        return None
    normalized = sorted(str(item) for item in input_refs)
    payload = json.dumps(normalized, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return _sha256(payload)


def validate_material_input_collector_authority(
    frontier_authority: Mapping[str, Any], *, resolver: SourceResolver
) -> CollectorAuthorityResult:
    """Require independently resolved collector attestation for the material-input manifest."""
    errors: list[str] = []
    prefix = "frontier_authority.material_input_collector_attestation"

    frontier_id = frontier_authority.get("frontier_id")
    if not _nonempty(frontier_id):
        return CollectorAuthorityResult(False, "COLLECTOR_AUTHORITY_UNRESOLVED", ("frontier_authority.frontier_id must be non-empty",))

    enumeration_artifact = frontier_authority.get("dependency_enumeration")
    if not isinstance(enumeration_artifact, Mapping):
        return CollectorAuthorityResult(False, "COLLECTOR_AUTHORITY_UNRESOLVED", ("frontier_authority.dependency_enumeration must be an object",))

    enumeration_bytes, resolution_error = _resolve(
        resolver, enumeration_artifact.get("evidence_ref"), prefix="frontier_authority.dependency_enumeration"
    )
    if resolution_error:
        return CollectorAuthorityResult(False, "COLLECTOR_READBACK_UNRESOLVED", (resolution_error,))
    assert enumeration_bytes is not None
    enumeration, parse_error = _json_object(enumeration_bytes, prefix="frontier_authority.dependency_enumeration.evidence")
    if parse_error:
        return CollectorAuthorityResult(False, "COLLECTOR_AUTHORITY_UNRESOLVED", (parse_error,))
    assert enumeration is not None

    manifest_ref = enumeration.get("input_manifest_ref")
    manifest_sha256 = enumeration.get("input_manifest_sha256")
    manifest_bytes, resolution_error = _resolve(
        resolver, manifest_ref, prefix="frontier_authority.dependency_enumeration.input_manifest"
    )
    if resolution_error:
        return CollectorAuthorityResult(False, "COLLECTOR_READBACK_UNRESOLVED", (resolution_error,))
    assert manifest_bytes is not None
    if manifest_sha256 != _sha256(manifest_bytes):
        errors.append("frontier_authority.dependency_enumeration.input_manifest_sha256 does not match resolved bytes")
    manifest, parse_error = _json_object(manifest_bytes, prefix="frontier_authority.dependency_enumeration.input_manifest")
    if parse_error:
        errors.append(parse_error)
        manifest = None

    collector_ref: Any = None
    input_refs_digest: str | None = None
    if manifest is not None:
        if manifest.get("frontier_id") != frontier_id:
            errors.append("frontier_authority.dependency_enumeration.input_manifest.frontier_id must equal frontier_id")
        collector_ref = manifest.get("collector_ref")
        if not _nonempty(collector_ref):
            errors.append("frontier_authority.dependency_enumeration.input_manifest.collector_ref must be non-empty")
        input_refs_digest = _input_refs_digest(manifest.get("input_refs"))
        if input_refs_digest is None:
            errors.append("frontier_authority.dependency_enumeration.input_manifest.input_refs must be a non-empty array of source refs")

    attestation_artifact = frontier_authority.get("material_input_collector_attestation")
    if not isinstance(attestation_artifact, Mapping):
        errors.append(f"{prefix} must contain independent evidence")
    else:
        attestation_bytes, resolution_error = _resolve(
            resolver, attestation_artifact.get("evidence_ref"), prefix=prefix
        )
        if resolution_error:
            errors.append(resolution_error)
        else:
            assert attestation_bytes is not None
            if attestation_artifact.get("evidence_sha256") != _sha256(attestation_bytes):
                errors.append(f"{prefix}.evidence_sha256 does not match independently resolved bytes")
            attestation, parse_error = _json_object(attestation_bytes, prefix=f"{prefix}.evidence")
            if parse_error:
                errors.append(parse_error)
            elif attestation is not None:
                expected = {
                    "frontier_id": frontier_id,
                    "collector_ref": collector_ref,
                    "input_manifest_ref": manifest_ref,
                    "input_manifest_sha256": manifest_sha256,
                    "input_refs_sha256": input_refs_digest,
                    "verdict": "collector_verified",
                }
                for key, value in expected.items():
                    if attestation.get(key) != value:
                        errors.append(f"{prefix}.evidence.{key} must equal {value!r}")
                verifier_ref = attestation.get("verifier_ref")
                if not _nonempty(verifier_ref):
                    errors.append(f"{prefix}.evidence.verifier_ref must be non-empty")
                if verifier_ref in _FORBIDDEN_VERIFIER_REFS or verifier_ref == collector_ref:
                    errors.append(f"{prefix}.evidence.verifier_ref cannot self-certify collector authority")

    if errors:
        return CollectorAuthorityResult(False, "COLLECTOR_AUTHORITY_UNRESOLVED", tuple(dict.fromkeys(errors)))
    return CollectorAuthorityResult(True, "COLLECTOR_AUTHORITY_VERIFIED", ())
