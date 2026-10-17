"""Cross-run lineage authority for execution evidence.

Historical truth, current readback, and current execution authority are distinct.
A prior provider-verified proposition remains verified historical state unless
affirmative evidence invalidates it. Current readback can still be required for
a new dependent action; when it is unavailable, only current execution authority
is unresolved. Projection omissions, search misses, and readback failures do not
rewrite established history.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from execution_evidence_authority import EvidenceResolver, validate_execution_evidence

AUTHORITATIVE = "PROVIDER_VERIFIED"
READBACK_UNRESOLVED = "PROVIDER_READBACK_UNRESOLVED"
READBACK_NOT_ATTEMPTED = "READBACK_NOT_ATTEMPTED"
UNESTABLISHED = "UNESTABLISHED"
CONTRADICTED = "CONTRADICTED"
SUPERSEDED = "SUPERSEDED"
REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class LineageResult:
    authoritative: bool
    truth_state: str
    readback_state: str
    authority_state: str
    execution_claim_id: str
    record_hash: str
    errors: tuple[str, ...]


def _canonical_hash(record: Mapping[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def reconcile_execution_lineage(
    record: Mapping[str, Any], *, resolver: EvidenceResolver
) -> LineageResult:
    """Reconcile a carried execution claim without collapsing state dimensions.

    Current provider verification governs current execution authority. Historical
    provider verification remains historical truth even when current readback is
    unavailable or a later projection omits the source.
    """
    errors: list[str] = []
    prior_state = str(record.get("prior_truth_state", "")).strip().upper()
    preserved_truth = AUTHORITATIVE if prior_state == AUTHORITATIVE else UNESTABLISHED

    evidence = record.get("execution_evidence")
    if not isinstance(evidence, Mapping):
        errors.append("lineage.execution_evidence must be an object")
        return LineageResult(
            False,
            preserved_truth,
            READBACK_NOT_ATTEMPTED,
            REJECTED,
            "",
            _canonical_hash(record),
            tuple(errors),
        )

    claim_id = str(evidence.get("execution_claim_id", ""))
    contradiction = record.get("contradicted_by")
    superseded = record.get("superseded_by")
    if contradiction:
        return LineageResult(
            False,
            preserved_truth,
            READBACK_NOT_ATTEMPTED,
            CONTRADICTED,
            claim_id,
            _canonical_hash(record),
            (),
        )
    if superseded:
        return LineageResult(
            False,
            preserved_truth,
            READBACK_NOT_ATTEMPTED,
            SUPERSEDED,
            claim_id,
            _canonical_hash(record),
            (),
        )

    if prior_state and prior_state not in {
        AUTHORITATIVE,
        UNESTABLISHED,
        READBACK_UNRESOLVED,
        CONTRADICTED,
        SUPERSEDED,
        REJECTED,
    }:
        errors.append("lineage.prior_truth_state is unknown")

    previous_hash = record.get("previous_record_hash")
    previous_record = record.get("previous_record")
    if previous_record is not None:
        if not isinstance(previous_record, Mapping):
            errors.append("lineage.previous_record must be an object")
        elif previous_hash != _canonical_hash(previous_record):
            errors.append("lineage.previous_record_hash does not match previous_record")

    verification = validate_execution_evidence(evidence, resolver=resolver)
    if verification.ok:
        if not errors:
            return LineageResult(
                True,
                AUTHORITATIVE,
                AUTHORITATIVE,
                AUTHORITATIVE,
                claim_id,
                _canonical_hash(record),
                (),
            )
        return LineageResult(
            False,
            AUTHORITATIVE,
            AUTHORITATIVE,
            REJECTED,
            claim_id,
            _canonical_hash(record),
            tuple(dict.fromkeys(errors)),
        )

    combined = tuple(dict.fromkeys([*errors, *verification.errors]))
    if verification.status == "provider_readback_unresolved" and not errors:
        # Preserve historical claim identity, but remove execution authority.
        return LineageResult(
            False,
            preserved_truth,
            READBACK_UNRESOLVED,
            READBACK_UNRESOLVED,
            claim_id,
            _canonical_hash(record),
            combined,
        )
    return LineageResult(
        False,
        preserved_truth,
        REJECTED,
        REJECTED,
        claim_id,
        _canonical_hash(record),
        combined,
    )
