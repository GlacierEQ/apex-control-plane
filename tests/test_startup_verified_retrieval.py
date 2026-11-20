"""Regression tests for source-verified startup retrieval in the owning consumer."""
import hashlib
import json
import unittest
from unittest.mock import patch
from pathlib import Path

from scripts import run_owned_continuity as host


class StartupRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "mission_id": "mission-one", "namespace": "scope-one",
            "cloud_index_db": "/private/index.sqlite3",
            "startup_search_query": "important evidence",
        }
        self.prior = {
            "decision": "DO_NOT_REPEAT_COMPLETED_INDEX",
            "checkpoint_digest": "sha256:checkpoint",
            "journal_source_ref": "spiral-journal:" + "a" * 64,
            "recovered_cursor": "continue:next",
        }
        self.hits = [{
            "source_id": "drive:doc-1", "revision": "r1",
            "text_sha256": "a" * 64, "excerpt": "important evidence",
        }]

    def test_resume_consumes_recovered_evidence_before_receipt(self):
        with (patch.object(host, "load_profile", return_value=self.profile),
              patch.object(host, "decide_next_action", return_value=self.prior),
              patch.object(host, "search_cloud_index", return_value=self.hits) as search,
              patch.object(host, "persist_startup_decision", return_value={"startup_receipt_key": "k"}) as persist):
            result = host.run_profile(Path("/private/profile.json"),
                                      session_id="new", invocation_id="turn",
                                      previous_session_id="old", previous_invocation_id="prior")
        self.assertEqual(result["decision"], "RETRIEVE_VERIFIED_EVIDENCE")
        self.assertEqual(result["retrieval_source_ids"], ["drive:doc-1"])
        self.assertFalse(result["index_executed"])
        self.assertEqual(persist.call_args.kwargs["decision"]["retrieval_digest"], result["retrieval_digest"])
        search.assert_called_once()

    def test_empty_retrieval_fails_before_persist(self):
        with (patch.object(host, "load_profile", return_value=self.profile),
              patch.object(host, "decide_next_action", return_value=self.prior),
              patch.object(host, "search_cloud_index", return_value=[]),
              patch.object(host, "persist_startup_decision") as persist):
            with self.assertRaisesRegex(ValueError, "no verified evidence"):
                host.run_profile(Path("/private/profile.json"),
                                 session_id="new", invocation_id="turn",
                                 previous_session_id="old", previous_invocation_id="prior")
            persist.assert_not_called()

    def test_unbounded_query_fails_before_search(self):
        self.profile["startup_search_query"] = "x" * 513
        with (patch.object(host, "load_profile", return_value=self.profile),
              patch.object(host, "decide_next_action", return_value=self.prior),
              patch.object(host, "search_cloud_index") as search):
            with self.assertRaisesRegex(ValueError, "bounded startup"):
                host.run_profile(Path("/private/profile.json"),
                                 session_id="new", invocation_id="turn",
                                 previous_session_id="old", previous_invocation_id="prior")
            search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
