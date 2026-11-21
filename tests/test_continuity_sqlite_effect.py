import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from scripts.continuity_sqlite_effect import apply_cursor_once, readback_cursor_once


class SQLiteEffectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        os.chmod(self.root, 0o700)
        self.db = self.root / "provider.sqlite"
        self.receipt = dict(status="STARTUP_DECISION_VERIFIED",
            registered_action="VERIFY_REQUIRED_RETRIEVED_SOURCES",
            action_result="REQUIRED_RETRIEVED_SOURCES_VERIFIED",
            action_source_ids=["source-a"], key="mission:startup:s:i",
            startup_receipt_digest="sha256:"+"a"*64,
            retrieval_digest="sha256:"+"b"*64, recovered_cursor="continue:verified",
            checkpoint_digest="sha256:checkpoint", journal_source_ref="journal")

    def test_real_durable_effect_restart_readback_and_no_repeat(self):
        self.assertEqual(readback_cursor_once(self.receipt, handoff_dir=self.root,
                         database=self.db)["status"], "OPERATION_NOT_CLAIMED")
        first = apply_cursor_once(self.receipt, handoff_dir=self.root, database=self.db)
        self.assertEqual(first["status"], "OPERATION_INVOKED_RECONCILIATION_REQUIRED")
        self.assertEqual(apply_cursor_once(self.receipt, handoff_dir=self.root,
                         database=self.db)["status"], "OPERATION_RECONCILIATION_REQUIRED")
        self.assertEqual(readback_cursor_once(self.receipt, handoff_dir=self.root,
                         database=self.db)["status"], "OPERATION_EFFECT_PROVIDER_VERIFIED")
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM applied_cursor").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT cursor FROM applied_cursor").fetchone()[0], "continue:verified")

    def test_claim_without_effect_stays_pending(self):
        from scripts.continuity_verified_artifact import consume_once_verified_handoff
        consume_once_verified_handoff(self.receipt, output_dir=self.root,
                  operation_name="apply_recovered_cursor", handler=lambda payload, identity: None)
        self.assertEqual(readback_cursor_once(self.receipt, handoff_dir=self.root,
                         database=self.db)["status"], "OPERATION_RECONCILIATION_REQUIRED")

    def test_conflicting_provider_row_denied(self):
        first = apply_cursor_once(self.receipt, handoff_dir=self.root, database=self.db)
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE applied_cursor SET cursor='forged' WHERE identity=?", (first["identity"],))
        with self.assertRaisesRegex(ValueError, "conflicts"):
            readback_cursor_once(self.receipt, handoff_dir=self.root, database=self.db)

    def test_tampered_handoff_denied(self):
        apply_cursor_once(self.receipt, handoff_dir=self.root, database=self.db)
        changed = dict(self.receipt, recovered_cursor="malicious")
        with self.assertRaises(ValueError):
            readback_cursor_once(changed, handoff_dir=self.root, database=self.db)


if __name__ == "__main__":
    unittest.main()
