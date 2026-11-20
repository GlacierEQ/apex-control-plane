"""The actual capability executor must not claim success on partial stdin delivery."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "src" / "control_plane.py"


def _run(tmp_path, script):
    skills = tmp_path / "skills"
    doc = skills / "agent" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    payload = "# Agent\n" + "x" * (2 * 1024 * 1024)
    doc.write_text(payload)
    result = subprocess.run(
        [sys.executable, str(ENTRY), "--exec-capability",
         "--skills-root", str(skills), "--select", "skill:agent",
         "--sha256", hashlib.sha256(doc.read_bytes()).hexdigest(),
         "--timeout-seconds", "5", "--", sys.executable, "-c", script],
        cwd=ROOT, capture_output=True, text=True, check=False, timeout=10,
    )
    return result, json.loads(result.stdout), len(doc.read_bytes())


def test_successful_child_that_ignores_large_context_cannot_claim_delivery(tmp_path):
    result, receipt, total = _run(tmp_path, "print('exited zero without reading')")
    assert result.returncode == 74, result.stderr
    assert receipt["exit_code"] == 74
    assert receipt["status"] == "failed"
    assert receipt["capability"]["stdin_bytes_written"] < total
    assert receipt["capability"]["stdin_delivery_complete"] is False
    assert receipt["mission_complete"] is False
    assert receipt["outcome_verified"] is False


def test_full_context_pipe_delivery_retains_successful_exit(tmp_path):
    script = "import sys;print(len(sys.stdin.buffer.read()))"
    result, receipt, total = _run(tmp_path, script)
    assert result.returncode == 0, result.stderr
    assert receipt["capability"]["stdin_bytes_written"] == total
    assert receipt["capability"]["stdin_delivery_complete"] is True
    assert receipt["stdout"].strip() == str(total)
    assert receipt["status"] == "process_succeeded_unverified"



def test_unresolved_writer_cannot_claim_full_delivery(tmp_path):
    """Adversarial writer-liveness signal must fail closed even with all bytes written."""
    import os
    shim = tmp_path / "sitecustomize.py"
    shim.write_text(
        "import threading\n"
        "_original=threading.Thread.is_alive\n"
        "def _injected(self):\n"
        "    if self.name=='capability-stdin-writer': return True\n"
        "    return _original(self)\n"
        "threading.Thread.is_alive=_injected\n"
    )
    skills = tmp_path / "skills"
    doc = skills / "agent" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# Agent\n")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, str(ENTRY), "--exec-capability",
         "--skills-root", str(skills), "--select", "skill:agent",
         "--sha256", hashlib.sha256(doc.read_bytes()).hexdigest(),
         "--timeout-seconds", "3", "--", sys.executable, "-c",
         "import sys;sys.stdin.buffer.read();print('ok')"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=8, check=False,
    )
    assert result.returncode == 74, (result.stdout, result.stderr)
    receipt = json.loads(result.stdout)
    assert receipt["capability"]["stdin_bytes_written"] == len(doc.read_bytes())
    assert receipt["capability"]["stdin_writer_unresolved"] is True
    assert receipt["capability"]["stdin_delivery_complete"] is False
    assert "InputWriterUnresolved" in receipt["capability"]["stdin_delivery_errors"]
    assert receipt["mission_complete"] is False
