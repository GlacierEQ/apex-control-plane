"""Owner-local startup CLI must recover mission policy from private profile on every run."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock
import importlib.util
import json
import os


def entrypoint():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_owned_continuity.py"
    spec = importlib.util.spec_from_file_location("run_owned_continuity", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProfileTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name) / "mission-profile.json"
        self.policy = {
            "schema": "glaciereq.owned-mission-profile/1",
            "mission_id": "mission-A", "store": "/root/local/store",
            "spiral_root": "/root/local/spiral", "bridge": "/root/local/bridge.py",
            "cloud_store": "/root/local/corpus", "cloud_index_db": "/root/local/index.db",
            "checkpoint_db": "/root/local/checkpoints.db",
            "namespace": "architecture", "source_ids": ["drive:primary:id-A"],
            "expected_cursor": "continue:exact", "required_corrections": ["CONTEXT FIRST"],
            "required_fact_keys": ["owner"]
        }
        self.path.write_text(json.dumps(self.policy))
        self.path.chmod(0o600)

    def tearDown(self):
        self.temp.cleanup()

    def test_private_profile_is_readable_and_supplies_exact_cursor(self):
        loaded = entrypoint().load_profile(self.path)
        self.assertEqual(loaded["expected_cursor"], "continue:exact")
        self.assertEqual(loaded["source_ids"], ["drive:primary:id-A"])

    def test_world_readable_profile_is_rejected(self):
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):
            entrypoint().load_profile(self.path)

    def test_duplicate_json_key_rejected(self):
        self.path.write_text('{"schema":"glaciereq.owned-mission-profile/1","schema":"fake"}')
        with self.assertRaises(ValueError):
            entrypoint().load_profile(self.path)

    def test_profile_symlink_refused(self):
        link = self.path.with_name("link.json")
        link.symlink_to(self.path)
        with self.assertRaises(ValueError):
            entrypoint().load_profile(link)

    def test_missing_source_policy_refused(self):
        self.policy["source_ids"] = []
        self.path.write_text(json.dumps(self.policy))
        with self.assertRaises(ValueError):
            entrypoint().load_profile(self.path)

    def test_owned_run_forwards_exact_policy_without_mutation(self):
        module = entrypoint()
        with mock.patch.object(module, "run_owned_cloud_mission", return_value={"status": "CHECKPOINTED"}) as run:
            result = module.run_profile(self.path, session_id="fresh-2", invocation_id="turn-3")
        self.assertEqual(result["status"], "CHECKPOINTED")
        args = run.call_args.kwargs
        self.assertEqual(args["session_id"], "fresh-2")
        self.assertEqual(args["expected_cursor"], "continue:exact")
        self.assertEqual(args["mission_id"], "mission-A")
        self.assertEqual(args["source_ids"], ["drive:primary:id-A"])
