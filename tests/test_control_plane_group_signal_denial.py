"""Denied process-group signaling falls back to bounded direct-child cleanup."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group signals")
def test_timeout_group_signal_denial_still_fails_closed(tmp_path):
    skill = tmp_path / "skills" / "agent" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# agent\n")
    injection = tmp_path / "injection"
    injection.mkdir()
    (injection / "sitecustomize.py").write_text(
        "import os\n"
        "def denied(*args, **kwargs): raise PermissionError('group signal denied')\n"
        "os.killpg=denied\n"
    )
    command = [
        sys.executable, str(ROOT / "src" / "control_plane.py"),
        "--exec-capability", "--skills-root", str(skill.parent.parent),
        "--select", "skill:agent",
        "--sha256", hashlib.sha256(skill.read_bytes()).hexdigest(),
        "--timeout-seconds", "0.2", "--",
        sys.executable, "-S", "-c", "import time;time.sleep(8)",
    ]
    start = time.monotonic()
    result = subprocess.run(
        command, cwd=ROOT, env=dict(os.environ, PYTHONPATH=str(injection)),
        capture_output=True, text=True, timeout=5,
    )
    assert time.monotonic() - start < 3
    assert result.returncode == 124, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["timed_out"] is True
    assert receipt["status"] == "failed"
    assert receipt["group_signal_denied"] is True
    assert receipt["descendant_containment_verified"] is False
    assert receipt["direct_child_reaped"] is True
