from __future__ import annotations

import hashlib
import json

from executable_frontier_authority import derive_frontier_id, validate_executable_frontier_authority


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def test_frontier_rejects_completeness_evidence_without_source_bound_dependency_basis() -> None:
    proposition = "Continue from source-bearing state and execute the next verified frontier."
    source = proposition.encode("utf-8")
    proposition_id = "operator:test:dependency-basis-integration"
    operation_class = "ai_architecture_continuation"
    target = "source-bound continuity"
    frontier_action = "execute verified continuation"
    frontier_id = derive_frontier_id(
        operation_class=operation_class,
        target=target,
        frontier_action=frontier_action,
        proposition_ids=[proposition_id],
    )

    completeness = {
        "frontier_id": frontier_id,
        "verdict": "complete",
        "operation_class": operation_class,
        "target": target,
        "frontier_action": frontier_action,
        "required_execution_claim_ids": [],
        "verifier_ref": "independent:test-verifier",
    }
    completeness_bytes = json.dumps(completeness, sort_keys=True, separators=(",", ":")).encode("utf-8")

    entailment = {
        "frontier_id": frontier_id,
        "verdict": "entailed",
        "operation_class": operation_class,
        "target": target,
        "frontier_action": frontier_action,
        "proposition_ids": [proposition_id],
        "verifier_ref": "independent:test-entailment",
    }
    entailment_bytes = json.dumps(entailment, sort_keys=True, separators=(",", ":")).encode("utf-8")

    sources = {
        "source:operator": source,
        "evidence:completeness": completeness_bytes,
        "evidence:entailment": entailment_bytes,
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
                    "proposition_id": proposition_id,
                    "proposition_text": proposition,
                    "source_kind": "operator_message",
                    "source_ref": "source:operator",
                    "source_sha256": _sha256(source),
                    "span_start_byte": 0,
                    "span_end_byte": len(source),
                    "span_sha256": _sha256(source),
                    "temporal_context": "current run",
                    "contradiction_state": "active",
                    "superseded_by": None,
                    "verification_state": "source_resolved",
                }
            ],
            "dependency_completeness_verification": {
                "evidence_ref": "evidence:completeness",
                "evidence_sha256": _sha256(completeness_bytes),
            },
            "entailment_verifications": [
                {
                    "evidence_ref": "evidence:entailment",
                    "evidence_sha256": _sha256(entailment_bytes),
                }
            ],
        }
    }

    def resolver(ref: str) -> bytes:
        return sources[ref]

    result = validate_executable_frontier_authority(receipt, resolver=resolver)

    # This must fail closed. If it passes, completeness is still self-contained
    # derivative evidence rather than source-bound dependency-basis authority.
    assert result.ok is False
    assert any("dependency_basis" in error for error in result.errors)
