"""Pending provider effects must never be replayed on a fallback."""
from datetime import UTC, datetime

import pytest

from src.dynamic_execution_fabric import DynamicExecutionFabric, SubstrateObservation, Workload


NOW = datetime(2026, 11, 17, tzinfo=UTC)


def observation(name: str, score: float) -> SubstrateObservation:
    return SubstrateObservation(
        name=name, capabilities=frozenset({"execute"}), health="healthy",
        health_score=score, private_repo=False, exact_source=False,
        receipts=False, terminal_readback=False, observed_at=NOW,
    )


@pytest.mark.parametrize("state", ["queued", "pending", "accepted", "submitted", "scheduled", "running", "processing", "in_progress"])
@pytest.mark.parametrize("flag", ["ok", "success"])
def test_pending_with_negative_completion_flag_never_falls_back(state, flag):
    fabric = DynamicExecutionFabric(now=lambda: NOW)
    work = Workload("pending-guard", "do not duplicate provider side effects", frozenset({"execute"}))
    calls = []

    def executor(provider, _work):
        calls.append(provider)
        return {"status": state, flag: False, "job_id": "operation-123"}

    result = fabric.execute(work, [observation("primary", 0.99), observation("secondary", 0.8)], executor)
    assert result.ok is False
    assert result.status == "pending"
    assert result.attempted == ("primary",)
    assert result.result["job_id"] == "operation-123"
    assert calls == ["primary"]


def test_explicit_terminal_failure_still_allows_fallback():
    fabric = DynamicExecutionFabric(now=lambda: NOW)
    work = Workload("terminal-failure", "retry after definitive failure", frozenset({"execute"}))
    calls = []

    def executor(provider, _work):
        calls.append(provider)
        return {"status": "failed", "ok": False} if provider == "primary" else {"status": "success"}

    result = fabric.execute(work, [observation("primary", 0.99), observation("secondary", 0.8)], executor)
    assert result.ok is True
    assert result.attempted == ("primary", "secondary")
    assert calls == ["primary", "secondary"]
