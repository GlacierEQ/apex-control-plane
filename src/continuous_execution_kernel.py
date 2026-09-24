"""Durable execution primitives harvested from continuous-control-plane-v1.

Donor provenance: continuous-control-plane-v1/src/continuous_control_plane.py.
The donor's blanket external_action -> exact approval_ref gate is intentionally NOT
transplanted. Authority is attributable source evidence, not a fresh permission gate.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Mapping
from uuid import uuid4

from source_bound_authorization import SourceBoundAuthorization, authorize_constituent_action


def _now() -> datetime:
    return datetime.now(UTC)


def _digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


class ExecutionState(str, Enum):
    RECEIVED = "RECEIVED"
    EXECUTING = "EXECUTING"
    WAITING = "WAITING"
    MUTATING = "MUTATING"
    READBACK = "READBACK"
    VERIFYING = "VERIFYING"
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class DurableEvent:
    event_type: str
    source_system: str
    subject_id: str
    payload: Mapping[str, Any]
    correlation_id: str
    provenance_refs: tuple[str, ...] = ()
    event_id: str = field(default_factory=lambda: str(uuid4()))

    @property
    def dedupe_key(self) -> str:
        return _digest({"event_type": self.event_type, "source_system": self.source_system,
                        "subject_id": self.subject_id, "payload": self.payload,
                        "correlation_id": self.correlation_id,
                        "provenance_refs": self.provenance_refs})


@dataclass(frozen=True, slots=True)
class DurableWork:
    mission_id: str
    correlation_id: str
    objective: str
    idempotency_key: str
    work_id: str = field(default_factory=lambda: str(uuid4()))
    state: ExecutionState = ExecutionState.RECEIVED
    required_receipts: tuple[str, ...] = ()
    authority_source_ref: str | None = None
    authority_envelope_sha256: str | None = None
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    attempt: int = 0


@dataclass(frozen=True, slots=True)
class ProviderReceipt:
    work_id: str
    receipt_kind: str
    provider: str
    status: str
    provider_receipt_id: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)
    receipt_id: str = field(default_factory=lambda: str(uuid4()))


class ContinuousExecutionKernel:
    """Idempotent work/lease/receipt kernel without a permission union."""

    def __init__(self) -> None:
        self.work: dict[str, DurableWork] = {}
        self.by_idempotency: dict[str, str] = {}
        self.receipts: dict[str, ProviderReceipt] = {}

    def submit(self, item: DurableWork) -> DurableWork:
        existing = self.by_idempotency.get(item.idempotency_key)
        if existing:
            return self.work[existing]
        self.work[item.work_id] = item
        self.by_idempotency[item.idempotency_key] = item.work_id
        return item

    def bind_authority(self, work_id: str, authorization: SourceBoundAuthorization, *,
                       connector: str, operation: str, target: Mapping[str, Any],
                       destructive: bool = False, material_strategy_delta: bool = False) -> DurableWork:
        digest = authorize_constituent_action(
            authorization, connector=connector, operation=operation, target=target,
            destructive=destructive, material_strategy_delta=material_strategy_delta,
        )
        current = self.work[work_id]
        bound = replace(current, authority_source_ref=authorization.source_ref,
                        authority_envelope_sha256=digest)
        self.work[work_id] = bound
        return bound

    def acquire_lease(self, work_id: str, owner: str, *, seconds: int = 300) -> DurableWork:
        current = self.work[work_id]
        now = _now()
        if current.lease_owner and current.lease_expires_at and current.lease_expires_at > now and current.lease_owner != owner:
            raise RuntimeError("work lease is active")
        leased = replace(current, lease_owner=owner, lease_expires_at=now + timedelta(seconds=seconds),
                         attempt=current.attempt + 1)
        self.work[work_id] = leased
        return leased

    def reconcile_expired_lease(self, work_id: str, *, now: datetime | None = None) -> DurableWork:
        current = self.work[work_id]
        at = now or _now()
        if current.lease_expires_at and current.lease_expires_at <= at:
            current = replace(current, lease_owner=None, lease_expires_at=None, state=ExecutionState.WAITING)
            self.work[work_id] = current
        return current

    def record_receipt(self, receipt: ProviderReceipt) -> ProviderReceipt:
        self.receipts[receipt.receipt_id] = receipt
        return receipt

    def missing_receipts(self, work_id: str) -> tuple[str, ...]:
        item = self.work[work_id]
        present = {r.receipt_kind for r in self.receipts.values() if r.work_id == work_id and r.status.lower() in {"success", "verified", "complete"}}
        return tuple(kind for kind in item.required_receipts if kind not in present)

    def complete(self, work_id: str) -> DurableWork:
        missing = self.missing_receipts(work_id)
        if missing:
            raise RuntimeError(f"required receipts missing: {', '.join(missing)}")
        completed = replace(self.work[work_id], state=ExecutionState.COMPLETE, lease_owner=None, lease_expires_at=None)
        self.work[work_id] = completed
        return completed
