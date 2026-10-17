"""Cross-session continuity contract tests for the existing APEX router.

These tests deliberately use two distinct host session IDs and a shared durable
fake. They do NOT claim to test ChatGPT host startup or provider persistence.
"""
import unittest
from types import SimpleNamespace

from src.connector_mission_router import ConnectorCapability, dispatch_recovered_once
from src.context_recovery import ContextApplication


class Journal:
    mission_id = "mission-A"
    objective = "Preserve full mission objective"
    terminal_outcome = "PROVIDER_READBACK_VERIFIED"
    cursor = "cursor-1"
    corrections = ("never reduce mission scope",)
    events = (
        {"kind": "mission", "data": {"mission_id": "mission-A"}, "sha256": "a" * 64},
        {"kind": "checkpoint", "data": {"cursor": "cursor-1"}, "sha256": "b" * 64},
    )

    def fact(self, key):
        return {"source": "provider:record", "value": self.cursor} if key == "frontier" else None


class Kernel:
    def __init__(self):
        self.phase = SimpleNamespace(value="context_recovering")
        self.receipts = []

    def record_context_recovery(self, reference, *, recovered_refs, details):
        self.receipts.append(details)
        self.phase.value = "ready"


class CrossSessionContract(unittest.TestCase):
    def test_new_session_reuses_correct_cursor_and_corrections_without_duplicate_effect(self):
        durable_reservations = set()
        durable_checkpoints = {}
        effects = []
        kernels = []

        def reserve(key):
            if key in durable_reservations:
                return False
            durable_reservations.add(key)
            return True

        def apply(recovery):
            self.assertEqual(recovery.cursor, "cursor-1")
            self.assertEqual(recovery.corrections, ("never reduce mission scope",))
            return ContextApplication(
                recovery.mission_id, recovery.source_ref, recovery.cursor,
                recovery.corrections, tuple(recovery.facts),
                "host-application:source-matched",
            )

        def persist(record):
            durable_checkpoints[record.operation_key] = record
            return record.operation_key

        def verify(key):
            return key in durable_checkpoints

        def invoke(session):
            kernel = Kernel()
            kernels.append(kernel)
            return dispatch_recovered_once(
                journal=Journal(), chat_session_id=session, kernel=kernel,
                expected_mission_id="mission-A",
                capability=ConnectorCapability("box", "upload", True, True, True),
                operation_id="operation-1", reserve=reserve,
                execute=lambda: effects.append("sent") or {"native_id": "id-1"},
                readback=lambda result: result["native_id"] == "id-1",
                persist_continuation=persist,
                verify_continuation=verify,
                fact_keys=("frontier",), apply_context=apply,
            )

        self.assertEqual(invoke("chat-1")["native_id"], "id-1")
        with self.assertRaisesRegex(ValueError, "already reserved"):
            invoke("chat-2")
        self.assertEqual(effects, ["sent"])
        self.assertEqual(len(durable_checkpoints), 1)
        self.assertEqual(len(kernels), 2)
        self.assertTrue(all(k.receipts for k in kernels))


if __name__ == "__main__":
    unittest.main()
