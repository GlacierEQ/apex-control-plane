"""Real SQLite-backed connector continuation adapter regression tests.

Unlike in-memory mocks these prove restart, durable cursor, no-replay and tamper detection.
The SQLite proof applies to workers sharing a filesystem, NOT native ChatGPT cold boot.
"""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest

from src.connector_mission_router import (
    AdmissionDenied, ConnectorCapability, MissionAdmission, dispatch_once
)
from src.mission_resume import MissionCheckpointStore, ResumeError


class ConnectorContinuationSQLiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "mission.db"
        self.store = MissionCheckpointStore(self.path, mission_id="case-A")
        self.store.initialize(
            mission_id="case-A", operator_objective="Preserve the exact case",
            desired_outcome="Durable, source-bound mission continuation",
            tasks=[{"id":"setup","order":1,"deps":[],"key":"setup-key",
                    "provider":"fixture","expected":"initialized"}]
        )
        self.mission = MissionAdmission("case-A", "case-A", True, "cursor-7",
                                        ("repair-1",), "spiral-journal:"+"a"*64)
        self.capability = ConnectorCapability("fixture", "create", True, True, True)
        self.key = "case-A:fixture:create:op-1"

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, store=None, operation="op-1"):
        ledger = store or self.store
        return dispatch_once(
            self.mission, self.capability, operation,
            ledger.reserve_connector_effect,
            lambda: {"native_id":"provider-10", "private_data":"DO_NOT_PERSIST"},
            lambda r: r["native_id"] == "provider-10",
            persist_continuation=lambda record: ledger.persist_connector_continuation(
                record, receipt_ref=record.native_result["native_id"],
                next_cursor="cursor-8"),
            verify_continuation=ledger.verify_connector_continuation,
        )

    def test_durable_checkpoint_survives_new_python_process(self):
        result = self._run()
        self.assertEqual(result["native_id"], "provider-10")
        script = (
            "import json,sys;"
            "from src.mission_resume import MissionCheckpointStore;"
            "s=MissionCheckpointStore(sys.argv[1],mission_id='case-A');"
            "print(json.dumps(s.load_connector_checkpoint(sys.argv[2])))"
        )
        root = Path(__file__).resolve().parents[1]
        proc = subprocess.run(
            [sys.executable, "-c", script, str(self.path), self.key],
            cwd=root, capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        checkpoint = json.loads(proc.stdout)
        self.assertEqual(checkpoint["cursor"], "cursor-7")
        self.assertEqual(checkpoint["next_cursor"], "cursor-8")
        self.assertEqual(checkpoint["correction_ids"], ["repair-1"])
        self.assertEqual(checkpoint["source_ref"], self.mission.source_ref)
        self.assertEqual(checkpoint["receipt_ref"], "provider-10")
        self.assertEqual(checkpoint["operation_key"], self.key)
        self.assertNotIn("private_data", json.dumps(checkpoint))
        with self.assertRaisesRegex(AdmissionDenied, "already reserved"):
            self._run(store=MissionCheckpointStore(self.path, mission_id="case-A"))

    def test_uncertain_effect_stays_reserved_and_cannot_replay(self):
        self.assertTrue(self.store.reserve_connector_effect(self.key))
        self.assertFalse(self.store.reserve_connector_effect(self.key))
        self.assertIsNone(self.store.load_connector_checkpoint(self.key))
        self.assertEqual(self.store.pending_connector_effects(), [self.key])
        attempts=[]
        with self.assertRaisesRegex(AdmissionDenied, "already reserved"):
            dispatch_once(
                self.mission,self.capability,"op-1",
                self.store.reserve_connector_effect,
                lambda: attempts.append("wrong replay"),
                lambda _: True,
                persist_continuation=lambda r: {},
                verify_continuation=lambda _: True,
            )
        self.assertEqual(attempts, [])

    def test_wrong_mission_cannot_reserve_another_mission_key(self):
        before = self.store.pending_connector_effects()
        with self.assertRaisesRegex(ResumeError, "mission"):
            self.store.reserve_connector_effect("case-B:fixture:create:op-1")
        self.assertEqual(self.store.pending_connector_effects(), before)

    def test_parallel_claims_use_database_uniqueness(self):
        def reserve(_):
            return MissionCheckpointStore(self.path, mission_id="case-A").reserve_connector_effect(self.key)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(reserve,range(8)))
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 7)

    def test_checkpoint_tampering_is_not_validated(self):
        self._run()
        with sqlite3.connect(self.path) as db:
            db.execute(
                "UPDATE connector_effect_reservations SET checkpoint_json=? WHERE operation_key=?",
                ('{"cursor":"injected"}', self.key)
            )
        with self.assertRaisesRegex(ResumeError, "integrity"):
            self.store.load_connector_checkpoint(self.key)


if __name__ == "__main__":
    unittest.main()
