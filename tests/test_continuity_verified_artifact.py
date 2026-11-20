import json
import os
from pathlib import Path
import tempfile
import unittest
from scripts.continuity_verified_artifact import apply_verified_handoff

class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        os.chmod(self.path, 0o700)
        self.receipt = dict(status="STARTUP_DECISION_VERIFIED",
            registered_action="VERIFY_REQUIRED_RETRIEVED_SOURCES",
            action_result="REQUIRED_RETRIEVED_SOURCES_VERIFIED",
            action_source_ids=["source-a"], key="mission:startup:s:i",
            startup_receipt_digest="sha256:" + "a"*64,
            retrieval_digest="sha256:" + "b"*64,
            recovered_cursor="cursor", checkpoint_digest="sha256:checkpoint",
            journal_source_ref="journal")
    def test_create_replay_and_conflict(self):
        first = apply_verified_handoff(self.receipt, output_dir=self.path)
        self.assertEqual(first["status"], "HANDOFF_CREATED")
        self.assertEqual(apply_verified_handoff(self.receipt, output_dir=self.path)["status"], "HANDOFF_REPLAY_VERIFIED")
        self.assertEqual(json.loads(Path(first["path"]).read_text())["recovered_cursor"], "cursor")
        changed = dict(self.receipt, recovered_cursor="attacker")
        with self.assertRaisesRegex(ValueError, "conflict"):
            apply_verified_handoff(changed, output_dir=self.path)
    def test_unverified_denied(self):
        for field in ("status", "registered_action", "action_result"):
            bad = dict(self.receipt, **{field: "bad"})
            with self.assertRaises(ValueError):
                apply_verified_handoff(bad, output_dir=self.path)
        self.assertEqual(list(self.path.iterdir()), [])
    def test_incomplete_write_denied(self):
        (self.path / ("a"*64 + ".json")).write_text("partial")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            apply_verified_handoff(self.receipt, output_dir=self.path)
    def test_private_directory_required(self):
        os.chmod(self.path, 0o755)
        with self.assertRaisesRegex(ValueError, "owner-private"):
            apply_verified_handoff(self.receipt, output_dir=self.path)
if __name__ == "__main__":
    unittest.main()
