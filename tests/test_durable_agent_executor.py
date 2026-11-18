"""Durable execution claims survive restart and prevent duplicate provider calls."""
from datetime import UTC, datetime

import pytest

from src.durable_agent_executor import DurableAgentExecutor
from src.dynamic_execution_fabric import SubstrateObservation, Workload


NOW = datetime(2026, 11, 17, tzinfo=UTC)


def setup():
    work = Workload("durable-1", "execute durable operation", frozenset({"execute"}))
    obs = SubstrateObservation(
        "provider", frozenset({"execute"}), "healthy", 1.0,
        False, False, False, False, NOW,
    )
    return work, [obs]


def test_claim_survives_restart_and_blocks_duplicate_provider_invocation(tmp_path):
    database = tmp_path / "claims.sqlite"
    work, observations = setup()
    calls = []

    def provider(name, workload):
        calls.append(name)
        return {"status": "success", "receipt": "abc"}

    first = DurableAgentExecutor(database, fabric=None)
    # Default fabric clock is current time; stale observations are still eligible.
    result = first.execute(work, observations, provider)
    assert result.state == "succeeded"
    second = DurableAgentExecutor(database)
    replay = second.execute(work, observations, provider)
    assert replay.state == "already_claimed:succeeded"
    assert replay.execution is None
    assert calls == ["provider"]


def test_crashed_executor_stays_claimed_until_explicit_reconciliation(tmp_path):
    database = tmp_path / "claims.sqlite"
    work, observations = setup()
    calls = []

    def crash(name, workload):
        calls.append(name)
        raise KeyboardInterrupt("provider outcome unknown")

    with pytest.raises(KeyboardInterrupt):
        DurableAgentExecutor(database).execute(work, observations, crash)
    recovered = DurableAgentExecutor(database)
    assert recovered.status(work.workload_id) == "invoking"
    replay = recovered.execute(work, observations, lambda *_: calls.append("REPLAY"))
    assert replay.state == "already_claimed:invoking"
    assert calls == ["provider"]
    with pytest.raises(ValueError):
        recovered.reconcile(work.workload_id, authoritative_state="failed", evidence="")
    recovered.reconcile(
        work.workload_id, authoritative_state="failed",
        evidence="provider job lookup confirmed no committed operation",
    )
    assert recovered.status(work.workload_id) == "failed"
    assert recovered.execute(work, observations, lambda *_: calls.append("REPLAY")).state == "already_claimed:failed"
    assert calls == ["provider"]


def test_reused_workload_id_cannot_change_objective(tmp_path):
    db = tmp_path / "claims.sqlite"
    work, observations = setup()
    executor = DurableAgentExecutor(db)
    executor.execute(work, observations, lambda *_: True)
    changed = Workload(work.workload_id, "different objective", work.capabilities)
    with pytest.raises(ValueError, match="different objective"):
        executor.execute(changed, observations, lambda *_: True)



def test_terminal_receipt_cannot_be_rewritten_by_reconciliation(tmp_path):
    database = tmp_path / "claims.sqlite"
    work, observations = setup()
    executor = DurableAgentExecutor(database)
    assert executor.execute(work, observations, lambda *_: {"status": "success"}).state == "succeeded"
    before = executor.readback(work.workload_id)
    with pytest.raises(ValueError, match="terminal outcomes are immutable"):
        executor.reconcile(work.workload_id, authoritative_state="failed", evidence="unverified contradictory report")
    assert executor.readback(work.workload_id) == before


def test_reconciled_claim_cannot_be_reconciled_again(tmp_path):
    database = tmp_path / "claims.sqlite"
    work, observations = setup()
    executor = DurableAgentExecutor(database)

    def crash(*_):
        raise KeyboardInterrupt("unknown result")

    with pytest.raises(KeyboardInterrupt):
        executor.execute(work, observations, crash)
    executor.reconcile(work.workload_id, authoritative_state="cancelled", evidence="authoritative provider cancellation receipt")
    before = executor.readback(work.workload_id)
    with pytest.raises(ValueError, match="terminal outcomes are immutable"):
        executor.reconcile(work.workload_id, authoritative_state="succeeded", evidence="conflicting receipt")
    assert executor.readback(work.workload_id) == before


def test_provider_completion_cannot_overwrite_concurrent_reconciliation(tmp_path):
    database = tmp_path / "claims.sqlite"
    work, observations = setup()
    executor = DurableAgentExecutor(database)

    def provider(*_):
        # Simulate independent authoritative readback arriving while the
        # original provider call is still outstanding.
        DurableAgentExecutor(database).reconcile(
            work.workload_id, authoritative_state="cancelled",
            evidence="authoritative cancellation receipt",
        )
        return {"status": "success", "receipt": "late"}

    outcome = executor.execute(work, observations, provider)
    assert outcome.state == "already_claimed:cancelled"
    record = executor.readback(work.workload_id)
    assert record["state"] == "cancelled"
    assert record["result"] == {"reconciliation_evidence": "authoritative cancellation receipt"}


def test_same_state_authoritative_reconciliation_wins_over_late_provider(tmp_path):
    database = tmp_path / "claims.sqlite"
    work, observations = setup()
    executor = DurableAgentExecutor(database)

    def provider(*_):
        DurableAgentExecutor(database).reconcile(
            work.workload_id,
            authoritative_state="succeeded",
            evidence="independently verified provider receipt",
        )
        return {"status": "success", "receipt": "late-unverified"}

    outcome = executor.execute(work, observations, provider)
    assert outcome.state == "already_claimed:succeeded"
    assert outcome.execution is None
    record = executor.readback(work.workload_id)
    assert record["state"] == "succeeded"
    assert record["result"] == {"reconciliation_evidence": "independently verified provider receipt"}
