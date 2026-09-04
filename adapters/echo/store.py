"""
APEX ECHO RECEIPT STORE
Standard: Append-only cryptographic ledger of state mutations.
Answers: 'Why do we believe that, and what happened to produce it?'
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from contracts.receipt import ECHOReceipt


class ECHOStore:
    """
    Append-only hash-chained ledger storing immutable mutation receipts.
    """

    def __init__(self, log_path: Optional[Path] = None):
        package_root = Path(__file__).resolve().parent.parent.parent
        self.path = log_path or (package_root / "data" / "echo_receipts.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def get_last_receipt(self) -> Optional[ECHOReceipt]:
        if not self.path.exists():
            return None
        last_line = None
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last_line = line.strip()
        if not last_line:
            return None
        data = json.loads(last_line)
        return ECHOReceipt(**data)

    def append_receipt(self, receipt: ECHOReceipt) -> None:
        last = self.get_last_receipt()
        if last:
            if receipt.previous_receipt_hash != last.receipt_hash:
                raise ValueError(
                    f"Hash chain broken! Expected previous {last.receipt_hash}, got {receipt.previous_receipt_hash}"
                )
        else:
            if receipt.previous_receipt_hash != "GENESIS_ROOT":
                raise ValueError(
                    "First receipt must anchor to GENESIS_ROOT, "
                    f"got {receipt.previous_receipt_hash}"
                )
        if not receipt.hash_matches_payload():
            raise ValueError(
                f"Receipt {receipt.receipt_id} hash does not match payload"
            )

        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(receipt.to_dict()) + "\n")

    def get_receipts_for_mission(self, mission_id: str) -> List[ECHOReceipt]:
        if not self.path.exists():
            return []
        results = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    d = json.loads(line.strip())
                    if d.get("mission_id") == mission_id:
                        results.append(ECHOReceipt(**d))
        return results

    def verify_chain_integrity(self) -> bool:
        return self.audit_chain().get("is_valid", False)

    def audit_chain(self) -> Dict[str, Any]:
        """
        Forensic audit of the append-only cryptographic receipt chain.
        Returns complete diagnostic receipt verifying 100% SHA-256 link integrity.
        """
        if not self.path.exists():
            return {"is_valid": True, "total_receipts": 0}
        prev_hash = "GENESIS_ROOT"
        count = 0
        with open(self.path, "r", encoding="utf-8") as f:
            for line_idx, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                count += 1
                d = json.loads(line.strip())
                rcpt = ECHOReceipt(**d)
                if count == 1 and rcpt.previous_receipt_hash != "GENESIS_ROOT":
                    return {
                        "is_valid": False,
                        "broken_at_index": count,
                        "receipt_id": rcpt.receipt_id,
                        "expected_prev": "GENESIS_ROOT",
                        "observed_prev": rcpt.previous_receipt_hash,
                        "total_checked": count,
                    }
                if count > 1 and rcpt.previous_receipt_hash != prev_hash:
                    return {
                        "is_valid": False,
                        "broken_at_index": count,
                        "receipt_id": rcpt.receipt_id,
                        "expected_prev": prev_hash,
                        "observed_prev": rcpt.previous_receipt_hash,
                        "total_checked": count,
                    }
                if not rcpt.hash_matches_payload():
                    return {
                        "is_valid": False,
                        "broken_at_index": count,
                        "receipt_id": rcpt.receipt_id,
                        "reason": "payload_hash_mismatch",
                        "stored_hash": rcpt.receipt_hash,
                        "recomputed_hash": rcpt.compute_payload_hash(),
                        "total_checked": count,
                    }
                prev_hash = rcpt.receipt_hash
        return {"is_valid": True, "total_receipts": count, "head_receipt_hash": prev_hash}
