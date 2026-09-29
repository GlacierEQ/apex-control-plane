from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.dynamic_execution_fabric import (
    DynamicExecutionFabric,
    DynamicObservationRegistry,
    SubstrateObservation,
    Workload,
)


NOW = datetime(2026, 9, 29, 22, 55, tzinfo=UTC)


def obs(
    name: str,
    *,
    capabilities: set[str],
    health: str = "healthy",
    score: float = 1.0,
    private_repo: bool = True,
    exact_source: bool = True,
    receipts: bool = True,
    terminal_readback: bool = True,
    observed_at: datetime = NOW,
    cost: float = 0.5,
    latency: float = 0.5,
) -> SubstrateObservation:
    return SubstrateObservation(
        name=name,
        capabilities=frozenset(capabilities),
        health=health,
        health_score=score,
        private_repo=private_repo,
        exact_source=exact_source,
        receipts=receipts,
        terminal_readback=terminal_readback,
        observed_at=observed_at,
        cost_score=cost,
        latency_score=latency,
    )


def test_private_ci_routes_around_exhausted_github_actions_to_healthy_buildkite() -> None:
    fabric = DynamicExecutionFabric(now=lambda: NOW)
    workload = Workload(
        workload_id="ci:computer-user:abc",
        objective="verify computer-user exact source",
        capabilities=frozenset({"ci", "python", "private_repo"}),
        private_repo=True,
        requires_exact_source=True,
        requires_receipts=True,
        requires_terminal_readback=True,
    )
    observations = [
        obs(
            "github_actions",
            capabilities={"ci", "python", "private_repo"},
            health="unavailable",
            score=0.0,
        ),
        obs("buildkite", capabilities={"ci", "python", "private_repo"}, score=0.96),
    ]

    plan = fabric.plan(workload, observations)

    assert plan.selected == "buildkite"
    assert plan.objective == workload.objective
    assert plan.routes[0].substrate == "buildkite"
    assert any(route.substrate == "github_actions" and not route.eligible for route in plan.routes)


def test_buildkite_is_not_sovereign_and_healthy_local_worker_can_take_over() -> None:
    fabric = DynamicExecutionFabric(now=lambda: NOW)
    workload = Workload(
        workload_id="test:runtime",
        objective="run the strongest valid verification route",
        capabilities=frozenset({"ci", "python"}),
        requires_exact_source=True,
        requires_receipts=True,
    )
    observations = [
        obs("buildkite", capabilities={"ci", "python"}, health="degraded", score=0.35),
        obs("local_mac", capabilities={"ci", "python"}, score=0.99, latency=0.95),
    ]

    plan = fabric.plan(workload, observations)

    assert plan.selected == "local_mac"
    assert plan.routes[0].substrate == "local_mac"
    assert plan.routes[1].substrate == "buildkite"


def test_missing_capability_changes_route_not_objective() -> None:
    fabric = DynamicExecutionFabric(now=lambda: NOW)
    workload = Workload(
        workload_id="deploy:ios",
        objective="ship the operator runtime to the reachable mobile surface",
        capabilities=frozenset({"deploy", "vercel"}),
        requires_terminal_readback=True,
    )

    plan = fabric.plan(
        workload,
        [
            obs("buildkite", capabilities={"ci", "python"}),
            obs("vercel", capabilities={"deploy", "vercel"}, score=0.92, private_repo=False),
        ],
    )

    assert plan.selected == "vercel"
    assert plan.objective == "ship the operator runtime to the reachable mobile surface"
    rejected = next(route for route in plan.routes if route.substrate == "buildkite")
    assert rejected.eligible is False
    assert "missing_capabilities" in rejected.reasons


