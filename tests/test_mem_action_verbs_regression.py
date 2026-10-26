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
