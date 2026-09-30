from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from connector_receipts import ConnectorReadReceipt
from response_claim_guard import ClaimAssertion, OutboundClaim, ResponseClaimViolation
from verified_response_emitter import verify_response_for_emission

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


def receipt() -> ConnectorReadReceipt:
    return ConnectorReadReceipt(
        receipt_id="read-emit-001",
        request_id="request-emit-001",
        connector="gmail",
        operation="message.read",
        profile="communications_read",
        target={"message_id": "msg-123"},
        observed_at=NOW,
        content_sha256="a" * 64,
        source_refs=("gmail:msg-123",),
    )


def test_response_emission_denied_when_current_provider_claim_has_no_receipt():
    claim = OutboundClaim(
        claim_id="gmail-current",
        assertion=ClaimAssertion.CURRENT_PROVIDER_STATE,
        statement="I read the current Gmail message.",
        evidence_refs=("read:read-emit-001",),
    )

    with pytest.raises(ResponseClaimViolation):
        verify_response_for_emission(text="Current Gmail state checked.", claims=(claim,))


def test_response_emission_allowed_when_claim_is_bound_to_current_run_receipt():
    claim = OutboundClaim(
        claim_id="gmail-current",
        assertion=ClaimAssertion.CURRENT_PROVIDER_STATE,
        statement="I read the current Gmail message.",
        evidence_refs=("read:read-emit-001",),
    )

    result = verify_response_for_emission(
        text="Current Gmail state checked.",
        claims=(claim,),
        read_receipts=(receipt(),),
    )

    assert result["status"] == "verified_for_emission"
    assert result["claim_count"] == 1
    assert result["claims"][0]["evidence_refs"] == ("read:read-emit-001",)
