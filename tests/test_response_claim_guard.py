from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from approved_operation_bridge import ConnectorExecutionReceipt
from connector_receipts import ConnectorReadReceipt
from response_claim_guard import (
    ClaimAssertion,
    OutboundClaim,
    ResponseClaimGuard,
    ResponseClaimViolation,
)

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


def read_receipt() -> ConnectorReadReceipt:
    return ConnectorReadReceipt(
        receipt_id="read-001",
        request_id="request-001",
        connector="github",
        operation="file.read",
        profile="repository_integrity",
        target={"repository": "GlacierEQ/apex-control-plane", "sha": "abc123"},
        observed_at=NOW,
        content_sha256="a" * 64,
        source_refs=("github:GlacierEQ/apex-control-plane",),
    )


def execution_receipt(*, readback: bool = True) -> ConnectorExecutionReceipt:
    return ConnectorExecutionReceipt(
        execution_receipt_id="execution-001",
        action_request_id="action-001",
        connector="github",
        operation="file.update",
        idempotency_key="idem-001",
        approval_scope_sha256="b" * 64,
        result_state="completed",
        verification_passed=True,
        executed_at=NOW,
        result_target={"repository": "GlacierEQ/apex-control-plane"},
        execution_content_sha256="c" * 64,
        execution_source_refs=("github:commit:abc123",),
        readback_at=NOW if readback else None,
        readback_content_sha256="d" * 64 if readback else None,
        readback_source_refs=("github:readback:abc123",) if readback else (),
    )


def test_current_provider_claim_requires_receipt_admitted_in_this_runtime():
    claim = OutboundClaim(
        claim_id="claim-1",
        assertion=ClaimAssertion.CURRENT_PROVIDER_STATE,
        statement="GitHub currently contains the object.",
        evidence_refs=("read:read-001",),
    )

    with pytest.raises(ResponseClaimViolation, match="not admitted in this runtime"):
        ResponseClaimGuard().validate(claim)

    validated = ResponseClaimGuard(read_receipts=(read_receipt(),)).validate(claim)
    assert validated.status == "allowed"


def test_current_provider_claim_without_any_current_run_receipt_fails_closed():
    claim = OutboundClaim(
        claim_id="claim-2",
        assertion=ClaimAssertion.CURRENT_PROVIDER_STATE,
        statement="I checked the provider and found it.",
    )

    with pytest.raises(ResponseClaimViolation, match="current-run connector read receipt"):
        ResponseClaimGuard().validate(claim)


def test_hash_and_identifier_claims_must_match_the_cited_receipt():
    guard = ResponseClaimGuard(read_receipts=(read_receipt(),))

    good_hash = OutboundClaim(
        claim_id="hash-good",
        assertion=ClaimAssertion.CURRENT_PROVIDER_HASH,
        statement="The current content hash is source-bound.",
        evidence_refs=("read:read-001",),
        claimed_value="a" * 64,
    )
    assert guard.validate(good_hash).status == "allowed"

    bad_hash = OutboundClaim(
        claim_id="hash-bad",
        assertion=ClaimAssertion.CURRENT_PROVIDER_HASH,
        statement="The current content hash is something else.",
        evidence_refs=("read:read-001",),
        claimed_value="f" * 64,
    )
    with pytest.raises(ResponseClaimViolation, match="not present"):
        guard.validate(bad_hash)

    good_identifier = OutboundClaim(
        claim_id="id-good",
        assertion=ClaimAssertion.CURRENT_PROVIDER_IDENTIFIER,
        statement="The current provider object is bound to this repository.",
        evidence_refs=("read:read-001",),
        claimed_value="GlacierEQ/apex-control-plane",
    )
    assert guard.validate(good_identifier).status == "allowed"

    bad_identifier = OutboundClaim(
        claim_id="id-bad",
        assertion=ClaimAssertion.CURRENT_PROVIDER_IDENTIFIER,
        statement="The provider object is a different repository.",
        evidence_refs=("read:read-001",),
        claimed_value="GlacierEQ/not-the-repo",
    )
    with pytest.raises(ResponseClaimViolation, match="not bound"):
        guard.validate(bad_identifier)


def test_absence_and_latest_claims_reject_generic_read_receipts():
    guard = ResponseClaimGuard(read_receipts=(read_receipt(),))
    for assertion in (
        ClaimAssertion.CURRENT_PROVIDER_ABSENCE,
        ClaimAssertion.CURRENT_PROVIDER_LATEST,
    ):
        claim = OutboundClaim(
            claim_id=assertion.value,
            assertion=assertion,
            statement="A generic read must not prove exhaustive semantics.",
            evidence_refs=("read:read-001",),
        )
        with pytest.raises(ResponseClaimViolation, match="fails closed"):
            guard.validate(claim)


def test_mutation_claim_requires_verified_execution_and_terminal_readback():
    claim = OutboundClaim(
        claim_id="mutation",
        assertion=ClaimAssertion.CURRENT_MUTATION,
        statement="The provider mutation completed and was read back.",
        evidence_refs=("execution:execution-001",),
    )

    without_readback = ResponseClaimGuard(
        execution_receipts=(execution_receipt(readback=False),)
    )
    with pytest.raises(ResponseClaimViolation, match="terminal readback"):
        without_readback.validate(claim)

    with_readback = ResponseClaimGuard(
        execution_receipts=(execution_receipt(readback=True),)
    )
    assert with_readback.validate(claim).status == "allowed"


def test_historical_state_is_explicit_and_cannot_masquerade_as_current_run():
    good = OutboundClaim(
        claim_id="history-good",
        assertion=ClaimAssertion.HISTORICAL_STATE,
        statement="Historical verified state records this prior result.",
        historical_ref="receipt-ledger:historical-001",
    )
    assert ResponseClaimGuard().validate(good).status == "allowed"

    no_ref = OutboundClaim(
        claim_id="history-no-ref",
        assertion=ClaimAssertion.HISTORICAL_STATE,
        statement="Historical state without a source reference.",
    )
    with pytest.raises(ResponseClaimViolation, match="historical_ref"):
        ResponseClaimGuard().validate(no_ref)

    masquerade = OutboundClaim(
        claim_id="history-masquerade",
        assertion=ClaimAssertion.HISTORICAL_STATE,
        statement="Historical state pretending to be a new read.",
        historical_ref="receipt-ledger:historical-001",
        evidence_refs=("read:read-001",),
    )
    with pytest.raises(ResponseClaimViolation, match="must not masquerade"):
        ResponseClaimGuard(read_receipts=(read_receipt(),)).validate(masquerade)


def test_runtime_policy_requires_the_outbound_claim_guard_invariants():
    payload = json.loads((ROOT / "config" / "apex_runtime_policy.json").read_text(encoding="utf-8"))
    invariants = payload["outbound_claim_invariants"]

    assert invariants["guard_required_before_response_emission"] is True
    assert invariants["current_provider_state_requires_current_run_read_receipt"] is True
    assert invariants["current_mutation_requires_verified_execution_and_terminal_readback"] is True
    assert invariants["historical_state_must_not_be_represented_as_current_run"] is True
    assert invariants["absence_claims_fail_closed_without_exhaustive_search_proof"] is True
    assert invariants["latest_claims_fail_closed_without_ordering_proof"] is True
