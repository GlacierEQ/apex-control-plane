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
    payload = b"provider execution history and source-bound frontier inputs"
    sources = {"basis:provider-history": payload}
    evidence = {
        "verifier_ref": "independent:dependency-discovery",
        "dependency_basis": [
            {
                "source_ref": "basis:provider-history",
                "source_kind": "provider_readback",
                "source_sha256": _sha256(payload),
            }
        ],
    }
    return evidence, sources


def test_independently_resolved_basis_is_authoritative() -> None:
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


def test_basis_readback_failure_is_unresolved_not_absence() -> None:
    evidence, sources = _fixture()
    del sources["basis:provider-history"]
    result = validate_dependency_basis(evidence, resolver=_resolver(sources))
    assert result.authoritative is False
    assert result.status == "DEPENDENCY_BASIS_UNRESOLVED"
    assert any("readback unresolved" in error for error in result.errors)


def test_receipt_cannot_verify_its_own_basis() -> None:
    evidence, sources = _fixture()
    evidence["verifier_ref"] = "frontier_receipt"
    result = validate_dependency_basis(evidence, resolver=_resolver(sources))
    assert result.authoritative is False
    assert any("self-certify" in error for error in result.errors)
