from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from connector_bridge_contract import build_action_proposal, build_read_request
from connector_receipts import (
    ConnectorReceiptError,
    load_connector_catalog,
    validate_action_request,
    validate_read_receipt,
)
from control_plane_runtime import CaseBrainOrchestrator, Producer


CATALOG_PATH = ROOT / "config" / "apex_connector_catalog.json"
NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)


def read_receipt(**overrides):
    payload = {
        "schema_version": 1,
        "receipt_id": "receipt-dropbox-001",
        "request_id": "request-dropbox-001",
        "connector": "dropbox",
        "operation": "file.metadata.read",
        "profile": "evidence_intake",
        "target": {"file_id": "id:evidence-001", "revision": "r1"},
        "result_state": "success",
        "observed_at": NOW.isoformat().replace("+00:00", "Z"),
        "content_sha256": "a" * 64,
        "source_refs": ["dropbox:id:evidence-001"],
        "external_action_authorized": False,
    }
    payload.update(overrides)
    return payload


def action_request(**overrides):
    payload = {
        "schema_version": 1,
        "action_request_id": "action-github-001",
        "connector": "github",
        "operation": "issue.create",
        "target": {"repository": "GlacierEQ/apex-control-plane"},
        "consequence": "Creates one named issue visible to repository collaborators.",
        "evidence_refs": ["receipt-github-001"],
        "approval": {
            "approved_by": "GlacierEQ",
            "approved_at": NOW.isoformat().replace("+00:00", "Z"),
            "approval_reference": "task-approval-001",
        },
    }
    payload.update(overrides)
    return payload


def write_catalog(
    tmp_path,
    *,
    enable_github_issue: bool = True,
    approval_required: bool = False,
):
    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    rule = raw["connectors"]["github"]["write_operations"]["issue.create"]
    rule["enabled"] = enable_github_issue
    rule["approval_required"] = approval_required
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return load_connector_catalog(path)


def test_catalog_loads_and_preserves_system_side_safety_controls():
    catalog = load_connector_catalog(CATALOG_PATH)

    assert catalog.catalog_id == "apex-connector-catalog"
    assert catalog.connectors["dropbox"]["read_operations"] == (
        "file.search",
        "file.list",
        "file.metadata.read",
        "file.extract_text",
        "file.download_preserve",
    )
    github_issue = catalog.connectors["github"]["write_operations"]["issue.create"]
    assert github_issue["enabled"] is True
    assert github_issue["approval_required"] is False
    assert github_issue["idempotency_required"] is True
    assert github_issue["terminal_readback_required"] is True


def test_read_receipt_is_accepted_as_evidence_not_action_authority():
    catalog = load_connector_catalog(CATALOG_PATH)

    receipt = validate_read_receipt(read_receipt(), catalog, now=NOW)

    assert receipt.connector == "dropbox"
    assert receipt.operation == "file.metadata.read"
    assert receipt.content_sha256 == "a" * 64


def test_read_receipt_rejects_unknown_operation_stale_time_and_action_claim():
    catalog = load_connector_catalog(CATALOG_PATH)

    with pytest.raises(ConnectorReceiptError, match="not allowed"):
        validate_read_receipt(read_receipt(operation="file.delete"), catalog, now=NOW)
    with pytest.raises(ConnectorReceiptError, match="stale"):
        validate_read_receipt(
            read_receipt(observed_at=(NOW - timedelta(days=2)).isoformat()),
            catalog,
            now=NOW,
        )
    with pytest.raises(ConnectorReceiptError, match="non-authorizing"):
        validate_read_receipt(
            read_receipt(external_action_authorized=True),
            catalog,
            now=NOW,
        )


