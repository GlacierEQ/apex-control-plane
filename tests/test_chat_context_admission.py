"""Regression: continuity must not become a first-use lockout."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from src.chat_context_admission import (
    ContextAdmissionDenied,
    ContextApplication,
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

    def test_existing_mission_requires_real_host_application_callback(self):
        class ExistingJournal(FreshJournal):
            events = FreshJournal.events + (
                {"kind": "checkpoint", "data": {"cursor": "next"}, "sha256": "b" * 64},
            )
            cursor = "next"
            corrections = ("Preserve the Operator's complete mission scope",)

            def fact(self, key):
                if key == "mission_frontier":
                    return {"source": "provider:verified-cursor", "value": "next"}
                return None

        def valid_application(recovery):
            return ContextApplication(
                mission_id=recovery.mission_id,
                source_ref=recovery.source_ref,
                cursor=recovery.cursor,
                corrections=recovery.corrections,
                fact_keys=tuple(recovery.facts),
                effect_ref="host-application:recovered-cursor-and-corrections",
            )

        # Retrieval alone must not be promoted to context application.
        effects = []
        with self.assertRaises(ContextAdmissionDenied):
            execute_with_recovered_context(
                journal=ExistingJournal(),
                chat_session_id="chat-resumed",
                expected_mission_id="authorized-new-mission",
                kernel=RecordingKernel(),
                fact_keys=("mission_frontier",),
                execute=lambda receipt: effects.append(receipt.cursor),
            )
        self.assertFalse(effects)

        # A source-matched callback receives corrections and facts before execution.
        kernel = RecordingKernel()
        observed = []
        def applied(recovery):
            observed.append((recovery.cursor, recovery.corrections,
                             recovery.facts["mission_frontier"]["value"]))
            return valid_application(recovery)

        result = execute_with_recovered_context(
            journal=ExistingJournal(),
            chat_session_id="chat-resumed",
            expected_mission_id="authorized-new-mission",
            kernel=kernel,
            fact_keys=("mission_frontier",),
            apply_context=applied,
            execute=lambda receipt: (receipt.cursor, receipt.application_ref,
                                     receipt.recovery.corrections),
        )
        self.assertEqual(observed, [
            ("next", ("Preserve the Operator's complete mission scope",), "next")
        ])
        self.assertEqual(result[0], "next")
        self.assertEqual(result[1], "host-application:recovered-cursor-and-corrections")
        self.assertEqual(result[2], ExistingJournal.corrections)
        self.assertTrue(kernel.receipts[0][2]["material_context_found"])
        self.assertTrue(kernel.receipts[0][2]["material_context_applied"])

        # A callback that attests to a different source, cursor, correction or
        # fact set must never release the executor.
        from dataclasses import replace
        def invalid_receipt(recovery, field):
            correct = valid_application(recovery)
            changes = {
                "source_ref": "spiral-journal:" + "0" * 64,
                "cursor": "old",
                "corrections": (),
                "fact_keys": (),
                "effect_ref": "",
            }
            return replace(correct, **{field: changes[field]})

        for field in ("source_ref", "cursor", "corrections",
                      "fact_keys", "effect_ref"):
            with self.subTest(field=field):
                called = []
                with self.assertRaises(ContextAdmissionDenied):
                    execute_with_recovered_context(
                        journal=ExistingJournal(),
                        chat_session_id="chat-resumed",
                        expected_mission_id="authorized-new-mission",
                        kernel=RecordingKernel(),
                        fact_keys=("mission_frontier",),
                        apply_context=lambda recovery, field=field: invalid_receipt(recovery, field),
                        execute=lambda receipt: called.append(receipt.cursor),
                    )
                self.assertFalse(called)

    def test_wrong_or_missing_mission_identity_never_applies_context(self):
        class ExistingJournal(FreshJournal):
            events = FreshJournal.events + (
                {"kind": "checkpoint", "data": {"cursor": "apex-cursor"}, "sha256": "b" * 64},
            )
            cursor = "apex-cursor"
            corrections = ("Preserve current mission identity",)

        # Even a source-matched callback cannot justify attaching the wrong mission.
        for expected in (None, "", "massive-daniel-mission", 123):
            with self.subTest(expected=expected):
                effects = []
                kernel = RecordingKernel()
                with self.assertRaises(ContextAdmissionDenied):
                    execute_with_recovered_context(
                        journal=ExistingJournal(),
                        chat_session_id="chat-massive-daniel",
                        expected_mission_id=expected,
                        kernel=kernel,
                        apply_context=lambda recovery: effects.append("applied"),
                        execute=lambda receipt: effects.append("executed"),
                    )
                self.assertEqual(effects, [])
                self.assertEqual(kernel.phase.value, "context_recovering")
                self.assertEqual(kernel.receipts, [])

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



class AlternateRecoveryRouteTests(unittest.TestCase):
    """The pre-existing APEX binding route must not bypass mission identity."""

    @staticmethod
    def _recovery(material=True):
        from src.spiral_chat_handoff import recover_existing_chat_session

        class Journal(FreshJournal):
            events = FreshJournal.events + (
                {"kind": "checkpoint", "data": {"cursor": "next"}, "sha256": "b" * 64},
            ) if material else FreshJournal.events
            cursor = "next" if material else ""

        return recover_existing_chat_session(Journal(), "chat-alternate")

    @staticmethod
    def _kernel():
        class BindingKernel(RecordingKernel):
            def __init__(self):
                super().__init__(phase="bootstrapped")
                self.bindings = []

            def bind_task(self, **kwargs):
                self.bindings.append(kwargs)
                self.phase.value = "context_recovering"

        return BindingKernel()

    def _bind(self, kernel, recovery, **kwargs):
        from src.spiral_live_journal import resume_authenticated_chat_in_apex
        return resume_authenticated_chat_in_apex(
            kernel, recovery,
            task_instruction="Resume authorized mission",
            target_state="verified-result",
            operation_class="resume_mission",
            applied_to_action=True,
            **kwargs,
        )

    def test_alternate_path_rejects_missing_invalid_and_wrong_identity_before_binding(self):
        from src.spiral_live_journal import SpiralChatAdmissionError
        recovery = self._recovery()
        for expected in (None, "", "unrelated-daniel-case", 123):
            with self.subTest(expected=expected):
                kernel = self._kernel()
                with self.assertRaises(SpiralChatAdmissionError):
                    self._bind(kernel, recovery, expected_mission_id=expected)
                self.assertEqual(kernel.bindings, [])
                self.assertEqual(kernel.receipts, [])
                self.assertEqual(kernel.phase.value, "bootstrapped")

    def test_alternate_path_binds_only_exact_requested_mission(self):
        recovery = self._recovery()
        kernel = self._kernel()
        self._bind(kernel, recovery, expected_mission_id=recovery.mission_id)
        self.assertEqual(kernel.phase.value, "ready")
        self.assertEqual(len(kernel.bindings), 1)
        self.assertEqual(len(kernel.receipts), 1)
        self.assertEqual(kernel.receipts[0][2]["mission_id"], recovery.mission_id)

    def test_alternate_path_keeps_fresh_first_use_admissible(self):
        recovery = self._recovery(material=False)
        kernel = self._kernel()
        self._bind(kernel, recovery)
        self.assertEqual(kernel.phase.value, "ready")
        self.assertEqual(len(kernel.bindings), 1)


if __name__ == "__main__":
    unittest.main()
