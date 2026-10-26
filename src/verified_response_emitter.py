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
import re
from typing import Sequence

from approved_operation_bridge import ConnectorExecutionReceipt
from connector_receipts import ConnectorReadReceipt
from response_claim_guard import ClaimAssertion, OutboundClaim, ResponseClaimGuard


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_POLICY = REPO_ROOT / "config" / "apex_runtime_policy.json"
REQUIRED_CLAIM_INVARIANTS = {
    "guard_required_before_response_emission",
    "execution_language_requires_typed_claims",
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

_PROVIDER = r"(?:gmail|github|dropbox|drive|notion|provider|connector|repository|repo|email|message|file|record)"
_READ_VERB = r"(?:checked|searched|read|fetched|found|verified|confirmed|queried|looked\s+up)"
_MUTATION_VERB = r"(?:updated|created|deleted|merged|sent|submitted|uploaded|published|changed|wrote|committed)"

LATEST_RE = re.compile(rf"\b(?:latest|most\s+recent|current\s+head)\b.*\b{_PROVIDER}\b|\b{_PROVIDER}\b.*\b(?:latest|most\s+recent|current\s+head)\b", re.IGNORECASE)
ABSENCE_RE = re.compile(r"\b(?:no|zero)\s+(?:results|matches|messages|emails|files|records|commits)\b|\b(?:nothing|none)\s+(?:was\s+)?found\b", re.IGNORECASE)
HASH_RE = re.compile(r"\b(?:sha(?:-?256)?|hash|content[_ -]?sha256)\b", re.IGNORECASE)
PROVIDER_READ_RE = re.compile(rf"\b(?:i|we)\s+(?:just\s+)?{_READ_VERB}\b.*\b{_PROVIDER}\b|\b{_PROVIDER}\b.*\b(?:was|were|is|are)\s+(?:just\s+)?{_READ_VERB}\b", re.IGNORECASE)
MUTATION_RE = re.compile(rf"\b(?:i|we)\s+(?:just\s+)?{_MUTATION_VERB}\b|\b{_PROVIDER}\b.*\b(?:was|were|has\s+been)\s+{_MUTATION_VERB}\b", re.IGNORECASE)
READBACK_RE = re.compile(r"\bread\s*back\b|\bterminal\s+readback\b", re.IGNORECASE)


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


def required_assertions_for_text(text: str) -> frozenset[ClaimAssertion]:
    """Detect the recurring high-risk execution/freshness claims that must be typed."""
    required: set[ClaimAssertion] = set()
    if LATEST_RE.search(text):
        required.add(ClaimAssertion.CURRENT_PROVIDER_LATEST)
    if ABSENCE_RE.search(text):
        required.add(ClaimAssertion.CURRENT_PROVIDER_ABSENCE)
    if PROVIDER_READ_RE.search(text):
        required.add(ClaimAssertion.CURRENT_PROVIDER_STATE)
    if MUTATION_RE.search(text) or READBACK_RE.search(text):
        required.add(ClaimAssertion.CURRENT_MUTATION)
    if HASH_RE.search(text) and (
        "current" in text.lower()
        or "fresh" in text.lower()
        or PROVIDER_READ_RE.search(text)
    ):
        required.add(ClaimAssertion.CURRENT_PROVIDER_HASH)
    return frozenset(required)


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

    claim_assertions = {claim.assertion for claim in claims}
    required = required_assertions_for_text(response_text)
    missing_assertions = sorted(assertion.value for assertion in required - claim_assertions)
    if missing_assertions:
        raise ResponseEmissionDenied(
            "response contains execution/freshness language without required typed claim(s): "
            + ", ".join(missing_assertions)
        )

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
