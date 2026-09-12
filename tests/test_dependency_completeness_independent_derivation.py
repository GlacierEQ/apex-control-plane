"""Regression test for dependency-completeness self-attestation.

This test intentionally defines the semantic boundary that the current
implementation does not yet satisfy: a completeness artifact may not create
its own authoritative dependency set and then pass merely because the frontier
repeats the same set.
"""

from __future__ import annotations

import hashlib
import json

from executable_frontier_authority import (
    derive_frontier_id,
    validate_executable_frontier_authority,
)


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def test_matching_self_attested_dependency_set_is_not_independent_derivation() -> None:
    """A matching artifact/frontier list is insufficient proof of completeness.

    The evidence artifact below asserts that there are no required execution
    dependencies. The frontier makes the same declaration. There is no
    independently derived dependency result, no extractor identity, and no
    bound derivation inputs. Authorization must therefore fail closed.
    """

    source_bytes = b"execute corrected action from source-bearing state"
    proposition_id = "proposition:operator-corrected-action"
    frontier_id = derive_frontier_id(
        operation_class="mutation",
        target="continuity-control-plane",
        frontier_action="execute corrected action",
        proposition_ids=[proposition_id],
        execution_claim_ids=[],
    )

    completeness = {
        "frontier_id": frontier_id,
        "verdict": "complete",
        "operation_class": "mutation",
        "target": "continuity-control-plane",
        "frontier_action": "execute corrected action",
        "required_execution_claim_ids": [],
        "verifier_ref": "independent:assertion-only-verifier",
    }
    completeness_bytes = json.dumps(
        completeness, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")

    entailment = {
        "frontier_id": frontier_id,
        "verdict": "entailed",
        "operation_class": "mutation",
        "target": "continuity-control-plane",
        "frontier_action": "execute corrected action",
        "proposition_ids": [proposition_id],
        "execution_claim_ids": [],
        "verifier_ref": "independent:test-entailment-verifier",
    }
    entailment_bytes = json.dumps(
        entailment, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")

    sources = {
        "source:operator": source_bytes,
        "evidence:dependency-completeness": completeness_bytes,
        "evidence:entailment": entailment_bytes,
    }

    receipt = {
        "frontier_authority": {
            "operation_class": "mutation",
            "target": "continuity-control-plane",
            "frontier_action": "execute corrected action",
            "frontier_id": frontier_id,
            "continuation_ref": frontier_id,
            "source_bindings": [
                {
                    "proposition_id": proposition_id,
                    "proposition_text": source_bytes.decode("utf-8"),
                    "source_ref": "source:operator",
                    "source_sha256": _sha256(source_bytes),
                    "span_start": 0,
                    "span_end": len(source_bytes),
                    "source_class": "operator_verbatim",
                    "superseded": False,
                }
            ],
            "execution_claim_ids": [],
            "execution_lineage_records": [],
            "dependency_completeness_verification": {
                "evidence_ref": "evidence:dependency-completeness",
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

    assert not result.ok, (
        "dependency completeness must not authorize from a matching self-attested "
        "required_execution_claim_ids list; an independently derived result and "
        "bound derivation inputs are required"
    )
