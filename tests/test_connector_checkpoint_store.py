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
        self.provider_path = Path(self.tmp.name) / "provider.db"
        with sqlite3.connect(self.provider_path) as db:
            db.execute("CREATE TABLE effects (native_id TEXT PRIMARY KEY, operation_key TEXT NOT NULL)")

    def tearDown(self):
        self.tmp.cleanup()

    def provider_effect(self):
        with sqlite3.connect(self.provider_path) as db:
            db.execute(
                "INSERT OR IGNORE INTO effects VALUES (?,?)",
                ("provider-10",self.key),
            )
        return {"native_id":"provider-10","private_data":"DO_NOT_PERSIST"}

    def provider_readback(self, native_id):
        with sqlite3.connect(self.provider_path) as db:
            row = db.execute("SELECT operation_key FROM effects WHERE native_id=?", (native_id,)).fetchone()
        return row is not None and row[0] == self.key

    def _run(self, store=None, operation="op-1"):
        ledger = store or self.store
        return dispatch_once(
            self.mission, self.capability, operation,
            ledger.reserve_connector_effect,
            self.provider_effect,
            lambda r: self.provider_readback(r["native_id"]),
            persist_continuation=lambda record: ledger.persist_connector_continuation(
                record, receipt_ref=record.native_result["native_id"],
                next_cursor="cursor-8"),
            verify_continuation=ledger.verify_connector_continuation,
        )

    def test_durable_checkpoint_survives_new_python_process(self):
        result = self._run()
        self.assertEqual(result["native_id"], "provider-10")
        script = (
            "import json,sqlite3,sys;"
            "from src.mission_resume import MissionCheckpointStore;"
            "s=MissionCheckpointStore(sys.argv[1],mission_id='case-A');"
            "def_read=lambda p,r: sqlite3.connect(sys.argv[3]).execute('SELECT 1 FROM effects WHERE native_id=?',(r,)).fetchone() is not None;"
            "print(json.dumps(s.recover_connector_checkpoint(sys.argv[2],def_read)))"
        )
        root = Path(__file__).resolve().parents[1]
        proc = subprocess.run(
            [sys.executable, "-c", script, str(self.path), self.key, str(self.provider_path)],
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

    def test_restart_cannot_promote_stale_or_unavailable_provider_claim(self):
        self._run()
        def unavailable(_provider,_ref):
            raise ConnectionError("provider offline")
        with self.assertRaisesRegex(ResumeError, "provider readback"):
            self.store.recover_connector_checkpoint(self.key, unavailable)
        with sqlite3.connect(self.provider_path) as db:
            db.execute("DELETE FROM effects")
        with self.assertRaisesRegex(ResumeError, "provider readback"):
            self.store.recover_connector_checkpoint(self.key, lambda p, r: self.provider_readback(r))
        self.assertIsNotNone(self.store.load_connector_checkpoint(self.key))
        self.assertFalse(self.store.reserve_connector_effect(self.key))

    def test_reserved_operation_resumes_after_restart_with_native_readback(self):
        from src.connector_mission_router import RecoveredEffect
        first = self._run()
        self.assertEqual(first["native_id"], "provider-10")
        replay = MissionCheckpointStore(self.path, mission_id="case-A")
        invoked = []
        def reconcile(key):
            checkpoint = replay.recover_connector_checkpoint(
                key, lambda provider, native_id: self.provider_readback(native_id)
            )
            return RecoveredEffect(
                operation_key=key,
                native_result={"native_id": checkpoint["receipt_ref"]},
                continuation_checkpoint=checkpoint,
            )
        received = dispatch_once(
            self.mission, self.capability, "op-1",
            replay.reserve_connector_effect,
            lambda: invoked.append("duplicate") or self.provider_effect(),
            lambda record: self.provider_readback(record["native_id"]),
            persist_continuation=lambda _: (_ for _ in ()).throw(AssertionError("duplicate continuation")),
            verify_continuation=replay.verify_connector_continuation,
            reconcile_reserved=reconcile,
        )
        self.assertEqual(received["native_id"], "provider-10")
        self.assertEqual(invoked, [])
        with sqlite3.connect(self.provider_path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM effects").fetchone()[0], 1)

    def test_stale_provider_cannot_be_resumed_or_replayed(self):
        from src.connector_mission_router import RecoveredEffect
        self._run()
        with sqlite3.connect(self.provider_path) as db:
            db.execute("DELETE FROM effects")
        replay = MissionCheckpointStore(self.path, mission_id="case-A")
        attempts = []
        def reconcile(key):
            checkpoint = replay.recover_connector_checkpoint(
                key, lambda provider, native_id: self.provider_readback(native_id)
            )
            return RecoveredEffect(key, {"native_id": checkpoint["receipt_ref"]}, checkpoint)
        with self.assertRaisesRegex(AdmissionDenied, "reconciliation failed"):
            dispatch_once(
                self.mission, self.capability, "op-1",
                replay.reserve_connector_effect,
                lambda: attempts.append("duplicate"),
                lambda result: self.provider_readback(result["native_id"]),
                persist_continuation=lambda _: None,
                verify_continuation=replay.verify_connector_continuation,
                reconcile_reserved=reconcile,
            )
        self.assertEqual(attempts, [])

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
