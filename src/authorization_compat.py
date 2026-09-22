"""Compatibility adapter from source-bound Operator authority to legacy exact-action validation.

The legacy exact-action digest remains useful as an immutable constituent-action
binding. For source-bound authorization it is synthesized only after the claimed
scope is independently re-resolved from Operator-authored bytes; it is never a
fresh per-operation approval.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from typing import Any, Mapping

from approved_operation_bridge import (
    ApprovedConnectorAction,
    action_scope_sha256,
    validate_approved_action_request,
)
from connector_receipts import ConnectorCatalog
from epistemic_risk_gate import Reversibility
from operator_source_binding_contract import SourceResolver
from source_bound_authorization import (
    AuthorizationScopeError,
    authorize_constituent_action,
    parse_authorization_envelope,
    verify_authorization_source,
)


def validate_authorized_action_request(
    payload: Mapping[str, Any],
    catalog: ConnectorCatalog,
    *,
    now: datetime | None = None,
    source_resolver: SourceResolver | None = None,
) -> ApprovedConnectorAction:
    """Accept legacy exact approval or independently verified source-bound authority."""
    envelope_payload = payload.get("authorization_envelope")
    if envelope_payload is None:
        return validate_approved_action_request(payload, catalog, now=now)
    if not isinstance(envelope_payload, Mapping):
        raise AuthorizationScopeError("authorization_envelope must be an object")
    if source_resolver is None:
        raise AuthorizationScopeError(
            "source-bound authorization requires independent Operator-source readback"
        )
    if "material_strategy_delta" in payload:
        raise AuthorizationScopeError(
            "material_strategy_delta is not caller-authoritative; encode the permitted "
            "strategy scope in the independently resolved Operator authorization record"
        )

    authorization = parse_authorization_envelope(envelope_payload)
    verify_authorization_source(authorization, resolver=source_resolver)

    connector = str(payload.get("connector") or "").strip()
    operation = str(payload.get("operation") or "").strip()
    target = payload.get("target")
    if not isinstance(target, Mapping):
        raise AuthorizationScopeError("target must be an object")
    provider_input = payload.get("provider_input")
    if not isinstance(provider_input, Mapping):
        raise AuthorizationScopeError("provider_input must be an object")
    consequence = str(payload.get("consequence") or "").strip()
    if not consequence:
        raise AuthorizationScopeError("consequence is required")

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

    evidence_refs_raw = payload.get("evidence_refs")
    if not isinstance(evidence_refs_raw, list):
        raise AuthorizationScopeError("evidence_refs must be an array")
    evidence_refs = tuple(str(item).strip() for item in evidence_refs_raw if str(item).strip())

    adapted = deepcopy(dict(payload))
    adapted.pop("authorization_envelope", None)
    adapted_approval = dict(approval)
    adapted_approval["approval_scope_sha256"] = action_scope_sha256(
        connector=connector,
        operation=operation,
        target=target,
        provider_input=provider_input,
        consequence=consequence,
        evidence_refs=evidence_refs,
        idempotency_key=str(payload.get("idempotency_key") or "").strip(),
    )
    adapted["approval"] = adapted_approval

    # Source-bound standing authority is invalidated by source supersession/contradiction,
    # not by the exact-action receipt-age window used for legacy approvals.
    action = validate_approved_action_request(adapted, catalog, now=None)

    write_rule = catalog.connectors[action.connector]["write_operations"][action.operation]
    destructive_rule = write_rule.get("destructive")
    if not isinstance(destructive_rule, bool):
        raise AuthorizationScopeError(
            "catalogued source-bound write operation must declare destructive=true|false"
        )
    destructive = (
        destructive_rule
        or action.execution_evidence.reversibility is Reversibility.IRREVERSIBLE
    )

    envelope_digest = authorize_constituent_action(
        authorization,
        connector=action.connector,
        operation=action.operation,
        target=action.target,
        provider_input=action.provider_input,
        consequence=action.consequence,
        destructive=destructive,
    )

    return replace(
        action,
        approval_reference=f"{authorization.source_ref}#auth={envelope_digest}",
    )
