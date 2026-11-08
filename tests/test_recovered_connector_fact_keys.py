"""Regression: requested recovery facts must reach the real connector bridge.

A fact-key-aware journal is required when keys are requested. These tests
exercise the existing admission/reservation/readback path with local provider
fixtures; they do not claim a live cloud consumer or human outcome.
"""
import unittest

from src.apex_session_gateway import ContextApplication, GatewayDenied, Recovery
from src.connector_mission_router import (
    ConnectorCapability, dispatch_recovered_once,
)


class FactAwareJournal:
    def __init__(self, events, facts=("source-fact",)):
        self.events = events
        self.facts = facts

    def recover(self, session, mission, *, fact_keys=()):
        self.events.append(("recover", tuple(fact_keys)))
        return Recovery(
            mission_id=mission,
            source_ref="mem:exact-source",
            cursor="cursor-2",
            corrections=("use current source",),
            facts=tuple(self.facts),
            material_context_found=True,
        )


class LegacyJournal:
    def recover(self, session, mission):
        return Recovery(
            mission_id=mission,
            source_ref="mem:exact-source",
            cursor="cursor-2",
            corrections=("use current source",),
            facts=(),
            material_context_found=True,
        )


class FactKeyConnectorTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.reserved = set()
        self.saved = {}
        self.capability = ConnectorCapability(
            provider="test-provider", action="readback", discovered=True,
            authenticated=True, permitted=True,
        )

    def apply(self, recovery):
        self.events.append(("apply", recovery.facts))
        return ContextApplication(
            mission_id=recovery.mission_id,
            source_ref=recovery.source_ref,
            cursor=recovery.cursor,
            corrections=recovery.corrections,
            facts=recovery.facts,
            application_ref="application:source-bound",
        )

    def reserve(self, key):
        self.events.append(("reserve", key))
        if key in self.reserved:
            return False
        self.reserved.add(key)
        return True

    def execute(self):
        self.events.append(("execute", True))
        return {"native_id": "provider:receipt-1"}

    def readback(self, result):
        self.events.append(("readback", result["native_id"]))
        return result == {"native_id": "provider:receipt-1"}

    def persist(self, record):
        self.events.append(("persist", record.correction_ids))
        self.saved[record.operation_key] = record
        return record.operation_key

    def verify(self, key):
        self.events.append(("verify", key))
        return key in self.saved

    def dispatch(self, journal, *, fact_keys=()):
        return dispatch_recovered_once(
            journal=journal,
            chat_session_id="chat-1",
            kernel=object(),
            expected_mission_id="memory-fix",
            capability=self.capability,
            operation_id="item-1",
            reserve=self.reserve,
            execute=self.execute,
            readback=self.readback,
            persist_continuation=self.persist,
            verify_continuation=self.verify,
            fact_keys=fact_keys,
            apply_context=self.apply,
        )

    def test_requested_facts_are_recovered_applied_and_read_back(self):
        result = self.dispatch(FactAwareJournal(self.events), fact_keys=("source-fact",))
        self.assertEqual(result["native_id"], "provider:receipt-1")
        self.assertEqual([x[0] for x in self.events],
                         ["recover", "apply", "reserve", "execute", "readback",
                          "persist", "verify"])
        self.assertEqual(self.events[0][1], ("source-fact",))
        self.assertEqual(self.events[1][1], ("source-fact",))
        self.assertEqual(len(self.saved), 1)

    def test_missing_requested_fact_is_denied_before_effect(self):
        with self.assertRaisesRegex(GatewayDenied, "not recovered"):
            self.dispatch(FactAwareJournal(self.events, facts=("unrelated",)),
                          fact_keys=("source-fact",))
        self.assertEqual([x[0] for x in self.events], ["recover"])
        self.assertFalse(self.reserved)
        self.assertFalse(self.saved)

    def test_legacy_journal_cannot_silently_ignore_requested_keys(self):
        with self.assertRaisesRegex(GatewayDenied, "cannot recover"):
            self.dispatch(LegacyJournal(), fact_keys=("source-fact",))
        self.assertEqual(self.events, [])
        self.assertFalse(self.reserved)

    def test_legacy_journal_without_requested_keys_still_executes(self):
        result = self.dispatch(LegacyJournal())
        self.assertEqual(result["native_id"], "provider:receipt-1")
        self.assertEqual([x[0] for x in self.events],
                         ["apply", "reserve", "execute", "readback", "persist", "verify"])

    def test_string_fact_keys_are_not_treated_as_character_sequence(self):
        with self.assertRaisesRegex(GatewayDenied, "sequence"):
            self.dispatch(FactAwareJournal(self.events), fact_keys="source-fact")
        self.assertEqual(self.events, [])
        self.assertFalse(self.reserved)


if __name__ == "__main__":
    unittest.main()
