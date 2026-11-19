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
    assert result.returncode == 124, result.stderr
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
