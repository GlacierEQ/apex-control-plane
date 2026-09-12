from __future__ import annotations

import hashlib
import json

from executable_frontier_authority import (
    build_entailment_attestation,
    derive_frontier_id,
    validate_executable_frontier_authority,
)


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _fixture() -> tuple[dict, dict[str, bytes], dict[str, bytes]]:
    proposition = "Continue the active architecture from the nearest valid frontier and execute, repair, code, test, compare, or otherwise advance it."
    source = (
        "Operator source before.\n" + proposition + "\nOperator source after.\n"
    ).encode("utf-8")
    start = source.index(proposition.encode("utf-8"))
    end = start + len(proposition.encode("utf-8"))
    proposition_ids = ["operator:continuity-progress:2026-09-11"]
    operation_class = "ai_architecture_continuation"
    target = "advance continuity architecture without derivative authority"
    frontier_action = "implement source-bound executable-frontier authorization"
    frontier_id = derive_frontier_id(
        operation_class=operation_class,
        target=target,
        frontier_action=frontier_action,
        proposition_ids=proposition_ids,
    )
    entailment = {
        "frontier_id": frontier_id,
        "verdict": "entailed",
        "operation_class": operation_class,
        "target": target,
        "frontier_action": frontier_action,
        "proposition_ids": proposition_ids,
        "verifier_ref": "verifier:test-entailment",
        "verification_method": "hmac-sha256",
        "verification_state": "verified",
    }
    verifier_material = b"test-entailment-verifier-material"
    entailment["attestation"] = build_entailment_attestation(
        entailment, key=verifier_material
    )
    entailment_bytes = json.dumps(
        entailment, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    sources = {
        "source:operator-current": source,
        "evidence:frontier-entailment": entailment_bytes,
    }
    receipt = {
        "frontier_authority": {
            "frontier_id": frontier_id,
            "continuation_ref": frontier_id,
            "operation_class": operation_class,
            "target": target,
            "frontier_action": frontier_action,
            "source_bindings": [
                {
                    "proposition_id": proposition_ids[0],
                    "proposition_text": proposition,
                    "source_kind": "operator_message",
                    "source_ref": "source:operator-current",
                    "source_sha256": _sha256(source),
                    "span_start_byte": start,
                    "span_end_byte": end,
                    "span_sha256": _sha256(source[start:end]),
                    "temporal_context": "2026-09-11 current Operator run",
                    "contradiction_state": "active",
                    "superseded_by": None,
                    "verification_state": "source_resolved",
                }
            ],
            "entailment_verifications": [
                {
                    "evidence_ref": "evidence:frontier-entailment",
                    "evidence_sha256": _sha256(entailment_bytes),
                }
            ],
        }
    }
    verifier_materials = {"verifier:test-entailment": verifier_material}
    return receipt, sources, verifier_materials


def _resolver(sources: dict[str, bytes]):
    def resolve(source_ref: str) -> bytes:
        return sources[source_ref]

    return resolve


def test_valid_frontier_requires_source_and_independent_entailment() -> None:
    receipt, sources, verifiers = _fixture()
    result = validate_executable_frontier_authority(
        receipt,
        resolver=_resolver(sources),
        verifier_resolver=_resolver(verifiers),
    )
    assert result.ok is True
    assert result.status == "frontier_authorized"


def test_continuation_summary_cannot_self_authorize_direction() -> None:
    receipt, sources, verifiers = _fixture()
    receipt["frontier_authority"]["source_bindings"][0]["source_kind"] = (
        "assistant_summary"
    )
    result = validate_executable_frontier_authority(
        receipt,
        resolver=_resolver(sources),
        verifier_resolver=_resolver(verifiers),
    )
    assert result.ok is False
    assert any("derivative" in error for error in result.errors)


def test_receipt_cannot_replace_source_bytes_with_matching_story() -> None:
    receipt, sources, verifiers = _fixture()
    receipt["frontier_authority"]["source_bindings"][0]["proposition_text"] = (
        "a fabricated but internally consistent summary"
    )
    result = validate_executable_frontier_authority(
        receipt,
        resolver=_resolver(sources),
        verifier_resolver=_resolver(verifiers),
    )
    assert result.ok is False
    assert any("exactly equal resolved source span" in error for error in result.errors)


def test_source_tampering_invalidates_bound_frontier() -> None:
    receipt, sources, verifiers = _fixture()
    sources["source:operator-current"] += b"tamper"
    result = validate_executable_frontier_authority(
        receipt,
        resolver=_resolver(sources),
        verifier_resolver=_resolver(verifiers),
    )
    assert result.ok is False
    assert any("source_sha256" in error for error in result.errors)


def test_superseded_proposition_cannot_authorize_frontier() -> None:
    receipt, sources, verifiers = _fixture()
    binding = receipt["frontier_authority"]["source_bindings"][0]
    binding["contradiction_state"] = "superseded"
    binding["superseded_by"] = "operator:newer-proposition"
    result = validate_executable_frontier_authority(
        receipt,
        resolver=_resolver(sources),
        verifier_resolver=_resolver(verifiers),
    )
    assert result.ok is False
    assert any("contradiction_state" in error for error in result.errors)
    assert any("superseded_by" in error for error in result.errors)


def test_retrieval_failure_remains_unresolved_not_evidence_absence() -> None:
    receipt, sources, verifiers = _fixture()
    del sources["source:operator-current"]
    result = validate_executable_frontier_authority(
        receipt,
        resolver=_resolver(sources),
        verifier_resolver=_resolver(verifiers),
    )
    assert result.ok is False
    assert result.status == "frontier_authorization_unresolved"
    assert any("source readback unresolved" in error for error in result.errors)


def test_frontier_id_detects_action_substitution() -> None:
    receipt, sources, verifiers = _fixture()
    receipt["frontier_authority"]["frontier_action"] = "write a summary instead"
    result = validate_executable_frontier_authority(
        receipt,
        resolver=_resolver(sources),
        verifier_resolver=_resolver(verifiers),
    )
    assert result.ok is False
    assert any("frontier_id is not bound" in error for error in result.errors)


def test_entailment_artifact_is_independently_resolved_and_hashed() -> None:
    receipt, sources, verifiers = _fixture()
    sources["evidence:frontier-entailment"] += b"tamper"
    result = validate_executable_frontier_authority(
        receipt,
        resolver=_resolver(sources),
        verifier_resolver=_resolver(verifiers),
    )
    assert result.ok is False
    assert any("evidence_sha256" in error for error in result.errors)


def test_frontier_receipt_cannot_be_its_own_entailment_verifier() -> None:
    receipt, sources, verifiers = _fixture()
    evidence = json.loads(sources["evidence:frontier-entailment"].decode("utf-8"))
    evidence["verifier_ref"] = "frontier_receipt"
    evidence["attestation"] = build_entailment_attestation(
        evidence, key=verifiers["verifier:test-entailment"]
    )
    evidence_bytes = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    sources["evidence:frontier-entailment"] = evidence_bytes
    receipt["frontier_authority"]["entailment_verifications"][0]["evidence_sha256"] = (
        _sha256(evidence_bytes)
    )
    result = validate_executable_frontier_authority(
        receipt,
        resolver=_resolver(sources),
        verifier_resolver=_resolver(verifiers),
    )
    assert result.ok is False
    assert any("cannot self-certify" in error for error in result.errors)


def test_rehashed_fabricated_entailment_still_fails_without_trusted_attestation() -> (
    None
):
    receipt, sources, verifiers = _fixture()
    evidence = json.loads(sources["evidence:frontier-entailment"].decode("utf-8"))
    evidence["target"] = "fabricated target"
    evidence_bytes = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    sources["evidence:frontier-entailment"] = evidence_bytes
    receipt["frontier_authority"]["entailment_verifications"][0]["evidence_sha256"] = (
        _sha256(evidence_bytes)
    )
    result = validate_executable_frontier_authority(
        receipt, resolver=_resolver(sources), verifier_resolver=_resolver(verifiers)
    )
    assert result.ok is False
    assert any(
        "target must equal" in error or "attestation" in error
        for error in result.errors
    )


def test_attestation_cannot_be_recomputed_without_independent_verifier_material() -> (
    None
):
    receipt, sources, verifiers = _fixture()
    evidence = json.loads(sources["evidence:frontier-entailment"].decode("utf-8"))
    evidence["attestation"] = build_entailment_attestation(
        evidence, key=b"receipt-controlled-material"
    )
    evidence_bytes = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    sources["evidence:frontier-entailment"] = evidence_bytes
    receipt["frontier_authority"]["entailment_verifications"][0]["evidence_sha256"] = (
        _sha256(evidence_bytes)
    )
    result = validate_executable_frontier_authority(
        receipt, resolver=_resolver(sources), verifier_resolver=_resolver(verifiers)
    )
    assert result.ok is False
    assert any("attestation does not verify" in error for error in result.errors)


def test_missing_verifier_readback_is_unresolved_not_evidence_absence() -> None:
    receipt, sources, _ = _fixture()
    result = validate_executable_frontier_authority(
        receipt, resolver=_resolver(sources), verifier_resolver=_resolver({})
    )
    assert result.ok is False
    assert result.status == "frontier_authorization_unresolved"
    assert any("verifier readback unresolved" in error for error in result.errors)


def test_derivative_verifier_identity_is_quarantined_even_with_valid_attestation() -> (
    None
):
    receipt, sources, verifiers = _fixture()
    evidence = json.loads(sources["evidence:frontier-entailment"].decode("utf-8"))
    evidence["verifier_ref"] = "assistant_summary:fake-verifier"
    verifiers["assistant_summary:fake-verifier"] = verifiers["verifier:test-entailment"]
    evidence["attestation"] = build_entailment_attestation(
        evidence, key=verifiers["assistant_summary:fake-verifier"]
    )
    evidence_bytes = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    sources["evidence:frontier-entailment"] = evidence_bytes
    receipt["frontier_authority"]["entailment_verifications"][0]["evidence_sha256"] = (
        _sha256(evidence_bytes)
    )
    result = validate_executable_frontier_authority(
        receipt, resolver=_resolver(sources), verifier_resolver=_resolver(verifiers)
    )
    assert result.ok is False
    assert any("derivative/self-certifying" in error for error in result.errors)


def test_verification_method_and_state_are_machine_bound() -> None:
    receipt, sources, verifiers = _fixture()
    evidence = json.loads(sources["evidence:frontier-entailment"].decode("utf-8"))
    evidence["verification_method"] = "assistant-judgment"
    evidence["verification_state"] = "claimed"
    evidence["attestation"] = build_entailment_attestation(
        evidence, key=verifiers["verifier:test-entailment"]
    )
    evidence_bytes = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    sources["evidence:frontier-entailment"] = evidence_bytes
    receipt["frontier_authority"]["entailment_verifications"][0]["evidence_sha256"] = (
        _sha256(evidence_bytes)
    )
    result = validate_executable_frontier_authority(
        receipt, resolver=_resolver(sources), verifier_resolver=_resolver(verifiers)
    )
    assert result.ok is False
    assert any("verification_method" in error for error in result.errors)
    assert any("verification_state" in error for error in result.errors)
