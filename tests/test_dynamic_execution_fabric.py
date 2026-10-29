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
    assert any(reason.startswith("missing_capabilities:") for reason in rejected.reasons)


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
    assert stale.eligible is True
    assert "stale_observation" in stale.reasons
    assert "buildkite" in plan.fallbacks


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



def test_execute_fails_over_between_ranked_substrates_without_changing_objective() -> None:
    fabric = DynamicExecutionFabric(now=lambda: NOW)
    workload = Workload(
        workload_id="ci:failover",
        objective="verify exact source and produce a terminal receipt",
        capabilities=frozenset({"ci", "python"}),
        requires_receipts=True,
        requires_terminal_readback=True,
    )
    observations = [
        obs("provider_a", capabilities={"ci", "python"}, score=0.99),
        obs("provider_b", capabilities={"ci", "python"}, score=0.90),
    ]
    calls: list[str] = []

    def execute(substrate: str, _workload: Workload) -> dict:
        calls.append(substrate)
        if substrate == "provider_a":
            raise RuntimeError("provider_a capacity exhausted")
        return {
            "status": "success",
            "receipt": "receipt-b",
            "terminal_readback": True,
        }

    result = fabric.execute(workload, observations, execute)

    assert calls == ["provider_a", "provider_b"]
    assert result.ok is True
    assert result.substrate == "provider_b"
    assert result.objective == workload.objective
    assert result.attempted == ("provider_a", "provider_b")
    assert result.failures[0]["substrate"] == "provider_a"


def test_execute_returns_route_exhausted_without_rewriting_mission() -> None:
    fabric = DynamicExecutionFabric(now=lambda: NOW)
    workload = Workload(
        workload_id="ci:exhausted",
        objective="complete the exact requested verification",
        capabilities=frozenset({"ci"}),
    )
    observations = [
        obs("provider_a", capabilities={"ci"}, score=0.9),
        obs("provider_b", capabilities={"ci"}, score=0.8),
    ]

    result = fabric.execute(
        workload,
        observations,
        lambda substrate, _workload: (_ for _ in ()).throw(RuntimeError(f"{substrate} failed")),
    )

    assert result.ok is False
    assert result.status == "route_exhausted"
    assert result.objective == workload.objective
    assert result.mission_state == "unchanged"
    assert result.attempted == ("provider_a", "provider_b")


def test_stale_route_executes_when_no_fresh_route_exists() -> None:
    fabric = DynamicExecutionFabric(now=lambda: NOW, freshness_window=timedelta(minutes=15))
    workload = Workload(
        workload_id="execution:stale-only",
        objective="carry out authorized work despite expired monitoring timestamp",
        capabilities=frozenset({"python", "ci"}),
    )
    old = obs(
        "known_executor",
        capabilities={"python", "ci"},
        observed_at=NOW - timedelta(hours=3),
    )
    calls: list[str] = []
    result = fabric.execute(workload, [old], lambda substrate, _: calls.append(substrate) or {"receipt": "real-execution"})
    assert calls == ["known_executor"]
    assert result.ok is True
    assert result.substrate == "known_executor"


def test_stale_route_is_fallback_after_fresh_executor_fails() -> None:
    fabric = DynamicExecutionFabric(now=lambda: NOW, freshness_window=timedelta(minutes=15))
    workload = Workload(
        workload_id="execution:fallback",
        objective="finish actual work through any capable route",
        capabilities=frozenset({"python", "ci"}),
    )
    attempts: list[str] = []
    def invoke(substrate: str, _: Workload) -> dict:
        attempts.append(substrate)
        if substrate == "fresh":
            raise RuntimeError("fresh route failed")
        return {"receipt": "stale-route-success"}

    result = fabric.execute(
        workload,
        [
            obs("old", capabilities={"python", "ci"}, observed_at=NOW - timedelta(hours=3)),
            obs("fresh", capabilities={"python", "ci"}),
        ],
        invoke,
    )
    assert attempts == ["fresh", "old"]
    assert result.ok is True
    assert result.substrate == "old"


def test_unrecognized_health_is_uncertain_not_a_veto_on_execution() -> None:
    fabric = DynamicExecutionFabric(now=lambda: NOW)
    workload = Workload(
        workload_id="execution:uncertain",
        objective="run despite incomplete provider health vocabulary",
        capabilities=frozenset({"python"}),
    )
    result = fabric.execute(
        workload,
        [obs("new-provider", capabilities={"python"}, health="warming_up")],
        lambda substrate, _: {"status": "success", "attempted": substrate},
    )
    assert result.ok is True
    assert result.substrate == "new-provider"


def test_actually_unavailable_provider_is_not_treated_as_executable() -> None:
    fabric = DynamicExecutionFabric(now=lambda: NOW)
    workload = Workload(
        workload_id="execution:unavailable",
        objective="do not invent a working route",
        capabilities=frozenset({"python"}),
    )
    called: list[str] = []
    result = fabric.execute(
        workload,
        [obs("offline", capabilities={"python"}, health="unavailable")],
        lambda substrate, _: called.append(substrate),
    )
    assert result.ok is False
    assert called == []



def test_explicit_failed_result_falls_back_instead_of_reporting_success() -> None:
    fabric = DynamicExecutionFabric(now=lambda: NOW)
    workload = Workload(
        workload_id="execution:reported-error",
        objective="do work rather than declare an error response successful",
        capabilities=frozenset({"python"}),
    )
    attempted: list[str] = []
    def execute(route: str, _: Workload) -> dict:
        attempted.append(route)
        return {"status": "failed", "error": "provider rejected operation"} if route == "primary" else {"status": "success", "receipt": "secondary-ok"}

    result = fabric.execute(workload, [
        obs("primary", capabilities={"python"}, score=0.99),
        obs("secondary", capabilities={"python"}, score=0.75),
    ], execute)
    assert result.ok is True
    assert result.substrate == "secondary"
    assert attempted == ["primary", "secondary"]
    assert result.failures[0]["substrate"] == "primary"


