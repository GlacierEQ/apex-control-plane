"""
APEX CONTROL PLANE CONTRACTS: ECHO RECEIPT
Standard: Immutable, Hash-Chained Forensic Receipts for all State Mutations.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ECHOReceipt:
    receipt_id: str
    mission_id: str
    correlation_id: str
    step: str
    started_at_utc: float
    completed_at_utc: float
    inputs_hash: str
    expected_state: Dict[str, Any]
    observed_state: Dict[str, Any]
    external_ids: Dict[str, Any]
    result: str  # "VERIFIED", "FAILED", "ROLLED_BACK"
    previous_receipt_hash: str
    receipt_hash: str = ""

    def __post_init__(self):
        if not self.receipt_hash:
            payload = {
                "receipt_id": self.receipt_id,
                "mission_id": self.mission_id,
                "correlation_id": self.correlation_id,
                "step": self.step,
                "started_at": self.started_at_utc,
                "completed_at": self.completed_at_utc,
                "inputs_hash": self.inputs_hash,
                "expected": self.expected_state,
                "observed": self.observed_state,
                "external_ids": self.external_ids,
                "result": self.result,
                "previous_receipt_hash": self.previous_receipt_hash,
            }
            raw = json.dumps(payload, sort_keys=True)
            self.receipt_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def create(
        cls,
        mission_id: str,
        correlation_id: str,
        step: str,
        started_at: float,
        expected_state: Dict[str, Any],
        observed_state: Dict[str, Any],
        external_ids: Dict[str, Any],
        result: str,
        previous_receipt_hash: str = "GENESIS_ROOT",
        inputs_payload: Optional[Any] = None,
    ) -> ECHOReceipt:
        r_id = f"rcpt_{uuid.uuid4().hex[:12]}"
        now = time.time()
        in_hash = hashlib.sha256(
            json.dumps(inputs_payload or {}, sort_keys=True).encode("utf-8")
        ).hexdigest()

        return cls(
            receipt_id=r_id,
            mission_id=mission_id,
            correlation_id=correlation_id,
            step=step,
            started_at_utc=started_at,
            completed_at_utc=now,
            inputs_hash=in_hash,
            expected_state=expected_state,
            observed_state=observed_state,
            external_ids=external_ids,
            result=result,
            previous_receipt_hash=previous_receipt_hash,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
