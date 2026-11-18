import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from cloud_continuity_corpus import ingest_cloud_snapshot, recover_cloud_context, dispatch_cloud_action


def doc(provider="drive", native_id="file-A", namespace="architecture", text="APEX source facts"):
    return {
        "provider": provider, "account": "operator", "native_id": native_id,
        "revision": "rev-1", "namespace": namespace,
        "title": f"{provider}-{native_id}", "url": f"https://example.net/{native_id}",
        "extracted_text": text, "modified_at": "2026-11-18T00:00:00Z",
    }


class CloudCorpusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name) / "corpus"

    def tearDown(self):
        self.tmp.cleanup()

    def test_two_clouds_and_matter_namespace_are_isolated(self):
        ingest_cloud_snapshot(self.root, [doc(), doc("box", "file-B", "legal", "Legal fact")])
        context = recover_cloud_context(self.root, namespace="architecture", required_source_ids=["drive:operator:file-A"])
        self.assertEqual(context["sources"][0]["text"], "APEX source facts")
        with self.assertRaises(ValueError):
            recover_cloud_context(self.root, namespace="architecture", required_source_ids=["box:operator:file-B"])

    def test_idempotency_and_prior_revision_preservation(self):
        ingest_cloud_snapshot(self.root, [doc()])
        self.assertEqual(ingest_cloud_snapshot(self.root, [doc()])["new_revisions"], 0)
        revised = doc(text="New authoritative content")
        revised["revision"] = "rev-2"
        ingest_cloud_snapshot(self.root, [revised])
        context = recover_cloud_context(self.root, namespace="architecture", required_source_ids=["drive:operator:file-A"])
        self.assertEqual(context["sources"][0]["revision"], "rev-2")
        self.assertEqual(len(json.loads((self.root / "manifest.json").read_text())["revisions"]), 2)

    def test_same_revision_conflict_rejected_without_manifest_mutation(self):
        ingest_cloud_snapshot(self.root, [doc()])
        first = (self.root / "manifest.json").read_bytes()
        with self.assertRaises(ValueError):
            ingest_cloud_snapshot(self.root, [doc(text="CHANGED WITHOUT REVISION")])
        self.assertEqual((self.root / "manifest.json").read_bytes(), first)

    def test_sha256_verification_fails_closed(self):
        ingest_cloud_snapshot(self.root, [doc()])
        next((self.root / "objects").iterdir()).write_text("tampered")
        with self.assertRaises(ValueError):
            recover_cloud_context(self.root, namespace="architecture", required_source_ids=["drive:operator:file-A"])

    def test_metadata_only_is_not_content(self):
        ingest_cloud_snapshot(self.root, [doc(text=None)])
        with self.assertRaises(ValueError):
            recover_cloud_context(self.root, namespace="architecture", required_source_ids=["drive:operator:file-A"])
        result = recover_cloud_context(self.root, namespace="architecture", required_source_ids=["drive:operator:file-A"], require_text=False)
        self.assertEqual(result["sources"][0]["content_state"], "METADATA_ONLY")

    def test_account_id_is_part_of_source_identity(self):
        a, b = doc(text="one"), doc(text="two")
        b["account"] = "other"
        ingest_cloud_snapshot(self.root, [a, b])
        result = recover_cloud_context(self.root, namespace="architecture", required_source_ids=["drive:other:file-A"])
        self.assertEqual(result["sources"][0]["text"], "two")

    def test_stale_ingestion_does_not_roll_back_provider_revision(self):
        new, old = doc(text="current"), doc(text="stale")
        new["revision"], old["revision"] = "rev-2", "rev-1"
        old["modified_at"] = "2026-10-18T00:00:00Z"
        ingest_cloud_snapshot(self.root, [new])
        ingest_cloud_snapshot(self.root, [old])
        result = recover_cloud_context(self.root, namespace="architecture", required_source_ids=["drive:operator:file-A"])
        self.assertEqual(result["sources"][0]["text"], "current")

    def test_verified_cloud_context_changes_registered_action(self):
        ingest_cloud_snapshot(self.root, [doc(), doc("box", "file-B", "legal", "Legal fact")])
        handlers = {"continue": lambda ctx: ctx["sources"][0]["text"],
                    "review": lambda ctx: "review:" + ctx["sources"][0]["text"]}
        common = dict(root=self.root, namespace="architecture", handlers=handlers, required_source_ids=["drive:operator:file-A"])
        self.assertEqual(dispatch_cloud_action(action="continue", **common), "APEX source facts")
        self.assertEqual(dispatch_cloud_action(action="review", **common), "review:APEX source facts")
        with self.assertRaises(ValueError):
            dispatch_cloud_action(self.root, namespace="architecture", action="review", handlers=handlers, required_source_ids=["box:operator:file-B"])
        with self.assertRaises(ValueError):
            dispatch_cloud_action(action="shell", **common)

if __name__ == "__main__":
    unittest.main()
