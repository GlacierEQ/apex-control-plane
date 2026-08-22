"""Direct authenticated-host plans for exact approved APEX provider operations.

No function in this module loads credentials, invokes a provider tool, or executes a
network request. The host receives one validated plan and performs the named provider
action directly, then submits digest-only execution and readback observations.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping

from approved_operation_bridge import ApprovedConnectorAction, validate_approved_action_request
from connector_receipts import ConnectorCatalog, ConnectorReceiptError, canonical_json


class ApprovedSessionDispatchError(RuntimeError):
    """Raised when an approved action cannot be mapped to one provider operation."""


_MCP_WRITE_TOOLS: dict[tuple[str, str], tuple[str, str]] = {
    ("mem", "note.create"): ("mem", "create_note"),
    ("mem", "note.update"): ("mem", "update_note"),
    ("mem", "collection.create"): ("mem", "create_collection"),
    ("mem", "collection.update"): ("mem", "update_collection"),
    ("supabase", "row.insert"): ("supabase", "execute_sql"),
    ("supabase", "row.update"): ("supabase", "execute_sql"),
    ("postman", "collection.create"): ("postman", "createCollection"),
    ("postman", "collection.update"): ("postman", "patchCollection"),
    ("postman", "spec.create"): ("postman", "createSpec"),
    ("postman", "monitor.create"): ("postman", "createMonitor"),
}

_GWS_WRITE_TOOLS: dict[str, tuple[str, str, str]] = {
    "document.create": ("docs", "documents", "create"),
    "document.update": ("docs", "documents", "batchUpdate"),
}

_GITHUB_WRITE_TOOLS: dict[str, str] = {
    "issue.create": "issue.create",
    "pull_request.create": "pull_request.create",
}


@dataclass(frozen=True, slots=True)
class ApprovedSessionOperationPlan:
    """One immutable, exact-approval-bound provider action for an authenticated host."""

    connector: str
    operation: str
    action_request_id: str
    idempotency_key: str
    approval_reference: str
    approval_scope_sha256: str
    provider_kind: str
    provider_name: str
    provider_operation: str
    provider_input: Mapping[str, Any]
    action_source_ref: str
    required_readback_operation: str
    external_action_authorized: bool = True


def _required_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ApprovedSessionDispatchError(f"{name} is required")
    return text


def _validate_supabase_write_input(action: ApprovedConnectorAction) -> None:
    if action.connector != "supabase":
        return
    query = _required_text(action.provider_input.get("query"), "approved Supabase provider_input.query")
    compact = " ".join(query.split()).lower()
    if ";" in compact or "--" in compact or "/*" in compact:
        raise ApprovedSessionDispatchError(
            "approved Supabase operations accept one comment-free statement"
        )
    if action.operation == "row.insert" and not compact.startswith("insert into "):
        raise ApprovedSessionDispatchError("supabase row.insert requires one INSERT INTO statement")
    if action.operation == "row.update":
        if not compact.startswith("update ") or " where " not in compact:
            raise ApprovedSessionDispatchError(
                "supabase row.update requires one UPDATE statement with WHERE"
            )


def _action_digest(action: ApprovedConnectorAction) -> str:
    return sha256(
        canonical_json(
            {
                "action_request_id": action.action_request_id,
                "approval_scope_sha256": action.approval_scope_sha256,
                "idempotency_key": action.idempotency_key,
            }
        ).encode("utf-8")
    ).hexdigest()


def _plan(
    *,
    action: ApprovedConnectorAction,
    provider_kind: str,
    provider_name: str,
    provider_operation: str,
    readback: str,
) -> ApprovedSessionOperationPlan:
    digest = _action_digest(action)
    return ApprovedSessionOperationPlan(
        connector=action.connector,
        operation=action.operation,
        action_request_id=action.action_request_id,
        idempotency_key=action.idempotency_key,
        approval_reference=action.approval_reference,
        approval_scope_sha256=action.approval_scope_sha256,
        provider_kind=provider_kind,
        provider_name=provider_name,
        provider_operation=provider_operation,
        provider_input=dict(action.provider_input),
        action_source_ref=(
            f"{provider_kind}://{provider_name}/{provider_operation}/{digest}"
        ),
        required_readback_operation=readback,
    )


def build_approved_session_operation_plan(
    *,
    action_request: Mapping[str, Any],
    catalog: ConnectorCatalog,
    now=None,
) -> ApprovedSessionOperationPlan:
    """Validate one exact approval and return one direct authenticated provider plan."""
    try:
        action = validate_approved_action_request(action_request, catalog, now=now)
    except (ConnectorReceiptError, ValueError) as exc:
        raise ApprovedSessionDispatchError(str(exc)) from exc
    _validate_supabase_write_input(action)

    if action.connector == "github":
        try:
            operation = _GITHUB_WRITE_TOOLS[action.operation]
        except KeyError as exc:
            raise ApprovedSessionDispatchError(
                f"no GitHub session mutation mapping for {action.operation}"
            ) from exc
        return _plan(
            action=action,
            provider_kind="browser_session",
            provider_name="github",
            provider_operation=operation,
            readback="provider_object.read",
        )

    if action.connector == "google_workspace":
        try:
            service, resource, method = _GWS_WRITE_TOOLS[action.operation]
        except KeyError as exc:
            raise ApprovedSessionDispatchError(
                f"no Workspace session mutation mapping for {action.operation}"
            ) from exc
        return _plan(
            action=action,
            provider_kind="gws",
            provider_name=f"{service}.{resource}",
            provider_operation=method,
            readback="document.read",
        )

    try:
        server, tool = _MCP_WRITE_TOOLS[(action.connector, action.operation)]
    except KeyError as exc:
        raise ApprovedSessionDispatchError(
            f"no authenticated session mutation mapping for {action.connector}.{action.operation}"
        ) from exc
    return _plan(
        action=action,
        provider_kind="mcp",
        provider_name=server,
        provider_operation=tool,
        readback="provider_object.read",
    )
