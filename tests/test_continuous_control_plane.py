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


def test_expired_dispatched_work_continues_beyond_legacy_attempt_count(tmp_path):
    cp=plane(tmp_path)
    work=cp.ingest_event(event())[0]
    compile_work(cp,work.work_id)
    claimed=cp.claim_next(worker_id="worker-1",capabilities=[work.capability],now=NOW,lease_seconds=1)
    assert claimed is not None
    exhausted=replace(claimed,max_attempts=claimed.attempt)
    cp.work[work.work_id]=exhausted
    cp.store.append_work(exhausted,reason="legacy_retry_counter_reached")
    changed=cp.reconcile_expired_leases(NOW+timedelta(seconds=2))
    assert changed[0].state is WorkState.RECEIVED
    recovered=plane(tmp_path)
    next_attempt=recovered.claim_next(
        worker_id="recovery-worker",capabilities=[work.capability],now=NOW+timedelta(seconds=3)
    )
    assert next_attempt is not None
    assert next_attempt.work_id == work.work_id
    assert next_attempt.attempt == claimed.attempt + 1
    assert next_attempt.state is WorkState.DISPATCHED


def test_atomic_lease_recovery_does_not_dead_letter_at_legacy_zero_budget(tmp_path):
    cp = plane(tmp_path)
    work = cp.ingest_event(event())[0]
    original = cp.claim_next(
        worker_id="first-worker", capabilities=[work.capability], now=NOW, lease_seconds=1
    )
    assert original is not None
    old_budget = replace(original, max_attempts=0)
    cp.work[work.work_id] = old_budget
    cp.store.append_work(old_budget, reason="preexisting_zero_legacy_retry_budget")

    another_instance = plane(tmp_path)
    attempt = another_instance.claim_next(
        worker_id="new-worker", capabilities=[work.capability], now=NOW+timedelta(seconds=5)
    )
    assert attempt is not None
    assert attempt.work_id == original.work_id
    assert attempt.state is WorkState.DISPATCHED
    assert attempt.attempt == 2


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


def test_imminent_filing_preempts_forensic_worker(tmp_path):
    cp = plane(tmp_path)
    forensic = cp.submit_work(
        mission_id="case-deadline", correlation_id="corr-urgent",
        domain="case", capability="case.worker", objective="Forensic hashes",
        idempotency_key="forensic-job", priority=100,
        metadata={"action_kind": "forensic_hash"},
    )
    filing = cp.submit_work(
        mission_id="case-deadline", correlation_id="corr-urgent",
        domain="case", capability="case.worker", objective="Submit filing",
        idempotency_key="filing-job", priority=1,
        metadata={"action_kind": "court_filing", "deadline_status": "verified",
                  "deadline_at": (NOW + timedelta(hours=1)).isoformat(),
                  "deadline_source_ref": "court:verified-case-deadline"},
    )
    compile_work(cp, forensic.work_id)
    compile_work(cp, filing.work_id)
    chosen = cp.claim_next(worker_id="worker", capabilities=["case.worker"], now=NOW)
    assert chosen is not None
    assert chosen.work_id == filing.work_id


def test_unverified_or_expired_deadline_cannot_preempt(tmp_path):
    cp = plane(tmp_path)
    baseline = cp.submit_work(
        mission_id="case-deadline", correlation_id="corr-ordinary",
        domain="case", capability="case.worker", objective="Higher priority",
        idempotency_key="ordinary-priority", priority=70,
    )
    unverified = cp.submit_work(
        mission_id="case-deadline", correlation_id="corr-ordinary",
        domain="case", capability="case.worker", objective="Unverified claim",
        idempotency_key="unverified-claim", priority=1,
        metadata={"action_kind": "court_filing", "deadline_status": "unknown",
                  "deadline_at": (NOW + timedelta(hours=1)).isoformat(),
                  "deadline_source_ref": "court:unverified"},
    )
    expired = cp.submit_work(
        mission_id="case-deadline", correlation_id="corr-ordinary",
        domain="case", capability="case.worker", objective="Expired filing window",
        idempotency_key="expired-filing", priority=1,
        metadata={"action_kind": "court_filing", "deadline_status": "verified",
                  "deadline_at": (NOW - timedelta(days=1)).isoformat(),
                  "deadline_source_ref": "court:past-cutoff"},
    )
    for item in (baseline, unverified, expired):
        compile_work(cp, item.work_id)
    chosen = cp.claim_next(worker_id="worker", capabilities=["case.worker"], now=NOW)
    assert chosen is not None
    assert chosen.work_id == baseline.work_id


