"""Fail-closed route/scope invariants for Operator-directed execution.

A route is how work is executed. Scope is what the Operator asked to achieve.
They are separate state dimensions: failure of a tool/provider/route must never
silently become deletion, deferral, or narrowing of mission scope.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Iterable


class ScopeInvariantViolation(RuntimeError):
    """Raised when routing attempts to mutate Operator mission scope."""


class RouteEventKind(str, Enum):
    TOOL_FAILURE = "tool_failure"
    ROUTE_UNAVAILABLE = "route_unavailable"
    TEMPORARY_SKIP = "temporary_skip"
    EXPLICIT_SCOPE_CHANGE = "explicit_scope_change"


@dataclass(frozen=True, slots=True)
class MissionRoutingState:
    mission_id: str
    objective: str
    scope_items: tuple[str, ...]
    active_route: str | None = None
    unavailable_routes: tuple[str, ...] = ()
    temporarily_deferred: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.mission_id.strip():
            raise ValueError("mission_id is required")
        if not self.objective.strip():
            raise ValueError("objective is required")
        if not self.scope_items or any(not item.strip() for item in self.scope_items):
            raise ValueError("scope_items must contain non-empty Operator scope")


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def assert_scope_transition(
    before: MissionRoutingState,
    after: MissionRoutingState,
    *,
    explicit_operator_scope_change: bool = False,
) -> None:
    """Reject accidental mission mutation during routing changes.

    Objective and scope are immutable across routing events unless the caller can
    bind an explicit Operator scope-change instruction. A blocker, failed tool,
    unavailable connector, timeout, or temporary skip is never such authority.
    """
    if before.mission_id != after.mission_id:
        raise ScopeInvariantViolation("routing transition changed mission identity")

    if explicit_operator_scope_change:
        return

    if before.objective != after.objective:
        raise ScopeInvariantViolation(
            "route change attempted to mutate the Operator objective"
        )
    if before.scope_items != after.scope_items:
        raise ScopeInvariantViolation(
            "route change attempted to mutate Operator scope without an explicit scope change"
        )


def apply_route_event(
    state: MissionRoutingState,
    *,
    kind: RouteEventKind | str,
    route: str | None = None,
    subject: str | None = None,
    replacement_route: str | None = None,
    explicit_operator_scope_change: bool = False,
    new_objective: str | None = None,
    new_scope_items: Iterable[str] | None = None,
) -> MissionRoutingState:
    """Apply routing data without laundering it into mission-direction authority."""
    event = RouteEventKind(kind)

    if event in {RouteEventKind.TOOL_FAILURE, RouteEventKind.ROUTE_UNAVAILABLE}:
        failed_route = (route or state.active_route or "").strip()
        if not failed_route:
            raise ValueError("failed/unavailable route must be identified")
        candidate = replace(
            state,
            active_route=(replacement_route.strip() if replacement_route else None),
            unavailable_routes=_ordered_unique((*state.unavailable_routes, failed_route)),
        )
        assert_scope_transition(state, candidate)
        return candidate

    if event is RouteEventKind.TEMPORARY_SKIP:
        deferred = (subject or "").strip()
        if not deferred:
            raise ValueError("temporary skip subject must be identified")
        # Sequencing metadata only: the deferred objective/scope remains in scope.
        candidate = replace(
            state,
            temporarily_deferred=_ordered_unique(
                (*state.temporarily_deferred, deferred)
            ),
            active_route=(replacement_route.strip() if replacement_route else state.active_route),
        )
        assert_scope_transition(state, candidate)
        return candidate

    if event is RouteEventKind.EXPLICIT_SCOPE_CHANGE:
        if not explicit_operator_scope_change:
            raise ScopeInvariantViolation(
                "scope mutation requires an explicit Operator scope-change instruction"
            )
        scope = tuple(new_scope_items) if new_scope_items is not None else state.scope_items
        candidate = replace(
            state,
            objective=new_objective.strip() if new_objective is not None else state.objective,
            scope_items=scope,
            active_route=(replacement_route.strip() if replacement_route else state.active_route),
        )
        assert_scope_transition(
            state,
            candidate,
            explicit_operator_scope_change=True,
        )
        return candidate

    raise AssertionError(f"unhandled route event: {event}")
