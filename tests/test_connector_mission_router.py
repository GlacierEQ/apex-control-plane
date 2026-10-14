"""Regression tests for connector-native mission routing."""
import unittest

from src.connector_mission_router import (
    AdmissionDenied, ConnectorCapability, MissionAdmission, admit, dispatch_once,
)


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
        self.assertEqual(dispatch_once(self.mission, self.capability, "op-1", reserve, execute, lambda r: r == "receipt-1"), "receipt-1")
        with self.assertRaisesRegex(AdmissionDenied, "already reserved"):
            dispatch_once(self.mission, self.capability, "op-1", reserve, execute, lambda _: True)
        self.assertEqual(effects, ["sent"])

    def test_failed_readback_keeps_reservation(self):
        keys = set()
        def reserve(key):
            if key in keys:
                return False
            keys.add(key)
            return True
        with self.assertRaisesRegex(AdmissionDenied, "not independently verified"):
            dispatch_once(self.mission, self.capability, "op-2", reserve, lambda: "unverified", lambda _: False)
        with self.assertRaisesRegex(AdmissionDenied, "already reserved"):
            dispatch_once(self.mission, self.capability, "op-2", reserve, lambda: "retry", lambda _: True)


if __name__ == "__main__":
    unittest.main()