def test_false_result_is_not_a_success_and_fallback_runs() -> None:
    fabric = DynamicExecutionFabric(now=lambda: NOW)
    workload = Workload("execution:false", "execute real work", frozenset({"python"}))
    result = fabric.execute(workload, [
        obs("primary", capabilities={"python"}, score=0.99),
        obs("secondary", capabilities={"python"}, score=0.70),
    ], lambda route, _: False if route == "primary" else {"status": "success", "receipt": "ok"})
    assert result.ok is True
    assert result.substrate == "secondary"


def test_accepted_asynchronous_result_is_not_completed_or_retried() -> None:
    fabric = DynamicExecutionFabric(now=lambda: NOW)
    workload = Workload("execution:queued", "submit async work once", frozenset({"ci"}))
    calls: list[str] = []
    def execute(route: str, _: Workload) -> dict:
        calls.append(route)
        return {"status": "queued", "job_id": "job-12"}

    result = fabric.execute(workload, [
        obs("primary", capabilities={"ci"}, score=0.99),
        obs("secondary", capabilities={"ci"}, score=0.80),
    ], execute)
    assert result.ok is False
    assert result.status == "pending"
    assert result.substrate == "primary"
    assert calls == ["primary"]
    assert result.result["job_id"] == "job-12"


def test_silent_executor_return_cannot_claim_verified_success_or_blindly_retry() -> None:
    fabric = DynamicExecutionFabric(now=lambda: NOW)
    workload = Workload("execution:silent", "report honest result", frozenset({"python"}))
    calls: list[str] = []
    def execute(route: str, _: Workload) -> None:
        calls.append(route)
        return None

    result = fabric.execute(workload, [
        obs("primary", capabilities={"python"}, score=0.99),
        obs("secondary", capabilities={"python"}, score=0.80),
    ], execute)
    assert result.ok is False
    assert result.status == "unconfirmed"
    assert calls == ["primary"]


def test_failed_return_without_alternative_is_exhausted_not_success() -> None:
    fabric = DynamicExecutionFabric(now=lambda: NOW)
    workload = Workload("execution:failed-only", "complete work", frozenset({"python"}))
    result = fabric.execute(workload, [obs("only", capabilities={"python"})],
                            lambda route, _: {"ok": False, "error": "provider refused"})
    assert result.ok is False
    assert result.status == "route_exhausted"
    assert result.failures[0]["substrate"] == "only"


def test_required_receipt_without_native_reference_is_unconfirmed() -> None:
    fabric = DynamicExecutionFabric(now=lambda: NOW)
    work = Workload(
        "execution:receipt-proof",
        "confirm the actual supported provider outcome",
        frozenset({"ci"}),
        requires_receipts=True,
    )
    attempted = []
    result = fabric.execute(work, [
        obs("primary", capabilities={"ci"}, score=0.99),
        obs("fallback", capabilities={"ci"}, score=0.80),
    ], lambda route, _: attempted.append(route) or {"status": "success"})
    assert result.ok is False
    assert result.status == "unconfirmed"
    assert attempted == ["primary"]
    assert result.objective == work.objective


def test_terminal_readback_requirement_cannot_be_satisfied_by_success_text() -> None:
    fabric = DynamicExecutionFabric(now=lambda: NOW)
    work = Workload(
        "execution:readback-proof",
        "read back deployed artifact rather than trusting the submission",
        frozenset({"deploy"}),
        requires_receipts=True,
        requires_terminal_readback=True,
    )
    attempted = []
    result = fabric.execute(work, [
        obs("primary", capabilities={"deploy"}),
        obs("fallback", capabilities={"deploy"}, score=0.7),
    ], lambda route, _: attempted.append(route) or {
        "status": "success", "receipt": "provider:submitted-1"
    })
    assert result.ok is False
    assert result.status == "unconfirmed"
    assert attempted == ["primary"]


def test_required_native_receipt_and_terminal_readback_enable_verified_success() -> None:
    fabric = DynamicExecutionFabric(now=lambda: NOW)
    work = Workload(
        "execution:verified-proof",
        "complete actual provider-verified work",
        frozenset({"deploy"}),
        requires_receipts=True,
        requires_terminal_readback=True,
    )
    result = fabric.execute(work, [
        obs("primary", capabilities={"deploy"}),
    ], lambda _route, _: {
        "status": "verified",
        "provider_receipt_id": "provider:operation-7",
        "terminal_readback": True,
    })
    assert result.ok is True
    assert result.status == "success"
    assert result.substrate == "primary"


def test_status_success_without_required_readback_is_not_blindly_replayed() -> None:
    fabric = DynamicExecutionFabric(now=lambda: NOW)
    work = Workload(
        "execution:unknown-provider-effect",
        "preserve uncertain effect and reconcile rather than duplicate it",
        frozenset({"ci"}),
        requires_terminal_readback=True,
    )
    attempted = []
    result = fabric.execute(work, [
        obs("primary", capabilities={"ci"}, score=0.99),
        obs("fallback", capabilities={"ci"}, score=0.6),
    ], lambda route, _: attempted.append(route) or {"status": "success", "terminal_readback": False})
    assert result.status == "unconfirmed"
    assert attempted == ["primary"]
