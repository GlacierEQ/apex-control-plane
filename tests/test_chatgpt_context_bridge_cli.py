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
UPSTREAM = Path(os.environ["SPIRAL_REAL_SOURCE_ROOT"]) if os.environ.get("SPIRAL_REAL_SOURCE_ROOT") else None
PYTHON = sys.executable

@unittest.skipUnless(UPSTREAM, "requires real pinned Spiral source via SPIRAL_REAL_SOURCE_ROOT")
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
    def require_one(self, directory, pattern):
        matches = list(directory.glob(pattern))
        self.assertEqual(len(matches), 1, f"Expected exactly one {pattern} file in {directory}")
        return matches[0]
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
        p = self.require_one(self.store / "journals", "*.jsonl")
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
    def test_source_bound_facts_are_recovered_not_silently_dropped(self):
        self.initialize()
        self.cmd("fact", "--key", "last_verified_result",
                 "--value", "CI verified", "--source", "github:GlacierEQ/apex-control-plane@sha")
        result = self.cmd("recover", "--session-id", "next-chat")
        self.assertEqual(result["facts"]["last_verified_result"]["value"], "CI verified")
        self.assertEqual(result["facts"]["last_verified_result"]["source"],
                         "github:GlacierEQ/apex-control-plane@sha")

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

    def test_symlinked_manifest_or_head_rejected_by_descriptor_open(self):
        self.initialize()
        anchor = self.require_one(self.store / "anchors", "*.json")
        original = anchor.with_suffix(".backup")
        anchor.rename(original)
        anchor.symlink_to(original)
        self.cmd("recover", "--session-id", "next-chat", ok=False)

    def test_symlinked_context_root_never_treated_as_mission_authority(self):
        self.initialize()
        original = self.store.with_name("original-store")
        self.store.rename(original)
        self.store.symlink_to(original, target_is_directory=True)
        self.cmd("recover", "--session-id", "next-chat", ok=False)

    def test_reconcile_recovers_authenticated_append_without_anchor(self):
        # A journal fsync can succeed just before a process loses the anchor update.
        # Reproduce that persisted state: authenticated descendant in journal,
        # but the independent anchor still names its verified ancestor.
        init = self.initialize()
        self.cmd("correct", "--instruction", "Preserve the source-qualified execution cursor")
        anchor = self.require_one(self.store / "anchors", "*.json")
        anchor.write_text(json.dumps({"mission_id": self.base[-1], "head": init["head"]}) + "\n")
        self.cmd("recover", "--session-id", "new-chat", ok=False)
        resumed = self.cmd("reconcile")
        self.assertEqual(resumed["status"], "VERIFIED_RECONCILED")
        self.assertEqual(resumed["previous_head"], init["head"])
        self.assertNotEqual(resumed["head"], init["head"])
        a = self.cmd("recover", "--session-id", "independent-chat-A")
        b = self.cmd("recover", "--session-id", "independent-chat-B")
        self.assertEqual(a["head"], b["head"])
        self.assertEqual(a["head"], resumed["head"])
        self.assertIn("Preserve the source-qualified execution cursor", a["corrections"])

    def test_reconcile_rejects_anchor_that_is_not_authenticated_ancestor(self):
        self.initialize()
        anchor = self.require_one(self.store / "anchors", "*.json")
        forged = {"mission_id": self.base[-1], "head": "0" * 64}
        anchor.write_text(json.dumps(forged) + "\n")
        self.cmd("reconcile", ok=False)
        self.assertEqual(json.loads(anchor.read_text()), forged)
        self.cmd("recover", "--session-id", "new-chat", ok=False)

    def test_reconcile_rejects_unverified_event_chain(self):
        init = self.initialize()
        journal = self.require_one(self.store / "journals", "*.jsonl")
        fabricated = {
            "seq": 2, "kind": "correction",
            "data": {"instruction": "malicious fabricated instruction"},
            "timestamp": "2026-11-17T00:00:00+00:00",
            "previous_sha256": init["head"], "sha256": "f" * 64,
            "auth_tag": "f" * 64,
        }
        with journal.open("ab") as handle:
            handle.write((json.dumps(fabricated) + "\n").encode())
        anchor = self.require_one(self.store / "anchors", "*.json")
        prior = anchor.read_bytes()
        self.cmd("reconcile", ok=False)
        self.assertEqual(anchor.read_bytes(), prior)
        self.cmd("recover", "--session-id", "next-chat", ok=False)

    def test_reconcile_is_read_only_when_head_is_current(self):
        init = self.initialize()
        journal = self.require_one(self.store / "journals", "*.jsonl")
        original = journal.read_bytes()
        proof = self.cmd("reconcile")
        self.assertEqual(proof["status"], "VERIFIED_UNCHANGED")
        self.assertEqual(proof["head"], init["head"])
        self.assertEqual(journal.read_bytes(), original)

    def test_admit_applies_authenticated_context_to_real_apex_kernel(self):
        self.initialize()
        self.cmd("correct", "--instruction", "Preserve past corrections and source identity")
        self.cmd("checkpoint", "--cursor", "APEX/known-next-operation")
        self.cmd("fact", "--key", "verified_capability", "--value", "pass",
                 "--source", "github:GlacierEQ/apex-control-plane@head")
        journal = self.require_one(self.store / "journals", "*.jsonl")
        anchor = self.require_one(self.store / "anchors", "*.json")
        before = (journal.read_bytes(), anchor.read_bytes())
        first = self.cmd("admit", "--session-id", "native-connected-host-A")
        second = self.cmd("admit", "--session-id", "native-connected-host-B")
        self.assertEqual(first["status"], "APEX_CONTEXT_ADMITTED")
        self.assertEqual(second["status"], "APEX_CONTEXT_ADMITTED")
        self.assertNotEqual(first["session_id"], second["session_id"])
        self.assertEqual(first["head"], second["head"])
        self.assertEqual(first["source_ref"], second["source_ref"])
        self.assertEqual(first["apex_phase"], "ready")
        self.assertTrue(first["recovered_context_applied_to_apex_instruction"])
        self.assertEqual(first["corrections"], ["Preserve past corrections and source identity"])
        self.assertEqual(first["facts"]["verified_capability"]["value"], "pass")
        self.assertEqual(first["cursor"], "APEX/known-next-operation")
        self.assertIn("context_recovery", first["apex_receipt_kinds"])
        self.assertFalse(first["downstream_action_executed"])
        self.assertFalse(first["automatic_chatgpt_host_hook_verified"])
        self.assertEqual((journal.read_bytes(), anchor.read_bytes()), before)

    def test_admit_denies_missing_or_stale_authenticated_journal(self):
        self.cmd("admit", "--session-id", "not-yet-created", ok=False)
        init = self.initialize()
        self.cmd("correct", "--instruction", "Do not lose corrections")
        anchor = self.require_one(self.store / "anchors", "*.json")
        anchor.write_text(json.dumps({"mission_id": self.base[-1], "head": init["head"]}) + "\n")
        self.cmd("admit", "--session-id", "stale-head", ok=False)
        self.cmd("reconcile")
        accepted = self.cmd("admit", "--session-id", "fresh-head")
        self.assertEqual(accepted["status"], "APEX_CONTEXT_ADMITTED")
        self.assertIn("Do not lose corrections", accepted["corrections"])

    def test_no_secret_material_in_stdout_or_artifact_permissions(self):
        init = self.initialize()
        key = self.require_one(self.store / "keys", "*.key")
        self.assertEqual(key.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(key.read_bytes().hex(), json.dumps(init))
        self.assertEqual(self.require_one(self.store / "journals", "*.jsonl").stat().st_mode & 0o777, 0o600)

if __name__ == "__main__":
    unittest.main()