def test_deadline_preemption_does_not_authorize_mutation(tmp_path):
    cp = plane(tmp_path)
    filing = cp.submit_work(
        mission_id="case-deadline", correlation_id="corr-auth",
        domain="case", capability="case.worker", objective="File complaint",
        idempotency_key="filing-with-auth", priority=1, external_action=True,
        metadata={"action_kind": "court_filing", "deadline_status": "verified",
                  "deadline_at": (NOW + timedelta(hours=1)).isoformat(),
                  "deadline_source_ref": "court:filing-cutoff"},
    )
    compile_work(cp, filing.work_id)
    claimed = cp.claim_next(worker_id="worker", capabilities=["case.worker"], now=NOW)
    assert claimed is not None
    assert claimed.work_id == filing.work_id
    cp.transition(filing.work_id, WorkState.EXECUTING, reason="execute")
    cp.transition(filing.work_id, WorkState.RECONCILING, reason="reconcile")
    cp.transition(filing.work_id, WorkState.CHANGESET_READY, reason="ready")
    with pytest.raises(PermissionError, match="authorization"):
        cp.transition(filing.work_id, WorkState.MUTATING, reason="not-authorized")


def test_newly_submitted_work_is_claimable_without_manual_compile(tmp_path):
    cp = plane(tmp_path)
    work = cp.ingest_event(event())[0]
    assert work.state is WorkState.RECEIVED
    claimed = cp.claim_next(worker_id="worker-direct", capabilities=[work.capability], now=NOW)
    assert claimed is not None
    assert claimed.work_id == work.work_id
    assert claimed.state is WorkState.DISPATCHED
    assert claimed.attempt == 1
    recovered = plane(tmp_path)
    assert recovered.work[work.work_id].state is WorkState.DISPATCHED


def test_reawakened_work_is_claimable_without_another_manual_compile(tmp_path):
    cp = plane(tmp_path)
    work = cp.ingest_event(event())[0]
    compile_work(cp, work.work_id)
    cp.transition(work.work_id, WorkState.DISPATCHED, reason="dispatch")
    cp.transition(work.work_id, WorkState.WAITING, reason="wait", not_before=NOW + timedelta(minutes=1))
    cp.reawaken_due(NOW + timedelta(minutes=2))
    claimed = cp.claim_next(
        worker_id="worker-resume",
        capabilities=[work.capability],
        now=NOW + timedelta(minutes=2),
    )
    assert claimed is not None
    assert claimed.work_id == work.work_id
    assert claimed.state is WorkState.DISPATCHED


def test_due_waiting_work_is_claimed_without_manual_wake_after_restart(tmp_path):
    cp = plane(tmp_path)
    work = cp.ingest_event(event())[0]
    compile_work(cp, work.work_id)
    cp.transition(work.work_id, WorkState.DISPATCHED, reason="dispatch")
    cp.transition(
        work.work_id, WorkState.WAITING,
        reason="temporarily_wait_for_due_time",
        not_before=NOW + timedelta(minutes=1),
    )
    restarted = plane(tmp_path)
    early = restarted.claim_next(
        worker_id="scheduled-run", capabilities=[work.capability],
        now=NOW + timedelta(seconds=59),
    )
    assert early is None
    claimed = restarted.claim_next(
        worker_id="scheduled-run", capabilities=[work.capability],
        now=NOW + timedelta(minutes=1, seconds=1),
    )
    assert claimed is not None
    assert claimed.work_id == work.work_id
    assert claimed.state is WorkState.DISPATCHED
    assert claimed.lease_owner == "scheduled-run"
    assert claimed.not_before is None or claimed.not_before <= NOW + timedelta(minutes=1, seconds=1)
    assert restarted.claim_next(
        worker_id="second-worker", capabilities=[work.capability],
        now=NOW + timedelta(minutes=1, seconds=2),
    ) is None


