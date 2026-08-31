import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def manifest():
    return json.loads((ROOT / "connectors" / "github_backend_ops.json").read_text())


def test_security_invariants():
    m = manifest()
    invariants = m["invariants"]
    assert invariants["destructive_actions_allowed"] is False
    assert invariants["default_branch_writes_allowed"] is False
    assert invariants["code_write_readback_required"] is True
    assert invariants["compare_before_write_required_by_router"] is True
    assert invariants["atomic_resource_lease_required_for_router_writes"] is True
    assert invariants["successful_write_idempotency"] is True
    assert invariants["append_only_execution_receipts"] is True
    assert invariants["append_only_route_decisions"] is True
    assert invariants["append_only_webhook_results"] is True
    assert invariants["raw_webhook_payload_persisted"] is False


def test_permission_aware_pr_composition():
    m = manifest()
    assert m["app_permissions_observed"]["pull_requests"] == "not_granted"
    assert m["routing"]["full_pull_read"].startswith("github.native:")
    assert m["routing"]["pull_create"] == "github.native:create_pull_request"
    assert m["routing"]["pull_review"] == "github.native:add_review_to_pr"


def test_router_is_the_execution_entrypoint():
    m = manifest()
    assert m["runtime"]["execution_entrypoint"] == "apex-github-router"
    assert m["runtime"]["internal_gateway"] == "apex-github-connector"
    assert m["runtime"]["router_contract_version"] == 2

    source = (ROOT / "supabase" / "functions" / "apex-github-router" / "index.ts").read_text()
    assert "acquire_github_connector_lease_v2" in source
    assert "release_github_connector_lease_v2" in source
    assert "expected_before_sha" in source
    assert "stale_write_precondition" in source
    assert "resource_lease_busy" in source
    assert "fallback_required" in source
    assert "github_connector_circuit_v2" in source
    assert "READ_RETRY_DELAYS_MS" in source


def test_gateway_pr_first_and_receipt_guards():
    source = (ROOT / "supabase" / "functions" / "apex-github-connector" / "index.ts").read_text()
    assert "default_branch_write_blocked" in source
    assert "github_connector_receipts_v1" in source
    assert "contents_readback_hash_mismatch" in source
    assert "token_persisted: false" in source
    assert 'detail_level: "issue_projection"' in source
    assert "PEM_PKCS8_BEGIN" in source


def test_forbidden_github_mutations_are_not_exposed():
    combined = "\n".join(
        (ROOT / "supabase" / "functions" / name / "index.ts").read_text()
        for name in ["apex-github-connector", "apex-github-router"]
    )
    forbidden = ["merge_pull_request", "delete_repository", "force_update_ref", "secret_export"]
    for name in forbidden:
        assert name not in combined


def test_webhook_is_hash_only_and_fail_closed_capable():
    source = (ROOT / "supabase" / "functions" / "apex-github-webhook" / "index.ts").read_text()
    assert "x-hub-signature-256" in source
    assert "x-github-delivery" in source
    assert "webhook_secret_not_bound" in source
    assert "raw_payload_persisted: false" in source
    assert "payload_sha256" in source


def test_webhook_worker_is_durable_and_router_backed():
    source = (ROOT / "supabase" / "functions" / "apex-github-webhook-worker" / "index.ts").read_text()
    assert "claim_github_webhook_events_v1" in source
    assert "finish_github_webhook_event_v1" in source
    assert "github_webhook_event_results_v1" in source
    assert "/functions/v1/apex-github-router" in source
    assert 'operation: "repo.get"' in source
    assert 'operation: "actions.runs"' in source


def test_router_and_worker_migrations_are_present():
    router = (ROOT / "db" / "migrations" / "20260831170616_github_backend_ops_router_v2.sql").read_text()
    worker = (ROOT / "db" / "migrations" / "20260831170915_github_webhook_worker_v1.sql").read_text()
    assert "github_connector_operation_leases_v2" in router
    assert "github_connector_route_decisions_v2" in router
    assert "github_connector_circuit_v2" in router
    assert "github_webhook_event_queue_v1" in router
    assert "for update skip locked" in worker.lower()
    assert "github_webhook_event_results_v1" in worker


def test_runtime_probe_artifact():
    probe = json.loads((ROOT / "connectors" / "github_backend_ops_runtime_probe.json").read_text())
    assert probe["connector_key"] == "github.backend_ops"
    assert probe["status"] == "router_v2_compare_before_write_verified"
    assert probe["resource_lease"] == "required"
    assert probe["destructive_action"] is False
