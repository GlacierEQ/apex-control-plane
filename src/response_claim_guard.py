"""Fail-closed outbound response-claim enforcement for APEX.

This module closes the gap between having execution/provider receipts and what an
agent is allowed to say in an outward response. APEX already records connector and
runtime receipts; this guard makes those receipts a prerequisite for freshness,
provider-state, mutation, hash, and provider-identifier claims.

Historical state is allowed only when explicitly classified as historical and bound
to a durable historical source reference. Claims about absence or "latest" provider
state fail closed until specialized exhaustive-search/order proof exists; a generic
read receipt is intentionally insufficient.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from approved_operation_bridge import ConnectorExecutionReceipt
from connector_receipts import ConnectorReadReceipt


class ResponseClaimViolation(RuntimeError):
    """Raised when outward-facing prose outruns current-run evidence."""


class ClaimAssertion(str, Enum):
    HISTORICAL_STATE = "historical_state"
    CURRENT_PROVIDER_STATE = "current_provider_state"
    CURRENT_PROVIDER_HASH = "current_provider_hash"
    CURRENT_PROVIDER_IDENTIFIER = "current_provider_identifier"
    CURRENT_PROVIDER_ABSENCE = "current_provider_absence"
    CURRENT_PROVIDER_LATEST = "current_provider_latest"
    CURRENT_MUTATION = "current_mutation"


@dataclass(frozen=True, slots=True)
class OutboundClaim:
    claim_id: str
    assertion: ClaimAssertion
    statement: str
    evidence_refs: tuple[str, ...] = ()
    historical_ref: str | None = None
    claimed_value: str | None = None

    def __post_init__(self) -> None:
        if not self.claim_id.strip():
            raise ResponseClaimViolation("claim_id is required")
        if not self.statement.strip():
            raise ResponseClaimViolation("statement is required")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ResponseClaimViolation("evidence_refs contains duplicates")


@dataclass(frozen=True, slots=True)
class ClaimValidation:
    claim_id: str
    assertion: str
    status: str
    evidence_refs: tuple[str, ...]


class ResponseClaimGuard:
    """Validate outward claims only against receipts admitted in this runtime."""

    def __init__(
        self,
        *,
        read_receipts: Sequence[ConnectorReadReceipt] = (),
        execution_receipts: Sequence[ConnectorExecutionReceipt] = (),
    ) -> None:
        self._reads = {receipt.receipt_id: receipt for receipt in read_receipts}
        self._executions = {
            receipt.execution_receipt_id: receipt for receipt in execution_receipts
        }

    def validate(self, claim: OutboundClaim) -> ClaimValidation:
        assertion = claim.assertion

        if assertion is ClaimAssertion.HISTORICAL_STATE:
            if not claim.historical_ref or not claim.historical_ref.strip():
                raise ResponseClaimViolation(
                    "historical_state requires an explicit historical_ref"
                )
            if claim.evidence_refs:
                raise ResponseClaimViolation(
                    "historical_state must not masquerade current-run receipt refs"
                )
            return self._ok(claim)

        if assertion is ClaimAssertion.CURRENT_PROVIDER_STATE:
            self._require_read_receipts(claim)
            return self._ok(claim)

        if assertion is ClaimAssertion.CURRENT_PROVIDER_HASH:
            receipts = self._require_read_receipts(claim)
            value = self._required_claimed_value(claim)
            if not any(receipt.content_sha256 == value for receipt in receipts):
                raise ResponseClaimViolation(
                    "current_provider_hash is not present on a cited current-run read receipt"
                )
            return self._ok(claim)

        if assertion is ClaimAssertion.CURRENT_PROVIDER_IDENTIFIER:
            receipts = self._require_read_receipts(claim)
            value = self._required_claimed_value(claim)
            if not any(self._receipt_contains_identifier(receipt, value) for receipt in receipts):
                raise ResponseClaimViolation(
                    "current_provider_identifier is not bound to a cited current-run read receipt"
                )
            return self._ok(claim)

        if assertion is ClaimAssertion.CURRENT_MUTATION:
            receipts = self._require_execution_receipts(claim)
            for receipt in receipts:
                if not receipt.verification_passed:
                    continue
                if receipt.readback_at is None or not receipt.readback_source_refs:
                    continue
                if receipt.result_state not in {"completed", "success", "succeeded"}:
                    continue
                return self._ok(claim)
            raise ResponseClaimViolation(
                "current_mutation requires a successful verified execution receipt with terminal readback"
            )

        if assertion in {
            ClaimAssertion.CURRENT_PROVIDER_ABSENCE,
            ClaimAssertion.CURRENT_PROVIDER_LATEST,
        }:
            raise ResponseClaimViolation(
                f"{assertion.value} fails closed: a generic provider read receipt does not prove "
                "exhaustive absence or ordering/latest semantics"
            )

        raise ResponseClaimViolation(f"unsupported claim assertion: {assertion!r}")

    def validate_all(self, claims: Sequence[OutboundClaim]) -> tuple[ClaimValidation, ...]:
        return tuple(self.validate(claim) for claim in claims)

    def _require_read_receipts(self, claim: OutboundClaim) -> tuple[ConnectorReadReceipt, ...]:
        if not claim.evidence_refs:
            raise ResponseClaimViolation(
                f"{claim.assertion.value} requires a current-run connector read receipt"
            )
        receipts: list[ConnectorReadReceipt] = []
        for reference in claim.evidence_refs:
            receipt_id = self._strip_ref(reference, "read")
            try:
                receipts.append(self._reads[receipt_id])
            except KeyError as exc:
                raise ResponseClaimViolation(
                    f"claim cites a read receipt not admitted in this runtime: {receipt_id}"
                ) from exc
        return tuple(receipts)

    def _require_execution_receipts(
        self, claim: OutboundClaim
    ) -> tuple[ConnectorExecutionReceipt, ...]:
        if not claim.evidence_refs:
            raise ResponseClaimViolation(
                "current_mutation requires a current-run connector execution receipt"
            )
        receipts: list[ConnectorExecutionReceipt] = []
        for reference in claim.evidence_refs:
            receipt_id = self._strip_ref(reference, "execution")
            try:
                receipts.append(self._executions[receipt_id])
            except KeyError as exc:
                raise ResponseClaimViolation(
                    f"claim cites an execution receipt not admitted in this runtime: {receipt_id}"
                ) from exc
        return tuple(receipts)

    @staticmethod
    def _strip_ref(reference: str, expected_kind: str) -> str:
        prefix, separator, locator = reference.strip().partition(":")
        if not separator or prefix != expected_kind or not locator:
            raise ResponseClaimViolation(
                f"evidence reference must use {expected_kind}:<receipt-id> form"
            )
        return locator

    @staticmethod
    def _required_claimed_value(claim: OutboundClaim) -> str:
        value = str(claim.claimed_value or "").strip()
        if not value:
            raise ResponseClaimViolation(
                f"{claim.assertion.value} requires claimed_value"
            )
        return value

    @staticmethod
    def _receipt_contains_identifier(receipt: ConnectorReadReceipt, value: str) -> bool:
        if value in receipt.source_refs:
            return True
        return ResponseClaimGuard._mapping_contains_value(receipt.target, value)

    @staticmethod
    def _mapping_contains_value(value: Mapping[str, Any], expected: str) -> bool:
        for item in value.values():
            if isinstance(item, Mapping):
                if ResponseClaimGuard._mapping_contains_value(item, expected):
                    return True
            elif isinstance(item, (list, tuple, set, frozenset)):
                if any(str(member) == expected for member in item):
                    return True
            elif str(item) == expected:
                return True
        return False

    @staticmethod
    def _ok(claim: OutboundClaim) -> ClaimValidation:
        return ClaimValidation(
            claim_id=claim.claim_id,
            assertion=claim.assertion.value,
            status="allowed",
            evidence_refs=claim.evidence_refs,
        )
