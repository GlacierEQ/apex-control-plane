import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_manifest_security_invariants():
    manifest = json.loads((ROOT / "connectors" / "github_backend_ops.json").read_text())
    invariants = manifest["invariants"]
    assert invariants["destructive_actions_allowed"] is False
    assert invariants["default_branch_writes_allowed"] is False
    assert invariants["code_write_readback_required"] is True
    assert invariants["successful_write_idempotency"] is True
    assert invariants["append_only_receipts"] is True
    assert invariants["raw_webhook_payload_persisted"] is False

def test_no_destructive_operation_is_exposed():
    manifest = json.loads((ROOT / "connectors" / "github_backend_ops.json").read_text())
    exposed = set(manifest["operations"]["read"]) | set(manifest["operations"]["write"])
    forbidden = {
        "delete_file", "delete_branch", "delete_repository",
        "merge_pull_request", "force_update_ref", "secret_export",
    }
    assert exposed.isdisjoint(forbidden)

def test_gateway_source_contains_pr_first_and_receipt_guards():
    source = (ROOT / "supabase" / "functions" / "apex-github-connector" / "index.ts").read_text()
    assert 'default_branch_write_blocked' in source
    assert 'github_connector_receipts_v1' in source
    assert 'readback_hash_mismatch' in source
    assert 'token_persisted: false' in source
    assert 'merge_pull_request' not in source
    assert 'DELETE /repos/' not in source

def test_webhook_source_is_hash_only():
    source = (ROOT / "supabase" / "functions" / "apex-github-webhook" / "index.ts").read_text()
    assert 'x-hub-signature-256' in source
    assert 'x-github-delivery' in source
    assert 'raw_payload_persisted: false' in source
    assert 'payload_sha256' in source
