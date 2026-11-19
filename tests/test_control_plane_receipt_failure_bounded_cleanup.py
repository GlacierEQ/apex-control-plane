"""Real CLI regression for durable launch-receipt failure cleanup."""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "src" / "control_plane.py"


@pytest.mark.skipif(os.name != "posix", reason="POSIX process group cleanup")
def test_launch_receipt_failure_returns_without_running_requested_command(tmp_path):
    skills = tmp_path / "skills"
    doc = skills / "agent" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# Agent\n")
    digest = hashlib.sha256(doc.read_bytes()).hexdigest()
    receipt = tmp_path / "receipt.json"
    shim = tmp_path / "sitecustomize.py"
    shim.write_text(
        "import os\n"
        "_replace=os.replace\n"
        "def fail_launched(src,dst):\n"
        " if os.path.basename(str(src)).startswith('.apex-receipt-'):\n"
        "  raise OSError('synthetic launched receipt write failure')\n"
        " return _replace(src,dst)\n"
        "os.replace=fail_launched\n"
    )
    # The child has not received its execution gate when the receipt fails.
    # A separate subprocess inheriting output pipes would otherwise keep
    # an unbounded drain join open if the process tree were not contained.
    command = [
        sys.executable, str(ENTRY), "--exec-capability",
        "--skills-root", str(skills), "--select", "skill:agent",
        "--sha256", digest, "--receipt-path", str(receipt), "--",
        sys.executable, "-c", "print('should not execute')",
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path)
    started = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=5, check=False)
    assert time.monotonic() - started < 3
    assert result.returncode == 2
    assert "cannot finalize durable receipt" in result.stderr
    assert json.loads(receipt.read_text())["status"] == "pending_unverified"
