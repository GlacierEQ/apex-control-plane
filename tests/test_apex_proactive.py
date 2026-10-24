"""Tests for the proactive engine. Every number here comes from a run."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from apex_proactive import (
    Breadcrumb,
    GraderIdentityError,
    SkillRegistry,
    StateReceipt,
    Trigger,
    WorkItem,
    gate_json,
    grade,
    render_value,
    run_phases,
    run_until_verified,
    snapshot_files,
    state_receipt,
    changed_test_files,
    top_k_tools,
)


def test_trigger_runs_and_only_named_surfaces_escalate():
    assert Trigger("x", "r").escalates() is False
    for surface in ("judgment", "offer_acceptance", "operator_fact", "tier2_log"):
        assert Trigger("x", "r", surface).escalates() is True


def test_verify_or_reroute_runs_until_verified_and_never_invents():
    result = run_until_verified([
        ("route-a", lambda: (_ for _ in ()).throw(RuntimeError("down"))),
        ("route-b", lambda: None),
        ("route-c", lambda: "verified-value"),
    ])
    assert result.verified is True
    assert result.value == "verified-value"
    assert result.attempts == ("route-a", "route-b", "route-c")
    failed = run_until_verified([("only", lambda: None)])
    assert failed.verified is False
    assert failed.value is None


def test_state_receipt_is_a_diff_not_a_narrative():
    receipt = state_receipt({"done": 3, "open": 5}, {"done": 4, "open": 4}, "run-1")
    assert isinstance(receipt, StateReceipt)
    assert receipt.diff == {"done": 1, "open": -1}
    assert receipt.to_dict()["diff"] == {"done": 1, "open": -1}


def test_worker_cannot_grade_own_work_and_verdicts_flip_state():
    work = WorkItem("w-1", "worker-1")
    with pytest.raises(GraderIdentityError):
        grade(work, grader_id="worker-1", verdict="PASS")
    assert work.state == "open"
    grade(work, grader_id="grader-9", verdict="PASS")
    assert work.state == "done"
    work2 = WorkItem("w-2", "worker-1")
    grade(work2, grader_id="grader-9", verdict="BLOCK")
    assert work2.state == "blocked"
    work3 = WorkItem("w-3", "worker-1")
    grade(work3, grader_id="grader-9", verdict="HOLD")
    assert work3.state == "held"
    with pytest.raises(ValueError):
        grade(WorkItem("w-4", "worker-1"), grader_id="grader-9", verdict="MAYBE")


def test_missing_evidence_renders_empty_never_zero():
    assert render_value(None) == ""
    assert render_value(0) == "0"
    assert render_value(42.50) == "42.5"


def test_structured_phases_pass_dicts_and_prose_fails_loudly():
    def extract(state):
        return {**state, "records": [{"v": 10}, {"v": 20}]}

    def total(state):
        return {**state, "total": sum(r["v"] for r in state["records"])}

    out = run_phases([extract, total], {})
    assert out["total"] == 30

    def prose_phase(state):
        return "total is 30"

    with pytest.raises(TypeError):
        run_phases([extract, prose_phase], {})


def test_breadcrumb_round_trips_all_fields():
    crumb = Breadcrumb(
        task="overhaul", last_step="tests", next_step="push",
        decisions=("ACP only", "GlacierEQ only"), open_question="",
        blocked_by="", artifact="sha",
    )
    restored = Breadcrumb.from_markdown(crumb.to_markdown())
    assert restored == crumb
    assert restored.next_step == "push"


def test_top_k_loads_k_not_all():
    tools = [
        {"name": f"tool-{i}", "description": f"does thing {i} with records"}
        for i in range(48)
    ]
    tools[7] = {"name": "find-definition", "description": "find where a function is defined"}
    top = top_k_tools(tools, "find where this function is defined", k=3)
    assert len(top) == 3
    assert top[0]["name"] == "find-definition"


def test_forced_invocation_beats_generic_reminder():
    registry = SkillRegistry()
    registry.register("debugging", "structured debugging workflow")
    assert registry.generic_reminder() is None
    assert registry.invoke("debugging") == "structured debugging workflow"
    assert registry.invoke("missing") is None


def test_test_gate_fails_on_changed_test_bytes_even_when_green(tmp_path):
    test_file = tmp_path / "test_x.py"
    test_file.write_text("assert 1 == 1\n")
    before = snapshot_files([test_file])
    test_file.write_text("assert 1 == 1  # weakened\n")
    after = snapshot_files([test_file])
    changed = changed_test_files(before, after)
    assert changed == [str(test_file)]
    assert '"gate": "fail"' in gate_json(changed)
    assert '"gate": "pass"' in gate_json(changed_test_files(before, before))
