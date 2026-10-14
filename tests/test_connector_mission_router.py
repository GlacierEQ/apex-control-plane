"""Mission routing regression, including actual Spiral->APEX context admission."""
import unittest
from types import SimpleNamespace

from src.connector_mission_router import (
    AdmissionDenied, ConnectorCapability, MissionAdmission, admit,
    dispatch_once, dispatch_recovered_once,
)
from src.chat_context_admission import ContextAdmissionDenied, ContextApplication


class ConnectorMissionRouterTests(unittest.TestCase):
    def setUp(self):
        self.mission = MissionAdmission("case-A", "case-A", True, "cursor-7", ("fix-1",))
        self.capability = ConnectorCapability("box", "upload", True, True, True)

    def test_valid_admission(self):
        admit(self.mission, self.capability)

    def test_wrong_mission_denied(self):
        with self.assertRaisesRegex(AdmissionDenied, "different mission"):
            admit(MissionAdmission("case-A", "case-B", True, "cursor-7", ()), self.capability)

    def test_discovered_does_not_mean_authenticated(self):
        with self.assertRaisesRegex(AdmissionDenied, "authentication"):
            admit(self.mission, ConnectorCapability("box", "upload", True, False, True))

    def test_unapplied_context_denied(self):
        with self.assertRaisesRegex(AdmissionDenied, "not been applied"):
            admit(MissionAdmission("case-A", "case-A", False, "cursor-7", ()), self.capability)

    def test_duplicate_reservation_blocks_second_effect(self):
        reserved = set()
        effects = []
        def reserve(key):
            if key in reserved:
                return False
            reserved.add(key)
            return True
        def execute():
            effects.append("sent")
            return "receipt-1"
        self.assertEqual(dispatch_once(self.mission, self.capability, "op-1", reserve, execute, lambda r: r == "receipt-1", persist_continuation=lambda record: record.operation_key, verify_continuation=lambda checkpoint: checkpoint in reserved), "receipt-1")
        with self.assertRaisesRegex(AdmissionDenied, "already reserved"):
            dispatch_once(self.mission, self.capability, "op-1", reserve, execute, lambda _: True, persist_continuation=lambda record: record.operation_key, verify_continuation=lambda _: True)
        self.assertEqual(effects, ["sent"])

    def test_failed_readback_keeps_reservation(self):
        keys = set()
        def reserve(key):
            if key in keys:
                return False
            keys.add(key)
            return True
        with self.assertRaisesRegex(AdmissionDenied, "not independently verified"):
            dispatch_once(self.mission, self.capability, "op-2", reserve, lambda: "unverified", lambda _: False, persist_continuation=lambda record: record.operation_key, verify_continuation=lambda _: True)
        with self.assertRaisesRegex(AdmissionDenied, "already reserved"):
            dispatch_once(self.mission, self.capability, "op-2", reserve, lambda: "retry", lambda _: True, persist_continuation=lambda record: record.operation_key, verify_continuation=lambda _: True)

    def test_fake_truthy_capability_rejected(self):
        with self.assertRaisesRegex(AdmissionDenied, "authentication"):
            admit(self.mission, ConnectorCapability("box", "upload", True, "yes", True))

    def test_fake_truthy_application_rejected(self):
        with self.assertRaisesRegex(AdmissionDenied, "not been applied"):
            admit(MissionAdmission("case-A", "case-A", 1, "cursor-7", ()), self.capability)

    def test_ambiguous_operation_identity_rejected_before_reservation(self):
        reserved = []
        with self.assertRaisesRegex(AdmissionDenied, "ambiguous"):
            dispatch_once(self.mission, self.capability, "op:one", lambda k: reserved.append(k), lambda: None, lambda _: True)
        self.assertEqual(reserved, [])

    def test_truthy_nonboolean_provider_readback_is_not_verified(self):
        keys = []
        with self.assertRaisesRegex(AdmissionDenied, "not independently verified"):
            dispatch_once(self.mission, self.capability, "op-3", lambda k: keys.append(k) or True, lambda: "receipt", lambda _: "yes", persist_continuation=lambda record: record.operation_key, verify_continuation=lambda _: True)
        self.assertEqual(len(keys), 1)


    def test_unpersisted_success_must_be_rejected_before_effect(self):
        """A provider readback alone cannot promote a mission to continued."""
        reservations = []
        actions = []
        with self.assertRaisesRegex(AdmissionDenied, "continuation"):
            dispatch_once(
                self.mission, self.capability, "unrecorded-1",
                lambda key: reservations.append(key) or True,
                lambda: actions.append("provider-effect") or "native-42",
                lambda _: True,
            )
        self.assertEqual(reservations, [])
        self.assertEqual(actions, [])

    def test_persistence_receipt_and_independent_readback_are_required(self):
        """Durable continuation must be source-bound and checked before success."""
        saved = {}
        executions = []
        def reserve(key):
            if key in saved:
                return False
            saved[key] = {"reserved": True}
            return True
        def preserve(record):
            self.assertEqual(record.mission_id, "case-A")
            self.assertEqual(record.cursor, "cursor-7")
            self.assertEqual(record.provider, "box")
            self.assertEqual(record.native_result, {"native_id": "provider-42"})
            checkpoint = {"key": record.operation_key, "next_cursor": "cursor-8"}
            saved[record.operation_key]["checkpoint"] = checkpoint
            return checkpoint
        def verify(checkpoint):
            return saved[checkpoint["key"]]["checkpoint"] == checkpoint
        result = dispatch_once(
            self.mission, self.capability, "recorded-1", reserve,
            lambda: executions.append("sent") or {"native_id":"provider-42"},
            lambda result: result["native_id"] == "provider-42",
            persist_continuation=preserve,
            verify_continuation=verify,
        )
        self.assertEqual(result, {"native_id": "provider-42"})
        self.assertEqual(executions, ["sent"])
        self.assertEqual(len(saved), 1)

    def test_failed_checkpoint_readback_keeps_reservation_and_blocks_replay(self):
        keys = set()
        effect = []
        def reserve(key):
            if key in keys:
                return False
            keys.add(key)
            return True
        args = (self.mission, self.capability, "unknown-checkpoint", reserve,
                lambda: effect.append("sent") or {"native_id":"provider-42"},
                lambda _: True)
        with self.assertRaisesRegex(AdmissionDenied, "continuation"):
            dispatch_once(
                *args, persist_continuation=lambda record: {"key": record.operation_key},
                verify_continuation=lambda _: False,
            )
        with self.assertRaisesRegex(AdmissionDenied, "already reserved"):
            dispatch_once(
                *args, persist_continuation=lambda record: {"key": record.operation_key},
                verify_continuation=lambda _: True,
            )
        self.assertEqual(effect, ["sent"])


