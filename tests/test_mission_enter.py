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
            "source_evidence": [{"source_id": "box:one", "text_sha256": "b" * 64}],
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


class StrictOwnerResponseTests(unittest.TestCase):
    @patch('scripts.mission_enter.subprocess.run')
    def test_duplicate_top_level_status_rejected(self, run):
        from scripts.mission_enter import _run
        run.return_value.returncode = 0
        run.return_value.stdout = '{"status":"DENIED","status":"REGISTERED_HANDLER_EFFECT_VERIFIED"}'
        with self.assertRaises(ValueError):
            _run(['owner'])

    @patch('scripts.mission_enter.subprocess.run')
    def test_duplicate_nested_packet_member_rejected(self, run):
        from scripts.mission_enter import _run
        run.return_value.returncode = 0
        run.return_value.stdout = '{"context_packet":{"digest":"bad","digest":"sha256:good"}}'
        with self.assertRaises(ValueError):
            _run(['owner'])

    @patch('scripts.mission_enter.subprocess.run')
    def test_nonfinite_owner_json_rejected(self, run):
        from scripts.mission_enter import _run
        run.return_value.returncode = 0
        run.return_value.stdout = '{"status":NaN}'
        with self.assertRaises(ValueError):
            _run(['owner'])

    @patch('scripts.mission_enter._run', side_effect=[START, {**CONSUMED, 'recovered_cursor': '  '}])
    def test_empty_recovered_cursor_denied_at_entry(self, run):
        with self.assertRaises(ValueError):
            enter(**KW)
        self.assertEqual(run.call_count, 2)


class VerifiedEvidenceBoundaryTests(unittest.TestCase):
    @patch("scripts.mission_enter._run", side_effect=[
        {**START, "context_packet": {**START["context_packet"], "digest": "sha256:bad"}}, CONSUMED])
    def test_malformed_packet_digest_never_consumes(self, run):
        with self.assertRaises(ValueError):
            enter(**KW)
        self.assertEqual(run.call_count, 1)

    @patch("scripts.mission_enter._run", side_effect=[START, {
        **CONSUMED, "source_evidence": [{"source_id": "box:one", "text_sha256": "0" * 63 + "G"}]}])
    def test_invalid_source_digest_rejected(self, run):
        with self.assertRaises(ValueError):
            enter(**KW)

    @patch("scripts.mission_enter._run", side_effect=[START, {
        **CONSUMED, "source_evidence": ["unstructured"]}])
    def test_unstructured_evidence_rejected(self, run):
        with self.assertRaises(ValueError):
            enter(**KW)
