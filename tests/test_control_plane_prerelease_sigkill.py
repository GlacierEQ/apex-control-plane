"""Deterministic forced interruption before the durable child execution gate opens."""
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


@pytest.mark.skipif(os.name != "posix", reason="POSIX launch-gate crash boundary")
def test_sigkill_before_gate_release_never_executes_requested_program(tmp_path):
    skills = tmp_path / "skills"
    document = skills / "agent" / "SKILL.md"
    document.parent.mkdir(parents=True)
    document.write_text("# Agent\n- exact durable launch test\n")
    digest = hashlib.sha256(document.read_bytes()).hexdigest()
    gate_seen = tmp_path / "about-to-release"
    executed = tmp_path / "program-executed"
    receipt = tmp_path / "receipt.json"
    shim = tmp_path / "sitecustomize.py"
    shim.write_text(
        "import os,time\nfrom pathlib import Path\n"
        "_write=os.write\n"
        "def _pause(fd,data):\n"
        " if data==b'G':\n"
        "  Path(os.environ['APEX_TEST_GATE_MARKER']).write_text('paused')\n"
        "  while True:time.sleep(0.05)\n"
        " return _write(fd,data)\n"
        "os.write=_pause\n"
    )
    args = [
        sys.executable, str(ENTRY), "--exec-capability",
        "--skills-root", str(skills), "--select", "skill:agent",
        "--sha256", digest, "--receipt-path", str(receipt), "--",
        sys.executable, "-c",
        "from pathlib import Path;import sys;Path(sys.argv[1]).write_text('executed')",
        str(executed),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path)
    env["APEX_TEST_GATE_MARKER"] = str(gate_seen)
    parent = subprocess.Popen(args, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
    group_id = None
    try:
        until = time.monotonic() + 5
        while not gate_seen.exists() and time.monotonic() < until:
            if parent.poll() is not None:
                break
            time.sleep(0.03)
        assert gate_seen.exists(), "parent never reached the pre-release boundary"
        state = json.loads(receipt.read_text())
        assert state["status"] == "launched_unverified"
        group_id = state["process_group_id"]
        assert not executed.exists()
        original = receipt.read_bytes()
        os.kill(parent.pid, signal.SIGKILL)
        parent.wait(timeout=3)
        time.sleep(0.35)
        assert not executed.exists(), "requested program ran without gate release"
        replay = subprocess.run(args, check=False, cwd=ROOT, capture_output=True, text=True, timeout=5)
        assert replay.returncode == 2
        assert replay.stdout == ""
        assert receipt.read_bytes() == original
        assert not executed.exists()
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=3)
        if group_id:
            try:
                os.killpg(group_id, signal.SIGKILL)
            except ProcessLookupError:
                pass
