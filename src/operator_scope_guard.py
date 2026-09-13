"""Fail-closed operator route/scope semantics."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EventClass(StrEnum):
    TOOL_FAILURE = "TOOL_FAILURE"
    ROUTE_UNAVAILABLE = "ROUTE_UNAVAILABLE"
    TEMPORARY_SKIP = "TEMPORARY_SKIP"
    OPERATOR_SCOPE_CHANGE = "OPERATOR_SCOPE_CHANGE"


class Effect(StrEnum):
    ROUTE_CHANGE_ONLY = "ROUTE_CHANGE_ONLY"
    CONTINUE_SAME_MISSION = "CONTINUE_SAME_MISSION"
    SEQUENCING_CHANGE_ONLY = "SEQUENCING_CHANGE_ONLY"
    CONTINUE_OTHER_FRONTIER = "CONTINUE_OTHER_FRONTIER"
    SCOPE_CHANGE = "SCOPE_CHANGE"
    DROP_OBJECTIVE = "DROP_OBJECTIVE"
    DEFER_OBJECTIVE = "DEFER_OBJECTIVE"
    NARROW_SCOPE = "NARROW_SCOPE"
    NO_SCOPE_CHANGE = "NO_SCOPE_CHANGE"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class ScopeResolution:
    allowed: bool
    normalized_effect: Effect
    mission_scope_preserved: bool
    reason: str


class ScopeSemanticViolation(RuntimeError):
    pass


def resolve_scope_effect(
    event_class: EventClass | str,
    requested_effect: Effect | str,
    *,
    explicit_operator_scope_change: bool = False,
) -> ScopeResolution:
    """Preserve mission scope unless the Operator explicitly changes it."""
    try:
        event = EventClass(str(event_class))
    except ValueError:
        return ScopeResolution(False, Effect.UNRESOLVED, True, "unknown event class; preserve mission and retrieve context")

    try:
        effect = Effect(str(requested_effect))
    except ValueError:
        effect = Effect.UNRESOLVED

    if event in {EventClass.TOOL_FAILURE, EventClass.ROUTE_UNAVAILABLE}:
        if effect not in {Effect.ROUTE_CHANGE_ONLY, Effect.CONTINUE_SAME_MISSION}:
            return ScopeResolution(False, Effect.ROUTE_CHANGE_ONLY, True, "tool/route failure changes execution route, never mission objective or scope")
        return ScopeResolution(True, Effect.ROUTE_CHANGE_ONLY, True, "select another viable route and continue the same mission")

    if event is EventClass.TEMPORARY_SKIP:
        if effect not in {Effect.SEQUENCING_CHANGE_ONLY, Effect.CONTINUE_OTHER_FRONTIER}:
            return ScopeResolution(False, Effect.SEQUENCING_CHANGE_ONLY, True, "temporary skip changes execution order only; objective remains in scope")
        return ScopeResolution(True, Effect.SEQUENCING_CHANGE_ONLY, True, "continue another frontier while preserving the skipped objective")

    if event is EventClass.OPERATOR_SCOPE_CHANGE:
        if not explicit_operator_scope_change:
            return ScopeResolution(False, Effect.NO_SCOPE_CHANGE, True, "scope mutation requires an explicit Operator scope/objective change")
        return ScopeResolution(True, Effect.SCOPE_CHANGE, False, "explicit Operator scope change controls")

    return ScopeResolution(False, Effect.UNRESOLVED, True, "preserve mission and retrieve context")


def require_scope_effect(
    event_class: EventClass | str,
    requested_effect: Effect | str,
    *,
    explicit_operator_scope_change: bool = False,
) -> ScopeResolution:
    resolution = resolve_scope_effect(
        event_class,
        requested_effect,
        explicit_operator_scope_change=explicit_operator_scope_change,
    )
    if not resolution.allowed:
        raise ScopeSemanticViolation(resolution.reason)
    return resolution