def test_due_waiting_work_is_recovered_alongside_other_ready_work(tmp_path):
    cp = plane(tmp_path)
    older = cp.ingest_event(event())[0]
    compile_work(cp, older.work_id)
    cp.transition(older.work_id, WorkState.DISPATCHED, reason="dispatch")
    cp.transition(
        older.work_id, WorkState.WAITING, reason="wait",
        not_before=NOW + timedelta(seconds=4),
    )
    fresh_event = ControlEvent(
        event_type="github.workflow.finished",
        source_system="github", subject_id="CASE-CHR-004",
        correlation_id="corr-2", occurred_at=NOW,
        payload={"conclusion": "failure"}, dedupe_key="distinct-event",
    )
    incoming = cp.ingest_event(fresh_event)
    ready = cp.claim_next(
        worker_id="worker", capabilities=[older.capability] + [x.capability for x in incoming],
        now=NOW + timedelta(seconds=5),
    )
    assert ready is not None
    assert cp.work[older.work_id].state is not WorkState.WAITING


def test_expired_nonexternal_lease_recovers_and_retries_without_manual_gate(tmp_path):
    cp = plane(tmp_path)
    work = cp.ingest_event(event())[0]
    first = cp.claim_next(worker_id="crashed-worker", capabilities=[work.capability], now=NOW, lease_seconds=1)
    assert first is not None and first.attempt == 1

    # A new worker must be able to recover the orphaned local task and claim it.
    restarted = plane(tmp_path)
    retried = restarted.claim_next(
        worker_id="replacement-worker",
        capabilities=[work.capability],
        now=NOW + timedelta(seconds=2), lease_seconds=30,
    )
    assert retried is not None
    assert retried.work_id == work.work_id
    assert retried.attempt == 2
    assert retried.lease_owner == "replacement-worker"
    assert retried.state is WorkState.DISPATCHED


def test_explicit_reconciliation_requeues_expired_local_task(tmp_path):
    cp = plane(tmp_path)
    work = cp.ingest_event(event())[0]
    cp.claim_next(worker_id="worker", capabilities=[work.capability], now=NOW, lease_seconds=1)
    recovered = cp.reconcile_expired_leases(NOW + timedelta(seconds=2))
    assert len(recovered) == 1
    assert recovered[0].state is WorkState.RECEIVED
    assert recovered[0].lease_owner is None


def test_expired_external_lease_is_not_blindly_replayed(tmp_path):
    cp = plane(tmp_path)
    work = cp.ingest_event(event("dockets.referral.ready"))[0]
    first = cp.claim_next(worker_id="sender", capabilities=[work.capability], now=NOW, lease_seconds=1)
    assert first is not None
    retried = cp.claim_next(worker_id="replacement", capabilities=[work.capability], now=NOW + timedelta(seconds=2))
    assert retried is None


def test_execute_next_local_runs_real_worker_and_persists_success(tmp_path):
    cp = plane(tmp_path)
    work = cp.ingest_event(event())[0]
    product = tmp_path / "actual-output.txt"

    def run(item):
        product.write_text(item.objective)
        assert product.read_text() == item.objective
        return ExecutionReceipt(
            work_id=item.work_id, mission_id=item.mission_id,
            correlation_id=item.correlation_id, receipt_kind="verification",
            status="verified", source_system="local-executor",
            details={"artifact": str(product), "verified_bytes": len(product.read_bytes())},
        )

    result = cp.execute_next_local(
        worker_id="local-worker", capabilities=[work.capability],
        executor=run, now=NOW,
    )
    assert product.read_text() == work.objective
    assert result["status"] == "complete"
    assert result["executed"] is True
    assert result["work_id"] == work.work_id
    restored = plane(tmp_path)
    assert restored.work[work.work_id].state is WorkState.COMPLETE
    assert len(restored.receipts) == 1


def test_execute_next_local_skips_external_writes_and_executes_local_work(tmp_path):
    cp = plane(tmp_path)
    external = cp.ingest_event(event("dockets.referral.ready"))[0]
    local = cp.ingest_event(event())[0]
    seen = []
    def run(item):
        seen.append(item.work_id)
        return None

    result = cp.execute_next_local(
        worker_id="local", capabilities=[external.capability, local.capability],
        executor=run, now=NOW,
    )
    assert seen == [local.work_id]
    assert result["status"] == "unconfirmed"
    assert cp.work[external.work_id].state is WorkState.RECEIVED
    assert cp.work[local.work_id].state is WorkState.RECONCILING


