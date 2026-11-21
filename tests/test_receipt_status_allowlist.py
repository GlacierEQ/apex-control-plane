"""Unknown execution states must not be interpreted as valid receipts."""
import json
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).resolve().parents[1] / "src" / "control_plane.py"

def test_unknown_status_fails_closed(tmp_path):
    for status in ("success", "completed", "retry", "", "PROCESS_SUCCEEDED_UNVERIFIED"):
        receipt = tmp_path / "receipt.json"
        receipt.write_text(json.dumps({"status": status, "outcome_verified": True,
                                       "cleanup_unresolved": False,
                                       "output_drains_unresolved": False,
                                       "direct_child_reaped": True}))
        result = subprocess.run([sys.executable, str(CLI), "--inspect-receipt", str(receipt)],
                                capture_output=True, text=True)
        assert result.returncode == 2
        data = json.loads(result.stdout)
        assert data["status"] == "inspection_failed"
        assert data["retry_authorized"] is False
        assert data["outcome_verified"] is False

def test_known_completed_status_still_unverified(tmp_path):
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({"status": "process_succeeded_unverified",
                                   "cleanup_unresolved": False,
                                   "output_drains_unresolved": False,
                                   "direct_child_reaped": True}))
    result = subprocess.run([sys.executable, str(CLI), "--inspect-receipt", str(receipt)],
                            capture_output=True, text=True)
    assert result.returncode == 0
    assert json.loads(result.stdout)["outcome_verified"] is False
