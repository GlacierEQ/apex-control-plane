"""Durable, cross-process admission-store regression for APEX model host."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from src.apex_session_gateway import (
    GatewayModelOutput, MemoryProposal, run_admitted_session,
)
from src.apex_session_gateway_store import GatewayCheckpointStore, GatewayStoreDenied
from src.apex_session_gateway import ContextApplication, Recovery
from tests.test_apex_session_gateway import (
    USER_MIDDLE, assertion,
)


class ExistingJournal:
    def recover(self, session, mission):
        return Recovery(mission_id="case-A", source_ref="original:user:middle", cursor="cursor-7", corrections=("preserve the complete mission scope",), facts=(), material_context_found=True)


class RecordingKernel:
    pass


class GatewaySQLiteIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "apex-continuations.sqlite"
        self.store = GatewayCheckpointStore(self.db, mission_id="case-A")
        self.user_span = assertion("user-message:correction", "user", USER_MIDDLE)
        self.source = {"user-message:correction": USER_MIDDLE.encode("utf-8")}
        self.invocations = []

    @staticmethod
    def apply(recovery):
        return ContextApplication(
            recovery.mission_id, recovery.source_ref, recovery.cursor,
            recovery.corrections, tuple(recovery.facts), "host:applied:source",
        )

    def model(self, receipt):
        self.invocations.append(receipt.mission_id)
        return GatewayModelOutput(
            text="A correction was recorded by the user.",
            attributions=(self.user_span,),
            memory_proposals=(MemoryProposal("user_correction", self.user_span),),
            corrections_applied=receipt.recovery.corrections,
        )

    def invoke(self):
        return run_admitted_session(
            journal=ExistingJournal(), chat_session_id="new-chat",
            kernel=RecordingKernel(), expected_mission_id="case-A",
            invocation_id="user-turn-1", apply_context=self.apply,
            invoke_model=self.model,
            resolve_source=lambda ref: self._source(ref),
            reserve=self.store.reserve, persist=self.store.persist,
            readback=self.store.readback,
        )

    def _source(self, ref):
        from src.apex_session_gateway import OriginRecord
        return OriginRecord("user", self.source[ref])

    def test_actual_sqlite_store_survives_new_process_with_authorship_and_corrections(self):
        result = self.invoke()
        self.assertIn("correction", result.text)
        self.assertEqual(self.invocations, ["case-A"])
        self.assertEqual(os.stat(self.db).st_mode & 0o077, 0)
        key = "case-A:model:new-chat:user-turn-1"
        code = (
            "import json,sys;"
            "from src.apex_session_gateway_store import GatewayCheckpointStore;"
            "e=GatewayCheckpointStore(sys.argv[1], mission_id='case-A').readback(sys.argv[2]);"
            "print(json.dumps({'mission':e.mission_id,'speaker':e.memory_proposals[0].source.speaker,"
            "'corrections':list(e.corrections),'authority':e.memory_authority,"
            "'author':e.response_author,'digest':e.digest}))"
        )
        run = subprocess.run(
            [sys.executable, "-c", code, str(self.db), key],
            cwd=str(Path(__file__).resolve().parents[1]),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True,
        )
        proof = json.loads(run.stdout)
        self.assertEqual(proof["mission"], "case-A")
        self.assertEqual(proof["speaker"], "user")
        self.assertEqual(proof["authority"], "SOURCE_CANDIDATE_ONLY")
        self.assertEqual(proof["author"], "assistant")
        self.assertEqual(proof["corrections"], ["preserve the complete mission scope"])
        self.assertTrue(proof["digest"].startswith("sha256:"))

    def test_cross_process_replay_is_denied_before_another_model_call(self):
        self.invoke()
        with self.assertRaisesRegex(Exception, "already reserved"):
            self.invoke()
        self.assertEqual(len(self.invocations), 1)

    def test_sqlite_atomic_reservation_has_one_winner_for_concurrent_workers(self):
        key = "case-A:model:concurrent-chat:concurrent-turn"
        def claim(_):
            store = GatewayCheckpointStore(self.db, mission_id="case-A")
            return store.reserve(key)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(claim, range(30)))
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 29)

    def test_tampered_storage_never_passes_readback(self):
        self.invoke()
        key = "case-A:model:new-chat:user-turn-1"
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                "UPDATE apex_session_gateway_continuations SET envelope_json=? WHERE operation_key=?",
                ('{"response_text":"tampered"}', key),
            )
        with self.assertRaisesRegex(GatewayStoreDenied, "readback|digest|invalid"):
            self.store.readback(key)

    def test_wrong_mission_cannot_claim_or_read_another_mission_checkpoint(self):
        wrong = GatewayCheckpointStore(self.db, mission_id="another-mission")
        with self.assertRaisesRegex(GatewayStoreDenied, "mission"):
            wrong.reserve("case-A:model:session:turn")
        self.invoke()
        with self.assertRaisesRegex(GatewayStoreDenied, "mission"):
            wrong.readback("case-A:model:new-chat:user-turn-1")

    def test_unsafe_symlink_db_path_is_denied(self):
        alias = Path(self.tmp.name) / "alias.db"
        alias.symlink_to(self.db)
        with self.assertRaisesRegex(GatewayStoreDenied, "symlink|regular"):
            GatewayCheckpointStore(alias, mission_id="case-A")


if __name__ == "__main__":
    unittest.main()
