import unittest

from src.agent_result_envelope import AgentResultEnvelope


class AgentResultEnvelopeTests(unittest.TestCase):
    def test_requires_explicit_identity_and_status(self):
        for payload in (
            {"agent_id": "worker", "status": "success"},
            {"task_id": "t1", "status": "success"},
            {"task_id": "t1", "agent_id": "worker"},
        ):
            with self.assertRaises(ValueError):
                AgentResultEnvelope.from_dict(payload)

    def test_rejects_blank_or_unknown_authority_fields(self):
        with self.assertRaises(ValueError):
            AgentResultEnvelope.from_dict({"task_id": "t1", "agent_id": "", "status": "success"})
        with self.assertRaises(ValueError):
            AgentResultEnvelope.from_dict({"task_id": "t1", "agent_id": "worker", "status": "completed"})

    def test_preserves_unique_result_fields_without_fabrication(self):
        payload = {
            "task_id": "provider-task-7",
            "agent_id": "provider-agent-2",
            "status": "blocked",
            "facts": [{"fact": "x"}],
            "sources": ["provider://receipt/1"],
            "verification": [{"receipt": "r1"}],
            "unresolved": ["terminal readback"],
        }
        result = AgentResultEnvelope.from_dict(payload)
        self.assertEqual(result.to_dict()["status"], "blocked")
        self.assertEqual(result.task_id, "provider-task-7")
        self.assertEqual(result.agent_id, "provider-agent-2")


if __name__ == "__main__":
    unittest.main()
