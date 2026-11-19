"""Real CLI regression: an unreapable terminated child cannot erase timeout evidence."""
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


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group timeout scenario")
def test_timeout_reap_failure_remains_bounded_and_unverified(tmp_path):
    skills = tmp_path / "skills"
    document = skills / "agent" / "SKILL.md"
    document.parent.mkdir(parents=True)
    document.write_text("# Agent\n- bounded cleanup\n")
    digest = hashlib.sha256(document.read_bytes()).hexdigest()
    shim = tmp_path / "sitecustomize.py"
    shim.write_text(
        "import subprocess,os\n"
        "_kill=os.kill\n"
        "os.killpg=lambda pgid,sig:_kill(pgid,sig)\n"
        "_wait=subprocess.Popen.wait\n"
        "def _fault(self,timeout=None):\n"
        " if timeout==1 and self.args and isinstance(self.args,list):\n"
        "  raise subprocess.TimeoutExpired(self.args,timeout)\n"
        " return _wait(self,timeout=timeout)\n"
        "subprocess.Popen.wait=_fault\n"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path)
    command = [
        sys.executable, str(ENTRY), "--exec-capability",
        "--skills-root", str(skills), "--select", "skill:agent",
        "--sha256", digest, "--timeout-seconds", "0.3", "--",
        sys.executable, "-c", "import time;time.sleep(30)",
    ]
    started = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                            text=True, timeout=5, check=False)
    assert time.monotonic() - started < 5
    assert result.returncode == 124, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["timed_out"] is True
    assert "TimeoutExpired: child did not reap after termination" in receipt["cleanup_error"]
    assert receipt["output_incomplete"] is True
    assert receipt["outcome_verified"] is False
    assert receipt["mission_complete"] is False
