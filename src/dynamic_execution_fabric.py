#!/usr/bin/env python3
"""Dynamic execution-substrate routing for the GlacierEQ control plane.

The router selects a currently eligible execution substrate from live observations.
No provider is canonical. Selection is ephemeral runtime state and never changes the
Operator objective, mission authority, or source truth.

Static policy defines invariants. Live observations decide the route.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable, FrozenSet, Iterable, Sequence


ELIGIBLE_HEALTH = {"healthy", "degraded", "unknown"}
INELIGIBLE_HEALTH = {"failed", "unavailable", "disabled", "exhausted"}


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
class RoutePlan:
    workload_id: str
    objective: str
    selected: str | None
    fallbacks: tuple[str, ...]
    routes: tuple[RouteCandidate, ...]
    execution_state: str
    mission_state: str = "unchanged"
    selection_is_authority: bool = False


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

        eligible = not reasons

        # Health dominates. Cost and latency tune among equally valid routes.
        capability_coverage = len(workload.capabilities & obs.capabilities) / max(
            len(workload.capabilities), 1
        )
        health_factor = {
            "healthy": 1.0,
            "degraded": 0.72,
            "unknown": 0.45,
        }.get(health, 0.0)
        raw = (
            (obs.health_score * 0.55)
            + (capability_coverage * 0.15)
            + (obs.latency_score * 0.15)
            + (obs.cost_score * 0.15)
        )
        score = max(0.0, min(1.0, raw * health_factor))
        if not eligible:
            score = 0.0

        return RouteCandidate(
            substrate=obs.name,
            eligible=eligible,
            score=round(score, 6),
            reasons=tuple(reasons),
            observed_at=obs.observed_at,
        )
