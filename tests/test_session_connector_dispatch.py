from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from connector_bridge_contract import build_read_request
from connector_receipts import load_connector_catalog, validate_read_receipt
from session_connector_dispatch import (
    SessionDispatchError,
    build_session_operation_plan,
    receipt_from_observation,
)


CATALOG_PATH = ROOT / "config" / "apex_connector_catalog.json"
NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)


def request(connector, operation, profile, provider_input):
    catalog = load_connector_catalog(CATALOG_PATH)
    payload = build_read_request(
        connector=connector,
        operation=operation,
        profile=profile,
        target={"object_ref": "apex-live-check", "provider_input": provider_input},
        catalog=catalog,
        requested_at=NOW,
    )
    payload["request_id"] = f"request-{connector}-{operation}"
    return catalog, payload


def test_dropbox_plan_maps_to_documented_authenticated_read_tool():
    catalog, payload = request(
        "dropbox",
        "file.search",
        "evidence_intake",
        {"query": "APEX"},
    )

    plan = build_session_operation_plan(request=payload, catalog=catalog)

    assert plan.provider_kind == "mcp"
    assert plan.provider_name == "dropbox"
    assert plan.provider_operation == "search"
    assert plan.provider_input == {"query": "APEX"}
    assert plan.external_action_authorized is False


def test_workspace_plan_maps_to_direct_read_only_drive_list_call():
    catalog, payload = request(
        "google_workspace",
        "drive.search",
        "current_source_review",
        {"q": "name contains 'APEX'", "pageSize": 5},
    )

    plan = build_session_operation_plan(request=payload, catalog=catalog)

    assert plan.provider_kind == "gws"
    assert plan.provider_name == "drive.files"
    assert plan.provider_operation == "list"
    assert plan.external_action_authorized is False


def test_session_observation_becomes_valid_non_authorizing_receipt():
    catalog, payload = request(
        "notion",
        "page.search",
        "knowledge_continuity",
        {"query": "APEX connector bridge", "page_size": 1},
    )
    plan = build_session_operation_plan(request=payload, catalog=catalog)

    receipt = receipt_from_observation(
        request=payload,
        plan=plan,
        provider_material='{"results":[{"id":"page-1"}]}',
        catalog=catalog,
        observed_at=NOW,
    )
    validated = validate_read_receipt(receipt, catalog, now=NOW)

    assert validated.connector == "notion"
    assert validated.operation == "page.search"
    assert validated.content_sha256 is not None
    assert receipt["external_action_authorized"] is False
    assert "results" not in receipt


def test_github_requires_authenticated_session_observation_not_direct_network_dispatch():
    catalog, payload = request(
        "github",
        "pull_request.read",
        "repository_integrity",
        {"repository": "GlacierEQ/apex-control-plane", "number": 64},
    )

    with pytest.raises(SessionDispatchError, match="authenticated GitHub"):
        build_session_operation_plan(request=payload, catalog=catalog)


def test_query_read_rejects_non_select_or_multi_statement_input():
    catalog, payload = request(
        "supabase",
        "query.read",
        "structured_state_review",
        {"query": "delete from receipts"},
    )
    with pytest.raises(SessionDispatchError, match="SELECT"):
        build_session_operation_plan(request=payload, catalog=catalog)

    catalog, payload = request(
        "supabase",
        "query.read",
        "structured_state_review",
        {"query": "select * from receipts; delete from receipts"},
    )
    with pytest.raises(SessionDispatchError, match="SELECT"):
        build_session_operation_plan(request=payload, catalog=catalog)


def test_plan_and_receipt_refuse_action_claims():
    catalog, payload = request(
        "mem",
        "record.search",
        "knowledge_continuity",
        {"query": "APEX"},
    )
    payload["external_action_authorized"] = True

    with pytest.raises(SessionDispatchError, match="non-authorizing"):
        build_session_operation_plan(request=payload, catalog=catalog)


# Native Google Workspace: exact authenticated connector adapters, never permission union.
@pytest.mark.parametrize(
    "operation,provider_input,tool",
    [
        ("drive.search", {"query": "APEX", "topn": 2}, "search"),
        ("drive.metadata.read", {"fileId": "file-123"}, "get_file_metadata"),
        ("drive.revisions.read", {"fileId": "file-123"}, "list_file_revisions"),
        ("document.read", {"document_id": "doc-123"}, "get_document_text"),
        ("spreadsheet.read", {"spreadsheet_id": "sheet-123"}, "get_spreadsheet_metadata"),
        ("spreadsheet.range.read", {"spreadsheet_id": "sheet-123", "sheet_name": "Cases", "range": "A1:C3"}, "get_spreadsheet_range"),
        ("presentation.read", {"presentation_url": "https://docs.google.com/presentation/d/a"}, "get_presentation_outline"),
        ("file.comments.read", {"id": "file-123"}, "get_file_comments"),
    ],
)
def test_native_google_workspace_maps_to_actual_authenticated_connector(operation, provider_input, tool):
    bound = {**provider_input, "link_id": "link_account_one"}
    catalog, payload = request("google_workspace", operation, "current_source_review", bound)
    payload["target"]["provider_route"] = "google_drive.native"
    plan = build_session_operation_plan(request=payload, catalog=catalog)
    assert (plan.provider_kind, plan.provider_name, plan.provider_operation) == ("mcp", "google_drive", tool)
    assert plan.provider_input == bound
    assert plan.external_action_authorized is False
    assert plan.source_ref.startswith(f"mcp://google_drive/{tool}/")


def test_native_google_workspace_requires_explicit_account_binding():
    catalog, payload = request("google_workspace", "drive.search", "current_source_review", {"query": "APEX"})
    payload["target"]["provider_route"] = "google_drive.native"
    with pytest.raises(SessionDispatchError, match="link_id"):
        build_session_operation_plan(request=payload, catalog=catalog)


@pytest.mark.parametrize("bad_input", [
    {"link_id": "link_account_one", "query": "APEX", "permission_override": True},
    {"link_id": "link_account_one", "query": "APEX", "upload_mode": "delete"},
])
def test_native_google_workspace_rejects_unknown_provider_arguments(bad_input):
    catalog, payload = request("google_workspace", "drive.search", "current_source_review", bad_input)
    payload["target"]["provider_route"] = "google_drive.native"
    with pytest.raises(SessionDispatchError, match="unsupported"):
        build_session_operation_plan(request=payload, catalog=catalog)


def test_native_google_workspace_refuses_undeclared_transport():
    catalog, payload = request("google_workspace", "drive.search", "current_source_review", {"query": "APEX", "link_id": "link_account_one"})
    payload["target"]["provider_route"] = "google_workspace.magic"
    with pytest.raises(SessionDispatchError, match="unknown Google Workspace route"):
        build_session_operation_plan(request=payload, catalog=catalog)


def test_native_google_workspace_receipt_contains_digest_not_retrieved_content():
    catalog, payload = request("google_workspace", "document.read", "current_source_review", {"document_id": "doc-123", "link_id": "link_account_one"})
    payload["target"]["provider_route"] = "google_drive.native"
    plan = build_session_operation_plan(request=payload, catalog=catalog)
    receipt = receipt_from_observation(request=payload, plan=plan, provider_material='{"secret_private_content":"never-persist"}', catalog=catalog, observed_at=NOW)
    assert receipt["content_sha256"]
    assert "never-persist" not in str(receipt)
    assert validate_read_receipt(receipt, catalog, now=NOW).operation == "document.read"
