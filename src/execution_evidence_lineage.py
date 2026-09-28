"""Cross-run lineage authority for execution evidence.

A prior VERIFIED execution claim is not permanently authoritative merely because a
previous run verified it. Each continuation must independently re-resolve provider
evidence. If readback becomes unavailable, the claim is preserved as historical
state but loses authority until readback is restored. Contradicted or superseded
claims likewise cannot authorize continuation.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from execution_evidence_authority import EvidenceResolver, validate_execution_evidence

AUTHORITATIVE = "PROVIDER_VERIFIED"
READBACK_UNRESOLVED = "PROVIDER_READBACK_UNRESOLVED"
CONTRADICTED = "CONTRADICTED"
SUPERSEDED = "SUPERSEDED"
REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class LineageResult:
    authoritative: bool
    truth_state: str
    execution_claim_id: str
    record_hash: str
    errors: tuple[str, ...]


def _canonical_hash(record: Mapping[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def reconcile_execution_lineage(
    record: Mapping[str, Any], *, resolver: EvidenceResolver
) -> LineageResult:
    """Re-resolve a carried execution claim and assign its current truth state.

    The carried record is historical input, not authority. `execution_evidence`
    must independently pass the provider-evidence verifier on every run.
    """
    errors: list[str] = []
    evidence = record.get("execution_evidence")
    if not isinstance(evidence, Mapping):
        errors.append("lineage.execution_evidence must be an object")
        return LineageResult(False, REJECTED, "", _canonical_hash(record), tuple(errors))

    claim_id = str(evidence.get("execution_claim_id", ""))
    contradiction = record.get("contradicted_by")
    superseded = record.get("superseded_by")
    if contradiction:
        return LineageResult(False, CONTRADICTED, claim_id, _canonical_hash(record), ())
    if superseded:
        return LineageResult(False, SUPERSEDED, claim_id, _canonical_hash(record), ())

    prior_state = str(record.get("prior_truth_state", "")).strip().upper()
    if prior_state and prior_state not in {
        AUTHORITATIVE, READBACK_UNRESOLVED, CONTRADICTED, SUPERSEDED, REJECTED
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
    if verification.ok and not errors:
        return LineageResult(True, AUTHORITATIVE, claim_id, _canonical_hash(record), ())

    combined = tuple(dict.fromkeys([*errors, *verification.errors]))
    if verification.status == "provider_readback_unresolved" and not errors:
        # Preserve historical claim identity, but remove execution authority.
        return LineageResult(False, READBACK_UNRESOLVED, claim_id, _canonical_hash(record), combined)
    return LineageResult(False, REJECTED, claim_id, _canonical_hash(record), combined)
