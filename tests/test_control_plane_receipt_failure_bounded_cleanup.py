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
        "def denied_group_kill(pgid,sig):\n"
        " raise PermissionError(1,'synthetic group signal denied')\n"
        "os.killpg=denied_group_kill\n"
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
                            capture_output=True, text=True, timeout=15, check=False)
    assert time.monotonic() - started < 5
    assert result.returncode == 2
    assert "pending receipt preserved" in result.stderr
    assert json.loads(receipt.read_text())["status"] == "pending_unverified"


@pytest.mark.skipif(os.name != "posix", reason="POSIX launch receipt gate")
def test_transient_launched_receipt_failure_must_not_overwrite_pending(tmp_path):
    """A later successful replace must never erase uncertain pending evidence."""
    skills = tmp_path / "skills"
    doc = skills / "agent" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# Agent\n")
    receipt = tmp_path / "execution.json"
    marker = tmp_path / "executed"
    shim = tmp_path / "sitecustomize.py"
    shim.write_text(
        "import os\n"
        "_replace=os.replace\n"
        "_failed=False\n"
        "def fail_once(src,dst):\n"
        " global _failed\n"
        " if not _failed and os.path.basename(str(src)).startswith('.apex-receipt-'):\n"
        "  _failed=True\n"
        "  raise OSError('synthetic one-time launch receipt failure')\n"
        " return _replace(src,dst)\n"
        "os.replace=fail_once\n"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path)
    command = [
        sys.executable, str(ENTRY), "--exec-capability",
        "--skills-root", str(skills), "--select", "skill:agent",
        "--sha256", hashlib.sha256(doc.read_bytes()).hexdigest(),
        "--receipt-path", str(receipt), "--",
        sys.executable, "-c",
        "import pathlib,sys;pathlib.Path(sys.argv[1]).touch()", str(marker),
    ]
    result = subprocess.run(command, cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=15, check=False)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "pending receipt preserved" in result.stderr
    assert not marker.exists()
    pending = receipt.read_bytes()
    assert json.loads(pending)["status"] == "pending_unverified"
    retry = subprocess.run(command, cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=15, check=False)
    assert retry.returncode == 2
    assert receipt.read_bytes() == pending
    assert not marker.exists()
