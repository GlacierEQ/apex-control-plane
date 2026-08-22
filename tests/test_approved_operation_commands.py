from __future__ import annotations

from datetime import UTC, datetime, timedelta
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from approved_operation_bridge import action_scope_sha256


NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)


def _load_script(name: str):
    path = SCRIPTS / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module


def action_request() -> dict:
    request = {
        "schema_version": 1,
        "action_request_id": "action-command-001",
        "connector": "github",
        "operation": "issue.create",
        "target": {"repository": "GlacierEQ/apex-control-plane"},
        "provider_input": {"title": "Command test", "body": "This text must not enter receipts."},
        "consequence": "Creates one named issue visible to repository collaborators.",
        "evidence_refs": ["receipt-github-001"],
        "idempotency_key": "command-test-action-001",
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
            "approval_reference": "command-test-approval-001",
            "approval_scope_sha256": "",
        },
    }
    request["approval"]["approval_scope_sha256"] = action_scope_sha256(
        connector=request["connector"],
        operation=request["operation"],
        target=request["target"],
        provider_input=request["provider_input"],
        consequence=request["consequence"],
        evidence_refs=tuple(request["evidence_refs"]),
        idempotency_key=request["idempotency_key"],
    )
    return request


def test_prepare_command_issues_an_exact_approved_host_plan(tmp_path):
    module = _load_script("prepare_approved_connector_action.py")
    action_path = tmp_path / "action.json"
    action_path.write_text(json.dumps(action_request()), encoding="utf-8")

    result = module.prepare_action_plan(action_request_path=action_path, now=NOW)

    assert result["status"] == "approved_for_direct_host_execution"
    assert result["repository_provider_execution"] is False
    assert result["external_action_authorized"] is True
    assert result["plan"]["provider_kind"] == "browser_session"
    assert result["plan"]["provider_operation"] == "issue.create"
    assert result["audit_scope"]["provider_input_sha256"]
    assert "provider_input" not in result["audit_scope"]


def test_execution_admission_command_keeps_provider_material_out_of_ledger(tmp_path):
    module = _load_script("admit_session_connector_execution_receipts.py")
    action_path = tmp_path / "action.json"
    action_path.write_text(json.dumps(action_request()), encoding="utf-8")
    execution_path = tmp_path / "provider-execution.json"
    readback_path = tmp_path / "provider-readback.json"
    execution_path.write_text('{"provider_id": 101, "secret": "do-not-ledger"}', encoding="utf-8")
    readback_path.write_text('{"number": 101, "title": "Command test"}', encoding="utf-8")
    manifest_path = tmp_path / "execution-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "result_state": "success",
                "verification_passed": True,
                "execution_source_refs": ["github://issue/create/101"],
                "execution_observation_path": str(execution_path),
                "executed_at": NOW.isoformat().replace("+00:00", "Z"),
                "result_target": {"repository": "GlacierEQ/apex-control-plane", "issue_number": 101},
                "readback_source_refs": ["github://issue/101"],
                "readback_observation_path": str(readback_path),
                "readback_at": (NOW + timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
            }
        ),
        encoding="utf-8",
    )
    ledger_path = tmp_path / "execution-receipts.jsonl"

    result = module.admit_execution_manifest(
        action_request_path=action_path,
        execution_manifest_path=manifest_path,
        receipt_ledger_path=ledger_path,
        commit_sha="b" * 40,
        now=NOW,
    )

    content = ledger_path.read_text(encoding="utf-8")
    assert result["status"] == "accepted"
    assert result["repository_provider_execution"] is False
    assert result["external_action_authorized"] is True
    assert "do-not-ledger" not in content
    assert "Command test" not in content
    assert "execution_content_sha256" in content
    assert "readback_content_sha256" in content
