"""The unfunded acceptance test must fail when any safety fact is false."""

import importlib.util
import os
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).with_name("verify-empty-stack.py")
SPEC = importlib.util.spec_from_file_location("empty_stack_verifier", SCRIPT)
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


def healthy_responses():
    return {
        "/accounts/": ["master_account"],
        "/accounts/master_account/credentials": [],
        "/portfolio/state": {"master_account": {}},
        "/bot-orchestration/status": {"status": "success", "data": {}},
        "/bot-orchestration/mqtt": {"data": {"mqtt_connected": True}},
        "/api/v1/auth/mode": {"mode": "local"},
        "/api/v1/auth/local-login": {"token": "test-only-token"},
        "/api/v1/servers": [{"name": "paper", "online": True}],
        "/api/v1/servers/paper/status": {"status": "online"},
        "/api/tags": {"models": [{"name": "qwen3:0.6b"}]},
        "/api/generate": {"done": True, "response": "READY"},
    }


class EmptyStackAcceptanceTests(unittest.TestCase):
    def verify_with(self, responses):
        def fake_request(url, **_kwargs):
            for path in sorted(responses, key=len, reverse=True):
                if url.endswith(path):
                    return deepcopy(responses[path])
            raise AssertionError(f"Unexpected endpoint: {url}")

        with patch.dict(os.environ, {"PAPER_API_USER": "test", "PAPER_API_PASSWORD": "test"}):
            with patch.object(VERIFIER, "request_json", side_effect=fake_request):
                VERIFIER.verify()

    def test_ready_requires_all_positive_receipts(self):
        self.verify_with(healthy_responses())

    def test_host_can_use_an_existing_free_model(self):
        data = healthy_responses()
        data["/api/tags"] = {"models": [{"name": "deepseek-r1:1.5b"}]}
        with patch.dict(os.environ, {"PAPER_MODEL_NAME": "deepseek-r1:1.5b"}):
            self.verify_with(data)

    def test_rejects_stored_exchange_credentials(self):
        data = healthy_responses()
        data["/accounts/master_account/credentials"] = ["coinbase_advanced_trade"]
        with self.assertRaisesRegex(AssertionError, "trading credentials"):
            self.verify_with(data)

    def test_rejects_nonzero_real_asset_balance(self):
        data = healthy_responses()
        data["/portfolio/state"] = {"master_account": {"coinbase": [{"units": 0.01}]}}
        with self.assertRaisesRegex(AssertionError, "Nonzero asset balance"):
            self.verify_with(data)

    def test_allows_zero_balance_entries(self):
        data = healthy_responses()
        data["/portfolio/state"] = {"master_account": {"paper": [{"units": 0, "usd_value": 0}]}}
        self.verify_with(data)

    def test_rejects_running_bot(self):
        data = healthy_responses()
        data["/bot-orchestration/status"] = {"status": "success", "data": {"live": {"running": True}}}
        with self.assertRaisesRegex(AssertionError, "running bot"):
            self.verify_with(data)

    def test_rejects_disconnected_broker(self):
        data = healthy_responses()
        data["/bot-orchestration/mqtt"] = {"data": {"mqtt_connected": False}}
        with self.assertRaisesRegex(AssertionError, "broker"):
            self.verify_with(data)

    def test_rejects_offline_condor_api_bridge(self):
        data = healthy_responses()
        data["/api/v1/servers"] = [{"name": "paper", "online": False}]
        with self.assertRaisesRegex(AssertionError, "cannot reach"):
            self.verify_with(data)

    def test_rejects_missing_local_model(self):
        data = healthy_responses()
        data["/api/tags"] = {"models": []}
        with self.assertRaisesRegex(AssertionError, "model"):
            self.verify_with(data)

    def test_rejects_empty_inference(self):
        data = healthy_responses()
        data["/api/generate"] = {"done": True, "response": ""}
        with self.assertRaisesRegex(AssertionError, "inference"):
            self.verify_with(data)


if __name__ == "__main__":
    unittest.main()
