from __future__ import annotations

import hashlib
import json

from execution_dependency_enumerator_authority import validate_dependency_enumeration


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _resolver(sources: dict[str, bytes]):
    def resolve(ref: str) -> bytes:
        return sources[ref]

    return resolve


def _fixture(claim_ids: list[str] | None = None):
    claim_ids = claim_ids or ["execution:alpha", "execution:beta"]
    inputs = {
        "provider:history": b'{"verified":["execution:alpha"]}',
        "source:continuation": b'{"depends_on":["execution:beta"]}',
    }
    manifest = {
        "frontier_id": "frontier:test",
        "collector_ref": "independent:material-input-collector:v1",
        "input_refs": sorted(inputs),
    }
    manifest_bytes = json.dumps(
        manifest, sort_keys=True, separators=(",", ":")
    ).encode()
    evidence = {
        "frontier_id": "frontier:test",
        "enumerator_ref": "independent:dependency-enumerator:v1",
        "enumerator_version": "1",
        "input_manifest_ref": "evidence:material-input-manifest",
        "input_manifest_sha256": _sha256(manifest_bytes),
        "input_refs": sorted(inputs),
        "input_sha256": {ref: _sha256(payload) for ref, payload in inputs.items()},
        "candidate_execution_claim_ids": claim_ids,
    }
    evidence_bytes = json.dumps(
        evidence, sort_keys=True, separators=(",", ":")
    ).encode()
    sources = dict(inputs)
    sources["evidence:material-input-manifest"] = manifest_bytes
    sources["evidence:dependency-enumeration"] = evidence_bytes
    artifact = {
        "evidence_ref": "evidence:dependency-enumeration",
        "evidence_sha256": _sha256(evidence_bytes),
    }
    return artifact, sources, claim_ids


def _rewrite_evidence(artifact: dict, sources: dict[str, bytes], **updates) -> None:
    evidence = json.loads(sources["evidence:dependency-enumeration"].decode())
    evidence.update(updates)
    encoded = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    sources["evidence:dependency-enumeration"] = encoded
    artifact["evidence_sha256"] = _sha256(encoded)


def _rewrite_manifest(sources: dict[str, bytes], **updates) -> None:
    manifest = json.loads(sources["evidence:material-input-manifest"].decode())
    manifest.update(updates)
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    sources["evidence:material-input-manifest"] = encoded
    evidence = json.loads(sources["evidence:dependency-enumeration"].decode())
    evidence["input_manifest_sha256"] = _sha256(encoded)
    evidence_bytes = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    sources["evidence:dependency-enumeration"] = evidence_bytes


def test_verified_enumeration_requires_independent_hashed_inputs() -> None:
    artifact, sources, claim_ids = _fixture()
    result = validate_dependency_enumeration(
        artifact,
        resolver=_resolver(sources),
        expected_frontier_id="frontier:test",
        declared_execution_claim_ids=claim_ids,
    )
    assert result.ok is True
    assert result.status == "DEPENDENCY_ENUMERATION_VERIFIED"
    assert result.required_execution_claim_ids == (
        "execution:alpha",
        "execution:beta",
    )


def test_omitted_execution_dependency_is_rejected() -> None:
    artifact, sources, claim_ids = _fixture()
    result = validate_dependency_enumeration(
        artifact,
        resolver=_resolver(sources),
        expected_frontier_id="frontier:test",
        declared_execution_claim_ids=[claim_ids[0]],
    )
    assert result.ok is False
    assert any("incomplete or substituted" in error for error in result.errors)


def test_enumerator_cannot_hide_dependency_present_in_resolved_inputs() -> None:
    artifact, sources, _ = _fixture()
    _rewrite_evidence(
        artifact,
        sources,
        candidate_execution_claim_ids=["execution:alpha"],
    )
    result = validate_dependency_enumeration(
        artifact,
        resolver=_resolver(sources),
        expected_frontier_id="frontier:test",
        declared_execution_claim_ids=["execution:alpha"],
    )
    assert result.ok is False
    assert result.required_execution_claim_ids == (
        "execution:alpha",
        "execution:beta",
    )
    assert any("deterministically derived" in error for error in result.errors)
    assert any("incomplete or substituted" in error for error in result.errors)


def test_enumerator_cannot_invent_dependency_absent_from_resolved_inputs() -> None:
    artifact, sources, _ = _fixture()
    forged = ["execution:alpha", "execution:beta", "execution:invented"]
    _rewrite_evidence(
        artifact,
        sources,
        candidate_execution_claim_ids=forged,
    )
    result = validate_dependency_enumeration(
        artifact,
        resolver=_resolver(sources),
        expected_frontier_id="frontier:test",
        declared_execution_claim_ids=forged,
    )
    assert result.ok is False
    assert result.required_execution_claim_ids == (
        "execution:alpha",
        "execution:beta",
    )
    assert any("deterministically derived" in error for error in result.errors)


