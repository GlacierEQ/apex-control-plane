"""Already reserved operations resume via native receipt, never replay side effects."""
import unittest
from src.connector_mission_router import (
    AdmissionDenied, ConnectorCapability, MissionAdmission,
    RecoveredEffect, dispatch_once,
)


class ReconcileReservedOperationTests(unittest.TestCase):
    def setUp(self):
        self.admission = MissionAdmission(
            "CHERRY", "CHERRY", True, "cursor-2", ("owner-correction",), "source:original",
        )
        self.capability = ConnectorCapability("case-provider", "private-write", True, True, True)
        self.key = "CHERRY:case-provider:private-write:op-1"
        self.effect = {"native_id": "case-provider:receipt-1"}
        self.checkpoint = {
            "mission_id": "CHERRY",
            "provider": "case-provider",
            "action": "private-write",
            "operation_key": self.key,
            "receipt_ref": "case-provider:receipt-1",
        }
        self.external_calls = []

    def execute(self):
        self.external_calls.append("execute")
        return self.effect

    def dispatch(self, reconcile, *, readback=None, verify=None):
        return dispatch_once(
            self.admission, self.capability, "op-1",
            reserve=lambda _: False, execute=self.execute,
            readback=readback or (lambda result: result == self.effect),
            persist_continuation=lambda _: self.checkpoint,
            verify_continuation=verify or (lambda checkpoint: checkpoint == self.checkpoint),
            reconcile_reserved=reconcile,
        )

    def test_reserved_operation_recovers_from_native_receipt_without_duplicate_effect(self):
        outcome = self.dispatch(lambda key: RecoveredEffect(
            key, self.effect, self.checkpoint
        ))
        self.assertEqual(outcome, self.effect)
        self.assertEqual(self.external_calls, [])

    def test_crash_after_provider_success_finishes_missing_checkpoint_without_replay(self):
        # A native provider receipt can exist without a saved APEX checkpoint.
        # Its independently verified result must be persisted, never created again.
        result = self.dispatch(lambda key: RecoveredEffect(key, self.effect, None))
        self.assertEqual(result, self.effect)
        self.assertEqual(self.external_calls, [])

    def test_unverified_native_result_cannot_bridge_missing_checkpoint(self):
        with self.assertRaises(AdmissionDenied):
            self.dispatch(
                lambda key: RecoveredEffect(key, {"native_id": "wrong"}, None),
                readback=lambda result: result == self.effect,
            )
        self.assertEqual(self.external_calls, [])

    def test_reserved_without_provider_checkpoint_remains_unreplayed(self):
        with self.assertRaisesRegex(AdmissionDenied, "reconcile"):
            self.dispatch(lambda _: None)
        self.assertEqual(self.external_calls, [])

    def test_wrong_mission_or_key_never_resumes(self):
        wrong = dict(self.checkpoint, mission_id="OTHER")
        with self.assertRaises(AdmissionDenied):
            self.dispatch(lambda key: RecoveredEffect(key, self.effect, wrong))
        with self.assertRaises(AdmissionDenied):
            self.dispatch(lambda key: RecoveredEffect("OTHER:key", self.effect, self.checkpoint))
        self.assertEqual(self.external_calls, [])

    def test_provider_or_checkpoint_readback_failure_cannot_promote_recovery(self):
        reconcile = lambda key: RecoveredEffect(key, self.effect, self.checkpoint)
        with self.assertRaises(AdmissionDenied):
            self.dispatch(reconcile, readback=lambda _: False)
        with self.assertRaises(AdmissionDenied):
            self.dispatch(reconcile, verify=lambda _: False)
        self.assertEqual(self.external_calls, [])

    def test_absent_reconcile_callback_retains_existing_no_replay_behavior(self):
        with self.assertRaisesRegex(AdmissionDenied, "already reserved"):
            self.dispatch(None)
        self.assertEqual(self.external_calls, [])


if __name__ == "__main__":
    unittest.main()
