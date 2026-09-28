"""Compatible durable mutation primitives harvested from feat/durable-workflow-machine.

Donor provenance:
- feat/durable-workflow-machine/contracts/changeset.py
- feat/durable-workflow-machine/verification/state_diff.py
- feat/durable-workflow-machine/contracts/receipt.py
- feat/durable-workflow-machine/workflows/master_run.py

This module deliberately does NOT transplant the donor's RootTruth/single-owner authority
model. Provider-native readback remains authoritative for provider facts, while execution
authority remains source-bound in the current runtime.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4


def _digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class VerifiedOperation:
    provider: str
    resource: str
    operation: str
    expected_before: Mapping[str, Any]
    desired_after: Mapping[str, Any]
    idempotency_key: str = ""

    def __post_init__(self) -> None:
        if not self.idempotency_key:
            object.__setattr__(self, "idempotency_key", _digest({
                "provider": self.provider,
                "resource": self.resource,
                "operation": self.operation,
                "desired_after": self.desired_after,
            })[:24])


@dataclass(frozen=True, slots=True)
class VerificationResult:
    verified: bool
    expected: Mapping[str, Any]
    observed: Mapping[str, Any]
    discrepancies: tuple[str, ...]
    verification_hash: str


def verify_expected_state(expected: Mapping[str, Any], observed: Mapping[str, Any]) -> VerificationResult:
    discrepancies = tuple(
        f"{key}: expected {expected[key]!r}, observed {observed.get(key)!r}"
        for key in expected
        if observed.get(key) != expected[key]
    )
    verified = not discrepancies
    return VerificationResult(
        verified=verified,
        expected=dict(expected),
        observed=dict(observed),
        discrepancies=discrepancies,
        verification_hash=_digest({"verified": verified, "expected": expected, "observed": observed}),
    )


@dataclass(frozen=True, slots=True)
class MutationReceipt:
    mission_id: str
    correlation_id: str
    result: str
    expected: Mapping[str, Any]
    observed: Mapping[str, Any]
    provider_receipt_ids: tuple[str, ...] = ()
    previous_receipt_hash: str = "GENESIS_ROOT"
    receipt_id: str = field(default_factory=lambda: f"rcpt_{uuid4().hex[:12]}")
    receipt_hash: str = ""

    def __post_init__(self) -> None:
        if not self.receipt_hash:
            object.__setattr__(self, "receipt_hash", _digest({
                "receipt_id": self.receipt_id,
                "mission_id": self.mission_id,
                "correlation_id": self.correlation_id,
                "result": self.result,
                "expected": self.expected,
                "observed": self.observed,
                "provider_receipt_ids": self.provider_receipt_ids,
                "previous_receipt_hash": self.previous_receipt_hash,
            }))


class VerificationFailure(RuntimeError):
    def __init__(self, result: VerificationResult):
        super().__init__("provider readback did not match expected state: " + "; ".join(result.discrepancies))
        self.result = result


def apply_with_verified_readback(
    operations: Sequence[VerifiedOperation],
    *,
    observe: Callable[[VerifiedOperation], Mapping[str, Any]],
    apply: Callable[[VerifiedOperation], str | None],
    readback: Callable[[VerifiedOperation], Mapping[str, Any]],
    compensate: Callable[[VerifiedOperation], None] | None = None,
) -> tuple[tuple[str, ...], tuple[VerificationResult, ...]]:
    """Preflight, mutate, read back, verify, and compensate in reverse on mismatch.

    This is an execution primitive, not an authority grant. Callers must bind source-bound
    authority before invoking it. Provider observations/readbacks control provider facts.
    """
    for op in operations:
        preflight = verify_expected_state(op.expected_before, observe(op))
        if not preflight.verified:
            raise VerificationFailure(preflight)

    applied: list[VerifiedOperation] = []
    receipt_ids: list[str] = []
    results: list[VerificationResult] = []
    try:
        for op in operations:
            provider_receipt = apply(op)
            applied.append(op)
            if provider_receipt:
                receipt_ids.append(provider_receipt)
            result = verify_expected_state(op.desired_after, readback(op))
            results.append(result)
            if not result.verified:
                raise VerificationFailure(result)
    except Exception:
        if compensate is not None:
            for op in reversed(applied):
                compensate(op)
        raise

    return tuple(receipt_ids), tuple(results)
