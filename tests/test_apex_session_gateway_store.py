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

    def test_sqlite_fact_binding_survives_cross_process_without_raw_fact_leak(self):
        recovery = Recovery(
            "case-A", "original:user:middle", "cursor-7",
            ("preserve the complete mission scope",),
            ("restricted:case-source-pointer:fact-A",), True,
        )
        run_admitted_session(
            journal=recovery, chat_session_id="fact-session",
            kernel=RecordingKernel(), expected_mission_id="case-A",
            invocation_id="fact-turn", apply_context=self.apply,
            invoke_model=self.model, resolve_source=self._source,
            reserve=self.store.reserve, persist=self.store.persist,
            readback=self.store.readback,
        )
        key = "case-A:model:fact-session:fact-turn"
        with sqlite3.connect(self.db) as conn:
            payload = conn.execute(
                "SELECT envelope_json FROM apex_session_gateway_continuations "
                "WHERE operation_key=?", (key,),
            ).fetchone()[0]
        self.assertNotIn("restricted:case-source-pointer:fact-A", payload)
        code = (
            "import json,sys;"
            "from src.apex_session_gateway_store import GatewayCheckpointStore;"
            "e=GatewayCheckpointStore(sys.argv[1], mission_id='case-A').readback(sys.argv[2]);"
            "print(json.dumps({'facts':e.recovered_facts_sha256,"
            "'application':e.application_ref_sha256,'digest':e.digest}))"
        )
        run = subprocess.run(
            [sys.executable, "-c", code, str(self.db), key],
            cwd=str(Path(__file__).resolve().parents[1]),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True,
        )
        proof = json.loads(run.stdout)
        self.assertTrue(proof["facts"].startswith("sha256:"))
        self.assertTrue(proof["application"].startswith("sha256:"))
        self.assertTrue(proof["digest"].startswith("sha256:"))

    def test_sqlite_rejects_missing_fact_binding_on_readback(self):
        recovery = Recovery(
            "case-A", "original:user:middle", "cursor-7",
            ("preserve the complete mission scope",), ("fact-pointer",), True,
        )
        run_admitted_session(
            journal=recovery, chat_session_id="fact-tamper",
            kernel=RecordingKernel(), expected_mission_id="case-A",
            invocation_id="fact-turn", apply_context=self.apply,
            invoke_model=self.model, resolve_source=self._source,
            reserve=self.store.reserve, persist=self.store.persist,
            readback=self.store.readback,
        )
        key = "case-A:model:fact-tamper:fact-turn"
        with sqlite3.connect(self.db) as conn:
            payload = json.loads(conn.execute(
                "SELECT envelope_json FROM apex_session_gateway_continuations "
                "WHERE operation_key=?", (key,),
            ).fetchone()[0])
            del payload["recovered_facts_sha256"]
            conn.execute(
                "UPDATE apex_session_gateway_continuations SET envelope_json=? "
                "WHERE operation_key=?", (json.dumps(payload), key),
            )
        with self.assertRaisesRegex(GatewayStoreDenied, "digest|readback"):
            self.store.readback(key)

    def test_fresh_mission_persists_without_invented_source_or_application(self):
        fresh = Recovery("case-A", "", "", (), (), False)
        result = run_admitted_session(
            journal=fresh, chat_session_id="fresh-chat",
            kernel=RecordingKernel(), expected_mission_id="case-A",
            invocation_id="fresh-turn", apply_context=None,
            invoke_model=lambda receipt: GatewayModelOutput("fresh response", (), (), ()),
            resolve_source=self._source, reserve=self.store.reserve,
            persist=self.store.persist, readback=self.store.readback,
        )
        self.assertEqual(result.text, "fresh response")
        checkpoint = self.store.readback("case-A:model:fresh-chat:fresh-turn")
        self.assertEqual(checkpoint.source_ref, "")
        self.assertEqual(checkpoint.cursor, "")
        self.assertEqual(checkpoint.application_ref_sha256, "")
        self.assertTrue(checkpoint.recovered_facts_sha256.startswith("sha256:"))

    def test_cursor_only_history_persists_after_source_matched_application(self):
        # A cursor alone is material recovery, even if the host's flag is false.
        cursor_only = Recovery("case-A", "", "cursor-only", (), (), False)
        result = run_admitted_session(
            journal=cursor_only, chat_session_id="cursor-chat",
            kernel=RecordingKernel(), expected_mission_id="case-A",
            invocation_id="cursor-turn", apply_context=self.apply,
            invoke_model=lambda receipt: GatewayModelOutput("cursor response", (), (), ()),
            resolve_source=self._source, reserve=self.store.reserve,
            persist=self.store.persist, readback=self.store.readback,
        )
        self.assertEqual(result.text, "cursor response")
        checkpoint = self.store.readback("case-A:model:cursor-chat:cursor-turn")
        self.assertEqual(checkpoint.source_ref, "")
        self.assertEqual(checkpoint.cursor, "cursor-only")
        self.assertTrue(checkpoint.application_ref_sha256.startswith("sha256:"))

    def test_persist_rejects_cross_session_checkpoint_even_with_valid_digest(self):
        # A caller may compute a correct content digest while claiming the wrong
        # chat session. The reserved operation key remains the session authority.
        from dataclasses import replace
        from src.apex_session_gateway import ContinuationEnvelope, _envelope_digest
        key = "case-A:model:reserved-chat:turn-a"
        self.assertTrue(self.store.reserve(key))
        envelope = ContinuationEnvelope(
            operation_key=key, chat_session_id="unrelated-chat",
            mission_id="case-A", source_ref="", cursor="", corrections=(),
            response_text="source-neutral response", attributions=(),
            memory_proposals=(), digest="",
        )
        envelope = replace(envelope, digest=_envelope_digest(envelope))
        with self.assertRaisesRegex(GatewayStoreDenied, "session"):
            self.store.persist(envelope)
        with self.assertRaisesRegex(GatewayStoreDenied, "not committed"):
            self.store.readback(key)

    def test_readback_rejects_cross_session_attribution_with_recomputed_digest(self):
        # An unkeyed digest alone cannot establish that stored session metadata
        # belongs to the reservation. Validate the reserved operation identity.
        from hashlib import sha256
        self.invoke()
        key = "case-A:model:new-chat:user-turn-1"
        with sqlite3.connect(self.db) as conn:
            payload = json.loads(conn.execute(
                "SELECT envelope_json FROM apex_session_gateway_continuations "
                "WHERE operation_key=?", (key,),
            ).fetchone()[0])
            payload["chat_session_id"] = "unrelated-chat"
            canonical = json.dumps(
                {k: v for k, v in payload.items() if k != "digest"},
                sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            ).encode("utf-8")
            payload["digest"] = "sha256:" + sha256(canonical).hexdigest()
            conn.execute(
                "UPDATE apex_session_gateway_continuations "
                "SET envelope_json=?,envelope_digest=? WHERE operation_key=?",
                (json.dumps(payload), payload["digest"], key),
            )
        with self.assertRaisesRegex(GatewayStoreDenied, "readback|session|authority"):
            self.store.readback(key)

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
