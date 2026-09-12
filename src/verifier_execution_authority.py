"""Fail-closed execution authority for content-addressed frontier verifiers.

Content-addressing proves which verifier implementation is named; it does not
prove that those bytes actually executed. Provider execution proof therefore
uses a distinct provider readback resolver. Generic source resolution is never
accepted as provider provenance, even when a reference uses a provider-looking
scheme.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

SourceResolver = Callable[[str], bytes]
ProviderReadbackResolver = Callable[[str, str], bytes]


@dataclass(frozen=True, slots=True)
class VerifierExecutionResult:
    ok: bool
    status: str
    errors: tuple[str, ...]


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


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


def _resolve(
    resolver: SourceResolver, ref: Any, *, prefix: str
) -> tuple[bytes | None, str | None]:
    if not _nonempty(ref):
        return None, f"{prefix}.source_ref must be non-empty"
    try:
        payload = resolver(str(ref))
    except Exception as exc:  # noqa: BLE001
        return None, f"{prefix}.source readback unresolved: {exc.__class__.__name__}"
    if not isinstance(payload, bytes):
        return None, f"{prefix}.resolver must return bytes"
    return payload, None


def _resolve_provider(
    resolver: ProviderReadbackResolver | None,
    *,
    provider: str,
    ref: Any,
    prefix: str,
) -> tuple[bytes | None, str | None]:
    if resolver is None:
        return None, f"{prefix}.provider readback resolver is required"
    if not _nonempty(ref):
        return None, f"{prefix}.provider readback reference must be non-empty"
    try:
        payload = resolver(provider, str(ref))
    except Exception as exc:  # noqa: BLE001
        return (
            None,
            f"{prefix}.provider readback unresolved: {exc.__class__.__name__}",
        )
    if not isinstance(payload, bytes):
        return None, f"{prefix}.provider resolver must return bytes"
    return payload, None


def _provider_readback_prefix(provider: str) -> str:
    return f"provider://{provider}/"


def derive_verifier_execution_claim_id(
    *,
    frontier_id: str,
    verifier_ref: str,
    implementation_sha256: str,
    provider: str,
    run_ref: str,
) -> str:
    material = json.dumps(
        {
            "frontier_id": frontier_id,
            "implementation_sha256": implementation_sha256,
            "provider": provider,
            "run_ref": run_ref,
            "verifier_ref": verifier_ref,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "verifier-execution:" + hashlib.sha256(material).hexdigest()


def validate_verifier_execution_authority(
    frontier_authority: Mapping[str, Any],
    *,
    resolver: SourceResolver,
    provider_resolver: ProviderReadbackResolver | None,
) -> VerifierExecutionResult:
    errors: list[str] = []
    prefix = "frontier_authority.verifier_execution_attestation"
    frontier_id = frontier_authority.get("frontier_id")
    if not _nonempty(frontier_id):
        return VerifierExecutionResult(
            False,
            "VERIFIER_EXECUTION_UNRESOLVED",
            ("frontier_authority.frontier_id must be non-empty",),
        )

    identity_artifact = frontier_authority.get("verifier_identity_attestation")
    if not isinstance(identity_artifact, Mapping):
        return VerifierExecutionResult(
            False,
            "VERIFIER_EXECUTION_UNRESOLVED",
            ("frontier_authority.verifier_identity_attestation must be an object",),
        )
    identity_bytes, resolution_error = _resolve(
        resolver,
        identity_artifact.get("evidence_ref"),
        prefix="frontier_authority.verifier_identity_attestation",
    )
    if resolution_error:
        return VerifierExecutionResult(
            False,
            "VERIFIER_EXECUTION_READBACK_UNRESOLVED",
            (resolution_error,),
        )
    assert identity_bytes is not None
    identity, parse_error = _json_object(
        identity_bytes,
        prefix="frontier_authority.verifier_identity_attestation.evidence",
    )
    if parse_error or identity is None:
        return VerifierExecutionResult(
            False,
            "VERIFIER_EXECUTION_UNRESOLVED",
            (parse_error or "verifier identity unresolved",),
        )
    verifier_ref = identity.get("verifier_ref")
    implementation_sha256 = identity.get("verifier_implementation_sha256")
    if not _nonempty(verifier_ref) or not _nonempty(implementation_sha256):
        errors.append(
            "verifier identity must expose verifier_ref and verifier_implementation_sha256"
        )

    artifact = frontier_authority.get("verifier_execution_attestation")
    if not isinstance(artifact, Mapping):
        errors.append(
            f"{prefix} must contain independently resolved provider execution evidence"
        )
    else:
        evidence_bytes, resolution_error = _resolve(
            resolver, artifact.get("evidence_ref"), prefix=prefix
        )
        if resolution_error:
            errors.append(resolution_error)
        else:
            assert evidence_bytes is not None
            if artifact.get("evidence_sha256") != _sha256(evidence_bytes):
                errors.append(
                    f"{prefix}.evidence_sha256 does not match independently resolved bytes"
                )
            evidence, parse_error = _json_object(
                evidence_bytes, prefix=f"{prefix}.evidence"
            )
            if parse_error:
                errors.append(parse_error)
            elif evidence is not None:
                for key, expected in (
                    ("frontier_id", frontier_id),
                    ("verifier_ref", verifier_ref),
                    ("verifier_implementation_sha256", implementation_sha256),
                    ("verdict", "verifier_executed"),
                ):
                    if evidence.get(key) != expected:
                        errors.append(
                            f"{prefix}.evidence.{key} must equal {expected!r}"
                        )
                provider = evidence.get("provider")
                run_ref = evidence.get("run_ref")
                if not _nonempty(provider) or not _nonempty(run_ref):
                    errors.append(
                        f"{prefix}.evidence.provider and run_ref must be non-empty"
                    )
                else:
                    provider = str(provider)
                    expected_claim_id = derive_verifier_execution_claim_id(
                        frontier_id=str(frontier_id),
                        verifier_ref=str(verifier_ref),
                        implementation_sha256=str(implementation_sha256),
                        provider=provider,
                        run_ref=str(run_ref),
                    )
                    if evidence.get("verifier_execution_claim_id") != expected_claim_id:
                        errors.append(
                            f"{prefix}.evidence.verifier_execution_claim_id is not bound to execution identity"
                        )
                    provider_readback_ref = evidence.get("provider_readback_ref")
                    expected_prefix = _provider_readback_prefix(provider)
                    if not _nonempty(provider_readback_ref) or not str(
                        provider_readback_ref
                    ).startswith(expected_prefix):
                        errors.append(
                            f"{prefix}.evidence.provider_readback_ref must be provider-scoped under {expected_prefix!r}"
                        )
                    else:
                        readback_bytes, readback_error = _resolve_provider(
                            provider_resolver,
                            provider=provider,
                            ref=provider_readback_ref,
                            prefix=f"{prefix}.provider_readback",
                        )
                        if readback_error:
                            errors.append(readback_error)
                        else:
                            assert readback_bytes is not None
                            readback, parse_error = _json_object(
                                readback_bytes,
                                prefix=f"{prefix}.provider_readback",
                            )
                            if parse_error:
                                errors.append(parse_error)
                            elif readback is not None:
                                required = {
                                    "frontier_id": frontier_id,
                                    "verifier_ref": verifier_ref,
                                    "verifier_implementation_sha256": implementation_sha256,
                                    "provider": provider,
                                    "run_ref": run_ref,
                                    "verifier_execution_claim_id": expected_claim_id,
                                    "state": "completed",
                                    "conclusion": "success",
                                    "readback_verified": True,
                                }
                                for key, expected in required.items():
                                    if readback.get(key) != expected:
                                        errors.append(
                                            f"{prefix}.provider_readback.{key} must equal {expected!r}"
                                        )
                                if (
                                    readback.get("provider_readback_ref")
                                    != provider_readback_ref
                                ):
                                    errors.append(
                                        f"{prefix}.provider_readback.provider_readback_ref must echo the exact provider-scoped readback reference"
                                    )
                                output_ref = readback.get("output_ref")
                                if not _nonempty(output_ref) or not str(
                                    output_ref
                                ).startswith(expected_prefix):
                                    errors.append(
                                        f"{prefix}.provider_readback.output_ref must be provider-scoped under {expected_prefix!r}"
                                    )
                                else:
                                    output_bytes, output_error = _resolve_provider(
                                        provider_resolver,
                                        provider=provider,
                                        ref=output_ref,
                                        prefix=f"{prefix}.provider_readback.output",
                                    )
                                    if output_error:
                                        errors.append(output_error)
                                    else:
                                        assert output_bytes is not None
                                        output_sha256 = _sha256(output_bytes)
                                        if (
                                            readback.get("output_sha256")
                                            != output_sha256
                                        ):
                                            errors.append(
                                                f"{prefix}.provider_readback.output_sha256 does not match independently resolved provider output bytes"
                                            )
                                        if evidence.get("output_sha256") != output_sha256:
                                            errors.append(
                                                f"{prefix}.evidence.output_sha256 does not match provider output"
                                            )

    if errors:
        status = (
            "VERIFIER_EXECUTION_READBACK_UNRESOLVED"
            if any("readback unresolved" in error for error in errors)
            else "VERIFIER_EXECUTION_UNRESOLVED"
        )
        return VerifierExecutionResult(
            False, status, tuple(dict.fromkeys(errors))
        )
    return VerifierExecutionResult(True, "VERIFIER_EXECUTION_VERIFIED", ())
