"""A failed gated spawn must release both parent pipe descriptors."""
import hashlib
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(os.name != "posix", reason="POSIX pre-exec gate")
def test_spawn_failure_closes_both_gate_fds(tmp_path, monkeypatch, capsys):
    skill = tmp_path / "skills" / "agent" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# Agent\n" + "Verified execution contract. " * 15)
    digest = hashlib.sha256(skill.read_bytes()).hexdigest()
    receipt = tmp_path / "receipt.json"
    actual_pipe = os.pipe
    gate_fds = []

    def track_pipe():
        pair = actual_pipe()
        gate_fds.extend(pair)
        return pair

    def fail_spawn(*args, **kwargs):
        raise OSError("forced spawn failure")

    monkeypatch.setattr(os, "pipe", track_pipe)
    monkeypatch.setattr(subprocess, "Popen", fail_spawn)
    monkeypatch.syspath_prepend(str(ROOT / "src"))
    monkeypatch.setattr(sys, "argv", [
        str(ROOT / "src" / "control_plane.py"), "--exec-capability",
        "--skills-root", str(skill.parent.parent), "--select", "skill:agent",
        "--sha256", digest, "--receipt-path", str(receipt),
        "--timeout-seconds", "1", "--", sys.executable, "-c", "pass",
    ])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(ROOT / "src" / "control_plane.py"), run_name="__main__")
    assert exc.value.code == 127
    assert len(gate_fds) == 2
    for fd in gate_fds:
        with pytest.raises(OSError):
            os.fstat(fd)
    assert 'forced spawn failure' in capsys.readouterr().out
