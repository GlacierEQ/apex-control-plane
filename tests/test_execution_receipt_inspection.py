"""Real CLI inspection: no process identity result permits retry."""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "src" / "control_plane.py"
# The inspector is an executable source module, not an installed package.
sys.path.insert(0, str(ROOT / "src"))


def run(path):
    return subprocess.run([sys.executable, str(CLI), "--inspect-receipt", str(path)],
                          capture_output=True, text=True, cwd=ROOT)


def test_live_child_birth_identity_is_observed(tmp_path):
    child = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(15)"])
    try:
        path = tmp_path / "receipt.json"
        path.write_text(json.dumps({
            "status": "launched_unverified", "pid": child.pid,
            "invocation_id": "live", "launched_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        }))
        result = run(path)
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data["process_identity"] == "birth_time_consistent"
        assert data["retry_authorized"] is False
        assert data["outcome_verified"] is False
    finally:
        child.terminate()
        child.wait(timeout=5)


def test_stale_birth_rejected(tmp_path):
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps({
        "status": "launched_unverified", "pid": os.getpid(),
        "invocation_id": "old", "launched_at_utc": "2020-01-01T00:00:00+00:00",
    }))
    data = json.loads(run(path).stdout)
    assert data["process_identity"] == "birth_time_mismatch"
    assert data["retry_authorized"] is False


def test_pending_has_no_process_proof(tmp_path):
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps({"status": "pending_unverified", "invocation_id": "pending"}))
    data = json.loads(run(path).stdout)
    assert data["process_identity"] == "insufficient_evidence"
    assert data["retry_authorized"] is False


def test_missing_receipt_is_failure(tmp_path):
    result = run(tmp_path / "missing.json")
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "inspection_failed"



def test_inspection_fails_closed_on_unresolved_or_legacy_cleanup(tmp_path):
    import json
    from inspect_execution_receipt import inspect

    path = tmp_path / "receipt.json"
    base = {
        "status": "process_succeeded_unverified",
        "outcome_verified": True,
        "cleanup_unresolved": False,
        "output_drains_unresolved": False,
        "direct_child_reaped": True,
        "group_signal_denied": False,
        "descendant_containment_verified": True,
    }
    for changes, expected in [
        ({}, "resolved_direct_child_only"),
        ({"cleanup_unresolved": True}, "unresolved"),
        ({"output_drains_unresolved": True}, "unresolved"),
        ({"direct_child_reaped": False}, "unresolved"),
        ({"cleanup_unresolved": None}, "unknown"),
    ]:
        record = dict(base, **changes)
        path.write_text(json.dumps(record))
        result = inspect(path)
        assert result["cleanup_status"] == expected
        assert result["outcome_verified"] is False
        assert result["outcome_evidence"] == "unattested_receipt"
        assert result["retry_authorized"] is False

    for key in ("group_signal_denied", "descendant_containment_verified"):
        record = dict(base)
        record.pop(key)
        path.write_text(json.dumps(record))
        assert inspect(path)["outcome_verified"] is False
    path.write_text(json.dumps({"status": "failed", "outcome_verified": True}))
    result = inspect(path)
    assert result["cleanup_status"] == "unknown"
    assert result["outcome_verified"] is False


def test_duplicate_members_cannot_promote_execution_receipt(tmp_path):
    path = tmp_path / "receipt.json"
    clean = ('{"status":"failed","status":"process_succeeded_unverified",'
             '"outcome_verified":true,"cleanup_unresolved":false,'
             '"output_drains_unresolved":false,"direct_child_reaped":true,'
             '"group_signal_denied":false,"descendant_containment_verified":true}')
    for payload in (clean, '{"status":"failed","nested":{"x":1,"x":2}}',
                    '{"status":"failed","outcome_verified":NaN}',
                    '{"status":"failed","outcome_verified":Infinity}'):
        path.write_text(payload)
        result = run(path)
        assert result.returncode == 2, result.stderr
        data = json.loads(result.stdout)
        assert data["status"] == "inspection_failed"
        assert data["retry_authorized"] is False


def test_unique_standard_json_receipt_still_inspects(tmp_path):
    path = tmp_path / "receipt.json"
    path.write_text('{"status":"failed","outcome_verified":false}')
    result = run(path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "inspected_unverified"


def test_forged_success_and_failure_receipts_never_attest_outcome(tmp_path):
    path = tmp_path / "receipt.json"
    for status in ("process_succeeded_unverified", "failed", "invented_success"):
        path.write_text(json.dumps({
            "status": status, "outcome_verified": True,
            "cleanup_unresolved": False, "output_drains_unresolved": False,
            "direct_child_reaped": True, "group_signal_denied": False,
            "descendant_containment_verified": True,
        }))
        completed = run(path)
        assert completed.returncode == 0, completed.stderr
        result = json.loads(completed.stdout)
        assert result["outcome_verified"] is False
        assert result["retry_authorized"] is False
        assert result["outcome_evidence"] == "unattested_receipt"


def test_detected_descendant_remains_visible_after_successful_cleanup(tmp_path):
    from inspect_execution_receipt import inspect
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps({
        "status": "failed", "exit_code": 74,
        "descendant_detected_after_exit": True,
        "cleanup_unresolved": False, "output_drains_unresolved": False,
        "direct_child_reaped": True,
    }))
    result = inspect(path)
    assert result["cleanup_status"] == "descendant_detected_cleanup_completed"
    assert result["descendant_detected_after_exit"] is True
    assert result["outcome_verified"] is False
    assert result["retry_authorized"] is False