def test_build_read_request_only_allows_catalogued_profile_operation():
    catalog = load_connector_catalog(CATALOG_PATH)

    request = build_read_request(
        connector="github",
        operation="branch_protection.read",
        profile="repository_integrity",
        target={"repository": "GlacierEQ/apex-control-plane"},
        catalog=catalog,
        requested_at=NOW,
    )

    assert request["external_action_authorized"] is False
    assert request["requested_at"] == "2026-08-22T12:00:00Z"
    with pytest.raises(ConnectorReceiptError, match="not allowed"):
        build_read_request(
            connector="github",
            operation="issue.create",
            profile="repository_integrity",
            target={"repository": "GlacierEQ/apex-control-plane"},
            catalog=catalog,
            requested_at=NOW,
        )


def test_inactive_write_route_remains_blocked_even_with_full_approval_record():
    catalog = load_connector_catalog(CATALOG_PATH)

    with pytest.raises(ConnectorReceiptError, match="inactive"):
        validate_action_request(
            action_request(
                connector="notion",
                operation="page.create",
                target={"parent_page_id": "page-001"},
            ),
            catalog,
        )


def test_recoverable_write_inherits_active_mission_authority(tmp_path):
    catalog = write_catalog(tmp_path, enable_github_issue=True, approval_required=False)

    payload = action_request()
    payload.pop("approval")
    validated = validate_action_request(payload, catalog)

    assert validated.connector == "github"
    assert validated.operation == "issue.create"
    assert validated.authority_mode == "active_mission_authority"
    assert validated.approved_by is None
    assert validated.approved_at is None
    assert validated.approval_reference is None


def test_consequence_sensitive_write_requires_scoped_authority(tmp_path):
    catalog = write_catalog(tmp_path, enable_github_issue=True, approval_required=True)

    payload = action_request()
    payload.pop("approval")
    with pytest.raises(ConnectorReceiptError, match="approval must be an object"):
        validate_action_request(payload, catalog)

    with pytest.raises(ConnectorReceiptError, match="approval_reference"):
        validate_action_request(
            action_request(approval={"approved_by": "GlacierEQ", "approved_at": NOW.isoformat()}),
            catalog,
        )

    validated = validate_action_request(action_request(), catalog)
    assert validated.authority_mode == "scoped_consequence_authority"
    assert validated.approval_reference == "task-approval-001"


def test_runtime_admits_read_receipt_with_safe_audit_details_and_deduplicates():
    catalog = load_connector_catalog(CATALOG_PATH)
    runtime = CaseBrainOrchestrator(
        producer=Producer(
            repo="GlacierEQ/apex-control-plane",
            commit_sha="a" * 40,
            component="connector-receipt-test",
        )
    )
    payload = read_receipt()

    accepted = runtime.admit_connector_read_receipt(payload, catalog, now=NOW)
    duplicate = runtime.admit_connector_read_receipt(payload, catalog, now=NOW)

    assert accepted["status"] == "accepted"
    assert accepted["external_action_authorized"] is False
    assert duplicate == {
        "status": "duplicate",
        "receipt_id": "receipt-dropbox-001",
        "external_action_authorized": False,
    }
    audit = runtime.receipts[-1]
    assert audit.action == "admit_connector_read_receipt"
    assert audit.details["target_sha256"]
    assert "target" not in audit.details
    assert audit.details["external_action_authorized"] is False


def test_action_proposal_reports_mission_authority_without_self_authorizing():
    catalog = load_connector_catalog(CATALOG_PATH)

    proposal = build_action_proposal(
        connector="github",
        operation="issue.create",
        target={"repository": "GlacierEQ/apex-control-plane"},
        consequence="Creates one issue visible to repository collaborators.",
        evidence_refs=["receipt-github-001"],
        catalog=catalog,
    )

    assert proposal["operation_active"] is True
    assert proposal["approval_required"] is False
    assert proposal["authority_mode"] == "active_mission_authority"
    assert proposal["external_action_authorized"] is False


def test_catalog_rejects_return_to_blanket_external_write_approval(tmp_path):
    raw = deepcopy(json.loads(CATALOG_PATH.read_text(encoding="utf-8")))
    raw["security"]["external_write_requires_exact_approval"] = True
    path = tmp_path / "regressed-catalog.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ConnectorReceiptError, match="blanket approval"):
        load_connector_catalog(path)
