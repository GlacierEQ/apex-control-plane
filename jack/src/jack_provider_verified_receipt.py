"""Provider-verified completion boundary for Jack execution receipts.

This wrapper preserves Jack's existing structural/state checks, then rejects any
EXECUTED-or-stronger action whose provider evidence cannot be independently
resolved and verified. String receipt references remain routing hints only.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from execution_evidence_authority import EvidenceResolver, validate_execution_evidence
from jack_relentless_gate import validate_receipt

_EXECUTED = {"EXECUTED", "VERIFIED", "COMMITTED", "DEPLOYED", "OBSERVED_IN_OPERATION"}


def validate_provider_verified_receipt(
    receipt: Mapping[str, Any], *, resolver: EvidenceResolver
) -> None:
    """Fail closed unless every claimed execution has independent provider proof."""
    validate_receipt(receipt)
    actions = receipt.get("actions_executed", [])
    if not isinstance(actions, list):
        raise ValueError("actions_executed must be a list")

    verified_claims = 0
    for index, action in enumerate(actions):
        if not isinstance(action, Mapping):
            continue
        state = str(action.get("state", "")).strip().upper()
        if state not in _EXECUTED or action.get("executed") is not True:
            continue
        evidence = action.get("execution_evidence")
        if not isinstance(evidence, Mapping):
            raise ValueError(
                f"actions_executed[{index}] requires execution_evidence; provider_receipt is routing-only"
            )
        result = validate_execution_evidence(evidence, resolver=resolver)
        if not result.ok:
            raise ValueError(
                f"actions_executed[{index}] independent execution evidence failed: "
                + "; ".join(result.errors)
            )
        verified_claims += 1

    gates = receipt.get("gates")
    if isinstance(gates, Mapping) and gates.get("readback_verified") is True and verified_claims == 0:
        raise ValueError("readback_verified requires independently verified execution evidence")
