import hashlib
import json

from execution_evidence_authority import derive_execution_claim_id
from execution_evidence_lineage import (
    AUTHORITATIVE,
    CONTRADICTED,
    READBACK_UNRESOLVED,
    REJECTED,
    SUPERSEDED,
    reconcile_execution_lineage,
)


def _sha(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _fixture():
    ref = "provider://github/actions/run/123"
    provider = "github"
    obj = "actions/run/123"
    source_sha = "abc123"
    operation = "merge-pr"
    claim_id = derive_execution_claim_id(
        provider=provider,
        provider_object_ref=obj,
        source_sha=source_sha,
        operation=operation,
    )
    provider_record = {
        "provider": provider,
        "provider_object_ref": obj,
        "source_sha": source_sha,
        "operation": operation,
        "execution_claim_id": claim_id,
        "state": "VERIFIED",
        "readback_verified": True,
        "verifier_ref": "provider://github/actions/run/123/readback",
    }
    payload = json.dumps(provider_record, sort_keys=True).encode()
    evidence = {
        "provider": provider,
        "provider_object_ref": obj,
        "source_sha": source_sha,
        "operation": operation,
        "execution_claim_id": claim_id,
        "state": "VERIFIED",
        "evidence_kind": "provider_api_response",
        "evidence_ref": ref,
        "evidence_sha256": _sha(payload),
    }
    return ref, payload, evidence


def test_verified_claim_must_be_re_read_from_provider():
    ref, payload, evidence = _fixture()
    result = reconcile_execution_lineage(
        {"prior_truth_state": "PROVIDER_VERIFIED", "execution_evidence": evidence},
        resolver=lambda requested: payload if requested == ref else (_ for _ in ()).throw(KeyError(requested)),
    )
    assert result.authoritative is True
    assert result.truth_state == AUTHORITATIVE


def test_prior_verified_claim_degrades_when_provider_readback_is_unavailable():
    _, _, evidence = _fixture()
    result = reconcile_execution_lineage(
        {"prior_truth_state": "PROVIDER_VERIFIED", "execution_evidence": evidence},
        resolver=lambda _: (_ for _ in ()).throw(ConnectionError("offline")),
    )
    assert result.authoritative is False
    assert result.truth_state == READBACK_UNRESOLVED
    assert result.execution_claim_id == evidence["execution_claim_id"]


def test_retrieval_failure_does_not_become_contradiction_or_absence():
    _, _, evidence = _fixture()
    result = reconcile_execution_lineage(
        {"prior_truth_state": "PROVIDER_VERIFIED", "execution_evidence": evidence},
        resolver=lambda _: (_ for _ in ()).throw(TimeoutError("timeout")),
    )
    assert result.truth_state == READBACK_UNRESOLVED
    assert result.truth_state not in {CONTRADICTED, SUPERSEDED, REJECTED}


def test_explicit_contradiction_quarantines_prior_verified_claim():
    ref, payload, evidence = _fixture()
    result = reconcile_execution_lineage(
        {
            "prior_truth_state": "PROVIDER_VERIFIED",
            "execution_evidence": evidence,
            "contradicted_by": "execution:replacement",
        },
        resolver=lambda _: payload,
    )
    assert result.authoritative is False
    assert result.truth_state == CONTRADICTED


def test_explicit_supersession_quarantines_prior_verified_claim():
    _, payload, evidence = _fixture()
    result = reconcile_execution_lineage(
        {
            "prior_truth_state": "PROVIDER_VERIFIED",
            "execution_evidence": evidence,
            "superseded_by": "execution:newer",
        },
        resolver=lambda _: payload,
    )
    assert result.authoritative is False
    assert result.truth_state == SUPERSEDED


def test_tampered_previous_lineage_record_is_rejected():
    ref, payload, evidence = _fixture()
    previous = {"truth_state": "PROVIDER_VERIFIED", "execution_claim_id": evidence["execution_claim_id"]}
    result = reconcile_execution_lineage(
        {
            "prior_truth_state": "PROVIDER_VERIFIED",
            "execution_evidence": evidence,
            "previous_record": previous,
            "previous_record_hash": "sha256:not-the-record",
        },
        resolver=lambda requested: payload if requested == ref else b"",
    )
    assert result.authoritative is False
    assert result.truth_state == REJECTED
