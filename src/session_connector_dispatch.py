"""Authenticated-session plans for the live APEX connector bridge.

This module contains no credentials and does not invoke provider tools. It maps an
APEX read request to a documented authenticated-session operation plan. The task
host performs that one provider read through its direct authenticated integration,
then supplies the in-memory observation to receipt_from_observation().
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from authenticated_session_bridge import ProviderObservation, build_read_receipt
from connector_bridge_contract import build_read_request
from connector_receipts import ConnectorCatalog, ConnectorReceiptError, canonical_json


class SessionDispatchError(RuntimeError):
    """Raised when a read request cannot be mapped to a safe provider operation."""


_MCP_READ_TOOLS: dict[tuple[str, str], tuple[str, str]] = {
    ("dropbox", "file.search"): ("dropbox", "search"),
    ("dropbox", "file.list"): ("dropbox", "list_folder"),
    ("dropbox", "file.metadata.read"): ("dropbox", "get_file_metadata"),
    ("dropbox", "file.extract_text"): ("dropbox", "get_file_content"),
    ("dropbox", "file.download_preserve"): ("dropbox", "download_link"),
    ("notion", "page.search"): ("notion", "notion-search"),
    ("notion", "page.read"): ("notion", "notion-fetch"),
    ("notion", "database.read"): ("notion", "notion-query-data-sources"),
    ("mem", "record.search"): ("mem", "search_notes"),
    ("mem", "record.read"): ("mem", "get_note"),
    ("supabase", "schema.read"): ("supabase", "list_projects"),
    ("supabase", "table.read"): ("supabase", "list_tables"),
    ("supabase", "query.read"): ("supabase", "execute_sql"),
    ("postman", "workspace.read"): ("postman", "getWorkspace"),
    ("postman", "collection.read"): ("postman", "getCollection"),
    ("postman", "spec.read"): ("postman", "getSpec"),
    ("postman", "monitor.read"): ("postman", "getMonitor"),
}

_GWS_READ_TOOLS: dict[str, tuple[str, str, str]] = {
    "drive.search": ("drive", "files", "list"),
    "document.read": ("docs", "documents", "get"),
    "spreadsheet.read": ("sheets", "spreadsheets", "get"),
    "presentation.read": ("slides", "presentations", "get"),
}


@dataclass(frozen=True, slots=True)
class SessionOperationPlan:
    """One provider read for an authenticated task host to perform directly."""

    connector: str
    operation: str
    profile: str
    request_id: str
    provider_kind: str
    provider_name: str
    provider_operation: str
    provider_input: Mapping[str, Any]
    source_ref: str
    external_action_authorized: bool = False


def _required_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SessionDispatchError(f"{name} must be an object")
    return value


def _required_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise SessionDispatchError(f"{name} is required")
    return text


def _validated_request_fields(
    request: Mapping[str, Any], catalog: ConnectorCatalog
) -> tuple[str, str, str, Mapping[str, Any]]:
    connector = _required_text(request.get("connector"), "request.connector")
    operation = _required_text(request.get("operation"), "request.operation")
    profile = _required_text(request.get("profile"), "request.profile")
    target = _required_mapping(request.get("target"), "request.target")
    _required_text(request.get("request_id"), "request.request_id")
    if request.get("external_action_authorized") is not False:
        raise SessionDispatchError("session dispatcher accepts only non-authorizing read requests")
    build_read_request(
        connector=connector,
        operation=operation,
        profile=profile,
        target=target,
        catalog=catalog,
    )
    return connector, operation, profile, target


def _provider_input(target: Mapping[str, Any]) -> Mapping[str, Any]:
    return _required_mapping(target.get("provider_input"), "request.target.provider_input")


def _validate_query_read_input(connector: str, operation: str, target: Mapping[str, Any]) -> None:
    if connector != "supabase" or operation != "query.read":
        return
    query = _required_text(_provider_input(target).get("query"), "query.read provider_input.query")
    compact = " ".join(query.split()).lower()
    if not compact.startswith("select ") or ";" in compact:
        raise SessionDispatchError("supabase query.read accepts one SELECT statement only")


def build_session_operation_plan(
    *, request: Mapping[str, Any], catalog: ConnectorCatalog
) -> SessionOperationPlan:
    """Map one validated APEX request to one direct authenticated provider read."""
    connector, operation, profile, target = _validated_request_fields(request, catalog)
    _validate_query_read_input(connector, operation, target)
    provider_input = dict(_provider_input(target))
    digest = sha256(canonical_json(target).encode("utf-8")).hexdigest()

    if connector == "google_workspace":
        try:
            service, resource, method = _GWS_READ_TOOLS[operation]
        except KeyError as exc:
            raise SessionDispatchError(f"no Workspace mapping for {operation}") from exc
        return SessionOperationPlan(
            connector=connector,
            operation=operation,
            profile=profile,
            request_id=str(request["request_id"]),
            provider_kind="gws",
            provider_name=f"{service}.{resource}",
            provider_operation=method,
            provider_input=provider_input,
            source_ref=f"gws://{service}/{resource}/{method}/{digest}",
        )

    if connector == "github":
        raise SessionDispatchError(
            "github reads require the authenticated GitHub browser/session bridge; "
            "supply its observation to receipt_from_observation"
        )

    try:
        server, tool = _MCP_READ_TOOLS[(connector, operation)]
    except KeyError as exc:
        raise SessionDispatchError(f"no authenticated-session mapping for {connector}.{operation}") from exc
    return SessionOperationPlan(
        connector=connector,
        operation=operation,
        profile=profile,
        request_id=str(request["request_id"]),
        provider_kind="mcp",
        provider_name=server,
        provider_operation=tool,
        provider_input=provider_input,
        source_ref=f"mcp://{server}/{tool}/{digest}",
    )


def receipt_from_observation(
    *,
    request: Mapping[str, Any],
    plan: SessionOperationPlan,
    provider_material: str | bytes | None,
    catalog: ConnectorCatalog,
    observed_at: datetime | None = None,
) -> Mapping[str, Any]:
    """Return a validation-ready receipt while retaining no provider material."""
    if plan.request_id != request.get("request_id"):
        raise SessionDispatchError("operation plan does not match the supplied request")
    if plan.external_action_authorized is not False:
        raise SessionDispatchError("operation plan must remain non-authorizing")
    observation = ProviderObservation(
        source_refs=(plan.source_ref,),
        material=provider_material,
        observed_at=(observed_at or datetime.now(UTC)).astimezone(UTC),
    )
    return build_read_receipt(request=request, observation=observation, catalog=catalog)


def load_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SessionDispatchError(f"JSON input not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SessionDispatchError(f"invalid JSON input: {path}: {exc}") from exc
    return _required_mapping(value, "JSON input")


def render_safe_receipt(receipt: Mapping[str, Any]) -> str:
    """Serialize receipt metadata only; provider output is never an argument here."""
    return json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
