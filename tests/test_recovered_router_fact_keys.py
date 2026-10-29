"""Regression for real APEX router/gateway fact-key handoff.

Callbacks are synthetic; separately run pinned-Spiral upstream integration.
"""
from __future__ import annotations

import unittest

from src.apex_session_gateway import (
    ContextApplication, GatewayDenied, Recovery, execute_with_recovered_context,
)
from src.connector_mission_router import ConnectorCapability, dispatch_recovered_once


class RecoveredRouterFactsTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.recovery = Recovery(
            mission_id="mission-1", source_ref="verified-source-1",
            cursor="cursor-7", corrections=("preserve-original",),
            facts=("application", "deadline"), material_context_found=True,
        )

    def apply(self, recovery):
        self.events.append("apply")
        return ContextApplication(
            recovery.mission_id, recovery.source_ref, recovery.cursor,
            recovery.corrections, recovery.facts, "host:applied-source",
        )

    def recover(self, *, expected="mission-1", fact_keys=("application",), apply=None):
        return execute_with_recovered_context(
            journal=self.recovery, chat_session_id="chat-2", kernel=object(),
            expected_mission_id=expected, fact_keys=fact_keys,
            apply_context=self.apply if apply is None else apply,
            execute=lambda receipt: receipt,
        )

    def test_valid_fact_selection_and_source_matched_receipt(self):
        receipt = self.recover()
        self.assertEqual(receipt.source_ref, self.recovery.source_ref)
        self.assertEqual(receipt.application_ref, "host:applied-source")
        self.assertEqual(self.events, ["apply"])

    def test_unrecovered_fact_rejected_before_application(self):
        with self.assertRaisesRegex(GatewayDenied, "requested fact key missing"):
            self.recover(fact_keys=("invented",))
        self.assertEqual(self.events, [])

    def test_invalid_fact_key_types_rejected_before_application(self):
        for keys in ("application", (None,), ("",)):
            with self.subTest(keys=keys):
                with self.assertRaises(GatewayDenied):
                    self.recover(fact_keys=keys)
        self.assertEqual(self.events, [])

    def test_wrong_mission_rejected_before_application(self):
        with self.assertRaisesRegex(GatewayDenied, "different mission"):
            self.recover(expected="other")
        self.assertEqual(self.events, [])

    def test_source_mismatch_rejected_even_with_verified_selector(self):
        def forged(r):
            self.events.append("apply")
            return ContextApplication(
                r.mission_id, "other-source", r.cursor,
                r.corrections, r.facts, "claim",
            )
        with self.assertRaisesRegex(GatewayDenied, "source-matched"):
            self.recover(apply=forged)
        self.assertEqual(self.events, ["apply"])

    def test_fresh_mission_remains_admissible_without_fact_selector(self):
        fresh = Recovery("new", "", "", (), (), False)
        receipt = execute_with_recovered_context(
            journal=fresh, chat_session_id="chat-3", kernel=object(),
            expected_mission_id="new", fact_keys=(), apply_context=None,
            execute=lambda rec: rec,
        )
        self.assertEqual(receipt.application_ref, "")

    def test_fresh_mission_cannot_claim_unrecovered_fact(self):
        fresh = Recovery("new", "", "", (), (), False)
        with self.assertRaisesRegex(GatewayDenied, "requested fact key missing"):
            execute_with_recovered_context(
                journal=fresh, chat_session_id="chat-3", kernel=object(),
                expected_mission_id="new", fact_keys=("phantom",),
                apply_context=None, execute=lambda _: self.fail("must not execute"),
            )

    def test_router_success_has_provider_and_persistence_readbacks(self):
        saved = {}
        def reserve(key):
            self.events.append("reserve")
            return True
        def execute():
            self.events.append("native-execute")
            return {"id": "provider-result-1"}
        def readback(result):
            self.events.append("provider-readback")
            return result["id"] == "provider-result-1"
        def persist(record):
            self.events.append("persist")
            saved[record.operation_key] = record
            return record.operation_key
        def verify(key):
            self.events.append("continuation-readback")
            return saved[key].source_ref == "verified-source-1"
        result = dispatch_recovered_once(
            journal=self.recovery, chat_session_id="chat-2", kernel=object(),
            expected_mission_id="mission-1", fact_keys=("application",),
            capability=ConnectorCapability("synthetic", "write", True, True, True),
            operation_id="op-1", apply_context=self.apply,
            reserve=reserve, execute=execute, readback=readback,
            persist_continuation=persist, verify_continuation=verify,
        )
        self.assertEqual(result, {"id": "provider-result-1"})
        self.assertEqual(self.events, [
            "apply", "reserve", "native-execute", "provider-readback",
            "persist", "continuation-readback",
        ])


if __name__ == "__main__":
    unittest.main()