class ExistingJournal:
    mission_id = "case-A"
    objective = "Advance an existing private mission"
    terminal_outcome = "PROVIDER_READBACK_VERIFIED"
    cursor = "cursor-7"
    corrections = ("preserve the complete mission scope",)
    events = (
        {"kind": "mission", "data": {"mission_id": "case-A"}, "sha256": "a" * 64},
        {"kind": "checkpoint", "data": {"cursor": "cursor-7"}, "sha256": "b" * 64},
    )
    def fact(self, key):
        return {"source": "provider:record", "value": "cursor-7"} if key == "frontier" else None


class RecordingKernel:
    def __init__(self):
        self.phase = SimpleNamespace(value="context_recovering")
        self.receipts = []
    def record_context_recovery(self, reference, *, recovered_refs, details):
        self.receipts.append((reference, recovered_refs, details))
        self.phase.value = "ready"


class IntegratedConnectorTests(unittest.TestCase):
    def setUp(self):
        self.capability = ConnectorCapability("box", "upload", True, True, True)
        self.keys = set()
        self.effects = []
        self.continuations = {}

    def persist(self, record):
        checkpoint = {"key": record.operation_key, "mission": record.mission_id,
                      "source": record.source_ref, "cursor": record.cursor,
                      "corrections": record.correction_ids}
        self.continuations[record.operation_key] = checkpoint
        return checkpoint

    def verify_persisted(self, checkpoint):
        return self.continuations.get(checkpoint["key"]) == checkpoint

    def reserve(self, key):
        if key in self.keys:
            return False
        self.keys.add(key)
        return True

    @staticmethod
    def apply_context(recovery):
        return ContextApplication(
            recovery.mission_id, recovery.source_ref, recovery.cursor,
            recovery.corrections, tuple(recovery.facts),
            "host-application:source-matched",
        )

    def invoke(self, *, expected="case-A", application=None, kernel=None):
        return dispatch_recovered_once(
            journal=ExistingJournal(),
            chat_session_id="session-1",
            kernel=kernel or RecordingKernel(),
            expected_mission_id=expected,
            capability=self.capability,
            operation_id="native-operation-1",
            reserve=self.reserve,
            execute=lambda: self.effects.append("native-effect") or {"native_id": "provider-10"},
            readback=lambda result: result.get("native_id") == "provider-10",
            persist_continuation=self.persist,
            verify_continuation=self.verify_persisted,
            fact_keys=("frontier",),
            apply_context=application,
        )

    def test_integrated_application_dispatch_and_replay_denial(self):
        self.assertEqual(self.invoke(application=self.apply_context)["native_id"], "provider-10")
        with self.assertRaisesRegex(AdmissionDenied, "already reserved"):
            self.invoke(application=self.apply_context)
        self.assertEqual(self.effects, ["native-effect"])

    def test_missing_application_cannot_reserve_or_execute(self):
        with self.assertRaisesRegex(ContextAdmissionDenied, "requires host application"):
            self.invoke()
        self.assertEqual(self.keys, set())
        self.assertEqual(self.effects, [])

    def test_wrong_mission_does_not_even_call_application(self):
        attempted = []
        def application(recovery):
            attempted.append(True)
            return self.apply_context(recovery)
        with self.assertRaisesRegex(ContextAdmissionDenied, "not the requested mission"):
            self.invoke(expected="different-mission", application=application)
        self.assertEqual(attempted, [])
        self.assertEqual(self.keys, set())
        self.assertEqual(self.effects, [])

    def test_authenticated_cursor_and_corrections_applied_before_effect(self):
        kernel = RecordingKernel()
        self.invoke(application=self.apply_context, kernel=kernel)
        self.assertEqual(kernel.receipts[0][2]["resume_cursor"], "cursor-7")
        self.assertEqual(kernel.receipts[0][2]["corrections"], ExistingJournal.corrections)
        self.assertTrue(kernel.receipts[0][2]["material_context_applied"])
        self.assertEqual(next(iter(self.continuations.values()))["source"], "spiral-journal:" + "b" * 64)
        self.assertEqual(next(iter(self.continuations.values()))["corrections"], ExistingJournal.corrections)


if __name__ == "__main__":
    unittest.main()
