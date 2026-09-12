from __future__ import annotations

import hashlib
import json
from unittest.mock import patch

from executable_frontier_authority import FrontierAuthorizationResult
from strict_executable_frontier_authority import validate_strict_executable_frontier_authority


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _resolver(sources: dict[str, bytes]):
    def resolve(ref: str) -> bytes:
        return sources[ref]
    return resolve


def _receipt_and_sources():
    frontier_id = "frontier:strict-test"
    claim_ids = ["execution:alpha", "execution:beta"]
    inputs = {
        "provider:history": b'{"verified":["execution:alpha"]}',
        "source:continuation": b'{"depends_on":["execution:beta"]}',
    }
    manifest = {
        "frontier_id": frontier_id,
        "collector_ref": "independent:material-input-collector:v1",
        "input_refs": sorted(inputs),
    }
    manifest_bytes = json.dumps(
        manifest, sort_keys=True, separators=(",", ":")
    ).encode()
    evidence = {
        "frontier_id": frontier_id,
        "enumerator_ref": "independent:dependency-enumerator:v1",
        "enumerator_version": "1",
        "input_manifest_ref": "evidence:material-input-manifest",
        "input_manifest_sha256": _sha256(manifest_bytes),
        "input_refs": sorted(inputs),
        "input_sha256": {ref: _sha256(payload) for ref, payload in inputs.items()},
        "candidate_execution_claim_ids": claim_ids,
    }
    encoded = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    sources = dict(inputs)
    sources["evidence:material-input-manifest"] = manifest_bytes
    sources["evidence:dependency-enumeration"] = encoded
    receipt = {
        "frontier_authority": {
            "frontier_id": frontier_id,
            "execution_claim_ids": claim_ids,
            "dependency_enumeration": {
                "evidence_ref": "evidence:dependency-enumeration",
                "evidence_sha256": _sha256(encoded),
            },
        }
    }
    return receipt, sources


def _base_authorized(*args, **kwargs):
    return FrontierAuthorizationResult(True, "frontier_authorized", ())


def test_strict_authority_requires_verified_enumeration() -> None:
    receipt, sources = _receipt_and_sources()
    with patch("strict_executable_frontier_authority.validate_executable_frontier_authority", _base_authorized):
        result = validate_strict_executable_frontier_authority(
            receipt, resolver=_resolver(sources)
        )
    assert result.ok is True
    assert result.status == "frontier_authorized"


def test_missing_enumeration_fails_closed() -> None:
    receipt, sources = _receipt_and_sources()
    del receipt["frontier_authority"]["dependency_enumeration"]
    with patch("strict_executable_frontier_authority.validate_executable_frontier_authority", _base_authorized):
        result = validate_strict_executable_frontier_authority(
            receipt, resolver=_resolver(sources)
        )
    assert result.ok is False
    assert any("dependency_enumeration" in error for error in result.errors)


def test_omitted_claim_rejected_after_base_authority_passes() -> None:
    receipt, sources = _receipt_and_sources()
    receipt["frontier_authority"]["execution_claim_ids"] = ["execution:alpha"]
    with patch("strict_executable_frontier_authority.validate_executable_frontier_authority", _base_authorized):
        result = validate_strict_executable_frontier_authority(
            receipt, resolver=_resolver(sources)
        )
    assert result.ok is False
    assert any("incomplete or substituted" in error for error in result.errors)


def test_input_readback_failure_stays_unresolved() -> None:
    receipt, sources = _receipt_and_sources()
    del sources["source:continuation"]
    with patch("strict_executable_frontier_authority.validate_executable_frontier_authority", _base_authorized):
        result = validate_strict_executable_frontier_authority(
            receipt, resolver=_resolver(sources)
        )
    assert result.ok is False
    assert any("readback unresolved" in error for error in result.errors)


def test_material_input_manifest_readback_failure_stays_unresolved() -> None:
    receipt, sources = _receipt_and_sources()
    del sources["evidence:material-input-manifest"]
    with patch("strict_executable_frontier_authority.validate_executable_frontier_authority", _base_authorized):
        result = validate_strict_executable_frontier_authority(
            receipt, resolver=_resolver(sources)
        )
    assert result.ok is False
    assert any("readback unresolved" in error for error in result.errors)


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
