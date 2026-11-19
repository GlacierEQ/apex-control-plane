"""Strict startup recovery regression tests."""
import json
import subprocess
import unittest
from src.mission_startup import recover_authenticated_mission
from src.apex_session_gateway import GatewayDenied

HEAD = "a" * 64
BASE = dict(status="VERIFIED_EXISTING", mission_id="mission", session_id="session",
            head=HEAD, source_ref="spiral-journal:" + HEAD,
            requires_actual_action_application=True,
            automatic_chatgpt_host_hook_verified=False,
            corrections=["Apply recovered correction"], cursor="inspect:evidence",
            facts={"evidence": {"source": "github:repo@sha", "value": "verified"}})

class StrictRecoveryTests(unittest.TestCase):
    def recover(self, raw):
        def runner(*args, **kwargs):
            return subprocess.CompletedProcess(args, 0, raw, "")
        return recover_authenticated_mission(
            bridge="bridge", store="store", spiral_root="spiral",
            mission_id="mission", session_id="session",
            required_fact_keys=("evidence",), runner=runner)

    def test_valid_recovery(self):
        recovery = self.recover(json.dumps(BASE))
        self.assertEqual(recovery.cursor, "inspect:evidence")
        self.assertEqual(recovery.corrections, ("Apply recovered correction",))
        self.assertIn("github:repo@sha", recovery.facts[0])

    def test_nan_rejected(self):
        with self.assertRaises(GatewayDenied):
            self.recover(json.dumps(BASE).replace('"verified"', 'NaN'))

    def test_infinity_rejected(self):
        with self.assertRaises(GatewayDenied):
            self.recover(json.dumps(BASE).replace('"verified"', 'Infinity'))

    def test_duplicate_nested_member_rejected(self):
        with self.assertRaises(GatewayDenied):
            self.recover(json.dumps(BASE).replace('"value": "verified"', '"value": "verified", "value": "forged"'))

    def test_missing_sourced_fact_rejected(self):
        with self.assertRaises(GatewayDenied):
            self.recover(json.dumps(dict(BASE, facts={})))
