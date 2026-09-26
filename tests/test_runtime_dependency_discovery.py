from __future__ import annotations

import json

from runtime_dependency_discovery import discover_execution_dependencies


def _resolver(sources: dict[str, bytes]):
    def resolve(ref: str) -> bytes:
        return sources[ref]
    return resolve


def test_runtime_discovers_execution_claims_from_resolved_source_provider_artifacts() -> None:
    claim = "execution:provider-verified-claim"
    sources = {
        "file:operator.txt": b"continue the active mission",
        "provider://github/readback.json": json.dumps(
            {"execution_claim_id": claim, "state": "VERIFIED"}
        ).encode(),
    }
    receipt = {
        "frontier_authority": {
            "execution_claim_ids": ["execution:caller-authored-must-not-control"],
            "source_bindings": [{"source_ref": "file:operator.txt"}],
            "provider_readback_ref": "provider://github/readback.json",
        }
    }

    result = discover_execution_dependencies(receipt, resolver=_resolver(sources))

    assert result.execution_claim_ids == (claim,)
    assert result.unresolved_refs == ()


def test_runtime_ignores_derivative_execution_ids_embedded_in_receipt() -> None:
    receipt = {
        "frontier_authority": {
            "execution_claim_ids": ["execution:derivative-receipt-value"],
            "assistant_summary": "execution:summary-value",
        }
    }

    result = discover_execution_dependencies(receipt, resolver=_resolver({}))

    assert result.execution_claim_ids == ()


def test_runtime_preserves_partial_discovery_when_one_reference_is_unresolved() -> None:
    claim = "execution:resolved"
    sources = {
        "provider://github/ok.json": json.dumps(
            {"nested": {"execution_claim_id": claim}}
        ).encode(),
    }
    receipt = {
        "frontier_authority": {
            "provider_refs": [
                "provider://github/ok.json",
                "provider://github/missing.json",
            ]
        }
    }

    result = discover_execution_dependencies(receipt, resolver=_resolver(sources))

    assert result.execution_claim_ids == (claim,)
    assert result.unresolved_refs == ("provider://github/missing.json",)
