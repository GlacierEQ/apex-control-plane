"""Executable route-vs-scope fidelity invariant for APEX.

A route is an implementation path. It is not the Operator's mission.
A route failure or temporary route skip therefore cannot mutate the active
objective or its scope. Objective deferment/removal is a separate authority
transition and requires an explicit source-bearing Operator reference.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class RouteScopeViolation(RuntimeError):
    """Raised when route state is promoted into mission/scope state."""


class ObjectiveState(str, Enum):
    ACTIVE = "active"
    DEFERRED = "deferred"
    REMOVED = "removed"


class RouteState(str, Enum):
    AVAILABLE = "available"
    SELECTED = "selected"
    BLOCKED = "blocked"
    TEMPORARILY_SKIPPED = "temporarily_skipped"


@dataclass(frozen=True, slots=True)
class RouteScopeSnapshot:
    objective_state: str
    selected_route_ref: str | None
    route_states: tuple[tuple[str, str], ...]
    operator_scope_mutation_ref: str | None


@dataclass(slots=True)
class RouteScopeFidelity:
    """Keep route mutations and Operator-owned objective mutations disjoint."""

    policy: Mapping[str, Any]
    objective_state: ObjectiveState = ObjectiveState.ACTIVE
    selected_route_ref: str | None = None
    route_states: dict[str, RouteState] = field(default_factory=dict)
    operator_scope_mutation_ref: str | None = None

    def __post_init__(self) -> None:
        self._validate_policy()

    def reset(self) -> RouteScopeSnapshot:
        self.objective_state = ObjectiveState.ACTIVE
        self.selected_route_ref = None
        self.route_states.clear()
        self.operator_scope_mutation_ref = None
        return self.snapshot()

    def block_route(
        self,
        route_ref: str,
        *,
        alternate_route_ref: str | None = None,
    ) -> RouteScopeSnapshot:
        """Block one route while preserving the mission as ACTIVE."""
        self._require_active_objective()
        route = _require_ref(route_ref, "route_ref")
        self.route_states[route] = RouteState.BLOCKED
        if self.selected_route_ref == route:
            self.selected_route_ref = None
        if alternate_route_ref is not None:
            self.select_route(alternate_route_ref)
        self._assert_route_change_preserved_mission()
        return self.snapshot()

    def temporarily_skip_route(
        self,
        route_ref: str,
        *,
        alternate_route_ref: str | None = None,
    ) -> RouteScopeSnapshot:
        """Change sequencing only; objective and scope remain ACTIVE."""
        self._require_active_objective()
        route = _require_ref(route_ref, "route_ref")
        self.route_states[route] = RouteState.TEMPORARILY_SKIPPED
        if self.selected_route_ref == route:
            self.selected_route_ref = None
        if alternate_route_ref is not None:
            self.select_route(alternate_route_ref)
        self._assert_route_change_preserved_mission()
        return self.snapshot()

    def select_route(self, route_ref: str) -> RouteScopeSnapshot:
        self._require_active_objective()
        route = _require_ref(route_ref, "route_ref")
        state = self.route_states.get(route)
        if state in {RouteState.BLOCKED, RouteState.TEMPORARILY_SKIPPED}:
            raise RouteScopeViolation(
                f"cannot select route in state={state.value}: {route}"
            )
        if self.selected_route_ref and self.selected_route_ref != route:
            prior = self.selected_route_ref
            if self.route_states.get(prior) is RouteState.SELECTED:
                self.route_states[prior] = RouteState.AVAILABLE
        self.route_states[route] = RouteState.SELECTED
        self.selected_route_ref = route
        self._assert_route_change_preserved_mission()
        return self.snapshot()

    def mutate_objective(
        self,
        new_state: str | ObjectiveState,
        *,
        operator_scope_mutation_ref: str,
    ) -> RouteScopeSnapshot:
        """Allow mission/scope mutation only from explicit Operator authority."""
        try:
            state = ObjectiveState(new_state)
        except ValueError as exc:
            raise RouteScopeViolation(
                "objective state must be active, deferred, or removed; route-level "
                "states such as skipped/blocked are forbidden"
            ) from exc
        if state is ObjectiveState.ACTIVE:
            raise RouteScopeViolation(
                "objective mutation is only for explicit deferment/removal"
            )
        authority = _require_operator_ref(operator_scope_mutation_ref)
        self.objective_state = state
        self.operator_scope_mutation_ref = authority
        self.selected_route_ref = None
        return self.snapshot()

    def snapshot(self) -> RouteScopeSnapshot:
        return RouteScopeSnapshot(
            objective_state=self.objective_state.value,
            selected_route_ref=self.selected_route_ref,
            route_states=tuple(
                sorted((ref, state.value) for ref, state in self.route_states.items())
            ),
            operator_scope_mutation_ref=self.operator_scope_mutation_ref,
        )

    def _require_active_objective(self) -> None:
        if self.objective_state is not ObjectiveState.ACTIVE:
            raise RouteScopeViolation(
                f"route mutation requires active objective; got {self.objective_state.value}"
            )

    def _assert_route_change_preserved_mission(self) -> None:
        if self.objective_state is not ObjectiveState.ACTIVE:
            raise RouteScopeViolation(
                "route mutation illegally changed objective state"
            )
        if self.operator_scope_mutation_ref is not None:
            raise RouteScopeViolation(
                "route mutation cannot manufacture Operator scope authority"
            )

    def _validate_policy(self) -> None:
        required_true = (
            "route_failure_preserves_objective",
            "temporary_skip_preserves_objective",
            "temporary_skip_is_sequence_only",
            "objective_mutation_requires_explicit_operator_ref",
        )
        for key in required_true:
            if self.policy.get(key) is not True:
                raise RouteScopeViolation(f"route-scope policy requires {key}=true")

        objective_states = set(self.policy.get("allowed_objective_states", ()))
        if objective_states != {item.value for item in ObjectiveState}:
            raise RouteScopeViolation("route-scope allowed_objective_states is invalid")
        route_states = set(self.policy.get("allowed_route_states", ()))
        if route_states != {item.value for item in RouteState}:
            raise RouteScopeViolation("route-scope allowed_route_states is invalid")
        forbidden = set(self.policy.get("forbidden_inferred_objective_states", ()))
        if "skipped" not in forbidden or "blocked" not in forbidden:
            raise RouteScopeViolation(
                "route-scope policy must forbid inferred skipped/blocked objective states"
            )


def _require_ref(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RouteScopeViolation(f"{field_name} must be non-empty")
    ref = value.strip()
    prefix, sep, locator = ref.partition(":")
    if not sep or not prefix.strip() or not locator.strip():
        raise RouteScopeViolation(
            f"{field_name} must use provider-or-kind:locator form"
        )
    return ref


def _require_operator_ref(value: str) -> str:
    ref = _require_ref(value, "operator_scope_mutation_ref")
    prefix = ref.split(":", 1)[0].strip().lower()
    if prefix not in {"operator-command", "operator-source"}:
        raise RouteScopeViolation(
            "objective/scope mutation requires explicit operator-command: or operator-source: authority"
        )
    return ref
