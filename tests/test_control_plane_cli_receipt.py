"""CLI regression: process success is not proof of a provider action."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def test_cli_does_not_fabricate_route_or_provider_receipt():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + str(ROOT)
    p = subprocess.run(
        [sys.executable, str(ROOT / "src" / "control_plane.py")],
        cwd=ROOT, env=env, text=True, capture_output=True, check=True,
    )
    result = json.loads(p.stdout)
    assert result["status"] == "NO_ROUTE_EXECUTED"
    assert result["execution_stage"] == "OBSERVED_ONLY"
    assert result["routes_run"] == 0
    assert result["context_application_ref"] is None
    assert result["provider_acceptance_id"] is None
    assert result["continuation_readback_id"] is None
    assert "receipt" not in result
