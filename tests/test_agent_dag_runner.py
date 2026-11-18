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
    with pytest.raises(ValueError, match="different objective"):
        execute_plan(db, changed)
