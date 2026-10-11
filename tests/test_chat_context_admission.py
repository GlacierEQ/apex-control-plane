"""Regression: continuity must not become a first-use lockout."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from src.chat_context_admission import (
    ContextAdmissionDenied,
    execute_with_recovered_context,
)


class FreshJournal:
    mission_id = "authorized-new-mission"
    objective = "Complete the Operator's authorized engineering result"
    terminal_outcome = "VERIFIED_ENGINEERING_RESULT"
    cursor = ""
    corrections = ()
    events = (
        {
            "kind": "mission",
            "data": {"mission_id": "authorized-new-mission"},
            "sha256": "a" * 64,
        },
    )

    def fact(self, key):
        return None


class RecordingKernel:
    def __init__(self, phase="context_recovering"):
        self.phase = SimpleNamespace(value=phase)
        self.receipts = []

    def record_context_recovery(self, reference, *, recovered_refs, details):
        self.receipts.append((reference, recovered_refs, details))
        self.phase.value = "ready"
        return "ready"


class ContextAdmissionTests(unittest.TestCase):
    def test_valid_new_mission_without_history_is_admitted(self):
        kernel = RecordingKernel()
        executions = []
        result = execute_with_recovered_context(
            journal=FreshJournal(),
            chat_session_id="chat-new",
            kernel=kernel,
            execute=lambda receipt: executions.append(receipt.mission_id) or "executed",
        )
        self.assertEqual(result, "executed")
        self.assertEqual(executions, ["authorized-new-mission"])
        self.assertEqual(kernel.phase.value, "ready")
        self.assertFalse(kernel.receipts[0][2]["material_context_found"])
        self.assertFalse(kernel.receipts[0][2]["material_context_applied"])
        self.assertEqual(kernel.receipts[0][2]["applied_context_refs"], ())

    def test_existing_mission_with_history_is_recovered(self):
        class ExistingJournal(FreshJournal):
            events = FreshJournal.events + (
                {"kind": "checkpoint", "data": {"cursor": "next"}, "sha256": "b" * 64},
            )
            cursor = "next"

        kernel = RecordingKernel()
        result = execute_with_recovered_context(
            journal=ExistingJournal(),
            chat_session_id="chat-resumed",
            kernel=kernel,
            execute=lambda receipt: receipt.cursor,
        )
        self.assertEqual(result, "next")
        self.assertTrue(kernel.receipts[0][2]["material_context_found"])
        self.assertTrue(kernel.receipts[0][2]["material_context_applied"])

    def test_untrusted_journal_does_not_invoke_executor(self):
        kernel = RecordingKernel()
        effects = []
        with self.assertRaises(ContextAdmissionDenied):
            execute_with_recovered_context(
                journal=None,
                chat_session_id="chat-untrusted",
                kernel=kernel,
                execute=lambda receipt: effects.append(receipt.mission_id),
            )
        self.assertFalse(effects)

    def test_wrong_kernel_phase_does_not_invoke_executor(self):
        kernel = RecordingKernel(phase="executing")
        effects = []
        with self.assertRaises(ContextAdmissionDenied):
            execute_with_recovered_context(
                journal=FreshJournal(),
                chat_session_id="chat-late",
                kernel=kernel,
                execute=lambda receipt: effects.append(receipt.mission_id),
            )
        self.assertFalse(effects)


if __name__ == "__main__":
    unittest.main()
