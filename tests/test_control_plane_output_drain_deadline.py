"""Real CLI integration: descendants must not defeat the work-unit deadline."""
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "src" / "control_plane.py"


@pytest.mark.skipif(os.name != "posix", reason="POSIX process group containment")
def test_background_descendant_holding_stdout_open_cannot_outlive_deadline(tmp_path):
    skills = tmp_path / "skills"
    doc = skills / "agent" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# Agent\n- bounded worker\n")
    digest = hashlib.sha256(doc.read_bytes()).hexdigest()
    receipt = tmp_path / "receipt.json"
    marker = tmp_path / "late-write"
    descendant = (
        "import pathlib,sys,time;"
        "time.sleep(3.5);pathlib.Path(sys.argv[1]).write_text('late')"
    )
    launcher = (
        "import subprocess,sys;"
        "subprocess.Popen([sys.executable,'-c',sys.argv[2],sys.argv[1]],"
        "stdout=sys.stdout,stderr=sys.stderr);print('parent exited',flush=True)"
    )
    cmd = [
        sys.executable, str(ENTRY),
        "--exec-capability", "--skills-root", str(skills),
        "--select", "skill:agent", "--sha256", digest,
        "--receipt-path", str(receipt), "--timeout-seconds", "0.7", "--",
        sys.executable, "-c", launcher, str(marker), descendant,
    ]
    group_id = None
    started = time.monotonic()
    try:
        completed = subprocess.run(cmd, check=False, cwd=ROOT, capture_output=True,
                                   text=True, timeout=7)
        elapsed = time.monotonic() - started
        if receipt.exists():
            group_id = json.loads(receipt.read_text()).get("process_group_id")
        assert elapsed < 2.5, f"output drain exceeded deadline: {elapsed:.2f}s"
        assert completed.returncode == 124, completed.stderr
        result = json.loads(completed.stdout)
        assert result["timed_out"] is True
        assert result["exit_code"] == 124
        assert result["outcome_verified"] is False
        assert "parent exited" in result["stdout"]
        assert result["output_incomplete"] is True
        time.sleep(1)
        assert not marker.exists(), "descendant survived execution deadline"
    finally:
        if group_id:
            try:
                os.killpg(group_id, signal.SIGKILL)
            except ProcessLookupError:
                pass
