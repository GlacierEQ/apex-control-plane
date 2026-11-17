"""Regression tests for the explicit, fail-closed continuity action gate."""
import unittest
from types import SimpleNamespace
from src.continuity_action_gate import execute_recovered_action

HEAD = "spiral-journal:" + "a" * 64


def recovered(cursor="resume:provider"):
    return SimpleNamespace(mission_id="glaciereq", source_ref=HEAD, cursor=cursor,
                           corrections=("Never restart finished work",),
                           facts={"owner": {"value": "existing", "source": "repo:main"}})


class ContinuityActionGateTests(unittest.TestCase):
    def test_recovered_cursor_changes_executed_action(self):
        called = []
        registry = {
            "resume": lambda state: called.append(("resume", state.corrections)) or "continued",
            "repair": lambda state: called.append(("repair", state.facts)) or "repaired",
        }
        first = execute_recovered_action(recovered(), expected_mission_id="glaciereq",
                                         expected_source_ref=HEAD, registry=registry)
        second = execute_recovered_action(recovered("repair:bridge"), expected_mission_id="glaciereq",
                                          expected_source_ref=HEAD, registry=registry)
        self.assertEqual((first.result, second.result), ("continued", "repaired"))
        self.assertEqual([entry[0] for entry in called], ["resume", "repair"])

    def test_unregistered_cursor_never_executes(self):
        called = []
        with self.assertRaises(ValueError):
            execute_recovered_action(recovered("unknown:task"), expected_mission_id="glaciereq",
                                     expected_source_ref=HEAD,
                                     registry={"resume": lambda _: called.append(True)})
        self.assertEqual(called, [])

    def test_wrong_identity_and_head_never_execute(self):
        called = []
        for mission, head in (("other", HEAD), ("glaciereq", "spiral-journal:" + "b" * 64)):
            with self.assertRaises(ValueError):
                execute_recovered_action(recovered(), expected_mission_id=mission,
                                         expected_source_ref=head,
                                         registry={"resume": lambda _: called.append(True)})
        self.assertFalse(called)

    def test_empty_cursor_never_executes(self):
        with self.assertRaises(ValueError):
            execute_recovered_action(recovered(""), expected_mission_id="glaciereq",
                                     expected_source_ref=HEAD, registry={"resume": lambda _: None})


if __name__ == "__main__":
    unittest.main()
