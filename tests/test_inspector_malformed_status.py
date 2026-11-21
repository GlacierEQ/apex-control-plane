"""Real receipt-inspection CLI regressions for malformed untrusted JSON."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "src" / "inspect_execution_receipt.py"

class MalformedReceiptTests(unittest.TestCase):
    def check_receipt(self, raw, expected_code=2):
        with tempfile.TemporaryDirectory() as root:
            receipt = Path(root) / "receipt.json"
            receipt.write_text(raw, encoding="utf-8")
            run = subprocess.run([sys.executable, str(SCRIPT), str(receipt)],
                                 capture_output=True, text=True, timeout=5)
            self.assertEqual(run.returncode, expected_code, run.stderr)
            result = json.loads(run.stdout)
            self.assertFalse(result["retry_authorized"])
            self.assertFalse(result.get("outcome_verified", False))
            return result

    def test_array_status(self):
        self.assertEqual(self.check_receipt('{"status":["completed"]}')["status"], "inspection_failed")

    def test_object_status(self):
        self.assertEqual(self.check_receipt('{"status":{"value":"completed"}}')["status"], "inspection_failed")

    def test_missing_status(self):
        self.assertEqual(self.check_receipt('{"invocation_id":"x"}')["status"], "inspection_failed")

    def test_deeply_nested_json(self):
        self.assertEqual(self.check_receipt('{"status":' + '[' * 1500 + '0' + ']' * 1500 + '}')["status"], "inspection_failed")

    def test_valid_unverified_status(self):
        result = self.check_receipt('{"status":"pending_unverified"}', expected_code=0)
        self.assertEqual(result["status"], "inspected_unverified")

if __name__ == "__main__":
    unittest.main()
