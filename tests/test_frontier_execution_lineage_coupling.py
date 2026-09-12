from __future__ import annotations

import hashlib
import json

from executable_frontier_authority import derive_frontier_id, validate_executable_frontier_authority
from execution_evidence_authority import derive_execution_claim_id


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _resolver(sources: dict[str, bytes]):
    def resolve(ref: str) -> bytes:
        return sources[ref]
    return resolve


def _fixture() -> tuple[dict, dict[str, bytes], str]:
    proposition = "Continue from provider-verified state and advance the continuity architecture without replacing source-bearing truth with derivative state."
    operator_source = ("Before.\n" + proposition + "\nAfter.\n").encode()
    start = operator_source.index(proposition.encode())
    end = start + len(proposition.encode())

    provider = "github"
    provider_object_ref = "github:GlacierEQ/apex-control-plane:commit:9117bc58"
    source_sha = "9117bc58e97c5d719f8aa0610a726580469b399b"
    operation = "merge_pull_request"
    claim_id = derive_execution_claim_id(
        provider=provider,
        provider_object_ref=provider_object_ref,
        source_sha=source_sha,
        operation=operation,
    )
    provider_readback = {
        "provider": provider,
        "provider_object_ref": provider_object_ref,
        "source_sha": source_sha,
        "operation": operation,
        "execution_claim_id": claim_id,
        "state": "VERIFIED",
        "readback_verified": True,
        "verifier_ref": "github-api:commit-readback",
    }
    provider_bytes = json.dumps(provider_readback, sort_keys=True, separators=(",", ":")).encode()
    execution_evidence = {
        "execution_claim_id": claim_id,
        "provider": provider,
        "provider_object_ref": provider_object_ref,
        "source_sha": source_sha,
        "operation": operation,
        "state": "VERIFIED",
        "evidence_kind": "provider_api_readback",
        "evidence_ref": "provider:github:commit:9117bc58",
        "evidence_sha256": _sha256(provider_bytes),
    }
    lineage_record = {
        "prior_truth_state": "PROVIDER_VERIFIED",
        "execution_evidence": execution_evidence,
    }

    proposition_id = "operator:continuity-progress:test"
    operation_class = "ai_architecture_continuation"
    target = "advance continuity architecture without derivative authority"
    frontier_action = "couple frontier authorization to current execution lineage"
    frontier_id = derive_frontier_id(
        operation_class=operation_class,
        target=target,
        frontier_action=frontier_action,
        proposition_ids=[proposition_id],
        execution_claim_ids=[claim_id],
    )
    entailment = {
        "frontier_id": frontier_id,
        "verdict": "entailed",
        "operation_class": operation_class,
        "target": target,
        "frontier_action": frontier_action,
        "proposition_ids": [proposition_id],
        "execution_claim_ids": [claim_id],
        "verifier_ref": "independent:test-entailment-verifier",
    }
    entailment_bytes = json.dumps(entailment, sort_keys=True, separators=(",", ":")).encode()

    sources = {
        "source:operator-current": operator_source,
        "provider:github:commit:9117bc58": provider_bytes,
        "evidence:frontier-entailment": entailment_bytes,
    }
    receipt = {
        "frontier_authority": {
            "frontier_id": frontier_id,
            "continuation_ref": frontier_id,
            "operation_class": operation_class,
            "target": target,
            "frontier_action": frontier_action,
            "execution_claim_ids": [claim_id],
            "execution_lineage_records": [lineage_record],
            "source_bindings": [
                {
                    "proposition_id": proposition_id,
                    "proposition_text": proposition,
                    "source_kind": "operator_message",
                    "source_ref": "source:operator-current",
                    "source_sha256": _sha256(operator_source),
                    "span_start_byte": start,
                    "span_end_byte": end,
                    "span_sha256": _sha256(operator_source[start:end]),
                    "temporal_context": "current Operator run",
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
    return receipt, sources, claim_id


def test_frontier_with_execution_dependency_requires_current_provider_authority() -> None:
    receipt, sources, _ = _fixture()
    result = validate_executable_frontier_authority(receipt, resolver=_resolver(sources))
    assert result.ok is True
    assert result.status == "frontier_authorized"


def test_carried_verified_state_cannot_authorize_when_provider_readback_disappears() -> None:
    receipt, sources, _ = _fixture()
    del sources["provider:github:commit:9117bc58"]
    result = validate_executable_frontier_authority(receipt, resolver=_resolver(sources))
    assert result.ok is False
    assert result.status == "frontier_authorization_unresolved"
    assert any("PROVIDER_READBACK_UNRESOLVED" in error for error in result.errors)


def test_execution_lineage_records_must_exactly_match_bound_claim_ids() -> None:
    receipt, sources, _ = _fixture()
    receipt["frontier_authority"]["execution_claim_ids"].append("execution:unbound")
    result = validate_executable_frontier_authority(receipt, resolver=_resolver(sources))
    assert result.ok is False
    assert any("exactly match execution_claim_ids" in error for error in result.errors)


def test_execution_claim_substitution_changes_frontier_identity() -> None:
    receipt, sources, _ = _fixture()
    receipt["frontier_authority"]["execution_claim_ids"] = ["execution:substituted"]
    result = validate_executable_frontier_authority(receipt, resolver=_resolver(sources))
    assert result.ok is False
    assert any("frontier_id is not bound" in error for error in result.errors)


def test_independent_entailment_must_bind_same_execution_claims() -> None:
    receipt, sources, _ = _fixture()
    evidence = json.loads(sources["evidence:frontier-entailment"].decode())
    evidence["execution_claim_ids"] = []
    tampered = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    sources["evidence:frontier-entailment"] = tampered
    receipt["frontier_authority"]["entailment_verifications"][0]["evidence_sha256"] = _sha256(tampered)
    result = validate_executable_frontier_authority(receipt, resolver=_resolver(sources))
    assert result.ok is False
    assert any("execution_claim_ids" in error for error in result.errors)
