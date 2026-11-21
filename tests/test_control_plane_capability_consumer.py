"""End-to-end capability pin enforcement through the real APEX CLI consumer."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "src" / "control_plane.py"


def invoke(*args):
    return subprocess.run([sys.executable, str(ENTRYPOINT), *map(str, args)],
                          capture_output=True, text=True, cwd=ROOT, check=False)


def test_real_consumer_loads_pinned_skill_into_subprocess_stdin(tmp_path):
    skills = tmp_path / "skills"
    doc = skills / "agent" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    content = "# Agent\n\n- Context first, execute real work.\n"
    doc.write_text(content, encoding="utf-8")
    digest = hashlib.sha256(content.encode()).hexdigest()
    result = invoke(
        "--exec-capability", "--skills-root", skills,
        "--select", "skill:agent", "--sha256", digest, "--",
        sys.executable, "-c",
        "import sys,hashlib; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())",
    )
    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    assert response["status"] == "process_succeeded_unverified"
    assert response["capability"]["qualified_name"] == "skill:agent"
    assert response["capability"]["sha256"] == digest
    assert response["stdout"].strip() == digest
    assert response["outcome_verified"] is False


def test_changed_skill_fails_before_execution(tmp_path):
    skills = tmp_path / "skills"
    doc = skills / "agent" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("modified untrusted instructions", encoding="utf-8")
    marker = tmp_path / "executed"
    result = invoke(
        "--exec-capability", "--skills-root", skills,
        "--select", "skill:agent", "--sha256", "0" * 64, "--",
        sys.executable, "-c", "import pathlib,sys;pathlib.Path(sys.argv[1]).write_text('executed')", marker,
    )
    assert result.returncode == 2
    assert not marker.exists()
    assert "mismatch" in result.stderr
    assert result.stdout == ""


def test_ambiguous_capability_fails_without_subprocess(tmp_path):
    skills = tmp_path / "skills"
    connectors = tmp_path / "connectors"
    for base, kind in ((skills, "SKILL.md"), (connectors, "CONNECTOR.md")):
        d = base / "shared" / kind
        d.parent.mkdir(parents=True)
        d.write_text("# same name")
    marker = tmp_path / "executed"
    result = invoke("--exec-capability", "--skills-root", skills,
                    "--connectors-root", connectors, "--select", "shared",
                    "--sha256", hashlib.sha256(b"# same name").hexdigest(), "--",
                    sys.executable, "-c",
                    "import pathlib,sys;pathlib.Path(sys.argv[1]).write_text('executed')",
                    marker)
    assert result.returncode == 2
    assert "ambiguous" in result.stderr
    assert not marker.exists()


def test_existing_exec_path_remains_compatible():
    result = invoke("--exec", sys.executable, "-c", "print('existing path')")
    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    assert response["stdout"].strip() == "existing path"
    assert response["outcome_verified"] is False


def test_timeout_kills_hung_child_and_reports_unverified(tmp_path):
    skills = tmp_path / "skills"
    doc = skills / "agent" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("capability context", encoding="utf-8")
    digest = hashlib.sha256(doc.read_bytes()).hexdigest()
    result = invoke(
        "--exec-capability", "--skills-root", skills,
        "--select", "skill:agent", "--sha256", digest,
        "--timeout-seconds", "0.15", "--",
        sys.executable, "-c", "import time; time.sleep(5)",
    )
    assert result.returncode == 124, (result.stderr, result.stdout)
    response = json.loads(result.stdout)
    assert response["timed_out"] is True
    assert response["executed"] is True
    assert response["routes_run"] == 1
    assert response["outcome_verified"] is False
    assert response["mission_complete"] is False


def test_invalid_timeout_rejected_before_child(tmp_path):
    skills = tmp_path / "skills"
    doc = skills / "agent" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("context", encoding="utf-8")
    marker = tmp_path / "should-not-exist"
    result = invoke(
        "--exec-capability", "--skills-root", skills,
        "--select", "skill:agent",
        "--sha256", hashlib.sha256(doc.read_bytes()).hexdigest(),
        "--timeout-seconds", "nan", "--",
        sys.executable, "-c",
        "import pathlib,sys;pathlib.Path(sys.argv[1]).touch()", marker,
    )
    assert result.returncode == 2
    assert not marker.exists()
    assert result.stdout == ""


def test_child_exit_127_is_still_recorded_as_executed(tmp_path):
    skills = tmp_path / "skills"
    doc = skills / "agent" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("context", encoding="utf-8")
    result = invoke(
        "--exec-capability", "--skills-root", skills,
        "--select", "skill:agent",
        "--sha256", hashlib.sha256(doc.read_bytes()).hexdigest(),
        "--", sys.executable, "-c", "import sys; sys.exit(127)",
    )
    assert result.returncode == 127
    response = json.loads(result.stdout)
    assert response["executed"] is True
    assert response["routes_run"] == 1
    assert response["timed_out"] is False


def test_timeout_terminates_descendant_process_group(tmp_path):
    """A timed-out agent cannot leave its delegated worker writing afterward."""
    import os
    import time
    if os.name != "posix":
        return
    skills = tmp_path / "skills"
    doc = skills / "agent" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("context", encoding="utf-8")
    marker = tmp_path / "descendant-survived"
    worker = (
        "import subprocess,sys,time;"
        "subprocess.Popen([sys.executable,'-c',"
        "'import pathlib,time,sys;time.sleep(1.2);pathlib.Path(sys.argv[1]).touch()',"
        "sys.argv[1]]);time.sleep(10)"
    )
    result = invoke(
        "--exec-capability", "--skills-root", skills,
        "--select", "skill:agent",
        "--sha256", hashlib.sha256(doc.read_bytes()).hexdigest(),
        "--timeout-seconds", "0.3", "--",
        sys.executable, "-c", worker, marker,
    )
    assert result.returncode == 124, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["timed_out"] is True
    assert receipt["executed"] is True
    time.sleep(1.4)
    assert not marker.exists(), "delegated worker survived parent timeout"


def test_large_subprocess_output_is_bounded_without_false_success(tmp_path):
    skills = tmp_path / "skills"
    doc = skills / "noisy" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# noisy", encoding="utf-8")
    digest = hashlib.sha256(doc.read_bytes()).hexdigest()
    result = invoke(
        "--exec-capability", "--skills-root", skills,
        "--select", "skill:noisy", "--sha256", digest, "--",
        sys.executable, "-c",
        "import sys;sys.stdout.write('A'*300000);sys.stderr.write('B'*240000)",
    )
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["stdout_bytes"] == 300000
    assert receipt["stderr_bytes"] == 240000
    assert receipt["stdout_truncated"] is True
    assert receipt["stderr_truncated"] is True
    assert len(receipt["stdout"]) == receipt["capture_limit_bytes"] == 65536
    assert len(receipt["stderr"]) == 65536
    assert receipt["outcome_verified"] is False
    assert receipt["mission_complete"] is False


def test_bounded_capture_preserves_small_output(tmp_path):
    skills = tmp_path / "skills"
    doc = skills / "small" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# small", encoding="utf-8")
    digest = hashlib.sha256(doc.read_bytes()).hexdigest()
    result = invoke(
        "--exec-capability", "--skills-root", skills,
        "--select", "skill:small", "--sha256", digest, "--",
        sys.executable, "-c", "import sys;print('OK');print('ERR',file=sys.stderr)",
    )
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["stdout"] == "OK\\n".replace("\\n", "\n")
    assert receipt["stderr"] == "ERR\\n".replace("\\n", "\n")
    assert receipt["stdout_truncated"] is False
    assert receipt["stderr_truncated"] is False


def test_durable_receipt_commits_final_execution(tmp_path):
    skills = tmp_path / "skills"
    doc = skills / "agent" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("trusted context", encoding="utf-8")
    receipt_path = tmp_path / "execution.json"
    result = invoke(
        "--exec-capability", "--skills-root", skills,
        "--select", "skill:agent",
        "--sha256", hashlib.sha256(doc.read_bytes()).hexdigest(),
        "--receipt-path", receipt_path, "--",
        sys.executable, "-c", "print('real subprocess')",
    )
    assert result.returncode == 0, result.stderr
    durable = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert durable == json.loads(result.stdout)
    assert durable["stdout"].strip() == "real subprocess"
    assert durable["outcome_verified"] is False
    assert durable["mission_complete"] is False
    assert not list(tmp_path.glob(".apex-receipt-*"))


def test_receipt_init_failure_prevents_child_execution(tmp_path):
    skills = tmp_path / "skills"
    doc = skills / "agent" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("trusted context", encoding="utf-8")
    marker = tmp_path / "should-not-run"
    receipt_path = tmp_path / "missing" / "receipt.json"
    result = invoke(
        "--exec-capability", "--skills-root", skills,
        "--select", "skill:agent",
        "--sha256", hashlib.sha256(doc.read_bytes()).hexdigest(),
        "--receipt-path", receipt_path, "--",
        sys.executable, "-c",
        "import pathlib,sys;pathlib.Path(sys.argv[1]).touch()", marker,
    )
    assert result.returncode == 2
    assert not marker.exists()
    assert not receipt_path.exists()


def test_existing_pending_receipt_is_never_overwritten_or_reexecuted(tmp_path):
    """Restarting a crashed invocation must not erase uncertain execution evidence."""
    skills = tmp_path / "skills"
    doc = skills / "agent" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("trusted context", encoding="utf-8")
    receipt_path = tmp_path / "execution.json"
    original = '{"status":"pending_unverified","previous_attempt":"preserve"}\n'
    receipt_path.write_text(original, encoding="utf-8")
    marker = tmp_path / "must-not-execute"
    result = invoke(
        "--exec-capability", "--skills-root", skills,
        "--select", "skill:agent",
        "--sha256", hashlib.sha256(doc.read_bytes()).hexdigest(),
        "--receipt-path", receipt_path, "--",
        sys.executable, "-c",
        "import pathlib,sys;pathlib.Path(sys.argv[1]).touch()", marker,
    )
    assert result.returncode == 2
    assert not marker.exists()
    assert receipt_path.read_text(encoding="utf-8") == original
    assert not list(tmp_path.glob(".apex-receipt-*"))


def test_existing_final_receipt_is_never_overwritten(tmp_path):
    skills = tmp_path / "skills"
    doc = skills / "agent" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("trusted context", encoding="utf-8")
    receipt_path = tmp_path / "execution.json"
    original = '{"status":"process_succeeded_unverified","outcome_verified":false}\n'
    receipt_path.write_text(original, encoding="utf-8")
    result = invoke(
        "--exec-capability", "--skills-root", skills,
        "--select", "skill:agent",
        "--sha256", hashlib.sha256(doc.read_bytes()).hexdigest(),
        "--receipt-path", receipt_path, "--",
        sys.executable, "-c", "print('should never run')",
    )
    assert result.returncode == 2
    assert receipt_path.read_text(encoding="utf-8") == original
    assert "should never run" not in result.stdout


def test_sigkill_preserves_launched_process_identity_and_blocks_retry(tmp_path):
    """A real interrupted parent retains child identity, but never certifies success."""
    import os
    import signal
    import time
    if os.name != "posix":
        return
    skills = tmp_path / "skills"
    doc = skills / "agent" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("trusted context", encoding="utf-8")
    receipt_path = tmp_path / "execution.json"
    marker = tmp_path / "duplicate-execution"
    args = [
        sys.executable, str(ENTRYPOINT), "--exec-capability",
        "--skills-root", str(skills), "--select", "skill:agent",
        "--sha256", hashlib.sha256(doc.read_bytes()).hexdigest(),
        "--receipt-path", str(receipt_path), "--",
        sys.executable, "-c", "import time;time.sleep(15)",
    ]
    parent = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=ROOT)
    launched = None
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if receipt_path.exists():
                data = json.loads(receipt_path.read_text(encoding="utf-8"))
                if data["status"] == "launched_unverified":
                    launched = data
                    break
            time.sleep(0.025)
        assert launched is not None, "launch identity was not persisted"
        assert launched["pid"] > 0
        assert launched["process_group_id"] == launched["pid"]
        assert len(launched["invocation_id"]) == 32
        assert launched["outcome_verified"] is False
        os.kill(parent.pid, signal.SIGKILL)
        parent.wait(timeout=5)
        preserved = receipt_path.read_bytes()
        retry = invoke(
            "--exec-capability", "--skills-root", skills,
            "--select", "skill:agent",
            "--sha256", hashlib.sha256(doc.read_bytes()).hexdigest(),
            "--receipt-path", receipt_path, "--",
            sys.executable, "-c",
            "import pathlib,sys;pathlib.Path(sys.argv[1]).touch()", marker,
        )
        assert retry.returncode == 2
        assert not marker.exists()
        assert receipt_path.read_bytes() == preserved
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=5)
        if launched is not None:
            try:
                os.killpg(launched["process_group_id"], signal.SIGKILL)
            except ProcessLookupError:
                pass
        parent.stdout.close()
        parent.stderr.close()


def test_command_sees_durable_launched_receipt_before_its_first_instruction(tmp_path):
    """Real consumer child verifies durable launch record exists before exec."""
    skills = tmp_path / "skills"
    doc = skills / "agent" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# Agent\n", encoding="utf-8")
    receipt = tmp_path / "launch.json"
    digest = hashlib.sha256(doc.read_bytes()).hexdigest()
    script = (
        "import json,pathlib,sys;"
        "r=json.loads(pathlib.Path(sys.argv[1]).read_text());"
        "assert r['status']=='launched_unverified',r;"
        "assert r['pid']>0;"
        "print('LAUNCH_COMMITTED_BEFORE_EXEC')"
    )
    result = invoke(
        "--exec-capability", "--skills-root", skills,
        "--select", "skill:agent", "--sha256", digest,
        "--receipt-path", receipt, "--",
        sys.executable, "-c", script, receipt,
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert "LAUNCH_COMMITTED_BEFORE_EXEC" in output["stdout"]
    assert json.loads(receipt.read_text())["status"] == "process_succeeded_unverified"


def test_disk_spool_is_strictly_bounded_for_noisy_child(tmp_path):
    """A real child cannot fill disk beyond the configured per-stream quota."""
    skills = tmp_path / "skills"
    doc = skills / "agent" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# Agent")
    digest = hashlib.sha256(b"# Agent").hexdigest()
    result = invoke(
        "--exec-capability", "--skills-root", skills,
        "--select", "skill:agent", "--sha256", digest,
        "--timeout-seconds", "10", "--",
        sys.executable, "-c",
        "import sys; sys.stdout.buffer.write(b'x' * (12 * 1024 * 1024)); sys.stdout.flush()",
    )
    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    assert response["executed"] is True
    assert response["stdout_bytes"] == 12 * 1024 * 1024
    assert response["stdout_truncated"] is True
    assert len(response["stdout"].encode()) <= 65536
    assert response["spool_limit_bytes_per_stream"] == 8 * 1024 * 1024
    assert response["outcome_verified"] is False


def test_output_quota_does_not_limit_child_work_files(tmp_path):
    skills = tmp_path / "skills"
    doc = skills / "agent" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# Agent")
    digest = hashlib.sha256(b"# Agent").hexdigest()
    artifact = tmp_path / "child-artifact.bin"
    result = invoke(
        "--exec-capability", "--skills-root", skills,
        "--select", "skill:agent", "--sha256", digest, "--",
        sys.executable, "-c",
        "import pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(b'x' * (10 * 1024 * 1024)); print('written')",
        artifact,
    )
    assert result.returncode == 0, result.stderr
    assert artifact.stat().st_size == 10 * 1024 * 1024
    assert json.loads(result.stdout)["stdout"].strip() == "written"


def test_nonreading_child_large_stdin_obeys_timeout(tmp_path):
    """A child ignoring a multi-megabyte capability cannot hang the executor."""
    import time
    skills = tmp_path / "skills"
    doc = skills / "agent" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    content = "# Agent\n" + ("x" * (2 * 1024 * 1024))
    doc.write_text(content)
    digest = hashlib.sha256(content.encode()).hexdigest()
    started = time.monotonic()
    result = invoke(
        "--exec-capability", "--skills-root", skills,
        "--select", "skill:agent", "--sha256", digest,
        "--timeout-seconds", "1", "--",
        sys.executable, "-c", "import time; time.sleep(30)",
    )
    elapsed = time.monotonic() - started
    assert elapsed < 8, (elapsed, result.stderr)
    assert result.returncode != 2, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["timed_out"] is True
    assert receipt["exit_code"] == 124
    assert receipt["outcome_verified"] is False


def test_large_stdin_reaches_reading_child(tmp_path):
    skills = tmp_path / "skills"
    doc = skills / "agent" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    content = "# Agent\n" + ("x" * (1024 * 1024))
    doc.write_text(content)
    digest = hashlib.sha256(content.encode()).hexdigest()
    result = invoke(
        "--exec-capability", "--skills-root", skills,
        "--select", "skill:agent", "--sha256", digest,
        "--timeout-seconds", "10", "--",
        sys.executable, "-c",
        "import sys,hashlib; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())",
    )
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["stdout"].strip() == digest
    assert receipt["exit_code"] == 0


def test_zero_exit_with_silent_live_descendant_fails_closed(tmp_path):
    """A worker cannot claim clean exit while its same-group descendant survives."""
    import os
    import time
    import pytest
    if os.name != "posix":
        pytest.skip("POSIX process groups required")
    skills = tmp_path / "skills"
    doc = skills / "agent" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# Agent")
    digest = hashlib.sha256(doc.read_bytes()).hexdigest()
    pid_file = tmp_path / "descendant.pid"
    script = (
        "import subprocess,sys,pathlib;"
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],"
        "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);"
        "pathlib.Path(sys.argv[1]).write_text(str(p.pid))"
    )
    try:
        result = invoke(
            "--exec-capability", "--skills-root", skills,
            "--select", "skill:agent", "--sha256", digest,
            "--timeout-seconds", "3", "--", sys.executable, "-c", script, pid_file,
        )
        assert result.returncode == 74, result.stderr
        payload = json.loads(result.stdout)
        assert payload["exit_code"] == 74
        assert payload["status"] == "failed"
        assert payload["cleanup_unresolved"] is True
        assert payload["descendant_group_unresolved"] is True
        assert payload["outcome_verified"] is False
    finally:
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text()), 9)
            except ProcessLookupError:
                pass
