"""Source-bound Operator authorization envelopes for provider actions.

Authorization is evidence of Operator authority, not a secondary approval gate.
A source-bound envelope is usable only after its claimed scope is independently
re-resolved from Operator-authored bytes and the source-span binding verifies.
The submitted action request therefore cannot manufacture its own authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from operator_source_binding_contract import SourceResolver, verify_source_span_binding


class AuthorizationScopeError(ValueError):
    pass


class AuthorizationScopeKind(str, Enum):
    EXPLICIT_ACTION = "explicit_action"
    PLAN_BATCH = "plan_batch"
    ACTION_CLASS = "action_class"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _canonical_sha256(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _required_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise AuthorizationScopeError(f"{name} is required")
    return text


def _constraint_match(actual: Any, expected: Any, *, path: str) -> None:
    """Require every source-authored constraint while allowing unspecified fields."""
    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping):
            raise AuthorizationScopeError(f"{path} must be an object")
        for key, value in expected.items():
            if key not in actual:
                raise AuthorizationScopeError(f"{path}.{key} is required by Operator scope")
            _constraint_match(actual[key], value, path=f"{path}.{key}")
        return
    if actual != expected:
        raise AuthorizationScopeError(f"{path} is outside the Operator authorization envelope")


@dataclass(frozen=True, slots=True)
class SourceBoundAuthorization:
    source_ref: str
    source_binding: Mapping[str, Any]
    kind: AuthorizationScopeKind
    connector: str
    operations: frozenset[str]
    target_constraints: Mapping[str, Any]
    provider_input_constraints: Mapping[str, Any]
    consequence_prefixes: tuple[str, ...]
    plan_ref: str | None = None
    allow_destructive: bool = False

    @property
    def scope_payload(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "source_ref": self.source_ref,
            "kind": self.kind.value,
            "connector": self.connector,
            "operations": sorted(self.operations),
            "target_constraints": dict(self.target_constraints),
            "provider_input_constraints": dict(self.provider_input_constraints),
            "consequence_prefixes": list(self.consequence_prefixes),
            "plan_ref": self.plan_ref,
            "allow_destructive": self.allow_destructive,
        }

    @property
    def envelope_sha256(self) -> str:
        return _canonical_sha256(self.scope_payload)


def parse_authorization_envelope(payload: Mapping[str, Any]) -> SourceBoundAuthorization:
    if not isinstance(payload, Mapping):
        raise AuthorizationScopeError("authorization envelope must be an object")
    try:
        kind = AuthorizationScopeKind(_required_text(payload.get("kind"), "authorization.kind"))
    except ValueError as exc:
        raise AuthorizationScopeError("authorization.kind is unsupported") from exc

    source_binding = payload.get("source_binding")
    if not isinstance(source_binding, Mapping):
        raise AuthorizationScopeError(
            "authorization.source_binding must independently bind the Operator source span"
        )
    source_ref = _required_text(payload.get("source_ref"), "authorization.source_ref")
    if str(source_binding.get("source_ref") or "").strip() != source_ref:
        raise AuthorizationScopeError(
            "authorization.source_binding.source_ref must match authorization.source_ref"
        )

    raw_operations = payload.get("operations")
    if not isinstance(raw_operations, Sequence) or isinstance(raw_operations, (str, bytes)):
        raise AuthorizationScopeError("authorization.operations must be an array")
    operations = frozenset(str(item).strip() for item in raw_operations if str(item).strip())
    if not operations:
        raise AuthorizationScopeError("authorization.operations requires at least one operation")

    target_constraints = payload.get("target_constraints", {})
    provider_input_constraints = payload.get("provider_input_constraints", {})
    for value, name in (
        (target_constraints, "authorization.target_constraints"),
        (provider_input_constraints, "authorization.provider_input_constraints"),
    ):
        if not isinstance(value, Mapping):
            raise AuthorizationScopeError(f"{name} must be an object")

    raw_prefixes = payload.get("consequence_prefixes", ())
    if not isinstance(raw_prefixes, Sequence) or isinstance(raw_prefixes, (str, bytes)):
        raise AuthorizationScopeError("authorization.consequence_prefixes must be an array")
    prefixes = tuple(str(item).strip() for item in raw_prefixes if str(item).strip())

    plan_ref = str(payload.get("plan_ref") or "").strip() or None
    if kind is AuthorizationScopeKind.PLAN_BATCH and plan_ref is None:
        raise AuthorizationScopeError("plan_batch authorization requires plan_ref")

    return SourceBoundAuthorization(
        source_ref=source_ref,
        source_binding=dict(source_binding),
        kind=kind,
        connector=_required_text(payload.get("connector"), "authorization.connector"),
        operations=operations,
        target_constraints=dict(target_constraints),
        provider_input_constraints=dict(provider_input_constraints),
        consequence_prefixes=prefixes,
        plan_ref=plan_ref,
        allow_destructive=payload.get("allow_destructive") is True,
    )


def verify_authorization_source(
    authorization: SourceBoundAuthorization,
    *,
    resolver: SourceResolver,
) -> str:
    """Resolve Operator bytes and prove they encode exactly this authorization scope."""
    verification = verify_source_span_binding(
        authorization.source_binding,
        resolver=resolver,
        prefix="authorization.source_binding",
        require_unsuperseded=True,
    )
    if verification.errors:
        raise AuthorizationScopeError("; ".join(verification.errors))
    if verification.span_text is None:
        raise AuthorizationScopeError("authorization source span could not be decoded")

    try:
        source_record = json.loads(verification.span_text)
    except json.JSONDecodeError as exc:
        raise AuthorizationScopeError(
            "authorization source span must be a JSON Operator authorization record"
        ) from exc
    if not isinstance(source_record, Mapping):
        raise AuthorizationScopeError("authorization source record must be an object")

    recorded_scope = source_record.get("authorization_scope", source_record)
    if not isinstance(recorded_scope, Mapping):
        raise AuthorizationScopeError("authorization source record scope must be an object")
    if _canonical_json(recorded_scope) != _canonical_json(authorization.scope_payload):
        raise AuthorizationScopeError(
            "submitted authorization envelope does not match independently resolved Operator source"
        )
    return authorization.envelope_sha256


def authorize_constituent_action(
    authorization: SourceBoundAuthorization,
    *,
    connector: str,
    operation: str,
    target: Mapping[str, Any],
    provider_input: Mapping[str, Any],
    consequence: str,
    destructive: bool = False,
) -> str:
    """Return the verified envelope digest when an action is inside Operator scope."""
    if connector != authorization.connector:
        raise AuthorizationScopeError("connector is outside the Operator authorization envelope")
    if operation not in authorization.operations:
        raise AuthorizationScopeError("operation is outside the Operator authorization envelope")
    _constraint_match(target, authorization.target_constraints, path="target")
    _constraint_match(
        provider_input,
        authorization.provider_input_constraints,
        path="provider_input",
    )
    if authorization.consequence_prefixes and not consequence.startswith(
        authorization.consequence_prefixes
    ):
        raise AuthorizationScopeError(
            "consequence is outside the Operator authorization envelope"
        )
    if destructive and not authorization.allow_destructive:
        raise AuthorizationScopeError(
            "destructive action requires a new source-bound Operator authorization"
        )
    return authorization.envelope_sha256
