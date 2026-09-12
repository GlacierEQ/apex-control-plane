"""Fail-closed authorization for continuity-dependent executable frontiers.

A continuation summary may suggest where to look, but it may not authorize the
branch that runtime execution follows. This module separates frontier selection
from frontier authorization by requiring independently resolved source spans
plus an independently resolved entailment artifact.

When a frontier depends on prior execution claims, those claim identities are
part of the frontier identity and each claim must reacquire present authority
through execution-evidence lineage reconciliation. Historical VERIFIED state is
never accepted as a substitute for current provider readback.

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

from execution_evidence_lineage import reconcile_execution_lineage
from operator_source_binding_contract import verify_source_span_binding

SourceResolver = Callable[[str], bytes]

_ENTAILED = "entailed"
_COMPLETE = "complete"


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
    *,
    operation_class: str,
    target: str,
    frontier_action: str,
    proposition_ids: Sequence[str],
    execution_claim_ids: Sequence[str] = (),
) -> str:
    """Derive frontier identity from source propositions and execution dependencies."""
    payload = {
        "operation_class": operation_class,
        "target": target,
        "frontier_action": frontier_action,
        "proposition_ids": sorted(proposition_ids),
        "execution_claim_ids": sorted(execution_claim_ids),
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


def _validate_execution_dependencies(
    records: Any,
    *,
    execution_claim_ids: Sequence[str],
    resolver: SourceResolver,
) -> tuple[str, ...]:
    """Require every declared execution dependency to reacquire current authority."""
    if not execution_claim_ids:
        if records not in (None, []):
            return (
                "frontier_authority.execution_lineage_records must be empty when no execution_claim_ids are declared",
            )
        return ()

    if not isinstance(records, list) or not records:
        return (
            "frontier_authority.execution_lineage_records must contain current lineage for every execution_claim_id",
        )

    errors: list[str] = []
    resolved_ids: list[str] = []
    for index, record in enumerate(records):
        prefix = f"frontier_authority.execution_lineage_records[{index}]"
        if not isinstance(record, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
        result = reconcile_execution_lineage(record, resolver=resolver)
        if result.execution_claim_id:
            resolved_ids.append(result.execution_claim_id)
        if not result.authoritative:
            errors.append(
                f"{prefix} is not currently authoritative: {result.truth_state}"
            )
            errors.extend(f"{prefix}: {error}" for error in result.errors)

    if len(resolved_ids) != len(set(resolved_ids)):
        errors.append("frontier_authority execution lineage claim ids must be unique")
    if sorted(resolved_ids) != sorted(execution_claim_ids):
        errors.append(
            "frontier_authority.execution_lineage_records must exactly match execution_claim_ids"
        )
    return tuple(dict.fromkeys(errors))



def _validate_dependency_completeness_artifact(
    artifact: Mapping[str, Any],
    *,
    resolver: SourceResolver,
    expected_frontier_id: str,
    execution_claim_ids: Sequence[str],
    operation_class: str,
    target: str,
    frontier_action: str,
) -> tuple[str, ...]:
    """Prove that the declared execution dependency set is complete, including empty sets."""
    errors: list[str] = []
    prefix = "frontier_authority.dependency_completeness_verification"
    source_bytes, resolution_error = _resolve(
        resolver, artifact.get("evidence_ref"), prefix=prefix
    )
    if resolution_error:
        return (resolution_error,)
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
        "verdict": _COMPLETE,
        "operation_class": operation_class,
        "target": target,
        "frontier_action": frontier_action,
    }
    for key, value in expected.items():
        if evidence.get(key) != value:
            errors.append(f"{prefix}.evidence.{key} must equal {value!r}")

    required_ids = evidence.get("required_execution_claim_ids")
    if not isinstance(required_ids, list) or not all(_nonempty(item) for item in required_ids):
        errors.append(
            f"{prefix}.evidence.required_execution_claim_ids must be an array of non-empty strings"
        )
    else:
        normalized_required = [str(item) for item in required_ids]
        if len(normalized_required) != len(set(normalized_required)):
            errors.append(
                f"{prefix}.evidence.required_execution_claim_ids must be unique"
            )
        if sorted(normalized_required) != sorted(execution_claim_ids):
            errors.append(
                f"{prefix}.evidence.required_execution_claim_ids proves declared execution_claim_ids are incomplete or substituted"
            )

    verifier_ref = evidence.get("verifier_ref")
    if not _nonempty(verifier_ref):
        errors.append(f"{prefix}.evidence.verifier_ref must be non-empty")
    if verifier_ref in {"frontier_receipt", "execution_receipt", "assistant_summary"}:
        errors.append(
            f"{prefix}.evidence.verifier_ref cannot self-certify dependency completeness"
        )
    return tuple(dict.fromkeys(errors))


def _validate_entailment_artifact(
    artifact: Mapping[str, Any],
    *,
    resolver: SourceResolver,
    expected_frontier_id: str,
    proposition_ids: Sequence[str],
    execution_claim_ids: Sequence[str],
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
    evidence_execution_ids = evidence.get("execution_claim_ids", [])
    if not isinstance(evidence_execution_ids, list) or sorted(evidence_execution_ids) != sorted(
        execution_claim_ids
    ):
        errors.append(
            f"{prefix}.evidence.execution_claim_ids must exactly match bound execution dependencies"
        )
    verifier_ref = evidence.get("verifier_ref")
    if not _nonempty(verifier_ref):
        errors.append(f"{prefix}.evidence.verifier_ref must be non-empty")
    if verifier_ref == "frontier_receipt":
        errors.append(
            f"{prefix}.evidence.verifier_ref cannot self-certify from frontier receipt"
        )
    return tuple(errors)


def validate_executable_frontier_authority(
    receipt: Mapping[str, Any], *, resolver: SourceResolver
) -> FrontierAuthorizationResult:
    """Authorize a frontier only from current source and execution evidence."""
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

    execution_claim_ids_raw = row.get("execution_claim_ids", [])
    if not isinstance(execution_claim_ids_raw, list) or not all(
        _nonempty(item) for item in execution_claim_ids_raw
    ):
        errors.append(
            "frontier_authority.execution_claim_ids must be an array of non-empty strings"
        )
        execution_claim_ids: list[str] = []
    else:
        execution_claim_ids = [str(item) for item in execution_claim_ids_raw]
        if len(execution_claim_ids) != len(set(execution_claim_ids)):
            errors.append("frontier_authority execution_claim_ids must be unique")

    errors.extend(
        _validate_execution_dependencies(
            row.get("execution_lineage_records"),
            execution_claim_ids=execution_claim_ids,
            resolver=resolver,
        )
    )

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
            execution_claim_ids=execution_claim_ids,
        )
        if row.get("frontier_id") != expected_frontier_id:
            errors.append(
                "frontier_authority.frontier_id is not bound to material frontier inputs"
            )
        if row.get("continuation_ref") != expected_frontier_id:
            errors.append(
                "frontier_authority.continuation_ref must equal the derived frontier_id"
            )

    completeness = row.get("dependency_completeness_verification")
    if not isinstance(completeness, Mapping):
        errors.append(
            "frontier_authority.dependency_completeness_verification must contain independent evidence"
        )
    elif expected_frontier_id:
        errors.extend(
            _validate_dependency_completeness_artifact(
                completeness,
                resolver=resolver,
                expected_frontier_id=expected_frontier_id,
                execution_claim_ids=execution_claim_ids,
                operation_class=str(operation_class),
                target=str(target),
                frontier_action=str(frontier_action),
            )
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
                    expected_frontier_id=expected_frontier_id,
                    proposition_ids=proposition_ids,
                    execution_claim_ids=execution_claim_ids,
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