def test_stale_health_is_ineligible_when_fresh_alternative_exists() -> None:
    fabric = DynamicExecutionFabric(now=lambda: NOW, freshness_window=timedelta(minutes=15))
    workload = Workload(
        workload_id="ci:gateway",
        objective="verify gateway",
        capabilities=frozenset({"ci", "typescript"}),
    )

    plan = fabric.plan(
        workload,
        [
            obs(
                "buildkite",
                capabilities={"ci", "typescript"},
                score=1.0,
                observed_at=NOW - timedelta(hours=2),
            ),
            obs("local_linux", capabilities={"ci", "typescript"}, score=0.8),
        ],
    )

    assert plan.selected == "local_linux"
    stale = next(route for route in plan.routes if route.substrate == "buildkite")
    assert stale.eligible is False
    assert "stale_observation" in stale.reasons


def test_route_plan_exposes_ranked_fallbacks_without_promoting_selection_to_authority() -> None:
    fabric = DynamicExecutionFabric(now=lambda: NOW)
    workload = Workload(
        workload_id="research:1",
        objective="complete the research task",
        capabilities=frozenset({"web"}),
    )
    plan = fabric.plan(
        workload,
        [
            obs("provider_a", capabilities={"web"}, score=0.9, cost=0.8),
            obs("provider_b", capabilities={"web"}, score=0.85, cost=0.95),
        ],
    )

    assert plan.selected == "provider_a"
    assert plan.fallbacks == ("provider_b",)
    assert plan.selection_is_authority is False
    assert plan.objective == workload.objective


def test_no_eligible_substrate_returns_blocked_execution_not_shrunken_mission() -> None:
    fabric = DynamicExecutionFabric(now=lambda: NOW)
    workload = Workload(
        workload_id="ci:private",
        objective="verify the exact private source and continue the mission",
        capabilities=frozenset({"ci", "private_repo"}),
        private_repo=True,
        requires_exact_source=True,
    )

    plan = fabric.plan(
        workload,
        [
            obs(
                "public_actions",
                capabilities={"ci"},
                private_repo=False,
                exact_source=False,
            )
        ],
    )

    assert plan.selected is None
    assert plan.execution_state == "no_current_route"
    assert plan.objective == workload.objective
    assert plan.mission_state == "unchanged"



def test_observation_registry_discovers_new_substrate_without_router_code_change() -> None:
    registry = DynamicObservationRegistry()
    registry.register("new_provider", lambda workload: obs(
        "new_provider",
        capabilities=set(workload.capabilities),
        score=0.97,
    ))
    fabric = DynamicExecutionFabric(now=lambda: NOW)
    workload = Workload(
        workload_id="dynamic:1",
        objective="execute using whatever healthy substrate exists now",
        capabilities=frozenset({"ci", "python"}),
    )

    observations = registry.observe(workload)
    plan = fabric.plan(workload, observations)

    assert [item.name for item in observations] == ["new_provider"]
    assert plan.selected == "new_provider"


def test_observer_failure_becomes_health_state_and_does_not_stop_other_routes() -> None:
    registry = DynamicObservationRegistry()

    def broken(_workload: Workload) -> SubstrateObservation:
        raise RuntimeError("provider discovery failed")

    registry.register("broken_provider", broken)
    registry.register("healthy_provider", lambda workload: obs(
        "healthy_provider",
        capabilities=set(workload.capabilities),
        score=0.88,
    ))
    fabric = DynamicExecutionFabric(now=lambda: NOW)
    workload = Workload(
        workload_id="dynamic:2",
        objective="continue through the strongest current route",
        capabilities=frozenset({"deploy"}),
    )

    observations = registry.observe(workload, observed_at=NOW)
    plan = fabric.plan(workload, observations)

    assert plan.selected == "healthy_provider"
    broken_observation = next(item for item in observations if item.name == "broken_provider")
    assert broken_observation.health == "unavailable"
    assert broken_observation.health_score == 0.0


def test_dynamic_registry_contains_no_static_winner() -> None:
    import json
    from pathlib import Path

    config = json.loads(
        (Path(__file__).resolve().parents[1] / "config" / "dynamic_execution_fabric.json").read_text()
    )

    assert config["selection_model"] == "live_observation_ranked_per_work_unit"
    assert "default_substrate" not in config
    assert config["live_state"]["embedded_in_registry"] is False
    assert config["live_state"]["required_per_work_unit"] is True
