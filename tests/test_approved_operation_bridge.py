from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from approved_operation_bridge import (
    ApprovedOperationError,
    ProviderExecutionObservation,
    action_scope_sha256,
    build_execution_receipt,
    validate_approved_action_request,
)
from approved_session_dispatch import (
    ApprovedSessionDispatchError,
    build_approved_session_operation_plan,
)
from connector_receipts import load_connector_catalog
from control_plane_runtime import CaseBrainOrchestrator, Producer


CATALOG_PATH = ROOT / "config" / "apex_connector_catalog.json"
NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)


def approved_action(**overrides):
    payload = {
        "schema_version": 1,
        "action_request_id": "action-github-approved-001",
        "connector": "github",
        "operation": "issue.create",
        "target": {"repository": "GlacierEQ/apex-control-plane"},
        "provider_input": {"title": "Approval-gated issue", "body": "Safe test fixture."},
        "consequence": "Creates one named issue visible to repository collaborators.",
        "evidence_refs": ["receipt-github-001"],
        "idempotency_key": "apex-approved-action-001",
        "execution_evidence": {
            "operation": "github.issue.create",
            "epistemic_state": "observed",
            "blast_radius": 1,
            "reversibility": 1,
            "source_state_observed": True,
            "dependency_map_observed": True,
            "recovery_checkpoint_verified": True,
            "recovery_procedure_verified": True,
            "dry_run_verified": True,
            "staged_execution": True,
            "novel_operation": False,
            "operator_explicit_irreversible_authorization": False,
        },
        "approval": {
            "approved_by": "GlacierEQ",
            "approved_at": NOW.isoformat().replace("+00:00", "Z"),
            "approval_reference": "task-approval-001",
            "approval_scope_sha256": "",
        },
    }
    payload.update(overrides)
    scope = action_scope_sha256(
        connector=payload["connector"],
        operation=payload["operation"],
        target=payload["target"],
        provider_input=payload["provider_input"],
        consequence=payload["consequence"],
        evidence_refs=tuple(payload["evidence_refs"]),
        idempotency_key=payload["idempotency_key"],
    )
    payload["approval"] = dict(payload["approval"], approval_scope_sha256=scope)
    return payload


def test_exact_approval_scope_builds_one_github_session_plan():
    catalog = load_connector_catalog(CATALOG_PATH)
    request = approved_action()

    plan = build_approved_session_operation_plan(
        action_request=request,
        catalog=catalog,
        now=NOW,
    )

    assert plan.connector == "github"
    assert plan.provider_kind == "browser_session"
    assert plan.provider_operation == "issue.create"
    assert plan.required_readback_operation == "provider_object.read"
    assert plan.external_action_authorized is True
    assert plan.provider_input["title"] == "Approval-gated issue"


def test_scope_cannot_be_reused_for_a_different_provider_payload():
    catalog = load_connector_catalog(CATALOG_PATH)
    request = approved_action()
    request["provider_input"] = {"title": "Different issue", "body": "Different payload."}

    with pytest.raises(ApprovedOperationError, match="approval scope"):
        validate_approved_action_request(request, catalog, now=NOW)


def test_inactive_provider_route_is_not_activated_by_an_approval_record():
    catalog = load_connector_catalog(CATALOG_PATH)
    request = approved_action(
        connector="notion",
        operation="page.create",
        target={"parent_page_id": "page-001"},
        provider_input={"title": "Not active"},
        consequence="Would create one page.",
        idempotency_key="notion-inactive-001",
        execution_evidence={
            **approved_action()["execution_evidence"],
            "operation": "notion.page.create",
        },
    )

    with pytest.raises(ApprovedSessionDispatchError, match="inactive"):
        build_approved_session_operation_plan(action_request=request, catalog=catalog, now=NOW)


def test_supabase_update_requires_one_constrained_statement_with_where():
    catalog = load_connector_catalog(CATALOG_PATH)
    request = approved_action(
        action_request_id="action-supabase-update-001",
        connector="supabase",
        operation="row.update",
        target={"project_ref": "project-001", "table": "records"},
        provider_input={"query": "UPDATE records SET state = 'done'"},
        consequence="Updates one observed record state.",
        idempotency_key="supabase-update-001",
        execution_evidence={
            **approved_action()["execution_evidence"],
            "operation": "supabase.row.update",
        },
    )

    with pytest.raises(ApprovedSessionDispatchError, match="WHERE"):
        build_approved_session_operation_plan(action_request=request, catalog=catalog, now=NOW)


