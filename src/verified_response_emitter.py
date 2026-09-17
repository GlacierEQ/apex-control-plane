"""Single fail-closed boundary for outward APEX response emission.

Agents should construct typed OutboundClaim objects, then pass the response through
this module. If any current/provider/mutation claim lacks the required current-run
receipt evidence, emission is denied before text leaves the runtime boundary.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
from typing import Sequence

from approved_operation_bridge import ConnectorExecutionReceipt
from connector_receipts import ConnectorReadReceipt
from response_claim_guard import OutboundClaim, ResponseClaimGuard


class ResponseEmissionDenied(RuntimeError):
    """Raised when an outward response cannot be evidence-authorized."""


def verify_response_for_emission(
    *,
    text: str,
    claims: Sequence[OutboundClaim],
    read_receipts: Sequence[ConnectorReadReceipt] = (),
    execution_receipts: Sequence[ConnectorExecutionReceipt] = (),
) -> dict[str, object]:
    """Fail closed unless every typed factual claim satisfies the receipt contract."""
    response_text = str(text or "").strip()
    if not response_text:
        raise ResponseEmissionDenied("response text is required")

    guard = ResponseClaimGuard(
        read_receipts=read_receipts,
        execution_receipts=execution_receipts,
    )
    validations = guard.validate_all(claims)
    return {
        "status": "verified_for_emission",
        "response_sha256": sha256(response_text.encode("utf-8")).hexdigest(),
        "claim_count": len(validations),
        "claims": [asdict(validation) for validation in validations],
        "text": response_text,
    }
