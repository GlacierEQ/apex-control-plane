"""Two independent chat sessions recover the SAME prior mission and bind to APEX before action."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from spiral_chat_handoff import recover_existing_chat_session, apply_recovery_to_apex


class FakeJournal:
    def __init__(self):
        self.mission_id = "mission-jobs"
        self.objective = "Obtain paid engineering employment"
        self.terminal_outcome = "PAID_EMPLOYMENT"
        self.events = (
            {"seq": 1, "kind": "mission", "data": {"mission_id": self.mission_id}, "sha256": "a" * 64},
            {"seq": 2, "kind": "verified_fact", "data": {"key": "application", "value": "received", "source": "employer:123"}, "sha256": "b" * 64},
            {"seq": 3, "kind": "correction", "data": {"instruction": "Do not confuse drafted with submitted"}, "sha256": "c" * 64},
            {"seq": 4, "kind": "checkpoint", "data": {"cursor": "apply:next-provider"}, "sha256": "d" * 64},
        )
        self.cursor = "apply:next-provider"
        self.corrections = ["Do not confuse drafted with submitted"]

    def fact(self, key):
        return {"key": "application", "value": "received", "source": "employer:123"} if key == "application" else None


class FakeApexKernel:
    def __init__(self):
        self.phase = SimpleNamespace(value="context_recovering")
        self.calls = []

    def record_context_recovery(self, reference, *, recovered_refs, details):
        self.calls.append((reference, recovered_refs, details))
        return "ready"


class ChatHandoffTests(unittest.TestCase):
    def test_new_chats_inherit_same_verified_mission_and_cursor(self):
        first = recover_existing_chat_session(FakeJournal(), "chat-A", fact_keys=("application",))
        second = recover_existing_chat_session(FakeJournal(), "chat-B", fact_keys=("application",))
        self.assertEqual(first.mission_id, second.mission_id)
        self.assertEqual(first.cursor, second.cursor)
        self.assertEqual(first.facts, second.facts)
        self.assertNotEqual(first.chat_session_id, second.chat_session_id)
        self.assertEqual(first.source_ref, "spiral-journal:" + "d" * 64)

    def test_apex_carries_recovered_corrections_and_cursor_into_gate(self):
        recovered = recover_existing_chat_session(FakeJournal(), "chat-A", fact_keys=("application",))
        kernel = FakeApexKernel()
        self.assertEqual(apply_recovery_to_apex(kernel, recovered, applied_to_action=True), "ready")
        self.assertEqual(kernel.calls[0][1], (recovered.source_ref,))
        self.assertEqual(kernel.calls[0][2]["applied_context_refs"], (recovered.source_ref,))
        self.assertEqual(kernel.calls[0][2]["resume_cursor"], "apply:next-provider")
        self.assertEqual(kernel.calls[0][2]["corrections"], ("Do not confuse drafted with submitted",))

    def test_material_context_cannot_be_ignored(self):
        recovered = recover_existing_chat_session(FakeJournal(), "chat-A")
        with self.assertRaises(ValueError):
            apply_recovery_to_apex(FakeApexKernel(), recovered, applied_to_action=False)

    def test_missing_or_untrusted_journal_rejected(self):
        with self.assertRaises(ValueError):
            recover_existing_chat_session(None, "chat-A")
        bad = FakeJournal()
        bad.events = ({"kind": "mission", "sha256": "a" * 64},)
        with self.assertRaises(ValueError):
            recover_existing_chat_session(bad, "chat-A")

    def test_cannot_apply_boot_proof_after_execution_begins(self):
        recovered = recover_existing_chat_session(FakeJournal(), "chat-A")
        kernel = FakeApexKernel()
        kernel.phase.value = "executing"
        with self.assertRaises(ValueError):
            apply_recovery_to_apex(kernel, recovered, applied_to_action=True)


if __name__ == "__main__":
    unittest.main()
