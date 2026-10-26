"""Regression: APEX must not discard completed ingest when a task handoff cannot run."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import spiral_live_journal as bridge


@pytest.mark.parametrize(
    "raw_text,allow_task,expected_owner",
    [
        ("Source: verified continuity record.", True, "NO_ACTION"),
        ("Review the Mem integration test on Friday.", False, "TASK_AUTHORITY_REQUIRED"),
    ],
)
def test_executed_ingest_is_persisted_without_falsely_blocking_or_completing(
    monkeypatch, raw_text, allow_task, expected_owner
):
    capture = {
        "source_provider": "mem",
        "source_id": "a50bb1ed-b7d2-4dc9-85e2-a99428fc4a61",
        "source_version": 1,
        "raw_text": raw_text,
        "observed_at": "2026-10-12T10:25:00-10:00",
        "project": "GlacierEQ/Continuity",
        "sensitivity": "non-sensitive",
        "account_key": "glaciereq",
        "timezone": "Pacific/Honolulu",
    }
    recovery = SimpleNamespace(mission_id="mission-1", source_ref="spiral-journal:verified", cursor="1")

    class Kernel:
        phase = SimpleNamespace(value="bootstrapped")
        execution_refs = []
        blocked = False

        def begin(self):
            self.phase = SimpleNamespace(value="executing")

        def record_execution(self, reference, *, details):
            self.execution_refs.append(reference)

        def block(self, *_args, **_kwargs):
            self.blocked = True

    kernel = Kernel()
    monkeypatch.setattr(bridge, "resume_authenticated_chat_in_apex", lambda *_a, **_k: None)
    stored = {}

    def persist(payload):
        stored["native-continuation-id"] = dict(payload)
        return {"id": "native-continuation-id"}

    def forbidden(*_a, **_k):
        pytest.fail("Task provider must not be called without an applicable authorized task")

    def authorize(_source_id, action):
        return action == "apex.ingest" or (action == "ticktick.task" and allow_task)

    outcome = bridge.execute_recovered_capture_in_apex(
        kernel, recovery, capture,
        authorize=authorize,
        ingest_rpc=lambda *_a: {"ingest": {"ingest_id": "native-ingest-1"}},
        find_tasks=forbidden,
        create_task=forbidden,
        read_task=forbidden,
        persist_result=persist,
        read_persisted_result=lambda ref: dict(stored[ref]),
    )
    assert outcome["status"] == "BOUND_PARTIAL_HANDOFF_PERSISTED"
    assert outcome["ingest_id"] == "native-ingest-1"
    assert outcome["owner_status"] == expected_owner
    assert outcome["mission_complete"] is False
    assert outcome["apex_phase"] == "executing"
    assert stored["native-continuation-id"]["owner_status"] == expected_owner
    assert stored["native-continuation-id"]["mission_complete"] is False
    assert kernel.execution_refs == ["apex-ingest:native-ingest-1"]
    assert kernel.blocked is False
