"""Contracts for Mem -> existing APEX intake -> native task owner.

The adapter is intentionally pure: these tests never perform external writes.
The live provider readback is separately recorded in Mem by native IDs.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mem_capture_action_bridge import (
    CaptureRoutingError, build_capture, make_ingest_rpc,
    make_ticktick_task, verify_ticktick_readback,
)

CAPTURE = {
    "source_provider": "mem",
    "source_id": "3a0d2c6d-b452-52fa-8fd2-e70f6123d76f",
    "source_version": 2,
    "raw_text": "Review the Mem integration test on Friday.",
    "observed_at": "2026-10-12T10:25:00-10:00",
    "project": "GlacierEQ/Memory Federation Control Plane",
    "sensitivity": "non-sensitive",
    "account_key": "glaciereq",
    "timezone": "Pacific/Honolulu",
}


def test_capture_classifies_action_and_preserves_source_without_inventing_time():
    item = build_capture(CAPTURE)
    assert set(item.categories) == {"ACTION", "COMMITMENT", "DEADLINE"}
    assert item.title == "Review the Mem integration test"
    assert item.due_date == "2026-10-16"
    assert item.due_precision == "day"
    assert item.raw_text == CAPTURE["raw_text"]
    assert item.source_id == CAPTURE["source_id"]
    assert item.source_version == 2
    assert len(item.raw_sha256) == 64


def test_mem_version_increment_does_not_duplicate_semantically_same_action():
    original = build_capture({**CAPTURE, "source_version": 1})
    revised = build_capture({**CAPTURE, "source_version": 2})
    assert original.idempotency_key == revised.idempotency_key


def test_changed_action_generates_distinct_action_identity():
    original = build_capture(CAPTURE)
    updated = build_capture({**CAPTURE, "raw_text": "Check the Mem integration test on Friday."})
    assert original.idempotency_key != updated.idempotency_key


def test_duplicate_source_has_stable_idempotency_key():
    assert build_capture(CAPTURE).idempotency_key == build_capture(dict(CAPTURE)).idempotency_key


def test_absent_deadline_is_recorded_but_not_sent_to_task_provider():
    item = build_capture({**CAPTURE, "raw_text": "Review the Mem integration test."})
    assert item.due_date is None
    with pytest.raises(CaptureRoutingError, match="date-only deadline required"):
        make_ticktick_task(item)


def test_next_friday_is_not_silently_interpreted():
    item = build_capture({**CAPTURE, "raw_text": "Review the Mem integration test next Friday."})
    assert item.due_date is None
    with pytest.raises(CaptureRoutingError, match="date-only deadline required"):
        make_ticktick_task(item)


def test_ingest_uses_existing_apex_rpc_without_fabricated_execution():
    item = build_capture(CAPTURE)
    plan = make_ingest_rpc(item)
    assert plan["rpc"] == "continuity_ingest_and_resolve_v1"
    assert plan["external_action_authorized"] is False
    assert plan["rpc_executed"] is False
    args = plan["args"]
    assert args["p_source_system"] == "mem"
    assert args["p_external_id"] == CAPTURE["source_id"] + ":v2"
    assert args["p_payload"]["source_id"] == CAPTURE["source_id"]
    assert args["p_payload"]["raw_text"] == CAPTURE["raw_text"]
    assert args["p_payload"]["due_precision"] == "day"
    assert args["p_payload"]["idempotency_key"] == item.idempotency_key
    assert args["p_external_ids"] == []


def test_apex_upsert_preserves_mem_revisions_without_duplicating_task_identity():
    a = make_ingest_rpc(build_capture({**CAPTURE, "source_version": 1}))
    b = make_ingest_rpc(build_capture({**CAPTURE, "source_version": 2}))
    assert a["args"]["p_external_id"] != b["args"]["p_external_id"]
    assert a["args"]["p_payload"]["idempotency_key"] == b["args"]["p_payload"]["idempotency_key"]


def test_ticktick_all_day_date_does_not_invent_clock_or_reminder():
    item = build_capture(CAPTURE)
    plan = make_ticktick_task(item)
    assert plan["owner"] == "ticktick"
    assert plan["authorization_required"] is True
    assert plan["external_action_executed"] is False
    assert plan["ambiguous_timeout"] == "RECONCILE_PROVIDER_NEVER_BLIND_RETRY"
    task = plan["task"]
    assert task["dueDate"] == "2026-10-16T00:00:00-10:00"
    assert task["isAllDay"] is True
    assert "reminders" not in task
    assert item.source_id in task["content"]
    assert item.idempotency_key in task["content"]


def test_restricted_or_unknown_material_cannot_leave_in_portable_projections():
    for sensitivity in ("restricted", "unclassified", "sealed"):
        item = build_capture({**CAPTURE, "sensitivity": sensitivity})
        with pytest.raises(CaptureRoutingError, match="restricted or unclassified"):
            make_ingest_rpc(item)
        with pytest.raises(CaptureRoutingError, match="restricted or unclassified"):
            make_ticktick_task(item)


def test_native_readback_requires_exact_source_and_active_state():
    item = build_capture(CAPTURE)
    task = make_ticktick_task(item)["task"]
    response = {
        **task, "id": "6acd437d8f086d8c22d09b15",
        "projectId": "inbox125380011", "status": 0, "etag": "znxl3lty",
        "dueDate": "2026-10-16T00:00:00-1000",
    }
    proof = verify_ticktick_readback(item, response)
    assert proof["provider_ref"] == response["id"]
    assert proof["idempotency_key"] == item.idempotency_key
    assert proof["status"] == "OWNER_NATIVE_READBACK_VERIFIED"
    assert proof["mission_complete"] is False


def test_conflicting_or_stale_readback_cannot_prove_current_state():
    item = build_capture(CAPTURE)
    expected = make_ticktick_task(item)["task"]
    provider = {**expected, "id": "task1", "status": 0}
    for changed in (
        {"content": "unrelated task"},
        {"dueDate": "2026-10-17T00:00:00-10:00"},
        {"isAllDay": False},
        {"timeZone": "UTC"},
        {"status": 2},
        {"id": ""},
    ):
        with pytest.raises(CaptureRoutingError):
            verify_ticktick_readback(item, {**provider, **changed})


def test_bad_source_metadata_is_never_assumed_to_be_authoritative():
    for variant in (
        {"source_version": -1}, {"source_version": 0},
        {"observed_at": "2026-10-12T10:25:00"},
        {"timezone": "Invalid/Zone"},
        {"source_provider": "unknown"},
    ):
        with pytest.raises(CaptureRoutingError):
            build_capture({**CAPTURE, **variant})
