"""Fail-closed identity authority for independent frontier verifiers.

A verifier label such as ``independent:foo`` is not evidence of identity. This
boundary resolves the collector attestation, then requires the attestation's
verifier identity to be content-addressed to independently resolved verifier
implementation bytes. The verifier reference is therefore derived from bytes,
not accepted from narrative metadata.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

SourceResolver = Callable[[str], bytes]


@dataclass(frozen=True, slots=True)
class VerifierIdentityResult:
    ok: bool
    status: str
    errors: tuple[str, ...]


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def derive_content_addressed_verifier_ref(payload: bytes) -> str:
    return "verifier:" + _sha256(payload)


def _resolve(
    resolver: SourceResolver, ref: Any, *, prefix: str
) -> tuple[bytes | None, str | None]:
    if not _nonempty(ref):
        return None, f"{prefix}.source_ref must be non-empty"
    try:
        payload = resolver(str(ref))
    except Exception as exc:  # noqa: BLE001 - fail-closed source boundary
        return None, f"{prefix}.source readback unresolved: {exc.__class__.__name__}"
    if not isinstance(payload, bytes):
        return None, f"{prefix}.resolver must return bytes"
    return payload, None


def _json_object(
    payload: bytes, *, prefix: str
) -> tuple[Mapping[str, Any] | None, str | None]:
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, f"{prefix} must resolve to UTF-8 JSON"
    if not isinstance(parsed, Mapping):
        return None, f"{prefix} must resolve to an object"
    return parsed, None


def validate_verifier_identity_authority(
    frontier_authority: Mapping[str, Any], *, resolver: SourceResolver
) -> VerifierIdentityResult:
    """Require collector-attestation verifier identity to derive from resolved bytes."""
    errors: list[str] = []
    prefix = "frontier_authority.verifier_identity_attestation"
    frontier_id = frontier_authority.get("frontier_id")
    if not _nonempty(frontier_id):
        return VerifierIdentityResult(
            False,
            "VERIFIER_IDENTITY_UNRESOLVED",
            ("frontier_authority.frontier_id must be non-empty",),
        )

    collector_artifact = frontier_authority.get("material_input_collector_attestation")
    if not isinstance(collector_artifact, Mapping):
        return VerifierIdentityResult(
            False,
            "VERIFIER_IDENTITY_UNRESOLVED",
            ("frontier_authority.material_input_collector_attestation must be an object",),
        )
    collector_bytes, resolution_error = _resolve(
        resolver,
        collector_artifact.get("evidence_ref"),
        prefix="frontier_authority.material_input_collector_attestation",
    )
    if resolution_error:
        return VerifierIdentityResult(
            False, "VERIFIER_IDENTITY_READBACK_UNRESOLVED", (resolution_error,)
        )
    assert collector_bytes is not None
    if collector_artifact.get("evidence_sha256") != _sha256(collector_bytes):
        errors.append(
            "frontier_authority.material_input_collector_attestation.evidence_sha256 does not match independently resolved bytes"
        )
    collector, parse_error = _json_object(
        collector_bytes,
        prefix="frontier_authority.material_input_collector_attestation.evidence",
    )
    if parse_error:
        errors.append(parse_error)
        collector = None

    claimed_verifier_ref = collector.get("verifier_ref") if collector is not None else None
    identity_artifact = frontier_authority.get("verifier_identity_attestation")
    if not isinstance(identity_artifact, Mapping):
        errors.append(f"{prefix} must contain independently resolved identity evidence")
    else:
        identity_bytes, resolution_error = _resolve(
            resolver, identity_artifact.get("evidence_ref"), prefix=prefix
        )
        if resolution_error:
            errors.append(resolution_error)
        else:
            assert identity_bytes is not None
            if identity_artifact.get("evidence_sha256") != _sha256(identity_bytes):
                errors.append(
                    f"{prefix}.evidence_sha256 does not match independently resolved bytes"
                )
            identity, parse_error = _json_object(
                identity_bytes, prefix=f"{prefix}.evidence"
            )
            if parse_error:
                errors.append(parse_error)
            elif identity is not None:
                if identity.get("frontier_id") != frontier_id:
                    errors.append(f"{prefix}.evidence.frontier_id must equal {frontier_id!r}")
                if identity.get("identity_scheme") != "sha256-content-addressed":
                    errors.append(
                        f"{prefix}.evidence.identity_scheme must equal 'sha256-content-addressed'"
                    )
                if identity.get("verdict") != "verifier_identity_verified":
                    errors.append(
                        f"{prefix}.evidence.verdict must equal 'verifier_identity_verified'"
                    )
                implementation_ref = identity.get("verifier_implementation_ref")
                implementation_bytes, implementation_error = _resolve(
                    resolver,
                    implementation_ref,
                    prefix=f"{prefix}.evidence.verifier_implementation",
                )
                if implementation_error:
                    errors.append(implementation_error)
                else:
                    assert implementation_bytes is not None
                    implementation_sha256 = _sha256(implementation_bytes)
                    if identity.get("verifier_implementation_sha256") != implementation_sha256:
                        errors.append(
                            f"{prefix}.evidence.verifier_implementation_sha256 does not match independently resolved bytes"
                        )
                    derived_ref = derive_content_addressed_verifier_ref(
                        implementation_bytes
                    )
                    if identity.get("verifier_ref") != derived_ref:
                        errors.append(
                            f"{prefix}.evidence.verifier_ref must equal content-addressed verifier identity {derived_ref!r}"
                        )
                    if claimed_verifier_ref != derived_ref:
                        errors.append(
                            "frontier_authority.material_input_collector_attestation.evidence.verifier_ref is not bound to resolved verifier implementation bytes"
                        )

    if errors:
        return VerifierIdentityResult(
            False, "VERIFIER_IDENTITY_UNRESOLVED", tuple(dict.fromkeys(errors))
        )
    return VerifierIdentityResult(True, "VERIFIER_IDENTITY_VERIFIED", ())
