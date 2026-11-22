"""Scheduler must not turn negative executor evidence into success or a blind retry."""
from test_continuous_control_plane import NOW, event, plane
from continuous_control_plane import ExecutionReceipt, WorkState
import pytest

@pytest.mark.parametrize("details", [
    {"outcome_verified": False},
    {"cleanup_unresolved": True},
    {"output_drains_unresolved": True},
    {"direct_child_reaped": False},
    {"status": "inspection_failed", "retry_authorized": False},
    {"status": "INSPECTION_FAILED", "retry_authorized": True},
    {"status": ["inspection_failed"]},
    {"status": None},
])
def test_negative_execution_evidence_requires_reconciliation(tmp_path, details):
    cp = plane(tmp_path)
    work = cp.ingest_event(event())[0]
    def run(item):
        return ExecutionReceipt(work_id=item.work_id, mission_id=item.mission_id,
            correlation_id=item.correlation_id, receipt_kind="verification",
            status="verified", source_system="local-executor", details=details)
    result = cp.execute_next_local(worker_id="worker", capabilities=[work.capability],
                                   executor=run, now=NOW)
    assert result["status"] == "unconfirmed"
    assert cp.work[work.work_id].state is WorkState.RECONCILING
    assert cp.work[work.work_id].attempt == 1
    assert len(cp.receipts) == 1
    restarted = plane(tmp_path)
    assert restarted.work[work.work_id].state is WorkState.RECONCILING
    assert restarted.claim_next(worker_id="replay", capabilities=[work.capability], now=NOW) is None

@pytest.mark.parametrize("malformed_status", [None, 42, [], {}])
def test_malformed_receipt_status_reconciles_without_crashing(tmp_path, malformed_status):
    cp = plane(tmp_path)
    work = cp.ingest_event(event())[0]
    def run(item):
        return ExecutionReceipt(work_id=item.work_id, mission_id=item.mission_id,
            correlation_id=item.correlation_id, receipt_kind="verification",
            status=malformed_status, source_system="local-executor", details={})
    result = cp.execute_next_local(worker_id="worker", capabilities=[work.capability],
                                   executor=run, now=NOW)
    assert result["status"] == "unconfirmed"
    assert cp.work[work.work_id].state is WorkState.RECONCILING


def test_provider_receipt_replay_cannot_certify_another_execution(tmp_path):
    cp = plane(tmp_path)
    first = cp.ingest_event(event())[0]
    # Two distinct local jobs sharing a provider receipt identifier.
    second = cp.submit_work(
        mission_id=first.mission_id, correlation_id=first.correlation_id,
        domain=first.domain, capability=first.capability,
        objective="independent execution", idempotency_key="independent-execution",
    )
    cp.record_receipt(ExecutionReceipt(
        work_id=first.work_id, mission_id=first.mission_id,
        correlation_id=first.correlation_id, receipt_kind="verification",
        status="verified", source_system="provider", details={"ok": True},
        provider_receipt_id="provider-replayed-id",
    ))
    def run(item):
        return ExecutionReceipt(
            work_id=item.work_id, mission_id=item.mission_id,
            correlation_id=item.correlation_id, receipt_kind="verification",
            status="verified", source_system="provider", details={"ok": True},
            provider_receipt_id="provider-replayed-id",
        )
    result = cp.execute_next_local(
        worker_id="worker", capabilities=[first.capability],
        executor=run, now=NOW, exclude_work_ids=[first.work_id],
    )
    assert result["status"] == "unconfirmed"
    assert cp.work[second.work_id].state is WorkState.RECONCILING
    assert len(cp.receipts) == 1
    restarted = plane(tmp_path)
    assert restarted.work[second.work_id].state is WorkState.RECONCILING
    assert restarted.claim_next(
        worker_id="replay", capabilities=[second.capability], now=NOW,
        exclude_work_ids=[first.work_id],
    ) is None

@pytest.mark.parametrize("malformed_details", [None, [], "inspection_failed", 17])
def test_malformed_receipt_details_fail_closed_without_scheduler_crash(tmp_path, malformed_details):
    cp = plane(tmp_path)
    work = cp.ingest_event(event())[0]

    def run(item):
        return ExecutionReceipt(
            work_id=item.work_id, mission_id=item.mission_id,
            correlation_id=item.correlation_id, receipt_kind="verification",
            status="verified", source_system="local-executor",
            details=malformed_details,
        )

    result = cp.execute_next_local(
        worker_id="worker", capabilities=[work.capability],
        executor=run, now=NOW,
    )
    assert result["status"] == "unconfirmed"
    assert cp.work[work.work_id].state is WorkState.RECONCILING
    assert plane(tmp_path).work[work.work_id].state is WorkState.RECONCILING


@pytest.mark.parametrize("duplicate_within_batch", [False, True])
def test_receipt_uuid_replay_never_certifies_new_execution(tmp_path, duplicate_within_batch):
    cp = plane(tmp_path)
    work = cp.ingest_event(event())[0]
    original = ExecutionReceipt(
        work_id=work.work_id, mission_id=work.mission_id,
        correlation_id=work.correlation_id, receipt_kind="verification",
        status="verified", source_system="local-executor", details={"ok": True},
    )
    if not duplicate_within_batch:
        cp.record_receipt(original)
    def run(item):
        return [original, original] if duplicate_within_batch else original
    result = cp.execute_next_local(
        worker_id="worker", capabilities=[work.capability],
        executor=run, now=NOW,
    )
    assert result["status"] == "unconfirmed"
    assert cp.work[work.work_id].state is WorkState.RECONCILING
    assert len(cp.receipts) == (0 if duplicate_within_batch else 1)
    restarted = plane(tmp_path)
    assert restarted.work[work.work_id].state is WorkState.RECONCILING
    assert restarted.claim_next(worker_id="replay", capabilities=[work.capability], now=NOW) is None
