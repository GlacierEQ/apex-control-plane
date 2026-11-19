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
