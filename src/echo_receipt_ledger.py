"""Append-only forensic receipt ledger compatible with current polycentric runtime.

Donor provenance:
- feat/durable-workflow-machine/contracts/receipt.py
- feat/durable-workflow-machine/adapters/echo/store.py

This harvest preserves the donor's hash-chain/tamper-evidence mechanism without importing
RootTruth/single-owner authority. Provider-native receipts remain evidence about provider
facts; this ledger records and verifies evidence and never grants execution authority.
"""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any, Iterable

from src.verified_changeset import MutationReceipt


GENESIS_ROOT = "GENESIS_ROOT"


def receipt_payload(receipt: MutationReceipt) -> dict[str, Any]:
    return {
        "receipt_id": receipt.receipt_id,
        "mission_id": receipt.mission_id,
        "correlation_id": receipt.correlation_id,
        "result": receipt.result,
        "expected": receipt.expected,
        "observed": receipt.observed,
        "provider_receipt_ids": receipt.provider_receipt_ids,
        "previous_receipt_hash": receipt.previous_receipt_hash,
    }


def receipt_hash_matches_payload(receipt: MutationReceipt) -> bool:
    # Reconstruct through the current receipt contract so hashing semantics have one owner.
    reconstructed = MutationReceipt(**{**receipt_payload(receipt), "receipt_hash": ""})
    return bool(receipt.receipt_hash) and receipt.receipt_hash == reconstructed.receipt_hash


def audit_receipt_chain(receipts: Iterable[MutationReceipt]) -> dict[str, Any]:
    previous = GENESIS_ROOT
    count = 0
    for count, receipt in enumerate(receipts, start=1):
        if receipt.previous_receipt_hash != previous:
            return {
                "is_valid": False,
                "broken_at_index": count,
                "receipt_id": receipt.receipt_id,
                "reason": "previous_receipt_hash_mismatch",
                "expected_previous": previous,
                "observed_previous": receipt.previous_receipt_hash,
            }
        if not receipt_hash_matches_payload(receipt):
            return {
                "is_valid": False,
                "broken_at_index": count,
                "receipt_id": receipt.receipt_id,
                "reason": "payload_hash_mismatch",
            }
        previous = receipt.receipt_hash
    return {"is_valid": True, "total_receipts": count, "head_receipt_hash": previous}


class EchoReceiptLedger:
    """Append-only local evidence projection with chain verification on every append."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def read_all(self) -> tuple[MutationReceipt, ...]:
        if not self.path.exists():
            return ()
        receipts: list[MutationReceipt] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    payload = json.loads(line)
                    payload["provider_receipt_ids"] = tuple(payload.get("provider_receipt_ids", ()))
                    receipts.append(MutationReceipt(**payload))
        return tuple(receipts)

    def audit(self) -> dict[str, Any]:
        return audit_receipt_chain(self.read_all())

    def append(self, receipt: MutationReceipt) -> None:
        existing = self.read_all()
        expected_previous = existing[-1].receipt_hash if existing else GENESIS_ROOT
        if receipt.previous_receipt_hash != expected_previous:
            raise ValueError(
                f"receipt chain mismatch: expected {expected_previous}, got {receipt.previous_receipt_hash}"
            )
        if not receipt_hash_matches_payload(receipt):
            raise ValueError(f"receipt {receipt.receipt_id} payload hash mismatch")
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(receipt), sort_keys=True, default=list) + "\n")

        audit = self.audit()
        if not audit["is_valid"]:
            raise RuntimeError(f"receipt ledger failed post-append audit: {audit}")
