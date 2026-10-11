"""Real Spiral ContinuityJournal -> native APEX kernel, including two fresh processes.

Requires upstream Spiral checked out as an independent pinned package. These
tests never substitute mock journal events or a fake APEX kernel.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from apex_runtime_kernel import create_verified_runtime_kernel
from spiral_live_journal import (
    open_authenticated_chat, resume_authenticated_chat_in_apex,
    SpiralChatAdmissionError, load_spiral_engine,
)

SOURCE_ROOT = os.environ.get("SPIRAL_REAL_SOURCE_ROOT", "")
if SOURCE_ROOT:
    upstream = load_spiral_engine(SOURCE_ROOT)
    ContinuityJournal = upstream.ContinuityJournal
    JournalIntegrityError = upstream.JournalIntegrityError
    MissionRunner = upstream.MissionRunner
    RouteResult = upstream.RouteResult

MISSION = "glaciereq-job"
OBJECTIVE = "Obtain verified paid engineering employment"
OUTCOME = "PAID_EMPLOYMENT"
KEY = b"independent-hmac-key-for-real-cross-process-test"


@unittest.skipUnless(SOURCE_ROOT, "requires pinned real Spiral package checkout")
class RealCrossProcessChatTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "persisted-mission.jsonl"
        journal = ContinuityJournal(
            self.path, MISSION, OBJECTIVE,
            terminal_outcome=OUTCOME, integrity_key=KEY)
        journal.verify_fact("application", "received", source="employer:application-123")
        journal.correct("Never mistake an application for a paid employment outcome")
        journal.define_task("JOB/submit", "Submit application and verify source receipt")
        journal.complete_task("JOB/submit", "employer:application-123")
        journal.checkpoint("JOB/await-response")
        self.head = journal.events[-1]["sha256"]

    def opened(self, *, session="chat-A", head=None, key=KEY):
        return open_authenticated_chat(
            self.path, spiral_source_root=SOURCE_ROOT, chat_session_id=session, mission_id=MISSION,
            objective=OBJECTIVE, terminal_outcome=OUTCOME,
            integrity_key=key, expected_head=self.head if head is None else head,
            fact_keys=("application",),
        )

    def test_true_existing_authenticated_journal_recovers_without_mutating_head(self):
        journal, recovery = self.opened()
        self.assertEqual(recovery.mission_id, MISSION)
        self.assertEqual(recovery.cursor, "JOB/await-response")
        self.assertIn("Never mistake", recovery.corrections[0])
        self.assertEqual(recovery.facts["application"]["source"], "employer:application-123")
        self.assertEqual(recovery.source_ref, "spiral-journal:" + self.head)
        self.assertEqual(journal.events[-1]["sha256"], self.head)

    def test_missing_journal_must_not_be_silently_recreated(self):
        self.path.unlink()
        with self.assertRaises(SpiralChatAdmissionError):
            self.opened()
        self.assertFalse(self.path.exists())

    def test_wrong_key_and_rollback_or_truncation_fail_closed(self):
        with self.assertRaises((SpiralChatAdmissionError, JournalIntegrityError)):
            self.opened(key=b"another-independent-secret-hmac-key")
        with self.assertRaises(SpiralChatAdmissionError):
            self.opened(head="f" * 64)
        self.path.write_text(self.path.read_text().splitlines()[0] + "\n")
        with self.assertRaises(SpiralChatAdmissionError):
            self.opened()

    def test_symlink_to_valid_signed_journal_fails_closed(self):
        alias = self.path.parent / "linked-mission.jsonl"
        alias.symlink_to(self.path)
        with self.assertRaises(SpiralChatAdmissionError):
            open_authenticated_chat(
                alias, spiral_source_root=SOURCE_ROOT,
                chat_session_id="chat-linked", mission_id=MISSION,
                objective=OBJECTIVE, terminal_outcome=OUTCOME,
                integrity_key=KEY, expected_head=self.head)

    def test_path_swap_during_authenticated_open_fails(self):
        saved = self.path.parent / "original.jsonl"
        replacement = self.path.parent / "attacker.jsonl"
        replacement.write_text(self.path.read_text())
        def race(_):
            self.path.rename(saved)
            self.path.symlink_to(replacement)
            return upstream
        with patch("spiral_live_journal.load_spiral_engine", side_effect=race):
            with self.assertRaises(SpiralChatAdmissionError):
                self.opened()

    def test_subprocess_key_is_never_in_command_line(self):
        text = Path(__file__).read_text()
        self.assertNotIn("KEY.hex(), session", text)
        self.assertNotIn("self.head, KEY.hex()", text)
        self.assertIn("SPIRAL_TEST_HMAC_KEY_HEX", text)

    def test_real_apex_kernel_receives_same_mission_and_source_proof(self):
        kernel = create_verified_runtime_kernel()
        journal, recovery = self.opened()
        resume_authenticated_chat_in_apex(
            kernel, recovery,
            task_instruction=OBJECTIVE, target_state=OUTCOME,
            operation_class="resume_mission", applied_to_action=True)
        snapshot = kernel.snapshot()
        self.assertEqual(snapshot.phase, "ready")
        self.assertEqual(kernel.task.target_state, OUTCOME)
        self.assertIn(recovery.source_ref, kernel.task.source_refs)
        self.assertIn("context_recovery", snapshot.receipt_kinds)

    def test_real_apex_rejects_unapplied_material_corrections(self):
        kernel = create_verified_runtime_kernel()
        _, recovery = self.opened()
        with self.assertRaises(ValueError):
            resume_authenticated_chat_in_apex(
                kernel, recovery,
                task_instruction=OBJECTIVE, target_state=OUTCOME,
                operation_class="resume_mission", applied_to_action=False)
        self.assertNotEqual(kernel.snapshot().phase, "ready")

    def test_two_independent_python_sessions_recover_identical_source(self):
        env = dict(os.environ)
        env["SPIRAL_TEST_HMAC_KEY_HEX"] = KEY.hex()
        command = [
            sys.executable, str(Path(__file__).resolve()), "--read-session",
            str(self.path), self.head]
        outputs = []
        for session in ("chat-A", "chat-B"):
            result = subprocess.run([*command, session], capture_output=True,
                                    text=True, env=env, timeout=15, check=True)
            outputs.append(json.loads(result.stdout.strip()))
        self.assertNotEqual(outputs[0]["session"], outputs[1]["session"])
        for out in outputs:
            self.assertEqual(out["mission"], MISSION)
            self.assertEqual(out["cursor"], "JOB/await-response")
            self.assertEqual(out["head"], self.head)
            self.assertTrue(out["correction_applied"])
        self.assertEqual(self.opened()[1].source_ref, "spiral-journal:" + self.head)

    def test_previous_external_attempt_is_not_blindly_replayed_in_new_process(self):
        journal, _ = self.opened()
        try:
            MissionRunner(journal).run(
                ["ats-submit-1"],
                lambda _: (_ for _ in ()).throw(RuntimeError("unknown provider outcome")),
                lambda _: None)
        except RuntimeError:
            pass
        new_head = ContinuityJournal(
            self.path, MISSION, OBJECTIVE, terminal_outcome=OUTCOME,
            integrity_key=KEY).events[-1]["sha256"]
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--no-replay",
             str(self.path), new_head, "chat-B"],
            capture_output=True, text=True, check=True, timeout=15,
            env={**os.environ, "SPIRAL_TEST_HMAC_KEY_HEX": KEY.hex()})
        out = json.loads(result.stdout)
        self.assertEqual(out["attempted"], [])
        self.assertFalse(out["mission_complete"])


def _run_worker():
    mode, path, head, session = sys.argv[1:]
    key_hex = os.environ["SPIRAL_TEST_HMAC_KEY_HEX"]
    journal, recovery = open_authenticated_chat(
        path, spiral_source_root=SOURCE_ROOT, chat_session_id=session, mission_id=MISSION,
        objective=OBJECTIVE, terminal_outcome=OUTCOME,
        integrity_key=bytes.fromhex(key_hex), expected_head=head,
        fact_keys=("application",))
    kernel = create_verified_runtime_kernel()
    resume_authenticated_chat_in_apex(
        kernel, recovery, task_instruction=OBJECTIVE, target_state=OUTCOME,
        operation_class="resume_mission", applied_to_action=True)
    if mode == "--read-session":
        print(json.dumps({
            "session": session, "mission": recovery.mission_id,
            "head": recovery.source_ref.split(":", 1)[1],
            "cursor": recovery.cursor,
            "correction_applied": kernel.snapshot().phase == "ready",
        }))
    elif mode == "--no-replay":
        result = MissionRunner(journal).run(
            ["ats-submit-1"],
            lambda _: (_ for _ in ()).throw(AssertionError("duplicate provider call")),
            lambda _: None)
        print(json.dumps({"attempted": result.attempted,
                          "mission_complete": journal.is_complete}))
    else:
        raise ValueError("unrecognized worker mode")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].startswith("--"):
        _run_worker()
    else:
        unittest.main()
