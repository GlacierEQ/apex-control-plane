"""Verify actual effects, durable recovery and no-duplicate behavior."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from operational_core import FileWriteAdapter, OperationalCore, OperationConflict


class FakeProvider:
    def __init__(self, *, idempotent=True):
        self.idempotent = idempotent
        self.effects = {}
        self.calls = 0
        self.behavior = "success"

    def execute(self, payload, operation_id):
        self.calls += 1
        if self.behavior == "crash_after_write":
            self.effects[payload["key"]] = payload["value"]
            raise TimeoutError("response lost after provider accepted")
        if self.behavior == "crash_before_write":
            raise TimeoutError("provider never accepted request")
        self.effects[payload["key"]] = payload["value"]
        return {"provider_ref": operation_id}

    def verify(self, payload):
        if self.behavior == "no_readback":
            return None
        return self.effects.get(payload["key"]) == payload["value"]


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.provider = FakeProvider()
        self.core = OperationalCore(self.root / "state.db",
                                    {"provider": self.provider, "file.write": FileWriteAdapter(self.root)})
        self.addCleanup(self.core.close)

    def test_connector_execution_and_independent_readback(self):
        self.core.submit("op1", "provider", {"key": "k", "value": 2})
        result = self.core.run("op1")
        self.assertTrue(result.verified)
        self.assertEqual(self.provider.effects["k"], 2)
        self.assertEqual(result.attempts, 1)
        self.assertIn("verified", [e["state"] for e in self.core.events("op1")])

    def test_verified_state_is_rechecked_and_repaired_when_target_drifts(self):
        self.core.submit("drift", "provider", {"key": "k", "value": 2})
        self.assertTrue(self.core.run("drift").verified)
        self.provider.effects.pop("k")
        self.assertTrue(self.core.run("drift").verified)
        self.assertEqual(self.provider.calls, 2)
        self.assertIn("retryable", [e["state"] for e in self.core.events("drift")])

    def test_same_request_is_idempotent(self):
        self.core.submit("op1", "provider", {"key": "k", "value": 2})
        self.core.submit("op1", "provider", {"key": "k", "value": 2})
        self.core.run("op1")
        self.core.run("op1")
        self.assertEqual(self.provider.calls, 1)
        with self.assertRaises(OperationConflict):
            self.core.submit("op1", "provider", {"key": "k", "value": 3})

    def test_provider_response_lost_but_effect_verified(self):
        self.provider.behavior = "crash_after_write"
        self.core.submit("op2", "provider", {"key": "k", "value": 7})
        self.assertTrue(self.core.run("op2").verified)
        self.assertEqual(self.provider.calls, 1)

    def test_non_idempotent_failed_write_not_replayed(self):
        self.provider.idempotent = False
        self.provider.behavior = "crash_before_write"
        self.core.submit("op3", "provider", {"key": "k", "value": 1})
        self.assertEqual(self.core.run("op3").state, "needs_reconciliation")
        self.assertEqual(self.core.run("op3").state, "needs_reconciliation")
        self.assertEqual(self.provider.calls, 1)

    def test_idempotent_failed_write_can_recover(self):
        self.provider.behavior = "crash_before_write"
        self.core.submit("op4", "provider", {"key": "k", "value": 1})
        self.assertEqual(self.core.run("op4").state, "retryable")
        self.provider.behavior = "success"
        self.assertTrue(self.core.run("op4").verified)
        self.assertEqual(self.provider.calls, 2)

    def test_readback_failure_does_not_repeat_ambiguous_write(self):
        self.provider.behavior = "no_readback"
        self.core.submit("op5", "provider", {"key": "k", "value": 1})
        self.assertEqual(self.core.run("op5").state, "uncertain")
        self.assertEqual(self.core.run("op5").state, "uncertain")
        self.assertEqual(self.provider.calls, 1)
        self.provider.behavior = "success"
        self.assertTrue(self.core.run("op5").verified)
        self.assertEqual(self.provider.calls, 1)

    def test_running_lease_prevents_second_execution(self):
        self.core.submit("op6", "provider", {"key": "k", "value": 1})
        self.core.db.execute("UPDATE operations SET state='running', attempts=1, lease_until='2999-01-01T00:00:00+00:00' WHERE id='op6'")
        self.assertEqual(self.core.run("op6").state, "running")
        self.assertEqual(self.provider.calls, 0)

    def test_crash_recovery_reads_back_first(self):
        self.core.submit("op7", "provider", {"key": "k", "value": 1})
        self.provider.effects["k"] = 1
        self.core.db.execute("UPDATE operations SET state='running', attempts=1, lease_until='2000-01-01T00:00:00+00:00' WHERE id='op7'")
        self.assertTrue(self.core.run("op7").verified)
        self.assertEqual(self.provider.calls, 0)

    def test_file_write_effect_and_integrity(self):
        target = self.root / "sub" / "result.txt"
        self.core.submit("op8", "file.write", {"path": str(target), "content": "done"})
        self.assertTrue(self.core.run("op8").verified)
        self.assertEqual(target.read_text(), "done")
        self.assertTrue(self.core.status("op8").verified)

    def test_reject_symlink_file_write(self):
        target = self.root / "target"
        target.write_text("untouched")
        link = self.root / "link"
        link.symlink_to(target)
        self.core.submit("op9", "file.write", {"path": str(link), "content": "changed"})
        self.assertEqual(self.core.run("op9").state, "uncertain")
        self.assertEqual(target.read_text(), "untouched")

    def test_reject_out_of_workspace(self):
        external = self.root.parent / "external-should-not-be-written.txt"
        self.core.submit("external", "file.write", {"path": str(external), "content": "bad"})
        result = self.core.run("external")
        self.assertFalse(result.verified)
        self.assertFalse(external.exists())

    def test_journal_is_private_at_creation(self):
        import os
        if os.name != "posix":
            self.skipTest("POSIX file permissions")
        self.assertEqual(self.core.path.stat().st_mode & 0o777, 0o600)

    def test_sqlite_persists_across_process_restart(self):
        self.core.submit("op10", "file.write", {"path": str(self.root / "saved.txt"), "content": "hello"})
        self.core.run("op10")
        self.core.close()
        with OperationalCore(self.root / "state.db", {"file.write": FileWriteAdapter(self.root)}) as resumed:
            self.assertTrue(resumed.status("op10").verified)
            self.assertEqual(resumed.run("op10").attempts, 1)

    def test_cli_real_end_to_end(self):
        cli = ROOT / "scripts" / "operate_direct.py"
        base = [sys.executable, str(cli), "--state", str(self.root / "cli.db"), "--root", str(self.root)]
        target = self.root / "cli.txt"
        s = subprocess.run(base + ["submit-file", "--id", "cli1", "--path", str(target), "--content", "operating"], capture_output=True, text=True)
        self.assertEqual(s.returncode, 0, s.stderr)
        self.assertTrue(json.loads(s.stdout)["verified"])
        self.assertEqual(target.read_text(), "operating")
        r = subprocess.run(base + ["run", "--id", "cli1"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(json.loads(r.stdout)["verified"])
        self.assertEqual(target.read_text(), "operating")
        p = subprocess.run(base + ["status", "--id", "cli1"], capture_output=True, text=True)
        self.assertTrue(json.loads(p.stdout)["verified"])

    def test_cli_queue_only_does_not_claim_execution(self):
        cli = ROOT / "scripts" / "operate_direct.py"
        target = self.root / "queued.txt"
        args = [sys.executable, str(cli), "--state", str(self.root / "queue.db"), "--root", str(self.root),
                "submit-file", "--queue-only", "--id", "q", "--path", str(target), "--content", "queued"]
        p = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse(json.loads(p.stdout)["verified"])
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
