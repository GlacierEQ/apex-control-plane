from __future__ import annotations
from dataclasses import replace
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

def plane(tmp_path, authorization_checker=None):
    return ContinuousControlPlane.from_config(
        JsonlControlStore(tmp_path),
        cfg(),
        authorization_checker=authorization_checker,
    )

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

def test_external_mutation_requires_verified_authorization_checker(tmp_path):
    allowed_ref = "source:operator-plan#auth=" + ("a" * 64)
    cp=plane(tmp_path, authorization_checker=lambda item, ref: ref == allowed_ref)
    work=cp.ingest_event(event("dockets.referral.ready"))[0]
    compile_work(cp,work.work_id)
    cp.claim_next(worker_id="case-worker",capabilities=[work.capability],now=NOW)
    cp.transition(work.work_id,WorkState.EXECUTING,reason="execute")
    cp.transition(work.work_id,WorkState.RECONCILING,reason="reconcile")
    cp.transition(work.work_id,WorkState.CHANGESET_READY,reason="ready")
    with pytest.raises(PermissionError):
        cp.transition(work.work_id,WorkState.MUTATING,reason="missing")
    with pytest.raises(PermissionError):
        cp.transition(work.work_id,WorkState.MUTATING,reason="fabricated",approval_ref="approval://operator/1")
    assert cp.transition(
        work.work_id,
        WorkState.MUTATING,
        reason="source-authorized",
        approval_ref=allowed_ref,
    ).state is WorkState.MUTATING

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


def test_executing_preserves_existing_claim_lease(tmp_path):
    cp=plane(tmp_path)
    work=cp.ingest_event(event())[0]
    compile_work(cp,work.work_id)
    claimed=cp.claim_next(worker_id="case-worker",capabilities=[work.capability],now=NOW,lease_seconds=30)
    assert claimed is not None
    executing=cp.transition(work.work_id,WorkState.EXECUTING,reason="execute")
    assert executing.lease_owner == "case-worker"
    assert executing.lease_expires_at == NOW + timedelta(seconds=30)


def test_stale_second_instance_cannot_double_claim(tmp_path):
    store=JsonlControlStore(tmp_path)
    cp1=ContinuousControlPlane.from_config(store,cfg())
    work=cp1.ingest_event(event())[0]
    compile_work(cp1,work.work_id)
    cp2=ContinuousControlPlane.from_config(JsonlControlStore(tmp_path),cfg())
    first=cp1.claim_next(worker_id="worker-1",capabilities=[work.capability],now=NOW)
    assert first is not None
    assert cp2.claim_next(worker_id="worker-2",capabilities=[work.capability],now=NOW) is None


def test_expired_dispatched_work_at_attempt_limit_dead_letters(tmp_path):
    cp=plane(tmp_path)
    work=cp.ingest_event(event())[0]
    compile_work(cp,work.work_id)
    claimed=cp.claim_next(worker_id="worker-1",capabilities=[work.capability],now=NOW,lease_seconds=1)
    assert claimed is not None
    exhausted=replace(claimed,max_attempts=claimed.attempt)
    cp.work[work.work_id]=exhausted
    cp.store.append_work(exhausted,reason="test_attempt_limit")
    changed=cp.reconcile_expired_leases(NOW+timedelta(seconds=2))
    assert changed[0].state is WorkState.DEAD_LETTER


def test_naive_now_is_rejected_explicitly(tmp_path):
    cp=plane(tmp_path)
    work=cp.ingest_event(event())[0]
    compile_work(cp,work.work_id)
    with pytest.raises(ValueError, match="timezone-aware"):
        cp.claim_next(
            worker_id="worker-1",
            capabilities=[work.capability],
            now=datetime(2026,9,3,9,15),
        )


def test_recovery_tolerates_only_torn_final_jsonl_line(tmp_path):
    cp=plane(tmp_path)
    work=cp.ingest_event(event())[0]
    with cp.store.work_path.open("ab") as handle:
        handle.write(b'{"work_id":"torn"')
    restored=plane(tmp_path)
    assert work.work_id in restored.work


def test_config_preserves_operator_identity_and_source_bound_authority():
    authority = cfg()["authority"]
    assert authority["operator"] == "OPERATOR"
    assert "source-bound" in authority["external_action"]
    assert "exact approval" not in authority["external_action"].lower()


def test_duplicate_event_repairs_missing_routed_work(tmp_path):
    store=JsonlControlStore(tmp_path)
    original=event()
    store.append_event(original)
    cp=ContinuousControlPlane.from_config(store,cfg())
    created=cp.ingest_event(original)
    assert len(created) == 1
    assert created[0].capability == "case.response.ingest"
    assert cp.ingest_event(original) == []


def test_provider_receipt_dedupe_is_scoped_by_source_system(tmp_path):
    cp=plane(tmp_path)
    work=cp.ingest_event(event())[0]
    first=ExecutionReceipt(
        work_id=work.work_id,
        mission_id=work.mission_id,
        correlation_id=work.correlation_id,
        receipt_kind="verification",
        status="verified",
        source_system="github",
        provider_receipt_id="provider-local-1",
        details={"source":"github"},
    )
    second=ExecutionReceipt(
        work_id=work.work_id,
        mission_id=work.mission_id,
        correlation_id=work.correlation_id,
        receipt_kind="verification",
        status="verified",
        source_system="buildkite",
        provider_receipt_id="provider-local-1",
        details={"source":"buildkite"},
    )
    cp.record_receipt(first)
    cp.record_receipt(second)
    assert {r.source_system for r in cp.receipts.values()} >= {"github","buildkite"}
