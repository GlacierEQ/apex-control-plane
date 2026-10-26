"""Regressions: recovered missions must execute authorized work before full completion."""
import unittest

from src.apex_session_gateway import ContextApplication, Recovery, GatewayDenied
from src.connector_mission_router import (
    AdmissionDenied, ConnectorCapability, dispatch_recovered_once,
)


class RecoveredMissionExecutionTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.journal = Recovery(
            mission_id="CHERRY", source_ref="spiral:original-1", cursor="cursor-11",
            corrections=("owner-correction",), facts=("fact-1",),
            material_context_found=True,
        )
        self.capability = ConnectorCapability(
            "case-provider", "write-private-artifact", True, True, True,
        )
        self.store = {}

    def apply(self, recovery):
        self.events.append("apply")
        return ContextApplication(
            mission_id=recovery.mission_id, source_ref=recovery.source_ref,
            cursor=recovery.cursor, corrections=recovery.corrections,
            facts=recovery.facts, application_ref="source-matched-application-1",
        )

    def reserve(self, key):
        self.events.append("reserve")
        return key not in self.store

    def execute(self):
        self.events.append("execute")
        return {"native_id": "private-artifact-42"}

    def readback(self, result):
        self.events.append("provider-readback")
        return result == {"native_id": "private-artifact-42"}

    def persist(self, record):
        self.events.append("persist")
        self.store[record.operation_key] = record
        return record.operation_key

    def verify(self, key):
        self.events.append("continuation-readback")
        return self.store[key].native_result["native_id"] == "private-artifact-42"

    def invoke(self, **overrides):
        options = dict(
            journal=self.journal, chat_session_id="session-1", kernel=object(),
            expected_mission_id="CHERRY", capability=self.capability,
            operation_id="artifact-1", reserve=self.reserve,
            execute=self.execute, readback=self.readback,
            persist_continuation=self.persist, verify_continuation=self.verify,
            fact_keys=("fact-1",), apply_context=self.apply,
            mission_scope={
                "mission_id": "CHERRY", "cursor": "cursor-11",
                "correction_ids": ["owner-correction"],
                "required_lanes": ["NEX", "Camaro"],
            },
            execution_evidence={
                "mission_id": "CHERRY", "cursor": "cursor-11",
                "applied_correction_ids": ["owner-correction"],
                "completed_lanes": ["NEX"],
                "evidence_refs": ["gmail:source-1"],
                "claimed_complete": False,
            },
        )
        options.update(overrides)
        return dispatch_recovered_once(**options)

    def test_authorized_partial_mission_executes_and_persists_native_receipt(self):
        result = self.invoke()
        self.assertEqual(result["native_id"], "private-artifact-42")
        self.assertEqual(self.events, [
            "apply", "reserve", "execute", "provider-readback",
            "persist", "continuation-readback",
        ])
        self.assertEqual(len(self.store), 1)

    def test_zero_completed_lanes_can_start_first_authorized_action(self):
        initial = {
            "mission_id": "CHERRY", "cursor": "cursor-11",
            "applied_correction_ids": ["owner-correction"],
            "completed_lanes": [],
            "evidence_refs": [],
            "claimed_complete": False,
        }
        result = self.invoke(execution_evidence=initial)
        self.assertEqual(result["native_id"], "private-artifact-42")
        self.assertEqual(len(self.store), 1)

    def test_partial_mission_continues_another_independent_lane_without_replay(self):
        self.invoke()
        def second_execute():
            self.events.append("execute-2")
            return {"native_id": "private-artifact-43"}
        second = self.invoke(
            operation_id="artifact-2", execute=second_execute,
            readback=lambda result: result["native_id"] == "private-artifact-43",
            verify_continuation=lambda key: self.store[key].native_result["native_id"] == "private-artifact-43",
        )
        self.assertEqual(second["native_id"], "private-artifact-43")
        self.assertEqual(len(self.store), 2)
        self.assertIn("CHERRY:case-provider:write-private-artifact:artifact-1", self.store)
        self.assertIn("CHERRY:case-provider:write-private-artifact:artifact-2", self.store)
        self.assertEqual(self.events.count("execute"), 1)
        self.assertEqual(self.events.count("execute-2"), 1)
        with self.assertRaisesRegex(AdmissionDenied, "already reserved"):
            self.invoke()
        self.assertEqual(len(self.store), 2)
        self.assertEqual(self.events.count("execute"), 1)

    def test_valid_new_mission_works_without_fidelity_snapshot(self):
        result = self.invoke(mission_scope=None, execution_evidence=None)
        self.assertEqual(result["native_id"], "private-artifact-42")
        self.assertIn("execute", self.events)

    def test_intent_only_audit_snapshot_cannot_veto_authorized_execution(self):
        result = self.invoke(execution_evidence=None)
        self.assertEqual(result["native_id"], "private-artifact-42")
        self.assertIn("execute", self.events)

    def test_evidence_only_audit_snapshot_cannot_veto_authorized_execution(self):
        result = self.invoke(mission_scope=None)
        self.assertEqual(result["native_id"], "private-artifact-42")
        self.assertIn("execute", self.events)

    def test_false_completion_rejected_before_any_provider_side_effect(self):
        bad = {
            "mission_id": "CHERRY", "cursor": "cursor-11",
            "applied_correction_ids": ["owner-correction"],
            "completed_lanes": ["NEX"],
            "evidence_refs": ["gmail:source-1"],
            "claimed_complete": True,
        }
        with self.assertRaisesRegex(AdmissionDenied, "mission fidelity"):
            self.invoke(execution_evidence=bad)
        self.assertNotIn("reserve", self.events)
        self.assertNotIn("execute", self.events)

    def test_wrong_source_application_cannot_enable_execution(self):
        def wrong_source(recovery):
            self.events.append("apply")
            return ContextApplication(
                recovery.mission_id, "spiral:other-mission",
                recovery.cursor, recovery.corrections, recovery.facts,
                "not-source-matched",
            )
        with self.assertRaises(GatewayDenied):
            self.invoke(apply_context=wrong_source)
        self.assertNotIn("execute", self.events)

    def test_missing_applied_fact_denies_before_reservation(self):
        def omits_fact(recovery):
            self.events.append("apply")
            return ContextApplication(
                recovery.mission_id, recovery.source_ref,
                recovery.cursor, recovery.corrections, (),
                "application-without-facts",
            )
        with self.assertRaises(GatewayDenied):
            self.invoke(apply_context=omits_fact)
        self.assertNotIn("reserve", self.events)

    def test_denied_provider_authority_never_executes(self):
        with self.assertRaises(AdmissionDenied):
            self.invoke(capability=ConnectorCapability(
                "case-provider", "write-private-artifact", True, True, False,
            ))
        self.assertNotIn("execute", self.events)


if __name__ == "__main__":
    unittest.main()
