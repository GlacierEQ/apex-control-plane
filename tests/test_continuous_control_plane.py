from __future__ import annotations
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from continuous_control_plane import (
    ContinuousControlPlane, ControlEvent, ExecutionReceipt,
    JsonlControlStore, WorkState, load_continuous_control_config,
)

NOW = datetime(2026, 9, 3, 9, 15, tzinfo=UTC)

def cfg():
    return load_continuous_control_config(ROOT / "config" / "continuous_control_plane.json")

def plane(tmp_path):
    return ContinuousControlPlane.from_config(JsonlControlStore(tmp_path), cfg())

def event(kind="gmail.reply.received"):
    return ControlEvent(
        event_type=kind, source_system="gmail", subject_id="CASE-CHR-003",
        correlation_id="corr-1", occurred_at=NOW,
        payload={"message_id":"m-1","thread_id":"t-1"},
        provenance_refs=("gmail://message/m-1",),
    )

def compile_work(cp, wid):
    cp.transition(wid, WorkState.HYDRATING, reason="hydrate")
    cp.transition(wid, WorkState.COMPILED, reason="compile")

def test_event_deduplicates_and_routes_once(tmp_path):
    cp=plane(tmp_path)
    first=cp.ingest_event(event())
    assert first[0].capability=="case.response.ingest"
    assert cp.ingest_event(event())==[]

def test_external_mutation_requires_exact_approval(tmp_path):
    cp=plane(tmp_path)
    work=cp.ingest_event(event("dockets.referral.ready"))[0]
    compile_work(cp,work.work_id)
    cp.claim_next(worker_id="case-worker",capabilities=[work.capability],now=NOW)
    cp.transition(work.work_id,WorkState.EXECUTING,reason="execute",lease_owner="case-worker",lease_expires_at=NOW+timedelta(minutes=1))
    cp.transition(work.work_id,WorkState.RECONCILING,reason="reconcile")
    cp.transition(work.work_id,WorkState.CHANGESET_READY,reason="ready")
    with pytest.raises(PermissionError):
        cp.transition(work.work_id,WorkState.MUTATING,reason="send")
    assert cp.transition(work.work_id,WorkState.MUTATING,reason="approved",approval_ref="approval://operator/1").state is WorkState.MUTATING

def test_completion_requires_receipt(tmp_path):
    cp=plane(tmp_path)
    work=cp.ingest_event(event())[0]
    compile_work(cp,work.work_id)
    cp.transition(work.work_id,WorkState.DISPATCHED,reason="dispatch")
    cp.transition(work.work_id,WorkState.EXECUTING,reason="execute")
    cp.transition(work.work_id,WorkState.RECONCILING,reason="reconcile")
    cp.transition(work.work_id,WorkState.CHANGESET_READY,reason="ready")
    cp.transition(work.work_id,WorkState.VERIFYING,reason="verify")
    with pytest.raises(RuntimeError):
        cp.transition(work.work_id,WorkState.COMPLETE,reason="premature")
    cp.record_receipt(ExecutionReceipt(
        work_id=work.work_id,mission_id=work.mission_id,correlation_id=work.correlation_id,
        receipt_kind="verification",status="verified",source_system="apex",details={"ok":True},
    ))
    assert cp.transition(work.work_id,WorkState.COMPLETE,reason="verified").state is WorkState.COMPLETE

def test_expired_external_lease_reconciles_before_retry(tmp_path):
    cp=plane(tmp_path)
    work=cp.ingest_event(event("dockets.referral.ready"))[0]
    compile_work(cp,work.work_id)
    cp.claim_next(worker_id="case-worker",capabilities=[work.capability],now=NOW,lease_seconds=1)
    changed=cp.reconcile_expired_leases(NOW+timedelta(seconds=2))
    assert changed[0].state is WorkState.RECONCILING

def test_waiting_reawakens_and_restart_recovers(tmp_path):
    cp=plane(tmp_path)
    work=cp.ingest_event(event())[0]
    compile_work(cp,work.work_id)
    cp.transition(work.work_id,WorkState.DISPATCHED,reason="dispatch")
    cp.transition(work.work_id,WorkState.WAITING,reason="wait",not_before=NOW+timedelta(minutes=1))
    assert cp.reawaken_due(NOW)==[]
    assert cp.reawaken_due(NOW+timedelta(minutes=2))[0].state is WorkState.RECEIVED
    restored=plane(tmp_path)
    assert restored.work[work.work_id].state is WorkState.RECEIVED
    assert restored.snapshot()["missions"]==["CASE-CHR-003"]

def test_routes_cover_interconnected_domains():
    routes={row["event_type"]:row for row in cfg()["event_routes"]}
    for required in (
        "dockets.referral.ready","gmail.reply.received","call_e.call.completed",
        "calendar.follow_up.due","github.workflow.*","buildkite.build.*",
        "genius.progress.*","connector.health.degraded",
    ):
        assert required in routes
    assert routes["dockets.referral.ready"]["external_action"] is True
