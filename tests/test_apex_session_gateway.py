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

    def test_mismatched_context_application_never_admits_model_or_reservation(self):
        from dataclasses import replace

        variants = (
            ("mission_id", "case-B"),
            ("source_ref", "unrelated:summary"),
            ("cursor", "stale-cursor"),
            ("corrections", ()),
            ("facts", ("injected-fact",)),
            ("application_ref", ""),
            ("application_ref", None),
        )
        for field, value in variants:
            with self.subTest(field=field, value=value):
                self.events.clear()
                self.reservations.clear()
                self.saved.clear()

                def mismatched(recovery):
                    return replace(self.apply(recovery), **{field: value})

                with self.assertRaisesRegex(GatewayDenied, "context application"):
                    self.invoke(apply=mismatched)
                self.assertEqual(self.events, ["apply"])
                self.assertEqual(self.reservations, set())
                self.assertEqual(self.saved, {})

    def test_mutable_recovery_cannot_drop_corrections_before_admission(self):
        # Runtime type annotations do not prevent a journal from returning lists.
        recovery = Recovery(
            "case-A", "original:user:middle", "cursor-7",
            ["critical correction"], ["restricted:source-pointer"], True,
        )
        def destructive_apply(record):
            self.events.append("apply")
            record.corrections.clear()
            record.facts.clear()
            return ContextApplication(
                record.mission_id, record.source_ref, record.cursor,
                tuple(record.corrections), tuple(record.facts), "false-attestation",
            )
        with self.assertRaisesRegex(GatewayDenied, "immutable typed source bindings"):
            run_admitted_session(
                journal=recovery, chat_session_id="mutable-session",
                kernel=RecordingKernel(), expected_mission_id="case-A",
                invocation_id="mutable-turn", apply_context=destructive_apply,
                invoke_model=self.model, resolve_source=self.sources.__getitem__,
                reserve=self.reserve, persist=self.persist, readback=self.readback,
            )
        self.assertEqual(recovery.corrections, ["critical correction"])
        self.assertEqual(self.events, [])
        self.assertEqual(self.reservations, set())
        self.assertEqual(self.saved, {})

    def test_callback_cannot_rewrite_frozen_recovery_and_self_attest(self):
        recovery = Recovery(
            "case-A", "original:user:middle", "cursor-7",
            ("critical correction",), ("restricted:source-pointer",), True,
        )
        def tampering_apply(record):
            self.events.append("apply")
            object.__setattr__(record, "corrections", ())
            object.__setattr__(record, "facts", ())
            return ContextApplication(
                record.mission_id, record.source_ref, record.cursor,
                record.corrections, record.facts, "false-attestation",
            )
        with self.assertRaisesRegex(GatewayDenied, "mutated recovered source bindings"):
            run_admitted_session(
                journal=recovery, chat_session_id="tampered-session",
                kernel=RecordingKernel(), expected_mission_id="case-A",
                invocation_id="tampered-turn", apply_context=tampering_apply,
                invoke_model=self.model, resolve_source=self.sources.__getitem__,
                reserve=self.reserve, persist=self.persist, readback=self.readback,
            )
        self.assertEqual(self.events, ["apply"])
        self.assertEqual(self.reservations, set())
        self.assertEqual(self.saved, {})

    def test_fresh_mission_without_historical_context_does_not_require_application(self):
        from src.apex_session_gateway import execute_with_recovered_context
        fresh = Recovery("new-mission", "", "", (), (), False)
        receipts = []
        result = execute_with_recovered_context(
            journal=fresh, chat_session_id="new-session", kernel=RecordingKernel(),
            expected_mission_id="new-mission", apply_context=None,
            execute=lambda receipt: receipts.append(receipt) or "admitted",
        )
        self.assertEqual(result, "admitted")
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0].application_ref, "")
        self.assertIsNone(receipts[0].application)

    def test_fresh_mission_runs_full_gateway_and_persists_without_fake_application(self):
        fresh = Recovery("new-mission", "", "", (), (), False)
        result = run_admitted_session(
            journal=fresh, chat_session_id="fresh-session", kernel=RecordingKernel(),
            expected_mission_id="new-mission", invocation_id="fresh-turn",
            apply_context=None,
            invoke_model=lambda receipt: GatewayModelOutput("fresh response", (), (), ()),
            resolve_source=self.sources.__getitem__, reserve=self.reserve,
            persist=self.persist, readback=self.readback,
        )
        self.assertEqual(result.text, "fresh response")
        self.assertEqual(self.events, ["reserve", "persist", "readback"])
        checkpoint = next(iter(self.saved.values()))
        self.assertEqual(checkpoint.mission_id, "new-mission")
        self.assertEqual(checkpoint.corrections, ())

    def test_recovered_correction_cannot_hide_behind_false_material_flag(self):
        from src.apex_session_gateway import execute_with_recovered_context
        mislabeled = Recovery("case-A", "original:user:middle", "cursor-7",
                              ("preserve the complete mission scope",), (), False)
        with self.assertRaisesRegex(GatewayDenied, "historical context application"):
            execute_with_recovered_context(
                journal=mislabeled, chat_session_id="new-session", kernel=RecordingKernel(),
                expected_mission_id="case-A", apply_context=None,
                execute=lambda _: self.fail("executor must not run"),
            )

    def test_recovered_context_without_application_denied_before_reservation(self):
        with self.assertRaisesRegex(GatewayDenied, "historical context application"):
            run_admitted_session(
                journal=ExistingJournal(), chat_session_id="new-session-1",
                kernel=RecordingKernel(), expected_mission_id="case-A",
                invocation_id="turn-1", apply_context=None,
                invoke_model=self.model, resolve_source=self.sources.__getitem__,
                reserve=self.reserve, persist=self.persist, readback=self.readback,
            )
        self.assertEqual(self.events, [])
        self.assertEqual(self.reservations, set())
        self.assertEqual(self.saved, {})

    def test_recovered_source_or_cursor_cannot_hide_behind_false_material_flag(self):
        from src.apex_session_gateway import execute_with_recovered_context
        for source_ref, cursor in (("source:original", ""), ("", "cursor:known")):
            with self.subTest(source_ref=source_ref, cursor=cursor):
                recovery = Recovery("case-A", source_ref, cursor, (), (), False)
                with self.assertRaisesRegex(GatewayDenied, "historical context application"):
                    execute_with_recovered_context(
                        journal=recovery, chat_session_id="new-session",
                        kernel=RecordingKernel(), expected_mission_id="case-A",
                        apply_context=None,
                        execute=lambda _: self.fail("source-bearing context must be applied"),
                    )

    def test_continuation_binds_recovered_facts_and_host_application_without_raw_fact_copy(self):
        import json
        from src.apex_session_gateway import _envelope_digest

        facts = ("restricted:source-pointer:fact-1",)
        recovery = Recovery(
            "case-A", "original:user:middle", "cursor-7",
            ("preserve the complete mission scope",), facts, True,
        )
        run_admitted_session(
            journal=recovery, chat_session_id="fact-binding-session",
            kernel=RecordingKernel(), expected_mission_id="case-A",
            invocation_id="fact-binding-turn", apply_context=self.apply,
            invoke_model=self.model, resolve_source=self.sources.__getitem__,
            reserve=self.reserve, persist=self.persist, readback=self.readback,
        )
        checkpoint = next(iter(self.saved.values()))
        expected_facts = "sha256:" + hashlib.sha256(json.dumps(
            list(facts), ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        expected_application = "sha256:" + hashlib.sha256(
            b"application:verified-source"
        ).hexdigest()
        self.assertEqual(checkpoint.recovered_facts_sha256, expected_facts)
        self.assertEqual(checkpoint.application_ref_sha256, expected_application)
        self.assertEqual(checkpoint.digest, _envelope_digest(checkpoint))
        self.assertNotIn(facts[0], repr(checkpoint))

    def test_dropped_fact_binding_is_rejected_by_provider_readback(self):
        from dataclasses import replace
        facts = ("restricted:source-pointer:fact-2",)
        recovery = Recovery(
            "case-A", "original:user:middle", "cursor-7",
            ("preserve the complete mission scope",), facts, True,
        )
        def stripped_readback(key):
            return replace(self.saved[key], recovered_facts_sha256="")
        with self.assertRaisesRegex(GatewayDenied, "readback"):
            run_admitted_session(
                journal=recovery, chat_session_id="fact-binding-session",
                kernel=RecordingKernel(), expected_mission_id="case-A",
                invocation_id="tampered-binding-turn", apply_context=self.apply,
                invoke_model=self.model, resolve_source=self.sources.__getitem__,
                reserve=self.reserve, persist=self.persist,
                readback=stripped_readback,
            )
        self.assertEqual(len(self.saved), 1)

    def test_legacy_continuation_snapshot_does_not_rehash_older_records(self):
        from src.apex_session_gateway import _snapshot
        old = ContinuationEnvelope(
            operation_key="old:model:session:turn", chat_session_id="session",
            mission_id="old", source_ref="source", cursor="cursor",
            corrections=(), response_text="old response", attributions=(),
            memory_proposals=(), digest="",
        )
        snapshot = _snapshot(old)
        self.assertNotIn("recovered_facts_sha256", snapshot)
        self.assertNotIn("application_ref_sha256", snapshot)

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


    def test_model_callback_cannot_erase_recovered_correction_after_admission(self):
        # The model callback is untrusted. Frozen dataclasses can still be
        # mutated with object.__setattr__, so the original correction must be
        # checked again after the model returns and before persistence.
        def malicious_model(receipt):
            object.__setattr__(receipt.recovery, "corrections", ())
            return GatewayModelOutput("tampered response", (), (), ())
        with self.assertRaisesRegex(GatewayDenied, "mutated admitted context"):
            self.invoke(model=malicious_model, invocation_id="model-mutated-correction")
        self.assertEqual(self.saved, {})

    def test_model_callback_cannot_rebind_source_receipt_after_admission(self):
        def malicious_model(receipt):
            object.__setattr__(receipt, "source_ref", "unrelated-source")
            object.__setattr__(receipt, "application_ref", "unrelated-application")
            return GatewayModelOutput(
                "tampered response", (), (), receipt.recovery.corrections,
            )
        with self.assertRaisesRegex(GatewayDenied, "mutated admitted context"):
            self.invoke(model=malicious_model, invocation_id="model-mutated-source")
        self.assertEqual(self.saved, {})

if __name__ == "__main__":
    unittest.main()
