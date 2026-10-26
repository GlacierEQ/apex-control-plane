"""Regression: actionable Operator verbs must not silently downgrade to references."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mem_capture_action_bridge import build_capture, make_ticktick_task


CAPTURE = {
    "source_provider": "mem",
    "source_id": "operator-action-2026-10-26",
    "source_version": 1,
    "raw_text": "Review the workflow on Friday.",
    "observed_at": "2026-10-12T10:25:00-10:00",
    "project": "GlacierEQ/APEX",
    "sensitivity": "non-sensitive",
    "account_key": "glaciereq",
    "timezone": "Pacific/Honolulu",
}


@pytest.mark.parametrize("verb", [
    "Build", "Fix", "Remove", "Repair", "Execute", "Implement",
    "Integrate", "Deploy", "Ship", "Enforce", "Complete", "Continue",
])
def test_operator_execution_verb_stays_actionable_and_has_a_native_task_plan(verb):
    text = f"{verb} the existing execution handoff on Friday."
    item = build_capture({**CAPTURE, "raw_text": text})
    assert item.raw_text == text
    assert item.categories == ("ACTION", "COMMITMENT", "DEADLINE")
    assert item.title == f"{verb} the existing execution handoff"
    assert item.due_date == "2026-10-16"
    task = make_ticktick_task(item)["task"]
    assert task["title"] == item.title
    assert task["isAllDay"] is True


def test_action_without_due_date_is_still_classified_as_action_not_reference():
    item = build_capture({**CAPTURE, "raw_text": "Remove the artificial blockers."})
    assert item.categories == ("ACTION", "COMMITMENT")
    assert item.title == "Remove the artificial blockers"
    assert item.due_date is None


def test_plain_source_note_remains_reference_without_invented_action():
    item = build_capture({**CAPTURE, "raw_text": "The blocker is recorded in this report."})
    assert item.categories == ("REFERENCE",)
    assert item.title is None


def test_undated_operator_action_executes_provider_handoff_once():
    from mem_capture_action_bridge import execute_authorized_capture
    capture = {**CAPTURE, "raw_text": "Fix the execution handoff."}
    item = build_capture(capture)
    native_task = make_ticktick_task(item)["task"]
    assert "dueDate" not in native_task
    observed = []

    def ingest_rpc(rpc_name, args):
        observed.append("ingest")
        return {"ingest_id": "native-ingest"}

    def find_tasks(key):
        observed.append("find")
        return []

    def create_task(payload):
        observed.append("create")
        assert "dueDate" not in payload
        return {"id": "native-task"}

    def read_task(task_id):
        observed.append("read")
        return {**native_task, "id": task_id}

    result = execute_authorized_capture(
        capture, authorize=lambda *_: True, ingest_rpc=ingest_rpc,
        find_tasks=find_tasks, create_task=create_task, read_task=read_task,
    )
    assert observed == ["ingest", "find", "create", "read"]
    assert result["owner_status"] == "OWNER_NATIVE_READBACK_VERIFIED"
    assert result["task_receipt"]["due_date"] is None
    assert result["mission_complete"] is False


def test_undated_native_task_readback_rejects_invented_deadline():
    from mem_capture_action_bridge import CaptureRoutingError, verify_ticktick_readback
    capture = {**CAPTURE, "raw_text": "Fix the execution handoff."}
    item = build_capture(capture)
    native = {**make_ticktick_task(item)["task"], "id": "native-task"}
    with pytest.raises(CaptureRoutingError, match="unexpected due date"):
        verify_ticktick_readback(item, {
            **native, "dueDate": "2026-10-30T00:00:00-10:00",
        })
