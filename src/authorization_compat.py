"""Compatibility adapter from source-bound Operator authority to legacy exact-action validation.

The legacy exact-action digest remains useful as an immutable constituent-action binding,
but it is derived here from a recovered source-bound authorization envelope. It is not a
new per-operation Operator approval.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Mapping

from approved_operation_bridge import (
    ApprovedConnectorAction,
    action_scope_sha256,
    validate_approved_action_request,
)
from connector_receipts import ConnectorCatalog
from source_bound_authorization import (
    AuthorizationScopeError,
    authorize_constituent_action,
    parse_authorization_envelope,
)


def validate_authorized_action_request(
    payload: Mapping[str, Any],
    catalog: ConnectorCatalog,
    *,
    now: datetime | None = None,
) -> ApprovedConnectorAction:
    """Accept legacy exact approval or a source-bound authorization envelope.

    For a source-bound envelope, membership is proven first. The legacy exact-action
    digest is then synthesized as an internal compatibility binding so downstream
    idempotency/readback machinery can remain unchanged during migration.
    """
    envelope_payload = payload.get("authorization_envelope")
    if envelope_payload is None:
        return validate_approved_action_request(payload, catalog, now=now)
    if not isinstance(envelope_payload, Mapping):
        raise AuthorizationScopeError("authorization_envelope must be an object")

    authorization = parse_authorization_envelope(envelope_payload)
    connector = str(payload.get("connector") or "").strip()
    operation = str(payload.get("operation") or "").strip()
    target = payload.get("target")
    if not isinstance(target, Mapping):
        raise AuthorizationScopeError("target must be an object")

    destructive = payload.get("destructive") is True
    material_strategy_delta = payload.get("material_strategy_delta") is True
    envelope_digest = authorize_constituent_action(
        authorization,
        connector=connector,
        operation=operation,
        target=target,
        destructive=destructive,
        material_strategy_delta=material_strategy_delta,
    )

    approval = payload.get("approval")
    if not isinstance(approval, Mapping):
        raise AuthorizationScopeError(
            "source-bound action requires approval metadata identifying the Operator source"
        )
    source_ref = str(approval.get("approval_reference") or "").strip()
    if source_ref != authorization.source_ref:
        raise AuthorizationScopeError(
            "approval_reference must match authorization_envelope.source_ref"
        )

    provider_input = payload.get("provider_input")
    if not isinstance(provider_input, Mapping):
        raise AuthorizationScopeError("provider_input must be an object")
    evidence_refs_raw = payload.get("evidence_refs")
    if not isinstance(evidence_refs_raw, list):
        raise AuthorizationScopeError("evidence_refs must be an array")
    evidence_refs = tuple(str(item).strip() for item in evidence_refs_raw if str(item).strip())

    adapted = deepcopy(dict(payload))
    adapted_approval = dict(approval)
    adapted_approval["approval_scope_sha256"] = action_scope_sha256(
        connector=connector,
        operation=operation,
        target=target,
        provider_input=provider_input,
        consequence=str(payload.get("consequence") or "").strip(),
        evidence_refs=evidence_refs,
        idempotency_key=str(payload.get("idempotency_key") or "").strip(),
    )
    adapted["approval"] = adapted_approval

    action = validate_approved_action_request(adapted, catalog, now=now)
    # Keep the source-bound envelope digest available to callers without changing the
    # legacy ApprovedConnectorAction ABI during this compatibility phase.
    object.__setattr__(action, "approval_reference", f"{authorization.source_ref}#auth={envelope_digest}")
    return action
