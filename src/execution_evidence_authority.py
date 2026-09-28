"""Independent authority boundary for execution and provider-readback claims.

An execution receipt may route retrieval, but it cannot prove its own execution.
Provider evidence must be independently resolved, byte-hashed, identity-bound, and
reconciled with the exact source state before EXECUTED/VERIFIED claims are trusted.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

EvidenceResolver = Callable[[str], bytes]

DERIVATIVE_EVIDENCE_KINDS = {
    "assistant_summary", "memory_summary", "profile_summary", "working_model",
    "manifest", "index", "checkpoint", "execution_receipt",
}
VERIFIED_STATES = {"VERIFIED", "COMMITTED", "DEPLOYED", "OBSERVED_IN_OPERATION"}
EXECUTED_STATES = {"EXECUTED", *VERIFIED_STATES}


@dataclass(frozen=True, slots=True)
class ExecutionEvidenceResult:
    ok: bool
    status: str
    errors: tuple[str, ...]


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def derive_execution_claim_id(*, provider: str, provider_object_ref: str, source_sha: str, operation: str) -> str:
    payload = json.dumps(
        {"operation": operation, "provider": provider, "provider_object_ref": provider_object_ref, "source_sha": source_sha},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return "execution:" + hashlib.sha256(payload).hexdigest()


def _resolve(resolver: EvidenceResolver, ref: Any, prefix: str) -> tuple[bytes | None, str | None]:
    if not _nonempty(ref):
        return None, f"{prefix}.evidence_ref must be non-empty"
    try:
        data = resolver(str(ref))
    except Exception as exc:  # fail closed at provider/readback boundary
        return None, f"{prefix}.provider readback unresolved: {exc.__class__.__name__}"
    if not isinstance(data, bytes):
        return None, f"{prefix}.resolver must return bytes"
    return data, None


def validate_execution_evidence(claim: Mapping[str, Any], *, resolver: EvidenceResolver) -> ExecutionEvidenceResult:
    """Validate one execution claim against independently resolved provider evidence."""
    errors: list[str] = []
    provider = claim.get("provider")
    provider_object_ref = claim.get("provider_object_ref")
    source_sha = claim.get("source_sha")
    operation = claim.get("operation")
    state = str(claim.get("state", "")).strip().upper()
    evidence_kind = str(claim.get("evidence_kind", "")).strip().lower()

    for name, value in (("provider", provider), ("provider_object_ref", provider_object_ref), ("source_sha", source_sha), ("operation", operation)):
        if not _nonempty(value):
            errors.append(f"execution_evidence.{name} must be non-empty")
    if state not in EXECUTED_STATES:
        errors.append("execution_evidence.state must be EXECUTED-or-stronger")
    if evidence_kind in DERIVATIVE_EVIDENCE_KINDS:
        errors.append("execution_evidence.evidence_kind is derivative and cannot prove execution")

    expected_id = ""
    if all(_nonempty(v) for v in (provider, provider_object_ref, source_sha, operation)):
        expected_id = derive_execution_claim_id(
            provider=str(provider), provider_object_ref=str(provider_object_ref),
            source_sha=str(source_sha), operation=str(operation),
        )
        if claim.get("execution_claim_id") != expected_id:
            errors.append("execution_evidence.execution_claim_id is not bound to provider object and source state")

    evidence_bytes, resolution_error = _resolve(resolver, claim.get("evidence_ref"), "execution_evidence")
    if resolution_error:
        errors.append(resolution_error)
    else:
        assert evidence_bytes is not None
        if claim.get("evidence_sha256") != _sha256(evidence_bytes):
            errors.append("execution_evidence.evidence_sha256 does not match independently resolved bytes")
        try:
            evidence = json.loads(evidence_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            errors.append("execution_evidence.evidence_ref must resolve to UTF-8 JSON")
            evidence = None
        if isinstance(evidence, Mapping):
            expected = {
                "provider": provider,
                "provider_object_ref": provider_object_ref,
                "source_sha": source_sha,
                "operation": operation,
                "execution_claim_id": expected_id,
            }
            for key, value in expected.items():
                if evidence.get(key) != value:
                    errors.append(f"execution_evidence.provider_evidence.{key} does not match claim")
            observed_state = str(evidence.get("state", "")).strip().upper()
            if observed_state != state:
                errors.append("execution_evidence.provider_evidence.state does not match claim")
            if state in VERIFIED_STATES and evidence.get("readback_verified") is not True:
                errors.append("verified execution requires provider evidence with readback_verified=true")
            verifier_ref = evidence.get("verifier_ref")
            if not _nonempty(verifier_ref):
                errors.append("execution_evidence.provider_evidence.verifier_ref must be non-empty")
            if verifier_ref in {claim.get("evidence_ref"), "execution_receipt", "self"}:
                errors.append("execution evidence cannot self-certify its provider readback")

    if errors:
        status = "provider_readback_unresolved" if any("readback unresolved" in e for e in errors) else "execution_evidence_rejected"
        return ExecutionEvidenceResult(False, status, tuple(dict.fromkeys(errors)))
    return ExecutionEvidenceResult(True, "execution_evidence_verified", ())
