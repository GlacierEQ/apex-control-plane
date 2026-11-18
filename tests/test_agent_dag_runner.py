"""Real subprocess integration and adversarial tests for durable DAG execution."""
import sys

import pytest

from src.agent_dag_runner import execute_plan, validate_plan


def job(identifier, script, *deps):
    return {
        "id": identifier,
        "objective": identifier,
        "command": [sys.executable, "-c", script],
        "depends_on": list(deps),
    }


def test_dag_executes_in_dependency_order_and_resumes_without_replay(tmp_path):
    marker = tmp_path / "order.txt"
    a = job("a", f"from pathlib import Path; Path({str(marker)!r}).write_text('a')")
    b = job("b", f"from pathlib import Path; p=Path({str(marker)!r}); p.write_text(p.read_text()+'b')", "a")
    plan = {"id": "dag-resume", "jobs": [b, a]}
    database = tmp_path / "claims.sqlite"
    first = execute_plan(database, plan)
    assert first["ok"] is True
    assert marker.read_text() == "ab"
    second = execute_plan(database, plan)
    assert second["ok"] is True
    assert marker.read_text() == "ab"
    assert second["jobs"]["a"]["invocation"] == "already_claimed:succeeded"
    assert second["jobs"]["b"]["invocation"] == "already_claimed:succeeded"


def test_failed_parent_blocks_dependent_side_effect(tmp_path):
    marker = tmp_path / "forbidden.txt"
    plan = {
        "id": "dag-block",
        "jobs": [
            job("parent", "raise SystemExit(3)"),
            job("child", f"from pathlib import Path; Path({str(marker)!r}).write_text('bad')", "parent"),
        ],
    }
    result = execute_plan(tmp_path / "claims.sqlite", plan)
    assert result["ok"] is False
    assert result["jobs"]["parent"]["state"] == "needs_reconciliation"
    assert result["jobs"]["child"]["state"] == "blocked_dependency"
    assert not marker.exists()


@pytest.mark.parametrize("jobs", [
    [job("a", "pass", "missing")],
    [job("a", "pass", "b"), job("b", "pass", "a")],
    [job("a", "pass"), job("a", "pass")],
])
def test_invalid_graph_rejected_before_side_effects(jobs, tmp_path):
    with pytest.raises(ValueError):
        execute_plan(tmp_path / "claims.sqlite", {"id": "bad", "jobs": jobs})


def test_changed_command_under_same_plan_id_rejected(tmp_path):
    db = tmp_path / "claims.sqlite"
    first = {"id": "same-plan", "jobs": [job("a", "print('original')")]}
    assert execute_plan(db, first)["ok"]
    changed = {"id": "same-plan", "jobs": [job("a", "print('replacement')")]}
    with pytest.raises(ValueError, match="different graph"):
        execute_plan(db, changed)


def test_changed_dependency_graph_rejected_before_new_side_effect(tmp_path):
    marker = tmp_path / "marker.txt"
    db = tmp_path / "claims.sqlite"
    original = {
        "id": "manifest-guard",
        "jobs": [job("a", f"from pathlib import Path; Path({str(marker)!r}).write_text('a')")],
    }
    assert execute_plan(db, original)["ok"]
    changed = {
        "id": "manifest-guard",
        "jobs": [
            original["jobs"][0],
            job("b", f"from pathlib import Path; Path({str(marker)!r}).write_text('BAD')", "a"),
        ],
    }
    with pytest.raises(ValueError, match="different graph"):
        execute_plan(db, changed)
    assert marker.read_text() == "a"


def test_changed_dependency_edge_rejected_even_if_commands_unchanged(tmp_path):
    db = tmp_path / "claims.sqlite"
    original = {"id": "edges", "jobs": [job("a", "pass"), job("b", "pass")]}
    assert execute_plan(db, original)["ok"]
    changed = {"id": "edges", "jobs": [job("a", "pass"), job("b", "pass", "a")]}
    with pytest.raises(ValueError, match="different graph"):
        execute_plan(db, changed)


def test_reordered_equivalent_plan_can_resume(tmp_path):
    db = tmp_path / "claims.sqlite"
    a = job("a", "pass")
    b = job("b", "pass", "a")
    assert execute_plan(db, {"id": "order", "jobs": [a, b]})["ok"]
    again = execute_plan(db, {"id": "order", "jobs": [b, a]})
    assert again["ok"]
    assert again["jobs"]["a"]["invocation"] == "already_claimed:succeeded"


@pytest.mark.parametrize("invalid_timeout", [0, -1, True, 1.5, "30"])
def test_invalid_timeout_rejected_before_execution(tmp_path, invalid_timeout):
    marker = tmp_path / "must-not-exist.txt"
    item = job("a", f"from pathlib import Path; Path({str(marker)!r}).write_text('bad')")
    item["timeout_seconds"] = invalid_timeout
    with pytest.raises(ValueError, match="timeout_seconds"):
        execute_plan(tmp_path / "claims.sqlite", {"id": "timeout-invalid", "jobs": [item]})
    assert not marker.exists()


def test_reserved_manifest_identifier_rejected_before_execution(tmp_path):
    item = job("__plan_manifest__", "pass")
    with pytest.raises(ValueError, match="job ids"):
        execute_plan(tmp_path / "claims.sqlite", {"id": "reserved", "jobs": [item]})


@pytest.mark.parametrize("plan_id,job_id", [
    ("alpha:beta", "job"),
    ("alpha", "beta:job"),
    ("alpha", "job:__plan_manifest__"),
])
def test_ambiguous_claim_keys_rejected_before_storage_or_dispatch(tmp_path, plan_id, job_id):
    database = tmp_path / "claims.sqlite"
    marker = tmp_path / "side_effect.txt"
    plan = {"id": plan_id, "jobs": [job(job_id, f"from pathlib import Path; Path({str(marker)!r}).write_text('BAD')")]}
    with pytest.raises(ValueError):
        execute_plan(database, plan)
    assert not database.exists()
    assert not marker.exists()


@pytest.mark.parametrize("command", [[""], ["bad\\x00binary"], [sys.executable, "bad\\x00argument"]])
def test_dag_rejects_invalid_os_argv_before_manifest_or_dispatch(tmp_path, command):
    db = tmp_path / "invalid-argv.sqlite"
    plan = {"id": "bad-argv-plan", "jobs": [{"id": "job", "objective": "reject", "command": command}]}
    with pytest.raises(ValueError, match="command"):
        execute_plan(db, plan)
    assert not db.exists()
