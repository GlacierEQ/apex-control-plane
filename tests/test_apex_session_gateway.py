"""Adversarial tests for the existing APEX admission -> model -> provenance -> checkpoint route.

A summary can index an original message; it can never acquire user authorship.
All examples are synthetic. No native ChatGPT hook or production provider is implied.
"""
import hashlib
import unittest

from src.apex_session_gateway import (
    GatewayDenied, OriginRecord, SourceAssertion, MemoryProposal,
    GatewayModelOutput, ContinuationEnvelope, run_admitted_session,
)
from src.apex_session_gateway import ContextApplication, Recovery


class ExistingJournal:
    """Stub journal: always recovers case-A, so a wrong expected mission is denied before apply."""
    def recover(self, session, mission):
        return Recovery(mission_id="case-A", source_ref="original:user:middle", cursor="cursor-7", corrections=("preserve the complete mission scope",), facts=(), material_context_found=True)


class RecordingKernel:
    """Stub kernel: unused by the local recovery path, kept for call-site shape."""
    pass


USER_MIDDLE = "Correcting the record: I did not instruct the assistant to compromise ATS."
ASSISTANT_FIRST = "Assistant proposed an unrelated concern about ATS security."


def assertion(ref, speaker, text):
    return SourceAssertion(
        source_ref=ref, speaker=speaker, verbatim=text,
        start_byte=0, end_byte=len(text.encode("utf-8")),
        source_sha256="sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


class SessionGatewayTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.reservations = set()
        self.saved = {}
        self.sources = {
            "original:user:middle": OriginRecord("user", USER_MIDDLE.encode("utf-8")),
            "original:assistant:first": OriginRecord("assistant", ASSISTANT_FIRST.encode("utf-8")),
        }
        self.user_assertion = assertion("original:user:middle", "user", USER_MIDDLE)
        self.assistant_assertion = assertion("original:assistant:first", "assistant", ASSISTANT_FIRST)

    def apply(self, recovery):
        self.events.append("apply")
        return ContextApplication(
            recovery.mission_id, recovery.source_ref, recovery.cursor,
            recovery.corrections, tuple(recovery.facts),
            "application:verified-source",
        )

    def model(self, receipt):
        self.events.append("model")
        self.assertEqual(receipt.mission_id, "case-A")
        self.assertEqual(receipt.cursor, "cursor-7")
        self.assertIn("preserve the complete mission scope", receipt.recovery.corrections)
        return GatewayModelOutput(
            text="The user explicitly corrected the assistant interpretation.",
            attributions=(self.user_assertion,),
            memory_proposals=(MemoryProposal("user_correction", self.user_assertion),),
            corrections_applied=receipt.recovery.corrections,
        )

    def reserve(self, key):
        self.events.append("reserve")
        if key in self.reservations:
            return False
        self.reservations.add(key)
        return True

    def persist(self, envelope):
        self.events.append("persist")
        self.assertIsInstance(envelope, ContinuationEnvelope)
        self.saved[envelope.operation_key] = envelope
        return envelope.operation_key

    def readback(self, key):
        self.events.append("readback")
        return self.saved[key]

    def invoke(self, *, model=None, resolve_source=None, expected="case-A",
               apply=None, persist=None, readback=None, invocation_id="turn-1"):
        return run_admitted_session(
            journal=ExistingJournal(), chat_session_id="new-session-1",
            kernel=RecordingKernel(), expected_mission_id=expected,
            invocation_id=invocation_id,
            apply_context=apply if apply is not None else self.apply,
            invoke_model=model if model is not None else self.model,
            resolve_source=resolve_source if resolve_source is not None else self.sources.__getitem__,
            reserve=self.reserve,
            persist=persist if persist is not None else self.persist,
            readback=readback if readback is not None else self.readback,
        )

    def test_valid_source_matched_correction_precedes_model_and_durable_readback(self):
        output = self.invoke()
        self.assertEqual(output.text, "The user explicitly corrected the assistant interpretation.")
        self.assertEqual(self.events, ["apply", "reserve", "model", "persist", "readback"])
        checkpoint = next(iter(self.saved.values()))
        self.assertEqual(checkpoint.mission_id, "case-A")
        self.assertEqual(checkpoint.cursor, "cursor-7")
        self.assertEqual(checkpoint.corrections, ("preserve the complete mission scope",))
        self.assertEqual(checkpoint.memory_proposals[0].source.speaker, "user")
        self.assertTrue(checkpoint.digest.startswith("sha256:"))
        self.assertEqual(checkpoint.response_author, "assistant")
        self.assertEqual(checkpoint.memory_authority, "SOURCE_CANDIDATE_ONLY")

    def test_assistant_opening_can_never_be_promoted_to_user_instruction(self):
        impersonation = assertion("original:assistant:first", "user", ASSISTANT_FIRST)
        def model(receipt):
            return GatewayModelOutput(
                "Wrongly attributed memory",
                (impersonation,),
                (MemoryProposal("user_instruction", impersonation),),
                receipt.recovery.corrections,
            )
        with self.assertRaisesRegex(GatewayDenied, "speaker"):
            self.invoke(model=model)
        self.assertEqual(self.saved, {})
        self.assertEqual(len(self.reservations), 1)

    def test_assistant_source_with_honest_speaker_cannot_be_saved_as_user_direction(self):
        def model(receipt):
            return GatewayModelOutput(
                "Discussion", (self.assistant_assertion,),
                (MemoryProposal("user_instruction", self.assistant_assertion),),
                receipt.recovery.corrections,
            )
        with self.assertRaisesRegex(GatewayDenied, "user-originated"):
            self.invoke(model=model)
        self.assertEqual(len(self.reservations), 1)

    def test_lost_middle_correction_rejected_before_persistence(self):
        def model(receipt):
            return GatewayModelOutput(
                "Omitted correction", (self.assistant_assertion,), (), (),
            )
        with self.assertRaisesRegex(GatewayDenied, "corrections"):
            self.invoke(model=model)
        self.assertEqual(len(self.reservations), 1)

    def test_summary_is_not_allowed_as_original_user_message(self):
        def fake_resolve(ref):
            return OriginRecord("memory_summary", USER_MIDDLE.encode())
        with self.assertRaisesRegex(GatewayDenied, "source speaker"):
            self.invoke(resolve_source=fake_resolve)
        self.assertEqual(len(self.reservations), 1)

    def test_mismatched_original_bytes_denied(self):
        def fake_resolve(ref):
            return OriginRecord("user", b"Another statement")
        with self.assertRaisesRegex(GatewayDenied, "digest"):
            self.invoke(resolve_source=fake_resolve)
        self.assertEqual(len(self.reservations), 1)

    def test_false_readback_does_not_count_as_checkpoint(self):
        def unverified(key):
            envelope = self.saved[key]
            return ContinuationEnvelope(
                operation_key=envelope.operation_key, chat_session_id=envelope.chat_session_id,
                mission_id=envelope.mission_id, source_ref=envelope.source_ref,
                cursor=envelope.cursor, corrections=envelope.corrections,
                response_text="Different response",
                attributions=envelope.attributions,
                memory_proposals=envelope.memory_proposals,
                digest=envelope.digest,
            )
        with self.assertRaisesRegex(GatewayDenied, "readback"):
            self.invoke(readback=unverified)
        self.assertEqual(len(self.reservations), 1)

    def test_repeat_invocation_is_denied_without_duplicate_checkpoint(self):
        self.invoke()
        self.events.clear()
        with self.assertRaisesRegex(GatewayDenied, "reserved"):
            self.invoke()
        self.assertEqual(self.events, ["apply", "reserve"])
        self.assertEqual(len(self.saved), 1)

    def test_wrong_mission_never_runs_model(self):
        with self.assertRaisesRegex(Exception, "not the requested mission"):
            self.invoke(expected="different-mission")
        self.assertEqual(self.events, [])
        self.assertEqual(self.reservations, set())

    def test_callback_preflight_denies_before_model(self):
        with self.assertRaisesRegex(GatewayDenied, "callbacks"):
            run_admitted_session(
                journal=ExistingJournal(), chat_session_id="session",
                kernel=RecordingKernel(), expected_mission_id="case-A",
                invocation_id="id",
                apply_context=self.apply, invoke_model=self.model,
                resolve_source=self.sources.__getitem__,
                reserve=None, persist=self.persist, readback=self.readback,
            )
        self.assertEqual(self.events, [])

    def test_explicit_acceptance_of_assistant_idea_requires_distinct_user_source(self):
        # A mere mention of an assistant statement is never itself adoption.
        def model(receipt):
            return GatewayModelOutput(
                "Unaccepted proposal", (),
                (MemoryProposal("user_fact", self.assistant_assertion),),
                receipt.recovery.corrections,
            )
        with self.assertRaisesRegex(GatewayDenied, "user-originated"):
            self.invoke(model=model)
        self.assertEqual(len(self.reservations), 1)



    def test_user_negation_cannot_be_memory_classified_as_an_instruction(self):
        # Exact user words and a valid hash do NOT prove that the user issued
        # the opposite of their correction. Source identity is necessary, not sufficient.
        def model(receipt):
            return GatewayModelOutput(
                "Misread correction",
                (self.user_assertion,),
                (MemoryProposal("user_instruction", self.user_assertion),),
                receipt.recovery.corrections,
            )
        with self.assertRaisesRegex(GatewayDenied, "explicit authority"):
            self.invoke(model=model)
        self.assertEqual(self.saved, {})
        self.assertEqual(len(self.reservations), 1)

    def test_unknown_memory_kind_cannot_bypass_authority_filter(self):
        def model(receipt):
            return GatewayModelOutput(
                "Suspicious derived kind", (self.user_assertion,),
                (MemoryProposal("operator_instruction", self.user_assertion),),
                receipt.recovery.corrections,
            )
        with self.assertRaisesRegex(GatewayDenied, "unsupported memory kind"):
            self.invoke(model=model)
        self.assertEqual(self.saved, {})

    def test_failing_model_retains_reservation_and_cannot_replay(self):
        def raises(receipt):
            self.events.append("model")
            raise RuntimeError("model failed after invocation")
        with self.assertRaisesRegex(RuntimeError, "model failed"):
            self.invoke(model=raises)
        self.assertEqual(self.events, ["apply", "reserve", "model"])
        self.assertEqual(self.saved, {})
        with self.assertRaisesRegex(GatewayDenied, "reserved"):
            self.invoke()
        self.assertEqual(self.events, ["apply", "reserve", "model", "apply", "reserve"])

if __name__ == "__main__":
    unittest.main()
