from __future__ import annotations

import hashlib
import json
from unittest.mock import patch

from executable_frontier_authority import FrontierAuthorizationResult
from strict_executable_frontier_authority import validate_strict_executable_frontier_authority
from verifier_identity_authority import derive_content_addressed_verifier_ref


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _resolver(sources: dict[str, bytes]):
    def resolve(ref: str) -> bytes:
        return sources[ref]
    return resolve


def _input_refs_digest(refs: list[str]) -> str:
    return _sha256(json.dumps(sorted(refs), separators=(",", ":")).encode())


def _receipt_and_sources():
    frontier_id = "frontier:strict-test"
    claim_ids = ["execution:alpha", "execution:beta"]
    inputs = {
        "provider:history": b'{"verified":["execution:alpha"]}',
        "source:continuation": b'{"depends_on":["execution:beta"]}',
    }
    collector_ref = "independent:material-input-collector:v1"
    manifest_ref = "evidence:material-input-manifest"
    manifest = {
        "frontier_id": frontier_id,
        "collector_ref": collector_ref,
        "input_refs": sorted(inputs),
    }
    manifest_bytes = json.dumps(
        manifest, sort_keys=True, separators=(",", ":")
    ).encode()
    manifest_sha256 = _sha256(manifest_bytes)
    evidence = {
        "frontier_id": frontier_id,
        "enumerator_ref": "independent:dependency-enumerator:v1",
        "enumerator_version": "1",
        "input_manifest_ref": manifest_ref,
        "input_manifest_sha256": manifest_sha256,
        "input_refs": sorted(inputs),
        "input_sha256": {ref: _sha256(payload) for ref, payload in inputs.items()},
        "candidate_execution_claim_ids": claim_ids,
    }
    encoded = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()

    verifier_implementation_ref = "implementation:collector-attestation-verifier:v1"
    verifier_implementation = b"collector-attestation-verifier implementation v1\n"
    verifier_ref = derive_content_addressed_verifier_ref(verifier_implementation)
    attestation = {
        "frontier_id": frontier_id,
        "collector_ref": collector_ref,
        "input_manifest_ref": manifest_ref,
        "input_manifest_sha256": manifest_sha256,
        "input_refs_sha256": _input_refs_digest(list(inputs)),
        "verdict": "collector_verified",
        "verifier_ref": verifier_ref,
    }
    attestation_bytes = json.dumps(
        attestation, sort_keys=True, separators=(",", ":")
    ).encode()
    verifier_identity = {
        "frontier_id": frontier_id,
        "identity_scheme": "sha256-content-addressed",
        "verdict": "verifier_identity_verified",
        "verifier_ref": verifier_ref,
        "verifier_implementation_ref": verifier_implementation_ref,
        "verifier_implementation_sha256": _sha256(verifier_implementation),
    }
    verifier_identity_bytes = json.dumps(
        verifier_identity, sort_keys=True, separators=(",", ":")
    ).encode()

    sources = dict(inputs)
    sources[manifest_ref] = manifest_bytes
    sources["evidence:dependency-enumeration"] = encoded
    sources["evidence:collector-attestation"] = attestation_bytes
    sources[verifier_implementation_ref] = verifier_implementation
    sources["evidence:verifier-identity"] = verifier_identity_bytes
    receipt = {
        "frontier_authority": {
            "frontier_id": frontier_id,
            "execution_claim_ids": claim_ids,
            "dependency_enumeration": {
                "evidence_ref": "evidence:dependency-enumeration",
                "evidence_sha256": _sha256(encoded),
            },
            "material_input_collector_attestation": {
                "evidence_ref": "evidence:collector-attestation",
                "evidence_sha256": _sha256(attestation_bytes),
            },
            "verifier_identity_attestation": {
                "evidence_ref": "evidence:verifier-identity",
                "evidence_sha256": _sha256(verifier_identity_bytes),
            },
        }
    }
    return receipt, sources


def _base_authorized(*args, **kwargs):
    return FrontierAuthorizationResult(True, "frontier_authorized", ())


def _validate(receipt: dict, sources: dict[str, bytes]):
    with patch("strict_executable_frontier_authority.validate_executable_frontier_authority", _base_authorized):
        return validate_strict_executable_frontier_authority(
            receipt, resolver=_resolver(sources)
        )


def test_strict_authority_requires_verified_enumeration_collector_and_verifier_identity() -> None:
    receipt, sources = _receipt_and_sources()
    result = _validate(receipt, sources)
    assert result.ok is True
    assert result.status == "frontier_authorized"


def test_missing_enumeration_fails_closed() -> None:
    receipt, sources = _receipt_and_sources()
    del receipt["frontier_authority"]["dependency_enumeration"]
    result = _validate(receipt, sources)
    assert result.ok is False
    assert any("dependency_enumeration" in error for error in result.errors)


def test_missing_collector_attestation_fails_closed() -> None:
    receipt, sources = _receipt_and_sources()
    del receipt["frontier_authority"]["material_input_collector_attestation"]
    result = _validate(receipt, sources)
    assert result.ok is False
    assert any("must contain independent evidence" in error for error in result.errors)


