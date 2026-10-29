#!/usr/bin/env python3
"""Dynamic execution-substrate routing for the GlacierEQ control plane.

The router selects a currently eligible execution substrate from live observations.
No provider is canonical. Selection is ephemeral runtime state and never changes the
Operator objective, mission authority, or source truth.

Static policy defines invariants. Live observations decide the route.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, FrozenSet, Iterable, Sequence


ELIGIBLE_HEALTH = {"healthy", "degraded", "unknown"}
INELIGIBLE_HEALTH = {"failed", "unavailable", "disabled", "exhausted"}
# Observation quality is not execution permission. Unknown/stale health is a
# ranking warning, never a reason to refuse a capable provider invocation.
OBSERVATION_WARNINGS = {"observation_from_future", "stale_observation", "unknown_health_state"}


@dataclass(frozen=True, slots=True)
class Workload:
    workload_id: str
    objective: str
    capabilities: FrozenSet[str]
    private_repo: bool = False
    requires_exact_source: bool = False
    requires_receipts: bool = False
    requires_terminal_readback: bool = False

    def __post_init__(self) -> None:
        if not self.workload_id.strip():
            raise ValueError("workload_id is required")
        if not self.objective.strip():
            raise ValueError("objective is required")
        if not self.capabilities:
            raise ValueError("at least one required capability is required")


@dataclass(frozen=True, slots=True)
class SubstrateObservation:
    name: str
    capabilities: FrozenSet[str]
    health: str
    health_score: float
    private_repo: bool
    exact_source: bool
    receipts: bool
    terminal_readback: bool
    observed_at: datetime
    cost_score: float = 0.5
    latency_score: float = 0.5

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("substrate name is required")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        for field_name, value in (
            ("health_score", self.health_score),
            ("cost_score", self.cost_score),
            ("latency_score", self.latency_score),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    substrate: str
    eligible: bool
    score: float
    reasons: tuple[str, ...]
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    ok: bool
    status: str
    workload_id: str
    objective: str
    substrate: str | None
    attempted: tuple[str, ...]
    failures: tuple[dict[str, str], ...]
    result: Any = None
    mission_state: str = "unchanged"


@dataclass(frozen=True, slots=True)
class RoutePlan:
    workload_id: str
    objective: str
    selected: str | None
    fallbacks: tuple[str, ...]
    routes: tuple[RouteCandidate, ...]
    execution_state: str
    mission_state: str = "unchanged"
    selection_is_authority: bool = False


class DynamicObservationRegistry:
    """Runtime registry of substrate observers.

    Observers are supplied by connectors or control-plane adapters at runtime.
    A failed observer degrades only that substrate; it does not stop collection
    from other registered substrates.
    """

    def __init__(self) -> None:
        self._observers: dict[str, Callable[[Workload], SubstrateObservation]] = {}

    def register(
        self,
        name: str,
        observer: Callable[[Workload], SubstrateObservation],
    ) -> None:
        key = name.strip()
        if not key:
            raise ValueError("observer name is required")
        self._observers[key] = observer

    def unregister(self, name: str) -> None:
        self._observers.pop(name, None)

    def observe(
        self,
        workload: Workload,
        *,
        observed_at: datetime | None = None,
    ) -> tuple[SubstrateObservation, ...]:
        fallback_time = observed_at or datetime.now(UTC)
        if fallback_time.tzinfo is None or fallback_time.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")

        observations: list[SubstrateObservation] = []
        for name in sorted(self._observers):
            observer = self._observers[name]
            try:
                observation = observer(workload)
                if observation.name != name:
                    observation = SubstrateObservation(
                        name=name,
                        capabilities=observation.capabilities,
                        health=observation.health,
                        health_score=observation.health_score,
                        private_repo=observation.private_repo,
                        exact_source=observation.exact_source,
                        receipts=observation.receipts,
                        terminal_readback=observation.terminal_readback,
                        observed_at=observation.observed_at,
                        cost_score=observation.cost_score,
                        latency_score=observation.latency_score,
                    )
            except Exception:
                observation = SubstrateObservation(
                    name=name,
                    capabilities=frozenset(),
                    health="unavailable",
                    health_score=0.0,
                    private_repo=False,
                    exact_source=False,
                    receipts=False,
                    terminal_readback=False,
                    observed_at=fallback_time,
                    cost_score=0.0,
                    latency_score=0.0,
                )
            observations.append(observation)
        return tuple(observations)


def _provider_outcome(result: Any) -> tuple[str, str | None]:
    """Distinguish terminal success, explicit failure, and uncertain execution.

    A callback invocation is not evidence of successful work. An ambiguous or
    queued side effect is not retried blindly, even when fallback routes exist.
    """
    if result is None:
        return "unconfirmed", "executor_returned_no_result"
    if result is False:
        return "failed", "executor_returned_false"
    if result is True:
        return "success", None
    if isinstance(result, Mapping):
        state = str(result.get("status") or result.get("state") or "").strip().lower()
        if result.get("ok") is False or result.get("success") is False:
            return "failed", str(result.get("error") or state or "provider_reported_failure")
        if state in {"failed", "failure", "error", "denied", "rejected", "cancelled", "canceled", "unavailable", "timed_out"}:
            return "failed", str(result.get("error") or state)
        if state in {"queued", "pending", "accepted", "submitted", "scheduled", "running", "processing", "in_progress"}:
            return "pending", None
        if result.get("error"):
            return "failed", str(result["error"])
        if state in {"success", "succeeded", "complete", "completed", "verified", "passed", "pass", "ok"} or result.get("ok") is True or result.get("success") is True:
            return "success", None
        if result.get("receipt") or result.get("provider_receipt_id"):
            return "success", None
        return "unconfirmed", "executor_returned_unclassified_result"
    if isinstance(result, str):
        state = result.strip().lower()
        if state in {"success", "completed", "verified", "succeeded"}:
            return "success", None
        if state in {"failed", "failure", "error", "rejected"}:
            return "failed", state
        if state in {"queued", "pending", "accepted", "running"}:
            return "pending", None
    return "unconfirmed", "executor_result_not_verified"


class DynamicExecutionFabric:
    """Rank live execution substrates without letting routing redefine the mission."""

    def __init__(
        self,
        *,
        now: Callable[[], datetime] | None = None,
        freshness_window: timedelta = timedelta(minutes=30),
    ) -> None:
        self._now = now or (lambda: datetime.now(UTC))
        self.freshness_window = freshness_window
        if freshness_window <= timedelta(0):
            raise ValueError("freshness_window must be positive")

    def plan(
        self,
        workload: Workload,
        observations: Sequence[SubstrateObservation] | Iterable[SubstrateObservation],
    ) -> RoutePlan:
        candidates = tuple(self._candidate(workload, item) for item in observations)
        ranked = tuple(
            sorted(
                candidates,
                key=lambda item: (
                    not item.eligible,
                    any(reason in OBSERVATION_WARNINGS for reason in item.reasons),
                    -item.score,
                    item.substrate,
                ),
            )
        )
        eligible = [item for item in ranked if item.eligible]
        selected = eligible[0].substrate if eligible else None
        fallbacks = tuple(item.substrate for item in eligible[1:])
        return RoutePlan(
            workload_id=workload.workload_id,
            objective=workload.objective,
            selected=selected,
            fallbacks=fallbacks,
            routes=ranked,
            execution_state="routable" if selected else "no_current_route",
        )

    def execute(
        self,
        workload: Workload,
        observations: Sequence[SubstrateObservation] | Iterable[SubstrateObservation],
        executor: Callable[[str, Workload], Any],
    ) -> ExecutionResult:
        """Attempt ranked eligible routes until one succeeds.

        Provider failure changes provider state for this work unit; it does not
        mutate the Operator objective or reinterpret the mission.
        """
        plan = self.plan(workload, observations)
        attempted: list[str] = []
        failures: list[dict[str, str]] = []

        route_order = ([plan.selected] if plan.selected else []) + list(plan.fallbacks)
        for substrate in route_order:
            if substrate is None:
                continue
            attempted.append(substrate)
            try:
                result = executor(substrate, workload)
            except Exception as exc:
                failures.append({
                    "substrate": substrate,
                    "error": str(exc),
                })
                continue
            outcome, reason = _provider_outcome(result)
            if outcome == "failed":
                failures.append({
                    "substrate": substrate,
                    "error": reason or "provider_reported_failure",
                })
                continue
            # A provider's optimistic status is not evidence of the specific
            # outcome this workload requires. Unknown side effects must be
            # reconciled; do not automatically replay on a fallback substrate.
            if outcome == "success" and workload.requires_receipts:
                has_receipt = (
                    isinstance(result, Mapping)
                    and bool(result.get("receipt") or result.get("provider_receipt_id"))
                )
                if not has_receipt:
                    outcome = "unconfirmed"
            if outcome == "success" and workload.requires_terminal_readback:
                has_readback = (
                    isinstance(result, Mapping)
                    and result.get("terminal_readback") is True
                )
                if not has_readback:
                    outcome = "unconfirmed"
            return ExecutionResult(
                ok=outcome == "success",
                status=outcome,
                workload_id=workload.workload_id,
                objective=workload.objective,
                substrate=substrate,
                attempted=tuple(attempted),
                failures=tuple(failures),
                result=result,
            )

        return ExecutionResult(
            ok=False,
            status="route_exhausted" if route_order else "no_current_route",
            workload_id=workload.workload_id,
            objective=workload.objective,
            substrate=None,
            attempted=tuple(attempted),
            failures=tuple(failures),
        )

    def _candidate(self, workload: Workload, obs: SubstrateObservation) -> RouteCandidate:
        reasons: list[str] = []
        now = self._now()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("router clock must return a timezone-aware datetime")

        age = now - obs.observed_at
        if age < timedelta(0):
            reasons.append("observation_from_future")
        if age > self.freshness_window:
            reasons.append("stale_observation")

        health = obs.health.strip().lower()
        if health in INELIGIBLE_HEALTH:
            reasons.append(f"health_{health}")
        elif health not in ELIGIBLE_HEALTH:
            reasons.append("unknown_health_state")

        missing = sorted(workload.capabilities - obs.capabilities)
        if missing:
            reasons.append("missing_capabilities:" + ",".join(missing))

        if workload.private_repo and not obs.private_repo:
            reasons.append("private_repo_unsupported")
        if workload.requires_exact_source and not obs.exact_source:
            reasons.append("exact_source_unverified")
        if workload.requires_receipts and not obs.receipts:
            reasons.append("receipts_unavailable")
        if workload.requires_terminal_readback and not obs.terminal_readback:
            reasons.append("terminal_readback_unavailable")

        # Monitoring uncertainty does not veto actual execution. Hard
        # incompatibility (capability, explicit unavailability, or a workload
        # requirement that this substrate cannot perform) is still factual.
        eligible = not any(reason not in OBSERVATION_WARNINGS for reason in reasons)

        # Health dominates. Cost and latency tune among equally valid routes.
        capability_coverage = len(workload.capabilities & obs.capabilities) / max(
            len(workload.capabilities), 1
        )
        health_factor = {
            "healthy": 1.0,
            "degraded": 0.72,
            "unknown": 0.45,
        }.get(health, 0.25)
        raw = (
            (obs.health_score * 0.55)
            + (capability_coverage * 0.15)
            + (obs.latency_score * 0.15)
            + (obs.cost_score * 0.15)
        )
        score = max(0.0, min(1.0, raw * health_factor))
        # Unknown or aged observations are attempted after fresh capable routes;
        # the execution result, not the monitoring age, determines success.
        if any(reason in OBSERVATION_WARNINGS for reason in reasons):
            score *= 0.5
        if not eligible:
            score = 0.0

        return RouteCandidate(
            substrate=obs.name,
            eligible=eligible,
            score=round(score, 6),
            reasons=tuple(reasons),
            observed_at=obs.observed_at,
        )
