"""The CLI must not fabricate an executed route without a provider host."""
import json
from pathlib import Path
import subprocess
import sys


def test_unbound_control_plane_does_not_claim_route_was_executed():
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, str(root / "src/control_plane.py")],
        cwd=root, text=True, capture_output=True, check=False,
    )
    payload = json.loads(proc.stdout)
    assert proc.returncode == 78
    assert payload["status"] == "HOST_EXECUTOR_NOT_BOUND"
    assert payload["routes_run"] == 0
    assert payload["provider_receipt"] is None
    assert payload["continuation_verified"] is False
    assert "before" not in payload and "after" not in payload
