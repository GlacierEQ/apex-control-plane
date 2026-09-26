import unittest
from src.buildkite_callback_contract import parse_buildkite_callback, verify_webhook_token

class BuildkiteCallbackContractTests(unittest.TestCase):
    def valid(self):
        return {"event":"build.finished","pipeline":{"slug":"verify"},"build":{"number":42,"commit":"abc123","state":"passed","meta_data":{"mission_id":"m1","correlation_id":"c1"}}}
    def test_requires_explicit_secret(self):
        self.assertFalse(verify_webhook_token("x",""))
        self.assertTrue(verify_webhook_token("x","x"))
    def test_missing_event_fails_closed(self):
        p=self.valid(); p.pop("event")
        with self.assertRaises(ValueError): parse_buildkite_callback(p)
    def test_missing_state_fails_closed(self):
        p=self.valid(); p["build"].pop("state")
        with self.assertRaises(ValueError): parse_buildkite_callback(p)
    def test_missing_correlation_fails_closed(self):
        p=self.valid(); p["build"]["meta_data"].pop("correlation_id")
        with self.assertRaises(ValueError): parse_buildkite_callback(p)
    def test_passed_callback_is_not_terminal_verification(self):
        r=parse_buildkite_callback(self.valid())
        self.assertTrue(r["passed_observed"])
        self.assertFalse(r["terminal_provider_verified"])
        self.assertEqual("callback_observation_only",r["authority"])
