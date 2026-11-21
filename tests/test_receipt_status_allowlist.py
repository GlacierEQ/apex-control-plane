"""Fail closed when durable execution receipt status is not an emitted state."""
import json
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).resolve().parents[1] / "src" / "control_plane.py"


def _inspect(tmp_path, status):
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({"status": status, "outcome_verified": True,
                                   "cleanup_unresolved": False,
                                   "output_drains_unresolved": False,
                                   "direct_child_reaped": True}))
    process = subprocess.run([sys.executable, str(CLI), "--inspect-receipt",
                              str(receipt)], capture_output=True, text=True)
    return process.returncode, json.loads(process.stdout)


def test_unknown_statuses_fail_closed(tmp_path):
    for status in ("success", "completed", "retry", "", "PROCESS_SUCCEEDED_UNVERIFIED"):
        code, result = _inspect(tmp_path, status)
        assert code == 2
        assert result["status"] == "inspection_failed"
        assert result["retry_authorized"] is False
        assert result["outcome_verified"] is False


def test_emitted_completion_still_unverified(tmp_path):
    code, result = _inspect(tmp_path, "process_succeeded_unverified")
    assert code == 0
    assert result["status"] == "inspected_unverified"
    assert result["outcome_verified"] is False
