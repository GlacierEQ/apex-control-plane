from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config" / "oci_live_source_parity.json"
FUNCTION_ROOT = ROOT / "supabase" / "functions"
HEX_64 = re.compile(r"^[0-9a-f]{64}$")


def test_oci_live_source_parity_contract() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["plane"] == "supabase-backend-ops"
    assert manifest["project_id"] == "dyhprklicgewmrimecey"
    assert manifest["parity_mode"] == "semantic_source_recovery_with_deployment_identity_lock"
    assert manifest["authority"]["github_is_versioned_code_authority"] is True
    assert manifest["authority"]["supabase_is_live_runtime_projection"] is True
    assert manifest["authority"]["deployment_bundle_hash_is_not_raw_index_ts_hash"] is True

    functions = manifest["functions"]
    assert len(functions) == 8
    assert len({row["slug"] for row in functions}) == len(functions)

    for row in functions:
        source = FUNCTION_ROOT / row["slug"] / "index.ts"
        assert source.is_file(), row["slug"]
        text = source.read_text(encoding="utf-8")
        assert "Deno.serve" in text, row["slug"]
        assert HEX_64.fullmatch(row["deployment_bundle_sha256"]), row["slug"]
        assert row["version"] >= 1
        assert row["verify_jwt"] is False


def test_oci_source_does_not_restore_hardcoded_donor_provider_state() -> None:
    forbidden_literals = (
        "mx-monterrey-1.aaaa",
        "MX-MONTERREY-1-AD-1",
        "glacier_agent_ed25519.pub",
        "local plaintext OCI CLI configuration dependency",
    )
    source_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(FUNCTION_ROOT.glob("apex-oci-*/index.ts"))
    )
    for literal in forbidden_literals:
        assert literal not in source_text


def test_oci_recovered_runtime_mechanisms() -> None:
    bootstrap = (FUNCTION_ROOT / "apex-oci-bootstrap-activate" / "index.ts").read_text(encoding="utf-8")
    census = (FUNCTION_ROOT / "apex-oci-census-once" / "index.ts").read_text(encoding="utf-8")
    inspect = (FUNCTION_ROOT / "apex-oci-instance-inspect-once" / "index.ts").read_text(encoding="utf-8")
    enable = (FUNCTION_ROOT / "apex-oci-enable-run-command" / "index.ts").read_text(encoding="utf-8")
    probe = (FUNCTION_ROOT / "apex-oci-run-command-probe" / "index.ts").read_text(encoding="utf-8")
    readback = (FUNCTION_ROOT / "apex-oci-run-command-readback" / "index.ts").read_text(encoding="utf-8")
    iam = (FUNCTION_ROOT / "apex-oci-run-command-iam-inspect" / "index.ts").read_text(encoding="utf-8")

    assert "resolve_apex_keymaster_secret_for_broker" in bootstrap
    assert "verify_apex_keymaster_secret" in bootstrap
    assert "ciphertext_sha256" in bootstrap
    assert "plaintext_returned: false" in bootstrap
    assert "apex_oci_resource_inventory_v1" in census
    assert "selected_targets" in inspect
    assert "Compute Instance Run Command" in enable
    assert "instanceAgentCommands" in probe
    assert "lifecycleState" in probe
    assert "instanceAgentCommands" in readback
    assert "agent_plugins" in readback
    assert "inspect_run_command_iam" in iam
