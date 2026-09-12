from __future__ import annotations

import hashlib

from dependency_basis_authority import validate_dependency_basis


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _resolver(sources: dict[str, bytes]):
    def resolve(ref: str) -> bytes:
        return sources[ref]

    return resolve


def _fixture():
    prefix = b"ignored-prefix::"
    span = b"provider execution history and source-bound frontier inputs"
    suffix = b"::ignored-suffix"
    payload = prefix + span + suffix
    start = len(prefix)
    end = start + len(span)
    sources = {"basis:provider-history": payload}
    evidence = {
        "verifier_ref": "independent:dependency-discovery",
        "dependency_basis": [
            {
                "basis_id": "basis:provider-history:material-state",
                "source_ref": "basis:provider-history",
                "source_kind": "provider_readback",
                "source_sha256": _sha256(payload),
                "span_start_byte": start,
                "span_end_byte": end,
                "span_sha256": _sha256(span),
                "temporal_context": "provider state at frontier selection",
                "contradiction_state": "active",
                "superseded_by": None,
                "verification_state": "source_resolved",
            }
        ],
    }
    return evidence, sources


def test_independently_resolved_span_bound_basis_is_authoritative() -> None:
    evidence, sources = _fixture()
    result = validate_dependency_basis(evidence, resolver=_resolver(sources))
    assert result.authoritative is True
    assert result.status == "DEPENDENCY_BASIS_VERIFIED"


def test_missing_basis_cannot_self_assert_completeness() -> None:
    evidence, sources = _fixture()
    evidence["dependency_basis"] = []
    result = validate_dependency_basis(evidence, resolver=_resolver(sources))
    assert result.authoritative is False


def test_derivative_summary_cannot_be_dependency_basis() -> None:
    evidence, sources = _fixture()
    evidence["dependency_basis"][0]["source_kind"] = "assistant_summary"
    result = validate_dependency_basis(evidence, resolver=_resolver(sources))
    assert result.authoritative is False
    assert any("derivative" in error for error in result.errors)


def test_basis_hash_mismatch_fails_closed() -> None:
    evidence, sources = _fixture()
    evidence["dependency_basis"][0]["source_sha256"] = "sha256:deadbeef"
    result = validate_dependency_basis(evidence, resolver=_resolver(sources))
    assert result.authoritative is False
    assert any("source_sha256" in error for error in result.errors)


def test_span_hash_mismatch_fails_closed() -> None:
    evidence, sources = _fixture()
    evidence["dependency_basis"][0]["span_sha256"] = "sha256:deadbeef"
    result = validate_dependency_basis(evidence, resolver=_resolver(sources))
    assert result.authoritative is False
    assert any("span_sha256" in error for error in result.errors)


def test_span_bounds_cannot_escape_resolved_source() -> None:
    evidence, sources = _fixture()
    evidence["dependency_basis"][0]["span_end_byte"] = 100000
    result = validate_dependency_basis(evidence, resolver=_resolver(sources))
    assert result.authoritative is False
    assert any("exceeds independently resolved source length" in error for error in result.errors)


def test_basis_readback_failure_is_unresolved_not_absence() -> None:
    evidence, sources = _fixture()
    del sources["basis:provider-history"]
    result = validate_dependency_basis(evidence, resolver=_resolver(sources))
    assert result.authoritative is False
    assert result.status == "DEPENDENCY_BASIS_UNRESOLVED"
    assert any("readback unresolved" in error for error in result.errors)


def test_superseded_basis_cannot_remain_authoritative() -> None:
    evidence, sources = _fixture()
    evidence["dependency_basis"][0]["contradiction_state"] = "superseded"
    evidence["dependency_basis"][0]["superseded_by"] = "basis:newer-provider-state"
    result = validate_dependency_basis(evidence, resolver=_resolver(sources))
    assert result.authoritative is False
    assert any("contradiction_state" in error for error in result.errors)
    assert any("superseded_by" in error for error in result.errors)


def test_missing_temporal_context_is_rejected() -> None:
    evidence, sources = _fixture()
    evidence["dependency_basis"][0]["temporal_context"] = ""
    result = validate_dependency_basis(evidence, resolver=_resolver(sources))
    assert result.authoritative is False
    assert any("temporal_context" in error for error in result.errors)


def test_duplicate_basis_identity_is_rejected() -> None:
    evidence, sources = _fixture()
    duplicate = dict(evidence["dependency_basis"][0])
    duplicate["source_ref"] = "basis:provider-history-copy"
    sources["basis:provider-history-copy"] = sources["basis:provider-history"]
    evidence["dependency_basis"].append(duplicate)
    result = validate_dependency_basis(evidence, resolver=_resolver(sources))
    assert result.authoritative is False
    assert any("basis_id must be unique" in error for error in result.errors)


def test_receipt_cannot_verify_its_own_basis() -> None:
    evidence, sources = _fixture()
    evidence["verifier_ref"] = "frontier_receipt"
    result = validate_dependency_basis(evidence, resolver=_resolver(sources))
    assert result.authoritative is False
    assert any("self-certify" in error for error in result.errors)
