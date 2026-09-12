from __future__ import annotations

import hashlib
import json

from execution_evidence_authority import (
    derive_execution_claim_id,
    validate_execution_evidence,
)


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _fixture() -> tuple[dict, dict[str, bytes]]:
    provider = "github"
    provider_object_ref = "github:GlacierEQ/apex-control-plane:commit:abc123"
    source_sha = "abc123"
    operation = "merge_pull_request"
    claim_id = derive_execution_claim_id(
        provider=provider,
        provider_object_ref=provider_object_ref,
        source_sha=source_sha,
        operation=operation,
    )
    evidence = {
        "provider": provider,
        "provider_object_ref": provider_object_ref,
        "source_sha": source_sha,
        "operation": operation,
        "execution_claim_id": claim_id,
        "state": "VERIFIED",
        "readback_verified": True,
        "verifier_ref": "github-api:commit-readback",
    }
    evidence_bytes = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    sources = {"provider:github:commit:abc123": evidence_bytes}
    claim = {
        "execution_claim_id": claim_id,
        "provider": provider,
        "provider_object_ref": provider_object_ref,
        "source_sha": source_sha,
        "operation": operation,
        "state": "VERIFIED",
        "evidence_kind": "provider_api_readback",
        "evidence_ref": "provider:github:commit:abc123",
        "evidence_sha256": _sha256(evidence_bytes),
    }
    return claim, sources


def _resolver(sources: dict[str, bytes]):
    def resolve(ref: str) -> bytes:
        return sources[ref]
    return resolve


def test_verified_claim_requires_independent_provider_bytes() -> None:
    claim, sources = _fixture()
    result = validate_execution_evidence(claim, resolver=_resolver(sources))
    assert result.ok is True
    assert result.status == "execution_evidence_verified"


def test_assistant_summary_cannot_prove_execution() -> None:
    claim, sources = _fixture()
    claim["evidence_kind"] = "assistant_summary"
    result = validate_execution_evidence(claim, resolver=_resolver(sources))
    assert result.ok is False
    assert any("derivative" in error for error in result.errors)


def test_tampered_provider_bytes_fail_hash_check() -> None:
    claim, sources = _fixture()
    sources[claim["evidence_ref"]] += b"\n"
    result = validate_execution_evidence(claim, resolver=_resolver(sources))
    assert result.ok is False
    assert any("evidence_sha256" in error for error in result.errors)


def test_missing_provider_readback_is_unresolved_not_absence() -> None:
    claim, _ = _fixture()
    result = validate_execution_evidence(claim, resolver=lambda ref: (_ for _ in ()).throw(FileNotFoundError(ref)))
    assert result.ok is False
    assert result.status == "provider_readback_unresolved"


def test_source_sha_substitution_changes_claim_identity() -> None:
    claim, sources = _fixture()
    claim["source_sha"] = "different"
    result = validate_execution_evidence(claim, resolver=_resolver(sources))
    assert result.ok is False
    assert any("execution_claim_id" in error for error in result.errors)


def test_execution_receipt_cannot_self_certify() -> None:
    claim, sources = _fixture()
    claim["evidence_kind"] = "execution_receipt"
    result = validate_execution_evidence(claim, resolver=_resolver(sources))
    assert result.ok is False
    assert any("derivative" in error for error in result.errors)
