"""Startup consumer cannot run without authenticated recovery and dispatch."""
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from scripts.continuity_mission_entrypoint import start_mission, start_registered_mission, start_context_gated_mission


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
            "session_id": "fresh-session", "cursor": "continue:next",
            "apex_runtime_id": "apex-test-runtime",
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


    def test_substituted_session_and_action_receipts_never_reach_consumer(self):
        valid = {
            "status": "RECOVERED_ACTION_DISPATCHED", "mission_id": "mission",
            "session_id": "fresh-session", "cursor": "continue:next",
            "head": "a" * 64, "downstream_action_executed": True,
            "apex_runtime_id": "apex-test-runtime", "apex_phase": "ready",
            "apex_receipt_kinds": ["context_recovery"],
            "action_name": "continue",
            "result": {"next_cursor": "continue:next",
                       "binding": "spiral-journal:" + "a" * 64},
        }
        for patch_fields in (
            {"session_id": "other-session"},
            {"cursor": "inspect:owner"},
            {"result": {"next_cursor": "continue:wrong",
                        "binding": "spiral-journal:" + "a" * 64}},
            {"apex_runtime_id": ""},
            {"head": "z" * 64},
        ):
            with self.subTest(patch_fields=patch_fields):
                altered = dict(valid, **patch_fields)
                with self.assertRaises(RuntimeError):
                    self.invoke(subprocess.CompletedProcess(
                        [], 0, json.dumps(altered), ""))

    def test_registered_handler_is_selected_by_recovered_cursor(self):
        base = {
            "status": "RECOVERED_ACTION_DISPATCHED", "mission_id": "mission",
            "session_id": "fresh-session", "head": "a" * 64,
            "downstream_action_executed": True, "apex_runtime_id": "apex-runtime",
            "apex_phase": "ready", "apex_receipt_kinds": ["context_recovery"],
        }
        called = []
        for action, cursor, result in (
            ("continue", "continue:phase-two", {
                "next_cursor": "continue:phase-two", "binding": "spiral-journal:" + "a" * 64}),
            ("inspect", "inspect:owner", {
                "key": "owner", "binding": "spiral-journal:" + "a" * 64}),
        ):
            receipt = dict(base, action_name=action, cursor=cursor, result=result)
            with patch("scripts.continuity_mission_entrypoint.subprocess.run",
                       return_value=subprocess.CompletedProcess([], 0, json.dumps(receipt), "")):
                actual = start_registered_mission(
                    store=Path("/tmp/store"), spiral_root=Path("/tmp/spiral"),
                    mission_id="mission", session_id="fresh-session",
                    handlers={
                        "continue": lambda r: called.append(("continue", r["cursor"])) or "continued",
                        "inspect": lambda r: called.append(("inspect", r["cursor"])) or "inspected",
                    })
            self.assertEqual(actual, "continued" if action == "continue" else "inspected")
        self.assertEqual(called, [("continue", "continue:phase-two"),
                                  ("inspect", "inspect:owner")])

    def test_missing_registered_handler_fails_closed(self):
        receipt = {
            "status": "RECOVERED_ACTION_DISPATCHED", "mission_id": "mission",
            "session_id": "fresh-session", "head": "a" * 64,
            "downstream_action_executed": True, "apex_runtime_id": "apex-runtime",
            "apex_phase": "ready", "apex_receipt_kinds": ["context_recovery"],
            "action_name": "inspect", "cursor": "inspect:owner",
            "result": {"key": "owner", "binding": "spiral-journal:" + "a" * 64},
        }
        called = []
        with patch("scripts.continuity_mission_entrypoint.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 0, json.dumps(receipt), "")):
            with self.assertRaisesRegex(ValueError, "no authorized mission handler"):
                start_registered_mission(
                    store=Path("/tmp/store"), spiral_root=Path("/tmp/spiral"),
                    mission_id="mission", session_id="fresh-session",
                    handlers={"continue": lambda r: called.append(r)},
                )
        self.assertEqual(called, [])

    def test_cli_forwards_explicit_legacy_cursor(self):
        from scripts.continuity_mission_entrypoint import main
        argv = [
            "continuity_mission_entrypoint.py", "--store", "/tmp/store",
            "--spiral-root", "/tmp/spiral", "--mission-id", "mission",
            "--session-id", "fresh-session",
            "--legacy-continue-cursor", "resume original task",
        ]
        with patch("sys.argv", argv), patch(
            "scripts.continuity_mission_entrypoint.start_mission"
        ) as start:
            main()
        self.assertEqual(
            start.call_args.kwargs["legacy_continue_cursor"],
            "resume original task",
        )

    def test_recovered_policy_changes_actual_handler_execution(self):
        base = {
            "status": "RECOVERED_ACTION_DISPATCHED", "mission_id": "mission",
            "session_id": "fresh-session", "cursor": "continue:next",
            "action_name": "continue", "head": "a" * 64,
            "downstream_action_executed": True, "apex_runtime_id": "apex",
            "apex_phase": "ready", "apex_receipt_kinds": ["context_recovery"],
        }
        calls = []
        def execute(corrections, facts):
            result = dict(base, result={
                "next_cursor": "continue:next",
                "binding": "spiral-journal:" + "a" * 64,
                "instructions_to_apply": corrections, "verified_facts": facts,
            })
            with patch("scripts.continuity_mission_entrypoint.subprocess.run",
                       return_value=subprocess.CompletedProcess([], 0, json.dumps(result), "")):
                return start_context_gated_mission(
                    store=Path("/tmp/store"), spiral_root=Path("/tmp/spiral"),
                    mission_id="mission", session_id="fresh-session",
                    handlers={"continue": lambda r: calls.append(r["cursor"]) or "EXECUTED"},
                    required_corrections={"continue": ("CONTEXT FIRST",)},
                    required_fact_keys={"continue": ("owner",)},
                )
        good = {"owner": {"source": "github:verified", "value": "APEX"}}
        self.assertEqual(execute(["CONTEXT FIRST"], good), "EXECUTED")
        for corrections, facts in (
            ([], good),
            (["CONTEXT FIRST"], {"owner": {"value": "APEX"}}),
            (["CONTEXT FIRST"], {}),
        ):
            with self.subTest(corrections=corrections, facts=facts):
                with self.assertRaises(ValueError):
                    execute(corrections, facts)
        self.assertEqual(calls, ["continue:next"])

    def test_missing_policy_rejects_even_authenticated_receipt(self):
        with patch("scripts.continuity_mission_entrypoint.start_mission",
                   side_effect=lambda **kw: kw["consumer"]({
                       "action_name": "continue", "cursor": "continue:next",
                       "result": {"instructions_to_apply": [], "verified_facts": {}},
                   })):
            with self.assertRaisesRegex(ValueError, "missing explicit action policy"):
                start_context_gated_mission(
                    store=Path("/tmp/store"), spiral_root=Path("/tmp/spiral"),
                    mission_id="mission", session_id="session",
                    handlers={"continue": lambda _: None},
                    required_corrections={}, required_fact_keys={},
                )

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
