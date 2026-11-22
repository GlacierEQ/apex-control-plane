"""Source-bound continuity startup packet coverage."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import run_owned_continuity as owner
from scripts.continuity_context_packet import publish_context_packet, read_context_packet


class StartupContextPacketTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        os.chmod(self.root, 0o700)
        self.profile = {"mission_id": "glaciereq", "namespace": "test-scope",
                        "cloud_index_db": str(self.root / "index.sqlite"),
                        "startup_search_query": "evidence",
                        "startup_required_source_ids": ["drive:one"]}
        self.hits = [{"source_id": "drive:one", "revision": "v1", "title": "Evidence",
                      "url": "https://example.com/one", "text_sha256": "a"*64,
                      "excerpt": "evidence for recovery"}]
        self.receipt = {"status": "STARTUP_DECISION_VERIFIED", "key": "m:startup:s:i",
                        "startup_receipt_digest": "sha256:"+"b"*64,
                        "checkpoint_digest": "sha256:prior", "journal_source_ref": "journal",
                        "recovered_cursor": "continue:real-work",
                        "registered_action": "VERIFY_REQUIRED_RETRIEVED_SOURCES",
                        "action_result": "REQUIRED_RETRIEVED_SOURCES_VERIFIED",
                        "action_source_ids": ["drive:one"]}
        self.prior = {"status": "CHECKPOINT_VERIFIED", "checkpoint_digest": "sha256:prior",
                      "journal_source_ref": "journal", "cursor": "continue:real-work",
                      "corrections_applied": ["CONTEXT FIRST"],
                      "completed_action": {"action": "index_cloud", "source_ids": ["drive:one"]}}
        self.bind()

    def bind(self):
        evidence = {"query": self.profile["startup_search_query"], "hits": self.hits}
        self.receipt["retrieval_digest"] = "sha256:" + hashlib.sha256(
            json.dumps(evidence, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False).encode()).hexdigest()

    def publish(self):
        return publish_context_packet(self.receipt, profile=self.profile,
                                      checkpoint=self.prior, hits=self.hits,
                                      output_dir=self.root)

    def test_recovered_context_is_durable_and_replay_safe(self):
        first = self.publish()
        self.assertEqual(first["status"], "CONTEXT_PACKET_CREATED")
        packet = read_context_packet(first["path"], expected_digest=first["digest"])
        self.assertEqual(packet["source_evidence"][0]["excerpt"], "evidence for recovery")
        self.assertEqual(packet["verified_corrections"], ["CONTEXT FIRST"])
        self.assertEqual(packet["next_transition"], "RESUME_FROM_VERIFIED_CURSOR")
        self.assertEqual(packet["previously_completed_action"]["action"], "index_cloud")
        self.assertEqual(self.publish()["status"], "CONTEXT_PACKET_REPLAY_VERIFIED")

    def test_retrieval_change_is_rejected(self):
        self.hits[0]["excerpt"] = "unverified contents"
        with self.assertRaisesRegex(ValueError, "retrieval digest"):
            self.publish()

    def test_cursor_change_is_rejected(self):
        self.receipt["recovered_cursor"] = "continue:other"
        with self.assertRaisesRegex(ValueError, "checkpoint"):
            self.publish()

    def test_multi_revision_conflict_blocks_resume(self):
        self.hits.append({**self.hits[0], "revision": "v2", "text_sha256": "f"*64})
        self.bind()
        result = self.publish()
        packet = read_context_packet(result["path"], expected_digest=result["digest"])
        self.assertEqual(packet["next_transition"], "RECONCILE_SOURCE_CONFLICT")
        self.assertEqual(packet["conflicting_source_ids"], ["drive:one"])

    def test_existing_packet_modification_fails_readback_and_replay(self):
        first = self.publish()
        Path(first["path"]).write_text('{"replaced":true}')
        with self.assertRaises(ValueError):
            read_context_packet(first["path"], expected_digest=first["digest"])
        with self.assertRaises(ValueError):
            self.publish()


class OwnedMissionStartupPacketTest(StartupContextPacketTest):
    def test_mission_start_emits_verified_context_packet(self):
        receipt = dict(self.receipt, prior_session_id="old", prior_invocation_id="first")
        with (patch.object(owner, "dispatch_verified_next_handler",
                           return_value={"status": "REGISTERED_HANDLER_EFFECT_VERIFIED"}),
              patch.object(owner, "read_startup_decision", return_value=receipt),
              patch.object(owner, "load_profile", return_value=self.profile),
              patch.object(owner, "read_checkpoint", return_value=self.prior),
              patch.object(owner, "search_cloud_index", return_value=self.hits)):
            result = owner.run_mission_start_with_context(
                Path("/private/profile.json"), session_id="new", invocation_id="second",
                output_dir=self.root, database=self.root / "provider.sqlite")
        self.assertEqual(result["context_packet"]["next_transition"],
                         "RESUME_FROM_VERIFIED_CURSOR")
        contents = read_context_packet(result["context_packet"]["path"],
                                       expected_digest=result["context_packet"]["digest"])
        self.assertEqual(contents["recovered_cursor"], "continue:real-work")

    def test_no_packet_on_unverified_dispatch(self):
        with (patch.object(owner, "dispatch_verified_next_handler",
                           return_value={"status": "DISPATCH_HALTED_UNVERIFIED_CONTEXT"}),
              patch.object(owner, "search_cloud_index") as search):
            result = owner.run_mission_start_with_context(
                Path("/private/profile.json"), session_id="new", invocation_id="second",
                output_dir=self.root, database=self.root / "provider.sqlite")
        self.assertEqual(result["status"], "DISPATCH_HALTED_UNVERIFIED_CONTEXT")
        search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
