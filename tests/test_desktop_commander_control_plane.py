import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def manifest():
    return json.loads((ROOT / "connectors" / "desktop_commander_glacier.json").read_text())


def test_manifest_preserves_device_boundary():
    m = manifest()
    assert m["source"]["private_repository"] is True
    assert m["source"]["private_github_actions_workflow"] is False
    assert m["runtime"]["local_mcp_transport"] == "stdio"
    assert m["runtime"]["inbound_desktop_port_required"] is False
    assert m["runtime"]["device_private_key_persisted_backend"] is False
    assert m["state"]["physical_device"] == "not_enrolled"
    assert m["state"]["worker"] == "source_runtime_hardened_device_unbound"
    assert m["state"]["selection_enabled"] is False


def test_public_action_face_validation_receipt():
    m = manifest()
    v = m["validation"]
    assert v["execution_face"] == "GlacierEQ/public-actions-runner-host"
    assert v["action"] == "udc-supabase-bridge-ci"
    assert v["adapter"] == "node-ci"
    assert v["workflow_run_id"] == 33686159662
    assert v["npm_ci_exit"] == 0
    assert v["typescript_noemit_exit"] == 0
    assert v["tests_exit"] == 0
    assert v["build_exit"] == 0
    assert v["bridge_policy_tests"] == "passed"


def test_local_agent_migration_is_service_role_only_and_append_only():
    source = (
        ROOT
        / "db"
        / "migrations"
        / "20260902202019_desktop_commander_local_agent_plane_v1.sql"
    ).read_text().lower()
    for table in [
        "desktop_commander_devices_v1",
        "desktop_commander_jobs_v1",
        "desktop_commander_receipts_v1",
        "desktop_commander_nonces_v1",
    ]:
        assert f"alter table public.{table} enable row level security" in source
        assert f"revoke all on public.{table} from public,anon,authenticated" in source
    assert "desktop_commander_receipts_v1 is append-only" in source
    assert "for update skip locked" in source
    assert "device_not_approved" in source
    assert "approved_roots_required" in source
    assert "desktop_commander_enrollment_token_v1" in source
    assert "validate_desktop_commander_enrollment_token_v1" in source


def test_remote_operation_policy_is_narrow_and_compare_before_write():
    source = (
        ROOT
        / "db"
        / "migrations"
        / "20260902202236_desktop_commander_operation_policy_v2.sql"
    ).read_text().lower()
    assert "desktop_commander_operation_policy_v1" in source
    assert "expected_before_sha_required" in source
    assert "desktop_commander_operation_not_allowed" in source
    assert "invalid_run_profile" in source
    for profile in ["git_status", "git_diff", "test", "build", "lint", "typecheck"]:
        assert profile in source


def test_bridge_uses_custom_auth_and_replay_defense():
    source = (
        ROOT
        / "supabase"
        / "functions"
        / "apex-desktop-commander-bridge"
        / "index.ts"
    ).read_text()
    assert "x-glacier-enrollment-token" in source
    assert "x-glacier-device-id" in source
    assert "x-glacier-timestamp" in source
    assert "x-glacier-nonce" in source
    assert "x-glacier-signature" in source
    assert "signature_timestamp_out_of_window" in source
    assert "nonce_replay_rejected" in source
    assert "Ed25519" in source
    assert "desktop_commander_nonces_v1" in source
    assert "validate_desktop_commander_enrollment_token_v1" in source
    assert "vault.decrypted_secrets" not in source
    assert "resolve_desktop_commander_enrollment_token_v1" not in source


def test_remote_manifest_forbids_high_risk_local_capabilities():
    operations = manifest()["operations"]
    assert operations["arbitrary_shell"] is False
    assert operations["system_power"] is False
    assert operations["service_management"] is False
    assert operations["registry_mutation"] is False
    assert operations["process_termination"] is False
    assert operations["scheduled_task_control"] is False
    assert operations["ownership_change"] is False


def test_keymaster_admission_is_narrow_and_idempotent():
    source = (
        ROOT
        / "db"
        / "migrations"
        / "20260902214312_github_oidc_udc_workload_allowlist_v1.sql"
    ).read_text()
    assert '"GlacierEQ/UDC"' in source
    assert "owner_login='GlacierEQ'" in source
    assert "permission_ceiling" in source
    assert "'contents:read'" in source
    assert "'wildcard',false" in source
    assert "expected_repositories" in source
    assert "@>" in source


