"""Regression: an exception may occur after a remote side effect commits."""
from datetime import UTC, datetime

from src.dynamic_execution_fabric import DynamicExecutionFabric, SubstrateObservation, Workload


def test_exception_never_replays_on_fallback():
    now = datetime(2026, 11, 17, tzinfo=UTC)
    workload = Workload("w1", "single remote mutation", frozenset({"execute"}))
    observations = [
        SubstrateObservation(name, frozenset({"execute"}), "healthy", score,
                             False, False, False, False, now)
        for name, score in (("primary", 1.0), ("fallback", 0.5))
    ]
    calls = []

    def executor(name, _workload):
        calls.append(name)
        raise TimeoutError("response lost after possible commit")

    result = DynamicExecutionFabric(now=lambda: now).execute(workload, observations, executor)
    assert calls == ["primary"]
    assert result.attempted == ("primary",)
    assert result.status == "unconfirmed"
    assert not result.ok
    assert result.substrate == "primary"
    assert result.failures[0]["error"] == "response lost after possible commit"
