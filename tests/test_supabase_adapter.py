"""
APEX SUPABASE ADAPTER L2/L3 TEST SUITE
Standard: Proves live Supabase integration, observe(), push_receipt(), and readback() verification.
"""

import unittest
from pathlib import Path

import sys
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from contracts.receipt import ECHOReceipt
from adapters.supabase.adapter import SupabaseAdapter


class TestSupabaseAdapter(unittest.TestCase):

    def setUp(self):
        self.adapter = SupabaseAdapter()

    def test_01_credentials_and_configuration(self):
        """Verifies that live Supabase credentials are loaded from environment."""
        self.assertTrue(self.adapter.is_configured(), "Supabase URL and Service Key must be configured")
        self.assertIn("supabase.co", self.adapter.url)

    def test_02_observe_apex_ops_log(self):
        """Verifies that observe() can query recent records from live Supabase."""
        res = self.adapter.observe("apex_ops_log", limit=3)
        self.assertTrue(res.get("configured"))
        self.assertEqual(res.get("table"), "apex_ops_log")
        self.assertIsInstance(res.get("records"), list)

    def test_03_push_receipt_and_readback(self):
        """Verifies the 5-point contract: observe -> execute -> readback -> verify on live Supabase."""
        receipt = ECHOReceipt.create(
            mission_id="msn_test_supabase_001",
            correlation_id="run_test_supabase_001",
            step="supabase.live_contract_test",
            started_at=1787840000.0,
            expected_state={"test": "l3_proof"},
            observed_state={"test": "l3_proof"},
            external_ids={},
            result="VERIFIED",
            previous_receipt_hash="GENESIS_TEST",
        )

        # 1. Execute
        write_res = self.adapter.push_receipt(receipt)
        self.assertEqual(write_res.get("status"), "APPLIED")
        remote_rec = write_res.get("remote_record")
        self.assertIsNotNone(remote_rec)
        rec_id = remote_rec.get("id")

        # 2. Readback
        rb_res = self.adapter.readback("apex_ops_log", "id", rec_id)
        self.assertTrue(rb_res.get("observed"))

        # 3. Verify
        is_valid = self.adapter.verify(rec_id, rb_res)
        self.assertTrue(is_valid, "Readback record must be mathematically verified in Supabase physical storage")


if __name__ == "__main__":
    unittest.main()
