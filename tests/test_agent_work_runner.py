"""Integration tests for runnable durable agent work units."""
import sys

from src.agent_work_runner import main, run_work_unit


def test_real_subprocess_runs_once_across_restart(tmp_path):
    db = tmp_path / "state.sqlite"
    marker = tmp_path / "marker.txt"
    command = [
        sys.executable, "-c",
        "from pathlib import Path; p=Path(__import__('sys').argv[1]); p.write_text(p.read_text()+'x' if p.exists() else 'x')",
        str(marker),
    ]
    first = run_work_unit(db, "job-1", "write marker", command)
    assert first["state"] == "succeeded"
    assert first["result"]["returncode"] == 0
    assert marker.read_text() == "x"
    second = run_work_unit(db, "job-1", "write marker", command)
    assert second["state"] == "already_claimed:succeeded"
    assert marker.read_text() == "x"


def test_failed_command_never_replays_automatically(tmp_path):
    db = tmp_path / "state.sqlite"
    command = [sys.executable, "-c", "raise SystemExit(9)"]
    first = run_work_unit(db, "job-failed", "failure", command)
    assert first["state"] == "needs_reconciliation"
    assert first["result"]["returncode"] == 9
    second = run_work_unit(db, "job-failed", "failure", command)
    assert second["state"] == "already_claimed:needs_reconciliation"


def test_cli_prints_json_and_executes(tmp_path, capsys):
    code = main([
        "--database", str(tmp_path / "cli.sqlite"),
        "--workload-id", "cli-1", "--objective", "hello",
        "--command", sys.executable, "-c", "print('hello')",
    ])
    assert code == 0
    assert '"state": "succeeded"' in capsys.readouterr().out


def test_same_workload_id_cannot_run_different_command(tmp_path):
    import pytest

    db = tmp_path / "identity.sqlite"
    first = [sys.executable, "-c", "print('first')"]
    second = [sys.executable, "-c", "print('second')"]
    assert run_work_unit(db, "identity-1", "same description", first)["state"] == "succeeded"
    with pytest.raises(ValueError, match="different objective"):
        run_work_unit(db, "identity-1", "same description", second)
