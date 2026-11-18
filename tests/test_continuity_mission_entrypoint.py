"""Startup consumer cannot run without authenticated recovery and dispatch."""
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from scripts.continuity_mission_entrypoint import start_mission


class StartupTests(unittest.TestCase):
    def invoke(self, completed):
        called = []
        with patch("scripts.continuity_mission_entrypoint.subprocess.run", return_value=completed) as run:
            result = start_mission(
                store=Path("/tmp/store"), spiral_root=Path("/tmp/spiral"),
                mission_id="mission", session_id="fresh-session",
                consumer=lambda receipt: called.append(receipt) or receipt["result"],
            )
        self.assertIn("dispatch", run.call_args.args[0])
        self.assertEqual(run.call_args.kwargs["timeout"], 60)
        return result, called

    def test_authenticated_dispatch_precedes_consumer(self):
        receipt = {
            "status": "RECOVERED_ACTION_DISPATCHED", "mission_id": "mission",
            "head": "a" * 64, "downstream_action_executed": True,
            "apex_phase": "ready", "apex_receipt_kinds": ["context_recovery"],
            "action_name": "continue",
            "result": {"next_cursor": "continue:next",
                       "binding": "spiral-journal:" + "a" * 64},
        }
        result, called = self.invoke(subprocess.CompletedProcess([], 0, json.dumps(receipt), ""))
        self.assertEqual(result["next_cursor"], "continue:next")
        self.assertEqual(len(called), 1)

    def test_rejected_dispatch_never_calls_consumer(self):
        for completed in (
            subprocess.CompletedProcess([], 1, "", "FAIL_CLOSED"),
            subprocess.CompletedProcess([], 0, "not json", ""),
            subprocess.CompletedProcess([], 0, json.dumps({
                "status": "APEX_CONTEXT_ADMITTED", "mission_id": "mission",
                "head": "a" * 64, "downstream_action_executed": False, "result": {},
            }), ""),
        ):
            with self.subTest(completed=completed):
                with self.assertRaises(RuntimeError):
                    self.invoke(completed)

    def test_missing_mission_never_invokes_bridge(self):
        with patch("scripts.continuity_mission_entrypoint.subprocess.run") as run:
            with self.assertRaises(ValueError):
                start_mission(
                    store=Path("/tmp/store"), spiral_root=Path("/tmp/spiral"),
                    mission_id="", session_id="session", consumer=lambda _: None,
                )
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
