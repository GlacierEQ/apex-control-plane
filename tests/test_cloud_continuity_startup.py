import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

from cloud_continuity_corpus import ingest_cloud_snapshot


def startup_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "continuity_mission_entrypoint.py"
    spec = importlib.util.spec_from_file_location("continuity_mission_entrypoint", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CloudStartupTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.corpus = Path(self.tmp.name) / "corpus"
        ingest_cloud_snapshot(self.corpus, [{
            "provider": "drive", "account": "operator", "native_id": "file-A",
            "revision": "r1", "namespace": "architecture", "title": "Source A",
            "url": "https://drive.google.com/file/d/file-A/view",
            "extracted_text": "APEX FROM DRIVE", "modified_at": "2026-11-18T00:00:00Z",
        }])

    def tearDown(self):
        self.tmp.cleanup()

    def _invoke(self, module, *, cloud_sources, handler):
        with mock.patch.object(module, "start_context_gated_mission", side_effect=lambda **kwargs: kwargs["handlers"]["continue"]({"cursor": "continue:build", "action_name": "continue", "result": {"verified_facts": {}, "instructions_to_apply": []}})):
            return module.start_cloud_context_gated_mission(
                store=Path("store"), spiral_root=Path("spiral"), mission_id="mission", session_id="session",
                cloud_store=self.corpus, cloud_namespace="architecture",
                handlers={"continue": handler}, cloud_sources_by_action={"continue": cloud_sources},
                required_corrections={"continue": ()}, required_fact_keys={"continue": ()})

    def test_cloud_sources_reach_real_consumer_after_gated_dispatch(self):
        mod = startup_module()
        result = self._invoke(mod, cloud_sources=("drive:operator:file-A",), handler=lambda bundle: (bundle["recovery"]["cursor"], bundle["cloud_context"]["sources"][0]["text"]))
        self.assertEqual(result, ("continue:build", "APEX FROM DRIVE"))

    def test_missing_source_prevents_consumer(self):
        mod = startup_module()
        handler = mock.Mock()
        with self.assertRaises(ValueError):
            self._invoke(mod, cloud_sources=("box:operator:missing",), handler=handler)
        handler.assert_not_called()

    def test_missing_explicit_cloud_action_policy_rejected(self):
        mod = startup_module()
        handler = mock.Mock()
        with mock.patch.object(mod, "start_context_gated_mission", side_effect=lambda **kwargs: kwargs["handlers"]["continue"]({"cursor": "continue:x", "action_name": "continue"})):
            with self.assertRaises(ValueError):
                mod.start_cloud_context_gated_mission(
                    store=Path("store"), spiral_root=Path("spiral"), mission_id="mission", session_id="session",
                    cloud_store=self.corpus, cloud_namespace="architecture", handlers={"continue": handler},
                    cloud_sources_by_action={}, required_corrections={"continue": ()}, required_fact_keys={"continue": ()})
        handler.assert_not_called()