def test_registry_runtime_ready_migration_preserves_unbound_device_boundary():
    source = (
        ROOT
        / "db"
        / "migrations"
        / "20260902221859_desktop_commander_registry_runtime_ready_v3.sql"
    ).read_text()
    assert "'desktop_commander.glacier'" in source
    assert "'source_runtime_ready'" in source
    assert "'physical_device_execution',4,false" in source
    assert "'selection_enabled',false" in source
    assert "'github.actions.public_runner'" in source
    assert "'runtime_verified_public_action_face'" in source
    assert "'exact_sha_private_workload',5,true" in source
    assert "'oidc_keymaster_one_repo_token',5,true" in source
    assert "'immutable_private_result',5,true" in source


def test_github_backend_ops_manifest_reports_desktop_commander_runtime_state():
    backend = json.loads((ROOT / "connectors" / "github_backend_ops.json").read_text())
    worker = backend["workers"]["glacier_desktop_commander"]
    assert worker["status"] == "source_runtime_hardened_device_unbound"
    assert worker["selection_enabled"] is False
    assert worker["action_face_run_id"] == 33686159662
    assert worker["source_merge_commit"] == "07ca4b4bd50d9ec6c368a2579c3032c1648798cf"
    assert worker["bridge_sha256"] == "a79a9200fce9d74469b058cce24d3b9588ff182fd44109e86be54184632c2fc6"


def test_runtime_hardening_v4_closes_reviewed_failure_modes():
    source = (
        ROOT
        / "db"
        / "migrations"
        / "20260902222552_desktop_commander_runtime_hardening_v4.sql"
    ).read_text()
    assert "identity_changed" in source
    assert "approval_reset" in source
    assert "approved_roots=case when v_identity_changed then '[]'::jsonb" in source
    assert "on conflict(idempotency_key) do nothing" in source.lower()
    assert "idempotency_key_conflict" in source
    assert "lease_expired_attempts_exhausted" in source
    assert "j.status='claimed'" in source
    assert "j.lease_expires_at<now()" in source
    assert "job_not_owned_or_lease_expired" in source
    assert "result_payload_too_large" in source
    assert "max_result_bytes" in source
    assert "record_desktop_commander_heartbeat_v1" in source
    assert "'job_claimed','claimed'" in source
    assert "selection_enabled',false" in source
    assert "p_status='completed' and v_job.mutation_class='read'" in source
    assert "'physical_device_execution'" in source
    assert "desktop_commander_registry_preserve_bound_v1" in source


def test_heartbeat_monotonic_v5_preserves_verified_selection():
    source = (
        ROOT
        / "db"
        / "migrations"
        / "20260902222903_desktop_commander_heartbeat_monotonic_v5.sql"
    ).read_text()
    assert "v_execution_verified boolean:=false" in source
    assert "capability='physical_device_execution'" in source
    assert "'selection_enabled',v_execution_verified" in source
    assert "'physical_device_execution_verified',v_execution_verified" in source
    assert "when v_execution_verified then 'healthy'" in source
    assert "when v_execution_verified then 'none'" in source


def test_bridge_v3_delegates_transactional_evidence_to_database():
    m = manifest()
    assert m["runtime"]["bridge_deploy_version"] == 3
    assert m["runtime"]["bridge_sha256"] == "a79a9200fce9d74469b058cce24d3b9588ff182fd44109e86be54184632c2fc6"
    source = (
        ROOT
        / "supabase"
        / "functions"
        / "apex-desktop-commander-bridge"
        / "index.ts"
    ).read_text()
    assert 'admin.rpc("record_desktop_commander_heartbeat_v1"' in source
    assert 'receipt_type:"job_claimed"' not in source
    assert '.from("connector_registry_v2").update' not in source
    assert 'nonceError.code==="23505"' in source
    assert "nonce_replay_rejected" in source
    assert "nonce_persistence_failed" in source


def test_bridge_v3_registry_receipt_does_not_promote_physical_execution():
    source = (
        ROOT
        / "db"
        / "migrations"
        / "20260902223005_desktop_commander_bridge_v3_registry_v6.sql"
    ).read_text()
    assert "'version',3" in source
    assert "a79a9200fce9d74469b058cce24d3b9588ff182fd44109e86be54184632c2fc6" in source
    assert "'selection_requires_read_only_execution_proof',true" in source
    assert "'verified_selection_monotonic',true" in source
    assert "physical_device_execution" not in source
