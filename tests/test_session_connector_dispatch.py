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
