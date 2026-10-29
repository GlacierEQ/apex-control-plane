"""Regression checks for Supabase validator error classification."""
import importlib.util
import pathlib
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

path = pathlib.Path(__file__).resolve().parents[1] / "connectors" / "supabase_validator.py"
spec = importlib.util.spec_from_file_location("supabase_validator", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ValidatorTests(unittest.TestCase):
    def check_http(self, status):
        error = HTTPError("https://example.invalid/rest/v1/", status, "test", {}, None)
        with patch.object(module.urllib.request, "urlopen", side_effect=error):
            return module.validate("https://example.invalid", "sample")

    def test_quota(self):
        self.assertEqual(self.check_http(402)["state"], "quota_exceeded")

    def test_auth(self):
        for status in (401, 403):
            with self.subTest(status=status):
                self.assertEqual(self.check_http(status)["state"], "auth_failed")

    def test_other_http(self):
        self.assertEqual(self.check_http(503)["state"], "unreachable")

    def test_missing_config(self):
        with patch.dict("os.environ", {"APEX_SUPABASE_URL": "", "APEX_SUPABASE_KEY": ""}):
            self.assertEqual(module.validate()["state"], "declared")


if __name__ == "__main__":
    unittest.main()
