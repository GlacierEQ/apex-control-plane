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


def test_sigkill_before_gate_release_never_executes_requested_program(tmp_path):
    """Deterministically kill parent at the exact one-byte launch gate boundary.

    A test-only sitecustomize shim intercepts the controller's write of b"G".
    This does not alter shipped behavior or grant credentials/authority.
    """
    if os.name != "posix":
        import pytest
        pytest.skip("POSIX inherited-fd launch gate required")
    skills = tmp_path / "skills"
    doc = skills / "agent" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("pre-release crash gate", encoding="utf-8")
    digest = hashlib.sha256(doc.read_bytes()).hexdigest()
    receipt = tmp_path / "receipt.json"
    executed_marker = tmp_path / "requested_program_started"
    gate_marker = tmp_path / "controller_at_release"
    startup_log = tmp_path / "python_startup_hooks"
    injection = tmp_path / "injection"
    injection.mkdir()
    (injection / "sitecustomize.py").write_text(
        "\n".join([
            "import os,time,pathlib",
            "with open(os.environ['GLACIEREQ_TEST_STARTUP_LOG'], 'a') as log: log.write(str(os.getpid()) + ',')",
            "_write = os.write",
            "def _wait_at_release(fd, data):",
            "    if data == b'G':",
            "        pathlib.Path(os.environ['GLACIEREQ_TEST_GATE_MARKER']).write_text(str(os.getpid()))",
            "        while True: time.sleep(0.01)",
            "    return _write(fd, data)",
            "os.write = _wait_at_release",
        ]) + "\n",
        encoding="utf-8",
    )
    cmd = [
        sys.executable, str(CLI), "--exec-capability", "--skills-root", str(skills),
        "--select", "skill:agent", "--sha256", digest, "--timeout-seconds", "5",
        "--receipt-path", str(receipt), "--",
        sys.executable, "-c",
        "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('EXECUTED')",
        str(executed_marker),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(injection)
    env["GLACIEREQ_TEST_GATE_MARKER"] = str(gate_marker)
    env["GLACIEREQ_TEST_STARTUP_LOG"] = str(startup_log)
    parent = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
    child_pid = None
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and not gate_marker.exists():
            if parent.poll() is not None:
                raise AssertionError(f"controller exited before gate: {parent.communicate()!r}")
            time.sleep(0.01)
        assert gate_marker.exists(), "did not reach deterministic pre-release boundary"
        assert receipt.is_file(), "launched receipt was not committed before release"
        original = receipt.read_bytes()
        record = json.loads(original)
        assert record["status"] == "launched_unverified"
        assert record["outcome_verified"] is False
        child_pid = record["pid"]
        startup_pids = {int(value) for value in startup_log.read_text().split(",") if value}
        assert parent.pid in startup_pids
        assert child_pid not in startup_pids, "gate trampoline ran ambient Python startup hooks before release"
        assert not executed_marker.exists(), "requested command ran before release"
        parent.kill()
        parent.wait(timeout=5)
        time.sleep(0.25)
        assert not executed_marker.exists(), "child executed after parent died before gate release"
        retry = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, timeout=5)
        assert retry.returncode == 2
        assert receipt.read_bytes() == original, "retry overwrote interrupted launch receipt"
        assert not executed_marker.exists()
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=5)
        if child_pid is not None:
            try:
                os.killpg(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
