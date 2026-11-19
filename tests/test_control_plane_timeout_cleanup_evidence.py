"""Real executor regression for a cleanup OSError after a confirmed timeout."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "src" / "control_plane.py"


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group cleanup")
def test_cleanup_oserror_preserves_timeout_and_uncertainty(tmp_path):
    skills = tmp_path / "skills"
    doc = skills / "agent" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# Agent\n")
    digest = hashlib.sha256(doc.read_bytes()).hexdigest()
    shim = tmp_path / "sitecustomize.py"
    shim.write_text(
        "import os\n"
        "_original=os.killpg\n"
        "def _kill_then_fail(pid, sig):\n"
        " _original(pid,sig)\n"
        " raise PermissionError('injected cleanup error after kill')\n"
        "os.killpg=_kill_then_fail\n"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path)
    cmd = [
        sys.executable, str(ENTRY), "--exec-capability",
        "--skills-root", str(skills), "--select", "skill:agent",
        "--sha256", digest, "--timeout-seconds", "0.25", "--",
        sys.executable, "-c", "import time;time.sleep(8)",
    ]
    result = subprocess.run(cmd, cwd=ROOT, env=env, check=False,
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 124, (result.stdout, result.stderr)
    receipt = json.loads(result.stdout)
    assert receipt["timed_out"] is True
    assert receipt["executed"] is True
    assert receipt["output_incomplete"] is True
    assert "PermissionError" in receipt["cleanup_error"]
    assert receipt["mission_complete"] is False
    assert receipt["outcome_verified"] is False
