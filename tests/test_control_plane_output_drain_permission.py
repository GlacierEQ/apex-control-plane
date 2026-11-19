"""Denied group termination after parent exit must preserve bounded output evidence."""
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


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
def test_denied_group_kill_during_inherited_pipe_timeout_is_explicit(tmp_path):
    skills = tmp_path / "skills"
    document = skills / "agent" / "SKILL.md"
    document.parent.mkdir(parents=True)
    document.write_text("# Agent\n")
    digest = hashlib.sha256(document.read_bytes()).hexdigest()
    shim = tmp_path / "sitecustomize.py"
    shim.write_text(
        "import os\n"
        "def _denied(pgid,sig):raise PermissionError('denied group termination')\n"
        "os.killpg=_denied\n"
    )
    launcher = (
        "import subprocess,sys;"
        "subprocess.Popen([sys.executable,'-c',"
        "'import time;time.sleep(2.0)'],stdout=sys.stdout,stderr=sys.stderr);"
        "print('direct parent exited',flush=True)"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path)
    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, str(ENTRY), "--exec-capability",
         "--skills-root", str(skills), "--select", "skill:agent",
         "--sha256", digest, "--timeout-seconds", "0.3", "--",
         sys.executable, "-c", launcher],
        cwd=ROOT, env=env, capture_output=True, text=True,
        timeout=5, check=False,
    )
    assert time.monotonic() - started < 1.8
    assert result.returncode == 124, (result.stdout, result.stderr)
    receipt = json.loads(result.stdout)
    assert receipt["timed_out"] is True
    assert receipt["output_incomplete"] is True
    assert "PermissionError" in receipt["cleanup_error"]
    assert receipt["stdout"].strip() == "direct parent exited"
    assert receipt["outcome_verified"] is False
