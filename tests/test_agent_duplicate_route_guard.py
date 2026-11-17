"""Duplicate observations must not cause a substrate to execute twice."""
from datetime import UTC, datetime

from src.dynamic_execution_fabric import DynamicExecutionFabric, SubstrateObservation, Workload


def test_duplicate_observations_are_not_fallback_routes():
    now = datetime(2026, 11, 17, tzinfo=UTC)
    workload = Workload("dedup-1", "execute once per provider", frozenset({"execute"}))

    def observation(name, score):
        return SubstrateObservation(
            name, frozenset({"execute"}), "healthy", score,
            False, False, False, False, now,
        )

    observations = [
        observation("primary", 1.0),
        observation("primary", 0.8),
        observation("secondary", 0.5),
    ]
    fabric = DynamicExecutionFabric(now=lambda: now)
    plan = fabric.plan(workload, observations)
    assert plan.selected == "primary"
    assert plan.fallbacks == ("secondary",)

    calls = []

    def executor(substrate, _workload):
        calls.append(substrate)
        return False if substrate == "primary" else True

    result = fabric.execute(workload, observations, executor)
    assert result.ok
    assert result.substrate == "secondary"
    assert result.attempted == ("primary", "secondary")
    assert calls == ["primary", "secondary"]


def test_duplicate_observations_do_not_repeat_failed_only_provider():
    now = datetime(2026, 11, 17, tzinfo=UTC)
    workload = Workload("dedup-2", "one provider", frozenset({"execute"}))
    observation = SubstrateObservation(
        "single", frozenset({"execute"}), "healthy", 1.0,
        False, False, False, False, now,
    )
    calls = []

    def executor(substrate, _workload):
        calls.append(substrate)
        return False

    result = DynamicExecutionFabric(now=lambda: now).execute(
        workload, [observation, observation], executor,
    )
    assert result.status == "route_exhausted"
    assert result.attempted == ("single",)
    assert calls == ["single"]