def test_runtime_admits_execution_receipt_without_provider_content_and_deduplicates():
    catalog = load_connector_catalog(CATALOG_PATH)
    action_request = approved_action()
    action = validate_approved_action_request(action_request, catalog, now=NOW)
    receipt = build_execution_receipt(
        action=action,
        execution=ProviderExecutionObservation(
            source_refs=("github://issue/create/result",),
            material=b'{"id": 123, "title": "Approval-gated issue"}',
            observed_at=NOW,
        ),
        result_target={"repository": "GlacierEQ/apex-control-plane", "issue_number": 123},
        readback=ProviderExecutionObservation(
            source_refs=("github://issue/123",),
            material=b'{"number": 123, "state": "open"}',
            observed_at=NOW + timedelta(seconds=1),
        ),
        verification_passed=True,
    )
    runtime = CaseBrainOrchestrator(
        producer=Producer(
            repo="GlacierEQ/apex-control-plane",
            commit_sha="a" * 40,
            component="approved-operation-test",
        )
    )

    accepted = runtime.admit_connector_execution_receipt(
        action_request,
        receipt,
        catalog,
        now=NOW,
    )
    duplicate = runtime.admit_connector_execution_receipt(
        action_request,
        receipt,
        catalog,
        now=NOW,
    )

    assert accepted["status"] == "accepted"
    assert accepted["external_action_authorized"] is True
    assert duplicate["status"] == "duplicate"
    audit = runtime.receipts[-1]
    assert audit.action == "admit_connector_execution_receipt"
    assert audit.details["external_action_authorized"] is True
    assert audit.details["provider_input_sha256"]
    assert audit.details["execution_content_sha256"]
    assert "provider_input" not in audit.details
    assert "result_target" not in audit.details
    assert "Approval-gated issue" not in str(audit.details)


def test_successful_execution_receipt_requires_terminal_readback():
    catalog = load_connector_catalog(CATALOG_PATH)
    action = validate_approved_action_request(approved_action(), catalog, now=NOW)

    with pytest.raises(ApprovedOperationError, match="terminal readback"):
        build_execution_receipt(
            action=action,
            execution=ProviderExecutionObservation(
                source_refs=("github://issue/create/result",),
                material=b"provider result",
                observed_at=NOW,
            ),
            result_target={"repository": "GlacierEQ/apex-control-plane", "issue_number": 123},
            readback=None,
            verification_passed=True,
        )


def test_successful_execution_receipt_requires_verified_terminal_readback():
    catalog = load_connector_catalog(CATALOG_PATH)
    action = validate_approved_action_request(approved_action(), catalog, now=NOW)

    with pytest.raises(ApprovedOperationError, match="verified terminal readback"):
        build_execution_receipt(
            action=action,
            execution=ProviderExecutionObservation(
                source_refs=("github://issue/create/result",),
                material=b"provider result",
                observed_at=NOW,
            ),
            result_target={"repository": "GlacierEQ/apex-control-plane", "issue_number": 123},
            readback=ProviderExecutionObservation(
                source_refs=("github://issue/123",),
                material=b"provider readback",
                observed_at=NOW + timedelta(seconds=1),
            ),
            verification_passed=False,
        )


@pytest.mark.parametrize(
    ("connector", "operation", "target", "provider_input", "provider_kind", "provider_operation"),
    [
        (
            "google_workspace",
            "document.create",
            {"parent": "root"},
            {"title": "Approved document"},
            "gws",
            "create",
        ),
        (
            "mem",
            "note.create",
            {"collection_id": "collection-001"},
            {"content": "Approved note"},
            "mcp",
            "create_note",
        ),
        (
            "postman",
            "collection.create",
            {"workspace_id": "workspace-001"},
            {"name": "Approved collection"},
            "mcp",
            "createCollection",
        ),
    ],
)
def test_active_provider_families_map_only_after_exact_approval(
    connector,
    operation,
    target,
    provider_input,
    provider_kind,
    provider_operation,
):
    catalog = load_connector_catalog(CATALOG_PATH)
    request = approved_action(
        action_request_id=f"action-{connector}-{operation}",
        connector=connector,
        operation=operation,
        target=target,
        provider_input=provider_input,
        consequence=f"Performs one approved {connector} {operation} operation.",
        idempotency_key=f"idempotency-{connector}-{operation}",
        execution_evidence={
            **approved_action()["execution_evidence"],
            "operation": f"{connector}.{operation}",
        },
    )

    plan = build_approved_session_operation_plan(action_request=request, catalog=catalog, now=NOW)

    assert plan.provider_kind == provider_kind
    assert plan.provider_operation == provider_operation
    assert plan.external_action_authorized is True


def test_supabase_insert_maps_after_exact_approval_and_single_statement_guard():
    catalog = load_connector_catalog(CATALOG_PATH)
    request = approved_action(
        action_request_id="action-supabase-insert-001",
        connector="supabase",
        operation="row.insert",
        target={"project_ref": "project-001", "table": "records"},
        provider_input={"query": "INSERT INTO records (id, state) VALUES (1, 'new')"},
        consequence="Creates one approved row in the named table.",
        idempotency_key="supabase-insert-001",
        execution_evidence={
            **approved_action()["execution_evidence"],
            "operation": "supabase.row.insert",
        },
    )

    plan = build_approved_session_operation_plan(action_request=request, catalog=catalog, now=NOW)

    assert plan.provider_kind == "mcp"
    assert plan.provider_name == "supabase"
    assert plan.provider_operation == "execute_sql"
    assert plan.external_action_authorized is True
