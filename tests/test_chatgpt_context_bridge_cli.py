"""Real-upstream CLI contract tests; never require provider credentials."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "chatgpt_context_bridge.py"
UPSTREAM = Path(os.environ["SPIRAL_REAL_SOURCE_ROOT"])
PYTHON = sys.executable

class ChatGPTContextBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Path(self.tmp.name) / "context-store"
        self.base = [PYTHON, str(SCRIPT), "--store", str(self.store), "--spiral-root", str(UPSTREAM),
                     "--mission-id", "glaciereq-chatgpt-context-enforcement"]
    def cmd(self, action, *args, ok=True):
        r = subprocess.run([*self.base, action, *args], text=True, capture_output=True, timeout=20)
        if ok:
            self.assertEqual(r.returncode, 0, r.stderr)
            return json.loads(r.stdout)
        self.assertNotEqual(r.returncode, 0)
        return r
    def initialize(self):
        return self.cmd("init", "--objective", "Recover and apply exact mission context in ChatGPT",
                        "--outcome", "LIVE_CHATGPT_SESSION_RECOVERY_VERIFIED")
    def test_two_independent_processes_recover_exact_existing_head(self):
        init = self.initialize()
        self.assertEqual(init["status"], "CREATED")
        a = self.cmd("recover", "--session-id", "actual-chat-A")
        b = self.cmd("recover", "--session-id", "actual-chat-B")
        self.assertEqual(a["status"], "VERIFIED_EXISTING")
        self.assertEqual(a["head"], b["head"])
        self.assertEqual(a["head"], init["head"])
        self.assertNotEqual(a["session_id"], b["session_id"])
        self.assertFalse(a["automatic_chatgpt_host_hook_verified"])
        self.assertTrue(a["requires_actual_action_application"])
    def test_fail_closed_for_missing_and_duplicate_mission(self):
        self.cmd("recover", "--session-id", "new-chat", ok=False)
        self.initialize()
        self.cmd("init", "--objective", "Another", "--outcome", "WRONG", ok=False)
    def test_head_anchor_detects_rollback(self):
        self.initialize()
        self.cmd("checkpoint", "--cursor", "HOST/real-invocation")
        p = next((self.store / "journals").glob("*.jsonl"))
        lines = p.read_text().splitlines()
        p.write_text(lines[0]+"\n")
        self.cmd("recover", "--session-id", "new-chat", ok=False)
    def test_corrections_and_cursor_survive_new_process(self):
        self.initialize()
        self.cmd("correct", "--instruction", "Do not present skills as automatic ChatGPT hooks")
        self.cmd("checkpoint", "--cursor", "HOST/real-invocation")
        result = self.cmd("recover", "--session-id", "another-chat")
        self.assertIn("Do not present skills as automatic ChatGPT hooks", result["corrections"])
        self.assertEqual(result["cursor"], "HOST/real-invocation")
        self.assertTrue(result["requires_actual_action_application"])
    def test_concurrent_corrections_do_not_lose_anchor(self):
        self.initialize()
        def run(text):
            return subprocess.Popen([*self.base, "correct", "--instruction", text],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        first = run("Keep verified outcomes durable")
        second = run("Never replay uncertain provider writes")
        for process in (first, second):
            stdout, stderr = process.communicate(timeout=30)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertEqual(json.loads(stdout)["status"], "VERIFIED_UPDATE")
        recovered = self.cmd("recover", "--session-id", "next-session")
        self.assertIn("Keep verified outcomes durable", recovered["corrections"])
        self.assertIn("Never replay uncertain provider writes", recovered["corrections"])

    def test_no_secret_material_in_stdout_or_artifact_permissions(self):
        init = self.initialize()
        key = next((self.store / "keys").glob("*.key"))
        self.assertEqual(key.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(key.read_bytes().hex(), json.dumps(init))
        self.assertEqual(next((self.store / "journals").glob("*.jsonl")).stat().st_mode & 0o777, 0o600)

if __name__ == "__main__":
    unittest.main()
