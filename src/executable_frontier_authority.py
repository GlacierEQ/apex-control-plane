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
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

SourceResolver = Callable[[str], bytes]

_ALLOWED_DIRECTION_SOURCE_KINDS = frozenset(
    {"operator_message", "operator_file", "operator_record"}
)
_DERIVATIVE_SOURCE_KINDS = frozenset(
    {
        "assistant_summary",
        "checkpoint",
        "index",
        "manifest",
        "memory_summary",
        "profile",
        "working_model",
    }
)
_ACTIVE_CONTRADICTION_STATES = frozenset({"active", "resolved_consistent"})
_VERIFIED = "source_resolved"
_ENTAILED = "entailed"


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


def derive_frontier_id(
    *, operation_class: str, target: str, frontier_action: str, proposition_ids: Sequence[str]
) -> str:
    """Derive the frontier identity from material authorization inputs."""
    payload = {
        "operation_class": operation_class,
        "target": target,
        "frontier_action": frontier_action,
        "proposition_ids": sorted(proposition_ids),
    }
    return "frontier:" + _canonical_digest(payload).removeprefix("sha256:")


def _resolve(resolver: SourceResolver, source_ref: Any, *, prefix: str) -> tuple[bytes | None, str | None]:
    if not _nonempty(source_ref):
        return None, f"{prefix}.source_ref must be non-empty"
    try:
        payload = resolver(str(source_ref))
    except Exception as exc:  # resolver boundary intentionally broad and fail-closed
        return None, f"{prefix}.source readback unresolved: {exc.__class__.__name__}"
    if not isinstance(payload, bytes):
        return None, f"{prefix}.resolver must return bytes"
    return payload, None


def _validate_direction_binding(
    binding: Mapping[str, Any], *, resolver: SourceResolver, index: int
) -> tuple[str, ...]:
    errors: list[str] = []
    prefix = f"frontier_authority.source_bindings[{index}]"

    proposition_id = binding.get("proposition_id")
    if not _nonempty(proposition_id):
        errors.append(f"{prefix}.proposition_id must be non-empty")

    source_kind = str(binding.get("source_kind", "")).strip()
    if source_kind in _DERIVATIVE_SOURCE_KINDS:
        errors.append(
            f"{prefix}.source_kind={source_kind!r} is derivative and cannot authorize executable direction"
        )
    elif source_kind not in _ALLOWED_DIRECTION_SOURCE_KINDS:
        errors.append(
            f"{prefix}.source_kind must be one of {sorted(_ALLOWED_DIRECTION_SOURCE_KINDS)!r}"
        )

    if str(binding.get("verification_state", "")).strip() != _VERIFIED:
        errors.append(f"{prefix}.verification_state must be {_VERIFIED!r}")

    contradiction_state = str(binding.get("contradiction_state", "")).strip()
    if contradiction_state not in _ACTIVE_CONTRADICTION_STATES:
        errors.append(
            f"{prefix}.contradiction_state must be active or resolved_consistent"
        )
    if _nonempty(binding.get("superseded_by")):
        errors.append(f"{prefix}.superseded_by must be empty for an active frontier source")

    source_bytes, resolution_error = _resolve(
        resolver, binding.get("source_ref"), prefix=prefix
    )
    if resolution_error:
        errors.append(resolution_error)
        return tuple(errors)
    assert source_bytes is not None

    if binding.get("source_sha256") != _sha256(source_bytes):
        errors.append(f"{prefix}.source_sha256 does not match independently resolved bytes")

    start = binding.get("span_start_byte")
    end = binding.get("span_end_byte")
    if (
        not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end, int)
        or isinstance(end, bool)
        or start < 0
        or end <= start
        or end > len(source_bytes)
    ):
        errors.append(f"{prefix}.span byte range is invalid for resolved source")
        return tuple(errors)

    span = source_bytes[start:end]
    if binding.get("span_sha256") != _sha256(span):
        errors.append(f"{prefix}.span_sha256 does not match independently resolved span")
    try:
        span_text = span.decode("utf-8")
    except UnicodeDecodeError:
        errors.append(f"{prefix}.source span must be valid UTF-8")
        return tuple(errors)
    if span_text != binding.get("proposition_text"):
        errors.append(f"{prefix}.proposition_text does not exactly equal resolved source span")
    return tuple(errors)


def _validate_entailment_artifact(
    artifact: Mapping[str, Any],
    *,
    resolver: SourceResolver,
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
        errors.append(f"{prefix}.evidence_sha256 does not match independently resolved bytes")
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
    if not isinstance(evidence_ids, list) or sorted(evidence_ids) != sorted(proposition_ids):
        errors.append(f"{prefix}.evidence.proposition_ids must exactly match bound propositions")
    verifier_ref = evidence.get("verifier_ref")
    if not _nonempty(verifier_ref):
        errors.append(f"{prefix}.evidence.verifier_ref must be non-empty")
    if verifier_ref == "frontier_receipt":
        errors.append(f"{prefix}.evidence.verifier_ref cannot self-certify from frontier receipt")
    return tuple(errors)


def validate_executable_frontier_authority(
    receipt: Mapping[str, Any], *, resolver: SourceResolver
) -> FrontierAuthorizationResult:
    """Authorize an executable frontier only from independently resolved evidence."""
    errors: list[str] = []
    row = receipt.get("frontier_authority")
    if not isinstance(row, Mapping):
        return FrontierAuthorizationResult(
            False, "frontier_authorization_required", ("frontier_authority must be an object",)
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
                errors.append(f"frontier_authority.source_bindings[{index}] must be an object")
                continue
            proposition_id = binding.get("proposition_id")
            if _nonempty(proposition_id):
                proposition_ids.append(str(proposition_id))
            errors.extend(
                _validate_direction_binding(binding, resolver=resolver, index=index)
            )
        if len(proposition_ids) != len(set(proposition_ids)):
            errors.append("frontier_authority proposition_ids must be unique")

    if not (_nonempty(operation_class) and _nonempty(target) and _nonempty(frontier_action)):
        expected_frontier_id = ""
    else:
        expected_frontier_id = derive_frontier_id(
            operation_class=str(operation_class),
            target=str(target),
            frontier_action=str(frontier_action),
            proposition_ids=proposition_ids,
        )
        if row.get("frontier_id") != expected_frontier_id:
            errors.append("frontier_authority.frontier_id is not bound to material frontier inputs")
        if row.get("continuation_ref") != expected_frontier_id:
            errors.append("frontier_authority.continuation_ref must equal the derived frontier_id")

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
