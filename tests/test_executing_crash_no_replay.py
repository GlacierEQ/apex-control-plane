"""Execution lease recovery must never replay uncertain local side effects.

Tests exercise the real durable JSONL scheduler and distinct process instances,
not a mocked ledger or invented provider receipt.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from continuous_control_plane import (
    ContinuousControlPlane, ControlEvent, JsonlControlStore,
    WorkState, load_continuous_control_config,
)

NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)


def plane(root: Path) -> ContinuousControlPlane:
    return ContinuousControlPlane.from_config(
        JsonlControlStore(root),
        load_continuous_control_config(ROOT / "config" / "continuous_control_plane.json"),
    )


def job(root: Path):
    cp = plane(root)
    item = cp.ingest_event(ControlEvent(
        event_type="gmail.reply.received", source_system="test",
        subject_id="mission-crash-guard", correlation_id="correlation-crash-guard",
        payload={"purpose": "crash lease recovery"},
    ))[0]
    return cp, item


def expire_invoked(cp: ContinuousControlPlane, item) -> None:
    claimed = cp.claim_next(
        worker_id="worker-before-crash", capabilities=[item.capability],
        now=NOW, lease_seconds=1,
    )
    assert claimed is not None and claimed.state is WorkState.DISPATCHED
    executing = cp.transition(item.work_id, WorkState.EXECUTING, reason="worker_invoked")
    assert executing.state is WorkState.EXECUTING
    assert executing.lease_expires_at == NOW + timedelta(seconds=1)


def test_crashed_executing_local_worker_without_receipt_requires_reconciliation(tmp_path):
    cp, item = job(tmp_path)
    expire_invoked(cp, item)
    after_crash = plane(tmp_path)
    called = []
    result = after_crash.execute_next_local(
        worker_id="replacement", capabilities=[item.capability],
        now=NOW + timedelta(seconds=2),
        executor=lambda claimed: called.append(claimed.work_id),
    )
    assert result["status"] == "idle"
    assert called == []
    assert after_crash.work[item.work_id].state is WorkState.RECONCILING
    assert plane(tmp_path).work[item.work_id].state is WorkState.RECONCILING
    assert plane(tmp_path).claim_next(
        worker_id="third", capabilities=[item.capability],
        now=NOW + timedelta(seconds=3),
    ) is None


def test_explicit_reconcile_no_receipt_executing_does_not_requeue(tmp_path):
    cp, item = job(tmp_path)
    expire_invoked(cp, item)
    after_crash = plane(tmp_path)
    changed = after_crash.reconcile_expired_leases(NOW + timedelta(seconds=2))
    assert len(changed) == 1
    assert changed[0].state is WorkState.RECONCILING
    assert changed[0].lease_owner is None
    assert plane(tmp_path).work[item.work_id].state is WorkState.RECONCILING
    assert after_crash.reconcile_expired_leases(NOW + timedelta(seconds=3)) == []


def test_explicit_reconcile_dispatched_receipt_cannot_be_replayed(tmp_path):
    from continuous_control_plane import ExecutionReceipt
    cp, item = job(tmp_path)
    claimed = cp.claim_next(
        worker_id="worker-before-crash", capabilities=[item.capability],
        now=NOW, lease_seconds=1,
    )
    assert claimed is not None
    cp.record_receipt_batch((ExecutionReceipt(
        work_id=item.work_id, mission_id=item.mission_id,
        correlation_id=item.correlation_id, receipt_kind="execution",
        status="verified", source_system="real-worker", details={"exit_code": 0},
    ),))
    after_crash = plane(tmp_path)
    changed = after_crash.reconcile_expired_leases(NOW + timedelta(seconds=2))
    assert len(changed) == 1
    assert changed[0].state is WorkState.RECONCILING
    assert plane(tmp_path).work[item.work_id].state is WorkState.RECONCILING


def test_stale_explicit_reconciler_cannot_clobber_new_active_lease(tmp_path):
    cp, item = job(tmp_path)
    first = cp.claim_next(
        worker_id="first", capabilities=[item.capability],
        now=NOW, lease_seconds=1,
    )
    assert first is not None
    stale_instance = plane(tmp_path)
    fresh_instance = plane(tmp_path)
    second = fresh_instance.claim_next(
        worker_id="second", capabilities=[item.capability],
        now=NOW + timedelta(seconds=2), lease_seconds=90,
    )
    assert second is not None and second.attempt == 2
    assert second.lease_owner == "second"
    # The stale instance remembers the first expired lease. It must refresh
    # inside the transaction before attempting any state transition.
    changed = stale_instance.reconcile_expired_leases(NOW + timedelta(seconds=3))
    assert changed == []
    current = plane(tmp_path).work[item.work_id]
    assert current.state is WorkState.DISPATCHED
    assert current.lease_owner == "second"
    assert current.attempt == 2


def test_expired_uninvoked_local_dispatch_remains_retriable(tmp_path):
    cp, item = job(tmp_path)
    assert cp.claim_next(
        worker_id="first", capabilities=[item.capability],
        now=NOW, lease_seconds=1,
    )
    changed = plane(tmp_path).reconcile_expired_leases(NOW + timedelta(seconds=2))
    assert len(changed) == 1
    assert changed[0].state is WorkState.RECEIVED
    resumed = plane(tmp_path).claim_next(
        worker_id="second", capabilities=[item.capability],
        now=NOW + timedelta(seconds=3),
    )
    assert resumed is not None and resumed.attempt == 2
