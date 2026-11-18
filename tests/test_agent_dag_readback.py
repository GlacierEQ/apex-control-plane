"""Read-only DAG recovery must never execute an unstarted work unit."""
import json
import sys

import pytest

from src.agent_dag_runner import execute_plan, inspect_plan, main


def plan(marker):
    return {
        "id": "inspect-1",
        "jobs": [
            {"id": "first", "objective": "write marker",
             "command": [sys.executable, "-c",
                         "from pathlib import Path; Path(__import__('sys').argv[1]).write_text('done')",
                         str(marker)]},
            {"id": "second", "objective": "dependent",
             "command": [sys.executable, "-c", "print('dependent')"],
             "depends_on": ["first"]},
        ],
    }


def test_readback_does_not_dispatch_before_or_after_execution(tmp_path):
    db = tmp_path / "state.sqlite"
    marker = tmp_path / "marker"
    p = plan(marker)
    before = inspect_plan(db, p)
    assert before["manifest_recorded"] is False
    assert before["jobs"]["first"]["state"] == "not_started"
    assert before["jobs"]["second"]["state"] == "blocked_dependency"
    assert not marker.exists()
    result = execute_plan(db, p)
    assert result["ok"]
    assert marker.read_text() == "done"
    after = inspect_plan(db, p)
    assert after["ok"]
    assert after["jobs"]["second"]["state"] == "succeeded"
    marker.unlink()
    assert inspect_plan(db, p)["ok"]
    assert not marker.exists()


def test_readback_rejects_changed_plan_identity(tmp_path):
    db = tmp_path / "state.sqlite"
    marker = tmp_path / "marker"
    p = plan(marker)
    execute_plan(db, p)
    changed = plan(marker)
    changed["jobs"][0]["command"] = [sys.executable, "-c", "print('substituted')"]
    with pytest.raises(ValueError, match="different graph"):
        inspect_plan(db, changed)


def test_cli_readback_never_runs_job(tmp_path, capsys):
    db = tmp_path / "state.sqlite"
    marker = tmp_path / "marker"
    file = tmp_path / "plan.json"
    file.write_text(json.dumps(plan(marker)))
    assert main(["--database", str(db), "--plan", str(file), "--readback"]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["jobs"]["first"]["state"] == "not_started"
    assert not marker.exists()


def test_readback_does_not_create_database_or_schema(tmp_path):
    db = tmp_path / "missing.sqlite"
    p = plan(tmp_path / "marker")
    assert inspect_plan(db, p)["manifest_recorded"] is False
    assert not db.exists()

    import sqlite3
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE unrelated (id INTEGER)")
    assert inspect_plan(db, p)["jobs"]["first"]["state"] == "not_started"
    with sqlite3.connect(db) as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE name='execution_claims'"
        ).fetchone() is None


def test_readback_on_readonly_database(tmp_path):
    db = tmp_path / "readonly.sqlite"
    marker = tmp_path / "marker"
    p = plan(marker)
    assert execute_plan(db, p)["ok"]
    db.chmod(0o444)
    assert inspect_plan(db, p)["ok"]
