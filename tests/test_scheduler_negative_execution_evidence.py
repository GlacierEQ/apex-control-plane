"""Scheduler must not turn negative executor evidence into success or a blind retry."""
from test_continuous_control_plane import NOW, event, plane
from src.continuous_control_plane import ExecutionReceipt, WorkState
import pytest

@pytest.mark.parametrize("details", [
    {"outcome_verified": False},
    {"cleanup_unresolved": True},
    {"output_drains_unresolved": True},
    {"direct_child_reaped": False},
    {"status": "inspection_failed", "retry_authorized": False},
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