def test_missing_verifier_identity_attestation_fails_closed() -> None:
    receipt, sources = _receipt_and_sources()
    del receipt["frontier_authority"]["verifier_identity_attestation"]
    result = _validate(receipt, sources)
    assert result.ok is False
    assert any("verifier_identity_attestation" in error for error in result.errors)


def test_omitted_claim_rejected_after_base_authority_passes() -> None:
    receipt, sources = _receipt_and_sources()
    receipt["frontier_authority"]["execution_claim_ids"] = ["execution:alpha"]
    result = _validate(receipt, sources)
    assert result.ok is False
    assert any("incomplete or substituted" in error for error in result.errors)


def test_input_readback_failure_stays_unresolved() -> None:
    receipt, sources = _receipt_and_sources()
    del sources["source:continuation"]
    result = _validate(receipt, sources)
    assert result.ok is False
    assert any("readback unresolved" in error for error in result.errors)


def test_material_input_manifest_readback_failure_stays_unresolved() -> None:
    receipt, sources = _receipt_and_sources()
    del sources["evidence:material-input-manifest"]
    result = _validate(receipt, sources)
    assert result.ok is False
    assert any("readback unresolved" in error for error in result.errors)


def test_collector_attestation_readback_failure_stays_unresolved() -> None:
    receipt, sources = _receipt_and_sources()
    del sources["evidence:collector-attestation"]
    result = _validate(receipt, sources)
    assert result.ok is False
    assert any("readback unresolved" in error for error in result.errors)


def test_verifier_implementation_readback_failure_stays_unresolved() -> None:
    receipt, sources = _receipt_and_sources()
    del sources["implementation:collector-attestation-verifier:v1"]
    result = _validate(receipt, sources)
    assert result.ok is False
    assert any("verifier_implementation" in error and "readback unresolved" in error for error in result.errors)


def test_manifest_cannot_swap_collector_identity_after_attestation() -> None:
    receipt, sources = _receipt_and_sources()
    manifest = json.loads(sources["evidence:material-input-manifest"].decode())
    manifest["collector_ref"] = "fabricated:collector"
    manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    sources["evidence:material-input-manifest"] = manifest_bytes
    evidence = json.loads(sources["evidence:dependency-enumeration"].decode())
    evidence["input_manifest_sha256"] = _sha256(manifest_bytes)
    encoded = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    sources["evidence:dependency-enumeration"] = encoded
    receipt["frontier_authority"]["dependency_enumeration"]["evidence_sha256"] = _sha256(encoded)
    result = _validate(receipt, sources)
    assert result.ok is False
    assert any("collector_ref" in error for error in result.errors)


def test_collector_cannot_self_certify_its_attestation() -> None:
    receipt, sources = _receipt_and_sources()
    attestation = json.loads(sources["evidence:collector-attestation"].decode())
    attestation["verifier_ref"] = attestation["collector_ref"]
    encoded = json.dumps(attestation, sort_keys=True, separators=(",", ":")).encode()
    sources["evidence:collector-attestation"] = encoded
    receipt["frontier_authority"]["material_input_collector_attestation"]["evidence_sha256"] = _sha256(encoded)
    result = _validate(receipt, sources)
    assert result.ok is False
    assert any("cannot self-certify collector authority" in error for error in result.errors)


def test_fabricated_independent_verifier_label_cannot_authorize() -> None:
    receipt, sources = _receipt_and_sources()
    attestation = json.loads(sources["evidence:collector-attestation"].decode())
    attestation["verifier_ref"] = "independent:totally-fabricated-verifier:v99"
    encoded = json.dumps(attestation, sort_keys=True, separators=(",", ":")).encode()
    sources["evidence:collector-attestation"] = encoded
    receipt["frontier_authority"]["material_input_collector_attestation"]["evidence_sha256"] = _sha256(encoded)
    result = _validate(receipt, sources)
    assert result.ok is False
    assert any("not bound to resolved verifier implementation bytes" in error for error in result.errors)


def test_verifier_identity_cannot_substitute_implementation_hash() -> None:
    receipt, sources = _receipt_and_sources()
    identity = json.loads(sources["evidence:verifier-identity"].decode())
    identity["verifier_implementation_sha256"] = "sha256:" + "0" * 64
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    sources["evidence:verifier-identity"] = encoded
    receipt["frontier_authority"]["verifier_identity_attestation"]["evidence_sha256"] = _sha256(encoded)
    result = _validate(receipt, sources)
    assert result.ok is False
    assert any("verifier_implementation_sha256" in error for error in result.errors)


def test_base_authority_failure_is_preserved() -> None:
    receipt, sources = _receipt_and_sources()
    base_failure = FrontierAuthorizationResult(
        False, "frontier_authorization_unresolved", ("source span unresolved",)
    )
    with patch(
        "strict_executable_frontier_authority.validate_executable_frontier_authority",
        return_value=base_failure,
    ):
        result = validate_strict_executable_frontier_authority(
            receipt, resolver=_resolver(sources)
        )
    assert result is base_failure
