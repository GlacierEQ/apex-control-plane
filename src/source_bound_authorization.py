"""Source-bound Operator authorization envelopes for provider actions.

Authorization is evidence of Operator authority, not a secondary approval gate.  One
Operator source may authorize an explicit action, a bounded plan/batch, or an action
class.  Every constituent provider action is still checked for membership, idempotency,
and material/destructive deltas before execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence


class AuthorizationScopeError(ValueError):
    pass


class AuthorizationScopeKind(str, Enum):
    EXPLICIT_ACTION = "explicit_action"
    PLAN_BATCH = "plan_batch"
    ACTION_CLASS = "action_class"


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return sha256(encoded).hexdigest()


def _required_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise AuthorizationScopeError(f"{name} is required")
    return text


@dataclass(frozen=True, slots=True)
class SourceBoundAuthorization:
    source_ref: str
    kind: AuthorizationScopeKind
    connector: str
    operations: frozenset[str]
    target_constraints: Mapping[str, Any]
    plan_ref: str | None = None
    allow_destructive: bool = False
    allow_material_strategy_delta: bool = False

    @property
    def envelope_sha256(self) -> str:
        return _canonical_sha256({
            "source_ref": self.source_ref,
            "kind": self.kind.value,
            "connector": self.connector,
            "operations": sorted(self.operations),
            "target_constraints": dict(self.target_constraints),
            "plan_ref": self.plan_ref,
            "allow_destructive": self.allow_destructive,
            "allow_material_strategy_delta": self.allow_material_strategy_delta,
        })


def parse_authorization_envelope(payload: Mapping[str, Any]) -> SourceBoundAuthorization:
    if not isinstance(payload, Mapping):
        raise AuthorizationScopeError("authorization envelope must be an object")
    try:
        kind = AuthorizationScopeKind(_required_text(payload.get("kind"), "authorization.kind"))
    except ValueError as exc:
        raise AuthorizationScopeError("authorization.kind is unsupported") from exc
    raw_operations = payload.get("operations")
    if not isinstance(raw_operations, Sequence) or isinstance(raw_operations, (str, bytes)):
        raise AuthorizationScopeError("authorization.operations must be an array")
    operations = frozenset(str(item).strip() for item in raw_operations if str(item).strip())
    if not operations:
        raise AuthorizationScopeError("authorization.operations requires at least one operation")
    target_constraints = payload.get("target_constraints", {})
    if not isinstance(target_constraints, Mapping):
        raise AuthorizationScopeError("authorization.target_constraints must be an object")
    plan_ref = str(payload.get("plan_ref") or "").strip() or None
    if kind is AuthorizationScopeKind.PLAN_BATCH and plan_ref is None:
        raise AuthorizationScopeError("plan_batch authorization requires plan_ref")
    return SourceBoundAuthorization(
        source_ref=_required_text(payload.get("source_ref"), "authorization.source_ref"),
        kind=kind,
        connector=_required_text(payload.get("connector"), "authorization.connector"),
        operations=operations,
        target_constraints=dict(target_constraints),
        plan_ref=plan_ref,
        allow_destructive=payload.get("allow_destructive") is True,
        allow_material_strategy_delta=payload.get("allow_material_strategy_delta") is True,
    )


def authorize_constituent_action(
    authorization: SourceBoundAuthorization,
    *,
    connector: str,
    operation: str,
    target: Mapping[str, Any],
    destructive: bool = False,
    material_strategy_delta: bool = False,
) -> str:
    """Return the envelope digest when a constituent action is within Operator scope."""
    if connector != authorization.connector:
        raise AuthorizationScopeError("connector is outside the Operator authorization envelope")
    if operation not in authorization.operations:
        raise AuthorizationScopeError("operation is outside the Operator authorization envelope")
    for key, expected in authorization.target_constraints.items():
        if target.get(key) != expected:
            raise AuthorizationScopeError(f"target.{key} is outside the Operator authorization envelope")
    if destructive and not authorization.allow_destructive:
        raise AuthorizationScopeError("destructive action requires renewed explicit Operator authority")
    if material_strategy_delta and not authorization.allow_material_strategy_delta:
        raise AuthorizationScopeError("material strategy delta requires renewed explicit Operator authority")
    return authorization.envelope_sha256
