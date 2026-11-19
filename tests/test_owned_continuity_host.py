"""Controlled-host execution acceptance tests (synthetic recovery; live CLI tested separately)."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import subprocess
import sys
import unittest

from src.apex_session_gateway import GatewayDenied
from src.cloud_continuity_corpus import ingest_cloud_snapshot
from src.owned_continuity_host import run_owned_cloud_mission, search_cloud_index


class OwnedHostTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.corpus = self.base / "cloud"
        self.db = self.base / "checkpoints.sqlite3"
        self.index = self.base / "search.sqlite3"
        self.mission = "test-glaciereq"
        self.cursor = "continue:verified-source-intake"
        self.correction = "CONTEXT FIRST: verify sources before acting"
        self.items = [
            {"provider": "drive", "account": "primary", "native_id": "doc-A",
             "revision": "rev-1", "namespace": "architecture", "title": "APEX Kernel",
             "url": "https://docs.google.com/document/d/doc-A/edit",
             "modified_at": "2026-11-18T00:00:00Z",
             "extracted_text": "APEX continuity kernel source material"},
            {"provider": "box", "account": "operator", "native_id": "doc-B",
             "revision": "rev-2", "namespace": "architecture", "title": "Case Source Router",
             "url": "https://app.box.com/file/doc-B",
             "modified_at": "2026-11-18T01:00:00Z",
             "extracted_text": "Authoritative source routing for continuity"},
        ]
        ingest_cloud_snapshot(self.corpus, self.items)
        self.sources = ["drive:primary:doc-A", "box:operator:doc-B"]

    def tearDown(self):
        self.temp.cleanup()

    def runner(self, command, **kwargs):
        payload = {
            "status": "VERIFIED_EXISTING", "mission_id": self.mission,
            "session_id": command[-1], "head": "a" * 64,
            "source_ref": "spiral-journal:" + "a" * 64, "cursor": self.cursor,
            "corrections": [self.correction],
            "facts": {"owner": {"source": "notion:operator", "value": "APEX"}},
            "requires_actual_action_application": True,
            "automatic_chatgpt_host_hook_verified": False,
        }
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

    def execute(self, *, session="session-1", turn="turn-1", sources=None, **overrides):
        args = dict(
            bridge=self.base / "bridge.py", store=self.base / "journal",
            spiral_root=self.base / "spiral", mission_id=self.mission,
            session_id=session, invocation_id=turn, cloud_store=self.corpus,
            cloud_index_db=self.index, checkpoint_db=self.db,
            namespace="architecture", source_ids=self.sources if sources is None else sources,
            expected_cursor=self.cursor, required_corrections=(self.correction,),
            required_fact_keys=("owner",), runner=self.runner,
        )
        args.update(overrides)
        return run_owned_cloud_mission(**args)

    def test_real_cloud_documents_become_durable_queryable_index(self):
        result = self.execute()
        self.assertEqual(result["status"], "CHECKPOINTED")
        self.assertEqual(result["source_count"], 2)
        hits = search_cloud_index(self.index, namespace="architecture", query="continuity")
        self.assertEqual({h["source_id"] for h in hits}, set(self.sources))
        self.assertTrue(all(h["revision"] and h["text_sha256"] for h in hits))
        self.assertEqual(result["journal_source_ref"], "spiral-journal:" + "a" * 64)

    def test_replay_of_same_invocation_denied_and_checkpoint_preserved(self):
        first = self.execute()
        with self.assertRaisesRegex(GatewayDenied, "reserved"):
            self.execute()
        self.assertEqual(self.execute(session="session-2", turn="turn-2")["source_count"], 2)
        self.assertEqual(len(search_cloud_index(self.index, namespace="architecture", query="continuity")), 2)
        self.assertEqual(first["checkpoint_key"], "test-glaciereq:model:session-1:turn-1")

    def test_wrong_recovered_cursor_denies_before_index_write(self):
        with self.assertRaises(GatewayDenied):
            self.execute(expected_cursor="continue:wrong")
        self.assertFalse(self.index.exists())

    def test_missing_required_correction_denies_before_index_write(self):
        with self.assertRaises(GatewayDenied):
            self.execute(required_corrections=("contradictory instruction",))
        self.assertFalse(self.index.exists())

    def test_owner_fact_value_and_source_gate_actual_index_action(self):
        self.execute(required_fact_values={"owner": "APEX"},
                     required_fact_sources={"owner": "notion:operator"})
        self.assertTrue(self.index.exists())

    def test_conflicting_fact_value_blocks_index_before_write(self):
        with self.assertRaisesRegex(GatewayDenied, "fact value"):
            self.execute(required_fact_values={"owner": "OTHER"})
        self.assertFalse(self.index.exists())

    def test_substituted_fact_source_blocks_index_before_write(self):
        with self.assertRaisesRegex(GatewayDenied, "fact source"):
            self.execute(required_fact_sources={"owner": "github:other"})
        self.assertFalse(self.index.exists())

    def test_cross_namespace_cloud_source_denied(self):
        with self.assertRaises(ValueError):
            self.execute(namespace="legal")
        self.assertFalse(self.index.exists())

    def test_tampered_cloud_object_denied(self):
        obj = next((self.corpus / "objects").iterdir())
        obj.write_text("changed in place")
        with self.assertRaises(ValueError):
            self.execute()
        self.assertFalse(self.index.exists())

    def test_independent_process_reads_committed_index(self):
        self.execute()
        code = ("import json; from src.owned_continuity_host import search_cloud_index;"
                " print(json.dumps(search_cloud_index(" + repr(str(self.index)) +
                ", namespace='architecture', query='APEX')))")
        completed = subprocess.run([sys.executable, "-c", code], check=True,
                                   capture_output=True, text=True)
        found = json.loads(completed.stdout)
        self.assertEqual([x["source_id"] for x in found], ["drive:primary:doc-A"])

    def test_namespace_search_cannot_cross_matter(self):
        self.execute()
        self.assertEqual(search_cloud_index(self.index, namespace="legal", query="continuity"), [])


if __name__ == "__main__":
    unittest.main()
