"""Fail-closed authorization for continuity-dependent executable frontiers.

A continuation summary may suggest where to look, but it may not authorize the
branch that runtime execution follows. This module separates frontier selection
from frontier authorization by requiring independently resolved source spans
plus an independently resolved entailment artifact.

The receipt never supplies authoritative source bytes. Callers provide a
resolver that returns bytes for source references; validation recomputes every
hash and exact span before accepting the frontier.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from operator_source_binding_contract import verify_source_span_binding

SourceResolver = Callable[[str], bytes]
VerifierResolver = Callable[[str], bytes]

_ENTAILED = "entailed"
_VERIFICATION_METHOD = "hmac-sha256"
_VERIFICATION_STATE = "verified"
_DERIVATIVE_VERIFIER_PREFIXES = (
    "assistant",
    "summary",
    "memory",
    "profile",
    "checkpoint",
    "manifest",
    "frontier_receipt",
)


@dataclass(frozen=True, slots=True)
class FrontierAuthorizationResult:
    ok: bool
    status: str
    errors: tuple[str, ...]


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _canonical_digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return _sha256(payload)


def _attestation_payload(evidence: Mapping[str, Any]) -> bytes:
    """Canonical bytes signed by the independently resolved verifier key."""
    unsigned = {key: value for key, value in evidence.items() if key != "attestation"}
    return json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def build_entailment_attestation(evidence: Mapping[str, Any], *, key: bytes) -> str:
    """Build a detached HMAC attestation for test/external verifier producers."""
    if not isinstance(key, bytes) or not key:
        raise ValueError("verifier key must be non-empty bytes")
    digest = hmac.new(key, _attestation_payload(evidence), hashlib.sha256).hexdigest()
    return f"{_VERIFICATION_METHOD}:{digest}"


def derive_frontier_id(
    *,
    operation_class: str,
    target: str,
    frontier_action: str,
    proposition_ids: Sequence[str],
) -> str:
    """Derive the frontier identity from material authorization inputs."""
    payload = {
        "operation_class": operation_class,
        "target": target,
        "frontier_action": frontier_action,
        "proposition_ids": sorted(proposition_ids),
    }
    return "frontier:" + _canonical_digest(payload).removeprefix("sha256:")


def _resolve(
    resolver: SourceResolver, source_ref: Any, *, prefix: str
) -> tuple[bytes | None, str | None]:
    if not _nonempty(source_ref):
        return None, f"{prefix}.source_ref must be non-empty"
    try:
        payload = resolver(str(source_ref))
    except Exception as exc:  # noqa: BLE001 - fail-closed resolver boundary
        return None, f"{prefix}.source readback unresolved: {exc.__class__.__name__}"
    if not isinstance(payload, bytes):
        return None, f"{prefix}.resolver must return bytes"
    return payload, None


def _validate_direction_binding(
    binding: Mapping[str, Any], *, resolver: SourceResolver, index: int
) -> tuple[str, ...]:
    prefix = f"frontier_authority.source_bindings[{index}]"
    verification = verify_source_span_binding(
        binding,
        resolver=resolver,
        prefix=prefix,
        require_unsuperseded=True,
    )
    errors = [
        error.replace(
            "is derivative and cannot authorize Operator direction",
            "is derivative and cannot authorize executable direction",
        )
        for error in verification.errors
    ]
    if verification.span_text is not None and verification.span_text != binding.get(
        "proposition_text"
    ):
        errors.append(
            f"{prefix}.proposition_text does not exactly equal resolved source span"
        )
    return tuple(dict.fromkeys(errors))


def _validate_entailment_artifact(
    artifact: Mapping[str, Any],
    *,
    resolver: SourceResolver,
    verifier_resolver: VerifierResolver | None,
    expected_frontier_id: str,
    proposition_ids: Sequence[str],
    operation_class: str,
    target: str,
    frontier_action: str,
    index: int,
) -> tuple[str, ...]:
    errors: list[str] = []
    prefix = f"frontier_authority.entailment_verifications[{index}]"
    source_bytes, resolution_error = _resolve(
        resolver, artifact.get("evidence_ref"), prefix=prefix
    )
    if resolution_error:
        errors.append(resolution_error)
        return tuple(errors)
    assert source_bytes is not None

    if artifact.get("evidence_sha256") != _sha256(source_bytes):
        errors.append(
            f"{prefix}.evidence_sha256 does not match independently resolved bytes"
        )
    try:
        evidence = json.loads(source_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        errors.append(f"{prefix}.evidence_ref must resolve to UTF-8 JSON")
        return tuple(errors)
    if not isinstance(evidence, Mapping):
        errors.append(f"{prefix}.evidence must be an object")
        return tuple(errors)

    expected = {
        "frontier_id": expected_frontier_id,
        "verdict": _ENTAILED,
        "operation_class": operation_class,
        "target": target,
        "frontier_action": frontier_action,
    }
    for key, value in expected.items():
        if evidence.get(key) != value:
            errors.append(f"{prefix}.evidence.{key} must equal {value!r}")
    evidence_ids = evidence.get("proposition_ids")
    if not isinstance(evidence_ids, list) or sorted(evidence_ids) != sorted(
        proposition_ids
    ):
        errors.append(
            f"{prefix}.evidence.proposition_ids must exactly match bound propositions"
        )
    verifier_ref = evidence.get("verifier_ref")
    if not _nonempty(verifier_ref):
        errors.append(f"{prefix}.evidence.verifier_ref must be non-empty")
        return tuple(errors)
    normalized_verifier = str(verifier_ref).strip().lower()
    if normalized_verifier.startswith(_DERIVATIVE_VERIFIER_PREFIXES):
        errors.append(
            f"{prefix}.evidence.verifier_ref is derivative/self-certifying and cannot self-certify or authorize entailment"
        )

    if evidence.get("verification_method") != _VERIFICATION_METHOD:
        errors.append(
            f"{prefix}.evidence.verification_method must be {_VERIFICATION_METHOD!r}"
        )
    if evidence.get("verification_state") != _VERIFICATION_STATE:
        errors.append(
            f"{prefix}.evidence.verification_state must be {_VERIFICATION_STATE!r}"
        )

    attestation = evidence.get("attestation")
    if not _nonempty(attestation):
        errors.append(f"{prefix}.evidence.attestation must be non-empty")
    if verifier_resolver is None:
        errors.append(
            f"{prefix}.independent verifier readback unresolved: verifier resolver is unavailable"
        )
        return tuple(errors)
    try:
        verifier_key = verifier_resolver(str(verifier_ref))
    except Exception as exc:  # noqa: BLE001 - fail-closed trust boundary
        errors.append(
            f"{prefix}.independent verifier readback unresolved: {exc.__class__.__name__}"
        )
        return tuple(errors)
    if not isinstance(verifier_key, bytes) or not verifier_key:
        errors.append(f"{prefix}.verifier resolver must return non-empty bytes")
        return tuple(errors)

    if _nonempty(attestation):
        expected_attestation = build_entailment_attestation(evidence, key=verifier_key)
        if not hmac.compare_digest(str(attestation), expected_attestation):
            errors.append(
                f"{prefix}.evidence.attestation does not verify against independently resolved verifier key"
            )
    return tuple(dict.fromkeys(errors))


def validate_executable_frontier_authority(
    receipt: Mapping[str, Any],
    *,
    resolver: SourceResolver,
    verifier_resolver: VerifierResolver | None = None,
) -> FrontierAuthorizationResult:
    """Authorize an executable frontier only from independently resolved evidence."""
    errors: list[str] = []
    row = receipt.get("frontier_authority")
    if not isinstance(row, Mapping):
        return FrontierAuthorizationResult(
            False,
            "frontier_authorization_required",
            ("frontier_authority must be an object",),
        )

    operation_class = row.get("operation_class")
    target = row.get("target")
    frontier_action = row.get("frontier_action")
    for field_name, value in (
        ("operation_class", operation_class),
        ("target", target),
        ("frontier_action", frontier_action),
    ):
        if not _nonempty(value):
            errors.append(f"frontier_authority.{field_name} must be non-empty")

    bindings = row.get("source_bindings")
    if not isinstance(bindings, list) or not bindings:
        errors.append("frontier_authority.source_bindings must be a non-empty array")
        proposition_ids: list[str] = []
    else:
        proposition_ids = []
        for index, binding in enumerate(bindings):
            if not isinstance(binding, Mapping):
                errors.append(
                    f"frontier_authority.source_bindings[{index}] must be an object"
                )
                continue
            proposition_id = binding.get("proposition_id")
            if _nonempty(proposition_id):
                proposition_ids.append(str(proposition_id))
            errors.extend(
                _validate_direction_binding(binding, resolver=resolver, index=index)
            )
        if len(proposition_ids) != len(set(proposition_ids)):
            errors.append("frontier_authority proposition_ids must be unique")

    if not (
        _nonempty(operation_class) and _nonempty(target) and _nonempty(frontier_action)
    ):
        expected_frontier_id = ""
    else:
        expected_frontier_id = derive_frontier_id(
            operation_class=str(operation_class),
            target=str(target),
            frontier_action=str(frontier_action),
            proposition_ids=proposition_ids,
        )
        if row.get("frontier_id") != expected_frontier_id:
            errors.append(
                "frontier_authority.frontier_id is not bound to material frontier inputs"
            )
        if row.get("continuation_ref") != expected_frontier_id:
            errors.append(
                "frontier_authority.continuation_ref must equal the derived frontier_id"
            )

    verifications = row.get("entailment_verifications")
    if not isinstance(verifications, list) or not verifications:
        errors.append(
            "frontier_authority.entailment_verifications must contain independent evidence"
        )
    elif expected_frontier_id:
        for index, artifact in enumerate(verifications):
            if not isinstance(artifact, Mapping):
                errors.append(
                    f"frontier_authority.entailment_verifications[{index}] must be an object"
                )
                continue
            errors.extend(
                _validate_entailment_artifact(
                    artifact,
                    resolver=resolver,
                    verifier_resolver=verifier_resolver,
                    expected_frontier_id=expected_frontier_id,
                    proposition_ids=proposition_ids,
                    operation_class=str(operation_class),
                    target=str(target),
                    frontier_action=str(frontier_action),
                    index=index,
                )
            )

    if errors:
        return FrontierAuthorizationResult(
            False, "frontier_authorization_unresolved", tuple(dict.fromkeys(errors))
        )
    return FrontierAuthorizationResult(True, "frontier_authorized", ())
