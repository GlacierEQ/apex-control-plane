import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def manifest():
    return json.loads((ROOT / "connectors" / "github_backend_ops.json").read_text())

def test_security_invariants():
    m = manifest()
    assert m["invariants"]["destructive_actions_allowed"] is False
    assert m["invariants"]["default_branch_writes_allowed"] is False
    assert m["invariants"]["code_write_readback_required"] is True
    assert m["invariants"]["successful_write_idempotency"] is True
    assert m["invariants"]["append_only_receipts"] is True
    assert m["invariants"]["raw_webhook_payload_persisted"] is False

def test_permission_aware_pr_composition():
    m = manifest()
    assert m["app_permissions_observed"]["pull_requests"] == "not_granted"
    assert set(m["local_operations"]["disabled_for_current_app"]) == {"pull.create", "pull.review"}
    assert m["composition"]["full_pull_read"].startswith("github.native:")
    assert m["composition"]["pull_create"] == "github.native:create_pull_request"

def test_gateway_pr_first_and_receipt_guards():
    source = (ROOT / "supabase" / "functions" / "apex-github-connector" / "index.ts").read_text()
    assert "default_branch_write_blocked" in source
    assert "github_connector_receipts_v1" in source
    assert "contents_readback_hash_mismatch" in source
    assert "token_persisted: false" in source
    assert 'detail_level: "issue_projection"' in source
    assert "PEM_PKCS8_BEGIN" in source

def test_forbidden_github_mutations_are_not_exposed():
    source = (ROOT / "supabase" / "functions" / "apex-github-connector" / "index.ts").read_text()
    forbidden = ["merge_pull_request", "delete_repository", "force_update_ref", "secret_export"]
    for name in forbidden:
        assert name not in source

def test_webhook_is_hash_only_and_fail_closed_capable():
    source = (ROOT / "supabase" / "functions" / "apex-github-webhook" / "index.ts").read_text()
    assert "x-hub-signature-256" in source
    assert "x-github-delivery" in source
    assert "webhook_secret_not_bound" in source
    assert "raw_payload_persisted: false" in source
    assert "payload_sha256" in source

def test_runtime_probe_artifact():
    probe = json.loads((ROOT / "connectors" / "github_backend_ops_runtime_probe.json").read_text())
    assert probe["connector_key"] == "github.backend_ops"
    assert probe["status"] == "runtime_write_readback_verified"
    assert probe["destructive_action"] is False
