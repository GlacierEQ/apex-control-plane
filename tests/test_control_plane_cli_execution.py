"""Executable APEX CLI behavior, not simulated success receipts."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "src" / "control_plane.py"


def test_idle_control_plane_cannot_fabricate_completed_routes() -> None:
    result = subprocess.run(
        [sys.executable, str(CLI)], cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "idle"
    assert payload["routes_run"] == 0
    assert payload["executed"] is False


def test_control_plane_runs_real_local_command_and_reports_actual_exit(tmp_path: Path) -> None:
    target = tmp_path / "executed.txt"
    command = [
        sys.executable,
        "-c",
        "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('actual execution')",
        str(target),
    ]
    result = subprocess.run(
        [sys.executable, str(CLI), "--exec", *command],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert target.read_text() == "actual execution"
    payload = json.loads(result.stdout)
    assert payload["status"] == "completed"
    assert payload["executed"] is True
    assert payload["routes_run"] == 1
    assert payload["exit_code"] == 0


def test_control_plane_propagates_real_process_failure() -> None:
    result = subprocess.run(
        [sys.executable, str(CLI), "--exec", sys.executable, "-c", "raise SystemExit(17)"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 17
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert payload["exit_code"] == 17
    assert payload["executed"] is True