def test_retrieval_failure_is_unresolved_not_absence() -> None:
    artifact, sources, claim_ids = _fixture()
    del sources["source:continuation"]
    result = validate_dependency_enumeration(
        artifact,
        resolver=_resolver(sources),
        expected_frontier_id="frontier:test",
        declared_execution_claim_ids=claim_ids,
    )
    assert result.ok is False
    assert any("readback unresolved" in error for error in result.errors)


def test_non_json_input_cannot_be_used_for_semantic_dependency_discovery() -> None:
    artifact, sources, claim_ids = _fixture()
    sources["source:continuation"] = b"depends on execution:beta"
    evidence = json.loads(sources["evidence:dependency-enumeration"].decode())
    evidence["input_sha256"]["source:continuation"] = _sha256(
        sources["source:continuation"]
    )
    encoded = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    sources["evidence:dependency-enumeration"] = encoded
    artifact["evidence_sha256"] = _sha256(encoded)
    result = validate_dependency_enumeration(
        artifact,
        resolver=_resolver(sources),
        expected_frontier_id="frontier:test",
        declared_execution_claim_ids=claim_ids,
    )
    assert result.ok is False
    assert any("UTF-8 JSON" in error for error in result.errors)


def test_tampered_input_invalidates_enumeration() -> None:
    artifact, sources, claim_ids = _fixture()
    sources["provider:history"] += b"tamper"
    result = validate_dependency_enumeration(
        artifact,
        resolver=_resolver(sources),
        expected_frontier_id="frontier:test",
        declared_execution_claim_ids=claim_ids,
    )
    assert result.ok is False
    assert any("does not match resolved bytes" in error for error in result.errors)


def test_frontier_or_receipt_cannot_self_certify_enumeration() -> None:
    artifact, sources, claim_ids = _fixture()
    _rewrite_evidence(artifact, sources, enumerator_ref="frontier_receipt")
    result = validate_dependency_enumeration(
        artifact,
        resolver=_resolver(sources),
        expected_frontier_id="frontier:test",
        declared_execution_claim_ids=claim_ids,
    )
    assert result.ok is False
    assert any("cannot self-certify" in error for error in result.errors)


def test_enumeration_is_bound_to_exact_frontier_identity() -> None:
    artifact, sources, claim_ids = _fixture()
    result = validate_dependency_enumeration(
        artifact,
        resolver=_resolver(sources),
        expected_frontier_id="frontier:different",
        declared_execution_claim_ids=claim_ids,
    )
    assert result.ok is False
    assert any("frontier_id" in error for error in result.errors)


def test_enumerator_cannot_silently_drop_an_entire_manifested_input() -> None:
    artifact, sources, _ = _fixture()
    evidence = json.loads(sources["evidence:dependency-enumeration"].decode())
    evidence["input_refs"] = ["provider:history"]
    evidence["input_sha256"] = {
        "provider:history": evidence["input_sha256"]["provider:history"]
    }
    evidence["candidate_execution_claim_ids"] = ["execution:alpha"]
    encoded = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    sources["evidence:dependency-enumeration"] = encoded
    artifact["evidence_sha256"] = _sha256(encoded)
    result = validate_dependency_enumeration(
        artifact,
        resolver=_resolver(sources),
        expected_frontier_id="frontier:test",
        declared_execution_claim_ids=["execution:alpha"],
    )
    assert result.ok is False
    assert any("input_refs must exactly match" in error for error in result.errors)


def test_manifest_readback_failure_is_unresolved_not_empty_input_universe() -> None:
    artifact, sources, claim_ids = _fixture()
    del sources["evidence:material-input-manifest"]
    result = validate_dependency_enumeration(
        artifact,
        resolver=_resolver(sources),
        expected_frontier_id="frontier:test",
        declared_execution_claim_ids=claim_ids,
    )
    assert result.ok is False
    assert any("readback unresolved" in error for error in result.errors)


def test_manifest_cannot_self_certify_material_input_discovery() -> None:
    artifact, sources, claim_ids = _fixture()
    _rewrite_manifest(sources, collector_ref="dependency_enumeration")
    artifact["evidence_sha256"] = _sha256(
        sources["evidence:dependency-enumeration"]
    )
    result = validate_dependency_enumeration(
        artifact,
        resolver=_resolver(sources),
        expected_frontier_id="frontier:test",
        declared_execution_claim_ids=claim_ids,
    )
    assert result.ok is False
    assert any("cannot self-certify material input discovery" in error for error in result.errors)
