from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/desktop_commander_control_plane.json"
BRIDGE = ROOT / "supabase/functions/apex-desktop-commander-bridge/index.ts"
MIGRATIONS = [
    "20260902202019_desktop_commander_local_agent_plane_v1.sql",
    "20260902202236_desktop_commander_operation_policy_v2.sql",
    "20260902214312_github_oidc_udc_workload_allowlist_v1.sql",
    "20260902221859_desktop_commander_registry_runtime_ready_v3.sql",
    "20260902222552_desktop_commander_runtime_hardening_v4.sql",
    "20260902222903_desktop_commander_heartbeat_monotonic_v5.sql",
    "20260902223005_desktop_commander_bridge_v3_registry_v6.sql",
    "20260902223417_desktop_commander_read_probe_policy_binding_v7.sql",
    "20260902223457_desktop_commander_execution_proof_registry_v8.sql",
    "20260902223813_desktop_commander_device_binding_guard_v9.sql",
    "20260902223902_desktop_commander_binding_registry_v10.sql",
]


def test_all_deployed_desktop_commander_migrations_are_source_controlled() -> None:
    for name in MIGRATIONS:
        assert (ROOT / "db/migrations" / name).is_file(), name


def test_static_contract_does_not_fossilize_live_device_state() -> None:
    config = json.loads(CONFIG.read_text())
    assert config["authority"]["live_device_state_is_runtime_only"] is True
    assert config["source_parity"]["migration_count"] == len(MIGRATIONS)
    serialized = json.dumps(config).lower()
    assert "physical_device" not in serialized
    assert "selection_enabled" not in serialized
    assert "last_heartbeat" not in serialized


def test_bridge_requires_signed_replay_protected_device_identity() -> None:
    source = BRIDGE.read_text()
    assert 'crypto.subtle.verify' in source
    assert 'Ed25519' in source
    assert 'x-glacier-timestamp' in source
    assert 'x-glacier-nonce' in source
    assert 'x-glacier-signature' in source
    assert 'nonce_replay_rejected' in source
    assert 'device_not_approved' in source


def test_bridge_exposes_bounded_job_lifecycle_not_arbitrary_shell() -> None:
    source = BRIDGE.read_text()
    for action in ('"status"', '"heartbeat"', '"claim"', '"finish"'):
        assert action in source
    assert 'unsupported_action' in source
    config = json.loads(CONFIG.read_text())
    assert "arbitrary_shell" in config["forbidden_by_default"]
    assert config["invariants"]["compare_before_write_required"] is True
    assert config["invariants"]["device_specific_execution_binding"] is True
