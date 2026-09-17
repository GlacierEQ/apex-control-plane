from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from response_claim_guard import ClaimAssertion, OutboundClaim, ResponseClaimViolation
from verified_response_emitter import ResponseEmissionDenied, verify_response_for_emission


def test_untyped_provider_read_language_is_blocked():
    with pytest.raises(ResponseEmissionDenied, match="current_provider_state"):
        verify_response_for_emission(
            text="I checked Gmail and found the message.",
            claims=(),
        )


def test_untyped_latest_language_is_blocked():
    with pytest.raises(ResponseEmissionDenied, match="current_provider_latest"):
        verify_response_for_emission(
            text="The latest GitHub commit is abc123.",
            claims=(),
        )


def test_untyped_absence_language_is_blocked():
    with pytest.raises(ResponseEmissionDenied, match="current_provider_absence"):
        verify_response_for_emission(
            text="No results were found in Dropbox.",
            claims=(),
        )


def test_typed_latest_claim_still_fails_without_specialized_ordering_proof():
    claim = OutboundClaim(
        claim_id="latest",
        assertion=ClaimAssertion.CURRENT_PROVIDER_LATEST,
        statement="The latest GitHub commit is abc123.",
    )
    with pytest.raises(ResponseClaimViolation, match="fails closed"):
        verify_response_for_emission(
            text="The latest GitHub commit is abc123.",
            claims=(claim,),
        )


def test_plain_non_execution_response_does_not_require_artificial_claim_metadata():
    result = verify_response_for_emission(
        text="The next step is to inspect the source-bearing record.",
        claims=(),
    )
    assert result["status"] == "verified_for_emission"
    assert result["claim_count"] == 0
