from dataclasses import replace

import pytest

from src.echo_receipt_ledger import EchoReceiptLedger, audit_receipt_chain
from src.verified_changeset import MutationReceipt


def _receipt(*, previous="GENESIS_ROOT", result="VERIFIED"):
    return MutationReceipt(
        mission_id="mission-1",
        correlation_id="corr-1",
        result=result,
        expected={"sha": "new"},
        observed={"sha": "new"},
        provider_receipt_ids=("github:123",),
        previous_receipt_hash=previous,
    )


def test_append_and_audit_hash_chained_receipts(tmp_path):
    ledger = EchoReceiptLedger(tmp_path / "echo.jsonl")
    first = _receipt()
    second = _receipt(previous=first.receipt_hash)
    ledger.append(first)
    ledger.append(second)
    audit = ledger.audit()
    assert audit["is_valid"]
    assert audit["total_receipts"] == 2
    assert audit["head_receipt_hash"] == second.receipt_hash


def test_append_rejects_broken_previous_hash(tmp_path):
    ledger = EchoReceiptLedger(tmp_path / "echo.jsonl")
    ledger.append(_receipt())
    with pytest.raises(ValueError, match="receipt chain mismatch"):
        ledger.append(_receipt(previous="wrong"))


def test_audit_detects_payload_tampering():
    original = _receipt()
    tampered = replace(original, observed={"sha": "tampered"})
    audit = audit_receipt_chain([tampered])
    assert not audit["is_valid"]
    assert audit["reason"] == "payload_hash_mismatch"


def test_provider_receipts_are_evidence_not_authority(tmp_path):
    ledger = EchoReceiptLedger(tmp_path / "echo.jsonl")
    receipt = _receipt()
    ledger.append(receipt)
    loaded = ledger.read_all()[0]
    assert loaded.provider_receipt_ids == ("github:123",)
    assert not hasattr(loaded, "approval")
    assert not hasattr(loaded, "authority_grant")
