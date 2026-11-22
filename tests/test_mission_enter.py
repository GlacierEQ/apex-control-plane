"""Fail-closed, causal mission-entry tests."""
import unittest
from unittest.mock import patch
from scripts.mission_enter import enter

START = {"status": "REGISTERED_HANDLER_EFFECT_VERIFIED",
         "context_packet": {"status": "CONTEXT_PACKET_CREATED",
                            "next_transition": "RESUME_FROM_VERIFIED_CURSOR",
                            "path": "/private/packet.json", "digest": "sha256:" + "a" * 64}}
CONSUMED = {"status": "CONTEXT_CONSUMED_PROVIDER_VERIFIED",
            "next_transition": "RESUME_FROM_VERIFIED_CURSOR",
            "source_evidence": [{"source_id": "box:one"}],
            "recovered_cursor": "continue:work",
            "native_chatgpt_startup_verified": False}
KW = dict(owner_script="owner.py", profile="profile.json", session_id="new",
          invocation_id="turn", output_dir="private", database="cursor.sqlite")


class MissionEnterTests(unittest.TestCase):
    @patch("scripts.mission_enter._run", side_effect=[START, CONSUMED])
    def test_verified_startup_causally_invokes_consumer(self, run):
        out = enter(**KW)
        self.assertEqual(out["context"]["recovered_cursor"], "continue:work")
        self.assertEqual(run.call_count, 2)
        self.assertIn("mission-start", run.call_args_list[0].args[0])
        self.assertIn("context-consume", run.call_args_list[1].args[0])
        self.assertIn("--auto-resume", run.call_args_list[0].args[0])
        self.assertNotIn("--auto-resume", run.call_args_list[1].args[0])

    @patch("scripts.mission_enter._run")
    def test_halted_start_never_consumes(self, run):
        run.return_value = {"status": "DISPATCH_HALTED_UNVERIFIED_CONTEXT"}
        with self.assertRaises(ValueError):
            enter(**KW)
        self.assertEqual(run.call_count, 1)

    @patch("scripts.mission_enter._run")
    def test_conflicting_packet_never_consumes(self, run):
        run.return_value = {**START, "context_packet": {
            **START["context_packet"], "next_transition": "RECONCILE_SOURCE_CONFLICT"}}
        with self.assertRaises(ValueError):
            enter(**KW)
        self.assertEqual(run.call_count, 1)

    @patch("scripts.mission_enter._run", side_effect=[
        START, {**CONSUMED, "status": "CONTEXT_UNVERIFIED"}])
    def test_unverified_consumer_denied(self, run):
        with self.assertRaises(ValueError):
            enter(**KW)

    @patch("scripts.mission_enter._run", side_effect=[
        START, {**CONSUMED, "native_chatgpt_startup_verified": True}])
    def test_false_host_claim_denied(self, run):
        with self.assertRaises(ValueError):
            enter(**KW)

    @patch("scripts.mission_enter._run", side_effect=[
        START, {**CONSUMED, "source_evidence": []}])
    def test_missing_evidence_denied(self, run):
        with self.assertRaises(ValueError):
            enter(**KW)
