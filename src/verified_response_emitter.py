"""Single fail-closed boundary for outward APEX response emission.

Agents should construct typed OutboundClaim objects, then pass the response through
this module. If any current/provider/mutation claim lacks the required current-run
receipt evidence, emission is denied before text leaves the runtime boundary.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from typing import Sequence

from approved_operation_bridge import ConnectorExecutionReceipt
from connector_receipts import ConnectorReadReceipt
from response_claim_guard import OutboundClaim, ResponseClaimGuard


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_POLICY = REPO_ROOT / "config" / "apex_runtime_policy.json"
REQUIRED_CLAIM_INVARIANTS = {
    "guard_required_before_response_emission",
    "current_provider_state_requires_current_run_read_receipt",
    "current_provider_hash_requires_receipt_hash_match",
    "current_provider_identifier_requires_receipt_binding",
    "current_mutation_requires_verified_execution_and_terminal_readback",
    "historical_state_requires_explicit_historical_reference",
    "historical_state_must_not_be_represented_as_current_run",
    "absence_claims_fail_closed_without_exhaustive_search_proof",
    "latest_claims_fail_closed_without_ordering_proof",
    "unadmitted_receipt_references_are_runtime_violations",
}


class ResponseEmissionDenied(RuntimeError):
    """Raised when an outward response cannot be evidence-authorized."""


def require_response_claim_policy(path: Path = DEFAULT_RUNTIME_POLICY) -> None:
    """Refuse response emission if the executable claim policy is missing or weakened."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ResponseEmissionDenied(f"response claim policy unavailable: {exc}") from exc

    invariants = payload.get("outbound_claim_invariants")
    if not isinstance(invariants, dict):
        raise ResponseEmissionDenied("outbound_claim_invariants policy is required")
    missing = sorted(
        key for key in REQUIRED_CLAIM_INVARIANTS if invariants.get(key) is not True
    )
    if missing:
        raise ResponseEmissionDenied(
            "response claim policy is weakened or incomplete: " + ", ".join(missing)
        )


def verify_response_for_emission(
    *,
    text: str,
    claims: Sequence[OutboundClaim],
    read_receipts: Sequence[ConnectorReadReceipt] = (),
    execution_receipts: Sequence[ConnectorExecutionReceipt] = (),
    policy_path: Path = DEFAULT_RUNTIME_POLICY,
) -> dict[str, object]:
    """Fail closed unless policy and every typed factual claim satisfy the receipt contract."""
    require_response_claim_policy(policy_path)

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
