"""Provider response shape cannot be promoted to a verified external effect."""
import pytest

from src.mission_resume import MissionCheckpointStore, ResumeError


def _plan():
    return {
        "mission_id": "agent-native-proof-20261114",
        "operator_objective": "Continue authorized work without fabricated completion",
        "desired_outcome": "Only actual provider receipt references unlock dependencies",
        "tasks": [
            {"id": "suspicious", "order": 1, "deps": [], "key": "native:suspicious",
             "provider": "source", "expected": "sourced result"},
            {"id": "independent", "order": 2, "deps": [], "key": "native:independent",
             "provider": "source", "expected": "independent result"},
            {"id": "dependent", "order": 3, "deps": ["suspicious"],
             "key": "native:dependent", "provider": "source", "expected": "dependent result"},
        ],
    }


@pytest.mark.parametrize("bogus", [True, {"receipt": "claimed"}, ["claimed"], "   ", ""])
def test_invalid_provider_result_never_verifies_or_unlocks_dependency(tmp_path, bogus):
    store = MissionCheckpointStore(tmp_path / "state.db")
    store.initialize(**_plan())

    def readback(key, expected):
        return bogus if key == "native:suspicious" else None

    # Invalid or non-native readback is route-local; independent work proceeds.
    task = store.resume("worker", readback)
    assert task is not None and task["task_id"] == "independent"
    assert store.task_state("suspicious") == "READY"
    assert store.task_state("dependent") == "READY"
    assert store.task_receipt("suspicious") is None


@pytest.mark.parametrize("bogus", [True, {"receipt": "claimed"}, "  "])
def test_invalid_provider_result_cannot_finish_inflight_task(tmp_path, bogus):
    store = MissionCheckpointStore(tmp_path / "state.db")
    store.initialize(**_plan())
    task = store.resume("worker", lambda key, expected: None)
    assert task["task_id"] == "suspicious"

    assert store.resume(
        "replacement-worker",
        lambda key, expected: bogus if key == "native:suspicious" else None,
    )["task_id"] == "independent"
    assert store.task_state("suspicious") == "NEEDS_PROOF"
    assert store.task_receipt("suspicious") is None


def test_rearm_rejects_forged_truthy_receipt_and_keeps_original_claim(tmp_path):
    store = MissionCheckpointStore(tmp_path / "state.db")
    store.initialize(**_plan())
    assert store.resume("first", lambda key, expected: None)["task_id"] == "suspicious"
    assert store.resume("second", lambda key, expected: None)["task_id"] == "independent"
    assert store.task_state("suspicious") == "NEEDS_PROOF"

    with pytest.raises(ResumeError, match="readback"):
        store.rearm_after_provider_guarantee(
            "suspicious",
            provider_idempotency_ref="provider-native:source:key-enforced",
            readback=lambda key, expected: {"receipt": "model-claimed-only"},
            idempotency_verifier=lambda provider, key, ref: {
                "provider": provider,
                "idempotency_key": key,
                "reference": ref,
                "native_enforced": True,
                "evidence": "provider contract enforces unique key",
            },
        )
    assert store.task_state("suspicious") == "NEEDS_PROOF"
    assert store.task_receipt("suspicious") is None


def test_genuine_native_string_receipt_still_recovers_dependency(tmp_path):
    store = MissionCheckpointStore(tmp_path / "state.db")
    store.initialize(**_plan())
    assert store.resume(
        "worker", lambda key, expected: "native:source:123" if key == "native:suspicious" else None,
    )["task_id"] == "independent"
    assert store.task_state("suspicious") == "VERIFIED_STEP"
    assert store.task_receipt("suspicious") == "native:source:123"
    assert store.resume(
        "next", lambda key, expected: "native:source:456" if key == "native:independent" else None,
    )["task_id"] == "dependent"