def test_execute_next_local_failed_receipt_requeues_nonexternal_work(tmp_path):
    cp = plane(tmp_path)
    work = cp.ingest_event(event())[0]
    def fail(item):
        return ExecutionReceipt(
            work_id=item.work_id, mission_id=item.mission_id,
            correlation_id=item.correlation_id, receipt_kind="execution",
            status="failed", source_system="local-process",
            details={"exit_code": 17},
        )
    result = cp.execute_next_local(worker_id="local", capabilities=[work.capability], executor=fail, now=NOW)
    assert result["status"] == "retryable_failure"
    assert result["exit_code"] == 17
    assert cp.work[work.work_id].state is WorkState.RECEIVED
    assert cp.work[work.work_id].attempt == 1


def test_execute_next_local_does_not_promote_unverified_execution_receipt(tmp_path):
    cp = plane(tmp_path)
    work = cp.ingest_event(event())[0]
    def run(item):
        return ExecutionReceipt(
            work_id=item.work_id, mission_id=item.mission_id,
            correlation_id=item.correlation_id, receipt_kind="execution",
            status="verified", source_system="local-process",
            details={"exit_code": 0, "scope": "command exited 0"},
        )
    result = cp.execute_next_local(worker_id="local", capabilities=[work.capability], executor=run, now=NOW)
    assert result["executed"] is True
    assert result["status"] == "awaiting_receipts"
    assert cp.work[work.work_id].state is WorkState.VERIFYING
    assert any(r.receipt_kind == "execution" for r in cp.receipts.values())


def test_execute_next_local_idle_does_not_claim_work_or_report_execution(tmp_path):
    cp = plane(tmp_path)
    result = cp.execute_next_local(worker_id="local", capabilities=["case.response.ingest"], executor=lambda item: None)
    assert result["status"] == "idle"
    assert result["executed"] is False


def test_local_worker_failure_after_retry_budget_keeps_mission_runnable(tmp_path):
    """A local worker's legacy attempt budget cannot permanently abandon work."""
    cp = plane(tmp_path)
    work = cp.ingest_event(event())[0]
    low_budget = replace(work, max_attempts=1)
    cp.work[work.work_id] = low_budget
    cp.store.append_work(low_budget, reason="simulate_prior_retry_budget")

    def fail(item):
        return ExecutionReceipt(
            work_id=item.work_id, mission_id=item.mission_id,
            correlation_id=item.correlation_id, receipt_kind="execution",
            status="failed", source_system="local-process",
            details={"exit_code": 17},
        )

    result = cp.execute_next_local(
        worker_id="local", capabilities=[work.capability], executor=fail, now=NOW
    )
    assert result["status"] == "retry_scheduled"
    assert result["executed"] is True
    assert result["exit_code"] == 17
    assert cp.work[work.work_id].state is WorkState.WAITING
    assert cp.work[work.work_id].not_before == NOW + timedelta(seconds=2)
    assert cp.claim_next(
        worker_id="too-soon", capabilities=[work.capability],
        now=NOW + timedelta(seconds=1),
    ) is None

    restarted = plane(tmp_path)

    def recover(item):
        return ExecutionReceipt(
            work_id=item.work_id, mission_id=item.mission_id,
            correlation_id=item.correlation_id, receipt_kind="verification",
            status="verified", source_system="local-process",
            details={"outcome": "recovered"},
        )

    recovered = restarted.execute_next_local(
        worker_id="replacement", capabilities=[work.capability],
        executor=recover, now=NOW + timedelta(seconds=3),
    )
    assert recovered["status"] == "complete"
    assert recovered["work_id"] == work.work_id
    assert restarted.work[work.work_id].state is WorkState.COMPLETE
    assert restarted.work[work.work_id].attempt == 2


