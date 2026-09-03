"""Durable event/work/receipt kernel for the interconnected APEX control plane."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import Enum
from fnmatch import fnmatchcase
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(UTC)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_sha256(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _dt(value: str | datetime | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return parsed


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z") if value else None


class WorkState(str, Enum):
    RECEIVED = "RECEIVED"
    HYDRATING = "HYDRATING"
    COMPILED = "COMPILED"
    DISPATCHED = "DISPATCHED"
    EXECUTING = "EXECUTING"
    WAITING = "WAITING"
    RECONCILING = "RECONCILING"
    CHANGESET_READY = "CHANGESET_READY"
    MUTATING = "MUTATING"
    READBACK = "READBACK"
    VERIFYING = "VERIFYING"
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"
    DEAD_LETTER = "DEAD_LETTER"


ALLOWED_TRANSITIONS = {
    WorkState.RECEIVED: {WorkState.HYDRATING, WorkState.BLOCKED},
    WorkState.HYDRATING: {WorkState.COMPILED, WorkState.BLOCKED},
    WorkState.COMPILED: {WorkState.DISPATCHED, WorkState.BLOCKED},
    WorkState.DISPATCHED: {WorkState.EXECUTING, WorkState.WAITING, WorkState.RECONCILING, WorkState.BLOCKED},
    WorkState.EXECUTING: {WorkState.RECONCILING, WorkState.WAITING, WorkState.BLOCKED, WorkState.DEAD_LETTER},
    WorkState.WAITING: {WorkState.RECEIVED, WorkState.RECONCILING, WorkState.BLOCKED},
    WorkState.RECONCILING: {WorkState.CHANGESET_READY, WorkState.WAITING, WorkState.BLOCKED, WorkState.DEAD_LETTER},
    WorkState.CHANGESET_READY: {WorkState.MUTATING, WorkState.VERIFYING, WorkState.BLOCKED},
    WorkState.MUTATING: {WorkState.READBACK, WorkState.BLOCKED, WorkState.DEAD_LETTER},
    WorkState.READBACK: {WorkState.VERIFYING, WorkState.WAITING, WorkState.BLOCKED, WorkState.DEAD_LETTER},
    WorkState.VERIFYING: {WorkState.COMPLETE, WorkState.WAITING, WorkState.BLOCKED, WorkState.DEAD_LETTER},
    WorkState.BLOCKED: {WorkState.RECEIVED, WorkState.RECONCILING, WorkState.DEAD_LETTER},
    WorkState.DEAD_LETTER: {WorkState.RECEIVED, WorkState.RECONCILING},
    WorkState.COMPLETE: set(),
}


@dataclass(frozen=True, slots=True)
class ControlEvent:
    event_type: str
    source_system: str
    subject_id: str
    payload: Mapping[str, Any]
    correlation_id: str
    event_id: str = field(default_factory=lambda: str(uuid4()))
    causation_id: str | None = None
    occurred_at: datetime = field(default_factory=utc_now)
    provenance_refs: tuple[str, ...] = ()
    dedupe_key: str | None = None

    def __post_init__(self) -> None:
        if not self.event_type.strip() or not self.source_system.strip() or not self.subject_id.strip():
            raise ValueError("event_type, source_system, and subject_id are required")
        if not self.correlation_id.strip():
            raise ValueError("correlation_id is required")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")

    @property
    def stable_dedupe_key(self) -> str:
        return self.dedupe_key or canonical_sha256({
            "event_type": self.event_type,
            "source_system": self.source_system,
            "subject_id": self.subject_id,
            "payload": self.payload,
            "correlation_id": self.correlation_id,
            "provenance_refs": self.provenance_refs,
        })

    def record(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source_system": self.source_system,
            "subject_id": self.subject_id,
            "payload": dict(self.payload),
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "occurred_at": _iso(self.occurred_at),
            "provenance_refs": list(self.provenance_refs),
            "dedupe_key": self.stable_dedupe_key,
            "payload_sha256": canonical_sha256(self.payload),
        }

    @classmethod
    def from_record(cls, row: Mapping[str, Any]) -> "ControlEvent":
        return cls(
            event_id=str(row["event_id"]),
            event_type=str(row["event_type"]),
            source_system=str(row["source_system"]),
            subject_id=str(row["subject_id"]),
            payload=dict(row.get("payload") or {}),
            correlation_id=str(row["correlation_id"]),
            causation_id=row.get("causation_id"),
            occurred_at=_dt(str(row["occurred_at"])) or utc_now(),
            provenance_refs=tuple(row.get("provenance_refs") or ()),
            dedupe_key=str(row["dedupe_key"]),
        )


@dataclass(frozen=True, slots=True)
class WorkItem:
    mission_id: str
    correlation_id: str
    domain: str
    capability: str
    objective: str
    idempotency_key: str
    work_id: str = field(default_factory=lambda: str(uuid4()))
    state: WorkState = WorkState.RECEIVED
    priority: int = 50
    external_action: bool = False
    approval_ref: str | None = None
    source_event_ids: tuple[str, ...] = ()
    required_receipt_kinds: tuple[str, ...] = ()
    not_before: datetime | None = None
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    attempt: int = 0
    max_attempts: int = 5
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def record(self) -> dict[str, Any]:
        row = asdict(self)
        row["state"] = self.state.value
        for key in ("created_at", "updated_at", "not_before", "lease_expires_at"):
            row[key] = _iso(getattr(self, key))
        row["source_event_ids"] = list(self.source_event_ids)
        row["required_receipt_kinds"] = list(self.required_receipt_kinds)
        row["metadata"] = dict(self.metadata)
        return row

    @classmethod
    def from_record(cls, row: Mapping[str, Any]) -> "WorkItem":
        return cls(
            work_id=str(row["work_id"]), mission_id=str(row["mission_id"]),
            correlation_id=str(row["correlation_id"]), domain=str(row["domain"]),
            capability=str(row["capability"]), objective=str(row["objective"]),
            idempotency_key=str(row["idempotency_key"]), state=WorkState(str(row["state"])),
            priority=int(row.get("priority", 50)), external_action=bool(row.get("external_action", False)),
            approval_ref=row.get("approval_ref"), source_event_ids=tuple(row.get("source_event_ids") or ()),
            required_receipt_kinds=tuple(row.get("required_receipt_kinds") or ()),
            not_before=_dt(row.get("not_before")), lease_owner=row.get("lease_owner"),
            lease_expires_at=_dt(row.get("lease_expires_at")), attempt=int(row.get("attempt", 0)),
            max_attempts=int(row.get("max_attempts", 5)), created_at=_dt(row.get("created_at")) or utc_now(),
            updated_at=_dt(row.get("updated_at")) or utc_now(), metadata=dict(row.get("metadata") or {}),
        )


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    work_id: str
    mission_id: str
    correlation_id: str
    receipt_kind: str
    status: str
    source_system: str
    details: Mapping[str, Any]
    receipt_id: str = field(default_factory=lambda: str(uuid4()))
    provider_receipt_id: str | None = None
    recorded_at: datetime = field(default_factory=utc_now)

    def record(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "recorded_at": _iso(self.recorded_at),
            "details": dict(self.details),
            "details_sha256": canonical_sha256(self.details),
        }

    @classmethod
    def from_record(cls, row: Mapping[str, Any]) -> "ExecutionReceipt":
        return cls(
            receipt_id=str(row["receipt_id"]), work_id=str(row["work_id"]),
            mission_id=str(row["mission_id"]), correlation_id=str(row["correlation_id"]),
            receipt_kind=str(row["receipt_kind"]), status=str(row["status"]),
            source_system=str(row["source_system"]), details=dict(row.get("details") or {}),
            provider_receipt_id=row.get("provider_receipt_id"),
            recorded_at=_dt(row.get("recorded_at")) or utc_now(),
        )


class JsonlControlStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.events_path = self.root / "events.jsonl"
        self.work_path = self.root / "work.jsonl"
        self.receipts_path = self.root / "receipts.jsonl"
        self.checkpoints_path = self.root / "checkpoints.jsonl"

    @staticmethod
    def _append(path: Path, row: Mapping[str, Any]) -> None:
        encoded = (canonical_json(row) + "\n").encode("utf-8")
        with path.open("ab") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _read(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        rows = []
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"corrupt control-plane JSONL {path}:{number}") from exc
            if not isinstance(row, dict):
                raise RuntimeError(f"control-plane record must be an object: {path}:{number}")
            rows.append(row)
        return rows

    def append_event(self, event: ControlEvent) -> None:
        self._append(self.events_path, event.record())

    def append_work(self, item: WorkItem, *, reason: str) -> None:
        self._append(self.work_path, {"reason": reason, **item.record()})

    def append_receipt(self, receipt: ExecutionReceipt) -> None:
        self._append(self.receipts_path, receipt.record())

    def append_checkpoint(self, row: Mapping[str, Any]) -> None:
        self._append(self.checkpoints_path, row)

    def recover(self):
        events = {row["event_id"]: ControlEvent.from_record(row) for row in self._read(self.events_path)}
        work: dict[str, WorkItem] = {}
        for row in self._read(self.work_path):
            work[str(row["work_id"])] = WorkItem.from_record(row)
        receipts = {row["receipt_id"]: ExecutionReceipt.from_record(row) for row in self._read(self.receipts_path)}
        return events, work, receipts


class ContinuousControlPlane:
    def __init__(self, store: JsonlControlStore, routes: Iterable[Mapping[str, Any]] = ()) -> None:
        self.store = store
        self.routes = tuple(dict(route) for route in routes)
        self.events, self.work, self.receipts = store.recover()
        self._event_dedupe = {event.stable_dedupe_key for event in self.events.values()}
        self._work_idempotency = {item.idempotency_key: item.work_id for item in self.work.values()}

    @classmethod
    def from_config(cls, store: JsonlControlStore, config: Mapping[str, Any]) -> "ContinuousControlPlane":
        return cls(store, config.get("event_routes") or ())

    def ingest_event(self, event: ControlEvent) -> list[WorkItem]:
        if event.stable_dedupe_key in self._event_dedupe:
            return []
        self.store.append_event(event)
        self.events[event.event_id] = event
        self._event_dedupe.add(event.stable_dedupe_key)
        created = []
        for route in self.routes:
            pattern = str(route.get("event_type") or "")
            if not pattern or not fnmatchcase(event.event_type, pattern):
                continue
            key = canonical_sha256({"route": route, "event": event.stable_dedupe_key})
            created.append(self.submit_work(
                mission_id=event.subject_id, correlation_id=event.correlation_id,
                domain=str(route["domain"]), capability=str(route["capability"]),
                objective=str(route["objective"]), idempotency_key=key,
                priority=int(route.get("priority", 50)), external_action=bool(route.get("external_action", False)),
                source_event_ids=(event.event_id,), required_receipt_kinds=tuple(route.get("required_receipt_kinds") or ()),
                metadata={"route_event_type": pattern},
            ))
        self.checkpoint(event.subject_id)
        return created

    def submit_work(self, *, mission_id: str, correlation_id: str, domain: str,
                    capability: str, objective: str, idempotency_key: str,
                    priority: int = 50, external_action: bool = False,
                    approval_ref: str | None = None, source_event_ids: tuple[str, ...] = (),
                    required_receipt_kinds: tuple[str, ...] = (),
                    not_before: datetime | None = None,
                    metadata: Mapping[str, Any] | None = None) -> WorkItem:
        existing = self._work_idempotency.get(idempotency_key)
        if existing:
            return self.work[existing]
        item = WorkItem(
            mission_id=mission_id, correlation_id=correlation_id, domain=domain,
            capability=capability, objective=objective, idempotency_key=idempotency_key,
            priority=max(0, min(100, priority)), external_action=external_action,
            approval_ref=approval_ref, source_event_ids=source_event_ids,
            required_receipt_kinds=required_receipt_kinds, not_before=not_before,
            metadata=dict(metadata or {}),
        )
        self.work[item.work_id] = item
        self._work_idempotency[idempotency_key] = item.work_id
        self.store.append_work(item, reason="submitted")
        return item

    def transition(self, work_id: str, target: WorkState, *, reason: str,
                   approval_ref: str | None = None, not_before: datetime | None = None,
                   lease_owner: str | None = None, lease_expires_at: datetime | None = None) -> WorkItem:
        current = self.work[work_id]
        if target not in ALLOWED_TRANSITIONS[current.state]:
            raise ValueError(f"invalid work transition {current.state.value}->{target.value}")
        effective_approval = approval_ref or current.approval_ref
        if target is WorkState.MUTATING and current.external_action and not effective_approval:
            raise PermissionError("external mutation requires an exact approval_ref")
        if target is WorkState.COMPLETE:
            present = {
                r.receipt_kind for r in self.receipts.values()
                if r.work_id == work_id and r.status.casefold() in {"pass", "passed", "success", "succeeded", "verified"}
            }
            missing = sorted(set(current.required_receipt_kinds) - present)
            if missing:
                raise RuntimeError("completion denied; missing receipt kinds: " + ", ".join(missing))
        updated = replace(
            current, state=target, approval_ref=effective_approval,
            not_before=not_before if target is WorkState.WAITING else current.not_before,
            lease_owner=lease_owner if target in {WorkState.DISPATCHED, WorkState.EXECUTING} else None,
            lease_expires_at=lease_expires_at if target in {WorkState.DISPATCHED, WorkState.EXECUTING} else None,
            updated_at=utc_now(),
        )
        self.work[work_id] = updated
        self.store.append_work(updated, reason=reason)
        self.checkpoint(updated.mission_id)
        return updated

    def record_receipt(self, receipt: ExecutionReceipt) -> ExecutionReceipt:
        current = self.work[receipt.work_id]
        if receipt.mission_id != current.mission_id or receipt.correlation_id != current.correlation_id:
            raise ValueError("receipt mission/correlation does not match work item")
        for existing in self.receipts.values():
            if receipt.provider_receipt_id and existing.provider_receipt_id == receipt.provider_receipt_id:
                return existing
        self.store.append_receipt(receipt)
        self.receipts[receipt.receipt_id] = receipt
        self.checkpoint(receipt.mission_id)
        return receipt

    def claim_next(self, *, worker_id: str, capabilities: Iterable[str],
                   now: datetime | None = None, lease_seconds: int = 90) -> WorkItem | None:
        instant = now or utc_now()
        supported = set(capabilities)
        candidates = [
            item for item in self.work.values()
            if item.state is WorkState.COMPILED and item.capability in supported
            and (item.not_before is None or item.not_before <= instant)
            and (item.lease_expires_at is None or item.lease_expires_at <= instant)
            and item.attempt < item.max_attempts
        ]
        if not candidates:
            return None
        chosen = sorted(candidates, key=lambda item: (-item.priority, item.created_at, item.work_id))[0]
        dispatched = replace(
            chosen, state=WorkState.DISPATCHED, lease_owner=worker_id,
            lease_expires_at=instant + timedelta(seconds=max(1, lease_seconds)),
            attempt=chosen.attempt + 1, updated_at=instant,
        )
        self.work[chosen.work_id] = dispatched
        self.store.append_work(dispatched, reason="claimed")
        self.checkpoint(dispatched.mission_id)
        return dispatched

    def reawaken_due(self, now: datetime | None = None) -> list[WorkItem]:
        instant = now or utc_now()
        return [
            self.transition(item.work_id, WorkState.RECEIVED, reason="waiting_deadline_due")
            for item in list(self.work.values())
            if item.state is WorkState.WAITING and item.not_before is not None and item.not_before <= instant
        ]

    def reconcile_expired_leases(self, now: datetime | None = None) -> list[WorkItem]:
        instant = now or utc_now()
        changed = []
        for item in list(self.work.values()):
            if item.state not in {WorkState.DISPATCHED, WorkState.EXECUTING}:
                continue
            if item.lease_expires_at is None or item.lease_expires_at > instant:
                continue
            if item.external_action:
                target, reason = WorkState.RECONCILING, "external_action_lease_expired_reconcile_before_retry"
            elif item.attempt >= item.max_attempts:
                target, reason = WorkState.DEAD_LETTER, "max_attempts_exhausted"
            else:
                target, reason = WorkState.BLOCKED, "lease_expired_requires_recovery"
            changed.append(self.transition(item.work_id, target, reason=reason))
        return changed

    def checkpoint(self, mission_id: str) -> dict[str, Any]:
        items = [item for item in self.work.values() if item.mission_id == mission_id]
        receipts = [r for r in self.receipts.values() if r.mission_id == mission_id]
        frontier = [
            {"work_id": i.work_id, "capability": i.capability, "state": i.state.value, "priority": i.priority}
            for i in sorted((i for i in items if i.state is not WorkState.COMPLETE), key=lambda x: (-x.priority, x.created_at))
        ]
        row = {
            "mission_id": mission_id, "recorded_at": _iso(utc_now()), "frontier": frontier,
            "work_states": {s.value: sum(1 for i in items if i.state is s) for s in WorkState},
            "receipt_count": len(receipts),
        }
        row["checkpoint_sha256"] = canonical_sha256(row)
        self.store.append_checkpoint(row)
        return row

    def snapshot(self) -> dict[str, Any]:
        return {
            "observed_at": _iso(utc_now()), "events": len(self.events),
            "work": len(self.work), "receipts": len(self.receipts),
            "states": {s.value: sum(1 for i in self.work.values() if i.state is s) for s in WorkState},
            "missions": sorted({i.mission_id for i in self.work.values()} | {e.subject_id for e in self.events.values()}),
        }


def load_continuous_control_config(path: Path | str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if int(payload.get("schema_version", 0)) != 1:
        raise ValueError("unsupported continuous-control-plane schema")
    if payload.get("control_plane") != "GlacierEQ/apex-control-plane":
        raise ValueError("continuous-control-plane authority must be GlacierEQ/apex-control-plane")
    return payload
