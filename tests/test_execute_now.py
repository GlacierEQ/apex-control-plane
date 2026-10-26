"""A real, provider-independent internal route must run without APEX boot gates."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from src.execute_now import Action, DirectExecutor, Step, ReconciliationRequired, ExecutionDenied


def test_internal_action_executes_without_boot_receipt_or_provider(tmp_path):
    runner = DirectExecutor(tmp_path / "journal.sqlite3")
    calls = []
    action = Action("CHERRY", "private-evidence", "compile", {"source": "box:original-1"})
    def effect(work):
        calls.append(work.operation_id)
        return {"artifact": "file:casebook-1"}
    receipt = runner.run(action, effect, verify=lambda result: result["artifact"] == "file:casebook-1")
    assert receipt.state == "VERIFIED"
    assert receipt.external is False
    assert receipt.provider_receipt_id is None
    assert calls == ["private-evidence"]


def test_repeated_action_returns_durable_original_without_reexecuting(tmp_path):
    journal = tmp_path / "journal.sqlite3"
    action = Action("CHERRY", "packet-1", "compile", {"claimant": "Cherry"})
    first = DirectExecutor(journal).run(action, lambda work: {"artifact": "local:packet-1"}, verify=lambda result: True)
    replay = DirectExecutor(journal).run(action, lambda work: pytest.fail("duplicated action"))
    assert first.operation_id == replay.operation_id
    assert replay.replayed is True
    assert replay.state == "VERIFIED"


def test_unrelated_authorized_action_continues_when_one_lane_errors(tmp_path):
    runner = DirectExecutor(tmp_path / "journal.sqlite3")
    fail = Action("CHERRY", "nex-blocked", "compile", {})
    other = Action("CHERRY", "camaro-internal", "compile", {})
    def explode(_):
        raise OSError("fixture: missing source")
    results = runner.run_many([
        Step(fail, explode),
        Step(other, lambda _: {"artifact": "local:camaro"}, lambda result: True),
    ])
    assert [r.state for r in results] == ["RECONCILE", "VERIFIED"]
    assert results[1].operation_id == "camaro-internal"
    with pytest.raises(ReconciliationRequired):
        runner.run(fail, lambda _: pytest.fail("must not replay an uncertain action"))


def test_external_provider_effect_requires_actual_authority_before_callback(tmp_path):
    runner = DirectExecutor(tmp_path / "journal.sqlite3")
    external = Action("CHERRY", "send-1", "send", {}, external=True, approval_ref="case:approval-1")
    with pytest.raises(ExecutionDenied):
        runner.run(external, lambda _: pytest.fail("external effect executed without approval"))
    with pytest.raises(ExecutionDenied):
        runner.run(external, lambda _: pytest.fail("external effect executed without readback"), authorization=lambda _: True)


def test_external_approved_effect_requires_native_receipt_and_readback(tmp_path):
    runner = DirectExecutor(tmp_path / "journal.sqlite3")
    external = Action("CHERRY", "send-2", "send", {}, external=True, approval_ref="case:approval-2")
    result = runner.run(
        external, lambda _: {"provider_receipt_id": "gmail:sent-42", "status": "SENT"},
        authorization=lambda _: True,
        verify=lambda result: result["provider_receipt_id"] == "gmail:sent-42",
    )
    assert result.state == "VERIFIED"
    assert result.provider_receipt_id == "gmail:sent-42"


def test_payload_drift_cannot_reuse_previous_operation_identity(tmp_path):
    runner = DirectExecutor(tmp_path / "journal.sqlite3")
    runner.run(Action("CHERRY", "same-id", "compile", {"a": 1}), lambda _: {"ok": True})
    with pytest.raises(ExecutionDenied, match="changed"):
        runner.run(Action("CHERRY", "same-id", "compile", {"a": 2}), lambda _: pytest.fail("drift executed"))


def test_real_cli_builds_readback_verified_casebook_from_source_records(tmp_path):
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "case-output"
    manifest.write_text(json.dumps({
        "mission_id": "CHERRY",
        "actions": [
            {
                "operation_id": "nex-evidence",
                "kind": "casebook",
                "title": "NEX source ledger",
                "claimant": "Cherry",
                "records": [
                    {"source_ref": "nex:ticket-100859", "statement": "Paid receipt $165.15", "classification": "SOURCE_REPORTED"},
                    {"source_ref": "nex:demand-200", "statement": "Separate $200 demand", "classification": "ALLEGED"},
                ],
            }
        ],
    }), encoding="utf-8")
    command = [sys.executable, str(Path(__file__).resolve().parents[1] / "src/control_plane.py"),
               "run-internal", "--manifest", str(manifest), "--out-dir", str(output),
               "--journal", str(tmp_path / "journal.sqlite3")]
    first = subprocess.run(command, capture_output=True, text=True, check=False)
    assert first.returncode == 0, first.stderr + first.stdout
    payload = json.loads(first.stdout)
    assert payload["results"][0]["state"] == "VERIFIED"
    artifact = output / "nex-evidence.md"
    assert artifact.is_file()
    content = artifact.read_text(encoding="utf-8")
    assert "nex:ticket-100859" in content
    assert "Paid receipt $165.15" in content
    assert "Separate $200 demand" in content
    second = subprocess.run(command, capture_output=True, text=True, check=False)
    assert second.returncode == 0, second.stderr + second.stdout
    assert json.loads(second.stdout)["results"][0]["replayed"] is True
