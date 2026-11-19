"""Crash/restart regression against the real APEX capability executable."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "src" / "control_plane.py"


def test_sigkill_pending_receipt_blocks_duplicate_execution(tmp_path):
    skills = tmp_path / "skills"
    doc = skills / "agent" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("Crash-safe test capability", encoding="utf-8")
    receipt = tmp_path / "receipt.json"
    marker = tmp_path / "started"
    second = tmp_path / "second-started"
    digest = hashlib.sha256(doc.read_bytes()).hexdigest()
    base = [sys.executable, str(CLI), "--exec-capability", "--skills-root",
            str(skills), "--select", "skill:agent", "--sha256", digest,
            "--receipt-path", str(receipt), "--"]
    child = [sys.executable, "-c",
             "import pathlib,sys,time; pathlib.Path(sys.argv[1]).write_text(str(__import__('os').getpid()));time.sleep(15)",
             str(marker)]
    parent = subprocess.Popen(base + child, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, cwd=ROOT)
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if receipt.exists() and marker.exists():
                break
            time.sleep(0.02)
        assert receipt.exists() and marker.exists(), "did not reach launched/pending boundary"
        pending_bytes = receipt.read_bytes()
        pending = json.loads(pending_bytes)
        assert pending["status"] == "launched_unverified"
        assert pending["outcome_verified"] is False
        assert pending["pid"] == int(marker.read_text())
        assert pending["process_group_id"] == pending["pid"]
        parent.kill()
        parent.wait(timeout=5)
        retry = subprocess.run(base + [
            sys.executable, "-c",
            "import pathlib,sys;pathlib.Path(sys.argv[1]).write_text('duplicate')",
            str(second)], capture_output=True, text=True, cwd=ROOT, timeout=5)
        assert retry.returncode == 2
        assert not second.exists()
        assert receipt.read_bytes() == pending_bytes
        assert json.loads(receipt.read_bytes())["status"] == "launched_unverified"
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=5)
        # Parent SIGKILL can orphan the child: clean up the test-owned group.
        if marker.exists() and os.name == 'posix':
            try:
                os.killpg(int(marker.read_text()), signal.SIGKILL)
            except (ProcessLookupError, ValueError):
                pass