def test_scheduled_local_retry_does_not_block_independent_work(tmp_path):
    cp = plane(tmp_path)
    failed = cp.ingest_event(event())[0]
    low_budget = replace(failed, max_attempts=1)
    cp.work[failed.work_id] = low_budget
    cp.store.append_work(low_budget, reason="simulate_prior_retry_budget")

    def fail(item):
        return ExecutionReceipt(
            work_id=item.work_id, mission_id=item.mission_id,
            correlation_id=item.correlation_id, receipt_kind="execution",
            status="failed", source_system="local-process",
            details={"exit_code": 9},
        )

    scheduled = cp.execute_next_local(
        worker_id="first", capabilities=[failed.capability], executor=fail, now=NOW
    )
    assert scheduled["status"] == "retry_scheduled"
    assert cp.work[failed.work_id].state is WorkState.WAITING

    independent = ControlEvent(
        event_type="github.workflow.finished", source_system="github",
        subject_id="ENGINEERING-OTHER", correlation_id="other-corr",
        occurred_at=NOW, payload={"conclusion": "success"},
        dedupe_key="independent-local-unit",
    )
    ready = cp.ingest_event(independent)[0]

    def succeed(item):
        return ExecutionReceipt(
            work_id=item.work_id, mission_id=item.mission_id,
            correlation_id=item.correlation_id, receipt_kind="verification",
            status="verified", source_system="local-executor",
            details={"completed": True},
        )

    result = cp.execute_next_local(
        worker_id="other", capabilities=[failed.capability, ready.capability],
        executor=succeed, now=NOW + timedelta(seconds=1),
    )
    assert result["status"] == "complete"
    assert result["work_id"] == ready.work_id
    assert cp.work[failed.work_id].state is WorkState.WAITING
    assert cp.work[ready.work_id].state is WorkState.COMPLETE


def test_drain_local_executes_all_independent_eligible_work_without_partial_success(tmp_path):
    cp = plane(tmp_path)
    first = cp.ingest_event(event())[0]
    second_event = replace(event(), subject_id="CASE-CHR-004", correlation_id="corr-2")
    second = cp.ingest_event(second_event)[0]
    seen = []

    def executor(item):
        seen.append(item.work_id)
        return [
            ExecutionReceipt(
                work_id=item.work_id, mission_id=item.mission_id,
                correlation_id=item.correlation_id, receipt_kind=kind,
                status="verified", source_system="test-executor", details={"ok": True},
            )
            for kind in ("execution", "verification")
        ]

    result = cp.drain_local(
        worker_id="local", capabilities=[first.capability], executor=executor, now=NOW,
    )
    assert set(seen) == {first.work_id, second.work_id}
    assert len(seen) == 2
    assert result["status"] == "local_batch_complete"
    assert result["work_items_processed"] == 2
    assert result["work_items_completed"] == 2
    assert result["mission_complete"] is False
    assert all(cp.work[k].state is WorkState.COMPLETE for k in seen)


def test_drain_local_continues_independent_work_after_recoverable_failure(tmp_path):
    cp = plane(tmp_path)
    first = cp.ingest_event(event())[0]
    second = cp.ingest_event(replace(
        event(), subject_id="CASE-CHR-004", correlation_id="corr-2",
    ))[0]
    calls = []

    def executor(item):
        calls.append(item.work_id)
        receipt_kwargs = {
            "work_id": item.work_id, "mission_id": item.mission_id,
            "correlation_id": item.correlation_id, "source_system": "test-executor",
        }
        if item.work_id == first.work_id:
            return ExecutionReceipt(
                **receipt_kwargs, receipt_kind="execution", status="failed",
                details={"exit_code": 17},
            )
        return [
            ExecutionReceipt(**receipt_kwargs, receipt_kind=kind, status="verified", details={"ok": True})
            for kind in ("execution", "verification")
        ]

    result = cp.drain_local(
        worker_id="local", capabilities=[first.capability], executor=executor, now=NOW,
    )
    assert calls == [first.work_id, second.work_id]
    assert result["status"] == "unfinished"
    assert result["work_items_completed"] == 1
    assert first.work_id in result["remaining_unverified_ids"]
    assert cp.work[first.work_id].state in {WorkState.RECEIVED, WorkState.WAITING}
    assert cp.work[second.work_id].state is WorkState.COMPLETE
    assert result["mission_complete"] is False


def test_drain_local_never_claims_success_for_previous_awaiting_verification(tmp_path):
    cp = plane(tmp_path)
    work = cp.ingest_event(event())[0]
    result = cp.execute_next_local(
        worker_id="local-1", capabilities=[work.capability],
        executor=lambda item: ExecutionReceipt(
            work_id=item.work_id, mission_id=item.mission_id,
            correlation_id=item.correlation_id, receipt_kind="execution",
            status="verified", source_system="test", details={"ok": True},
        ), now=NOW,
    )
    assert result["status"] == "awaiting_receipts"
    drain = cp.drain_local(
        worker_id="local-2", capabilities=[work.capability],
        executor=lambda item: None, now=NOW,
    )
    assert drain["status"] == "unfinished"
    assert drain["work_items_processed"] == 0
    assert drain["remaining_unverified_ids"] == [work.work_id]
    assert drain["mission_complete"] is False
