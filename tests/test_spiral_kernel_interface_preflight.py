"""Fail closed before effectful context application on an incompatible APEX kernel."""
import unittest
from types import SimpleNamespace
from src.spiral_live_journal import SpiralChatAdmissionError, resume_authenticated_chat_in_apex

class KernelInterfacePreflightTests(unittest.TestCase):
    def test_missing_interfaces_cannot_trigger_callback(self):
        recovery = SimpleNamespace(material_context_found=True, mission_id="m",
            source_ref="spiral-journal:"+"a"*64, cursor="c", corrections=(), facts={})
        for missing in ("bind_task", "record_context_recovery"):
            with self.subTest(missing=missing):
                effects = []
                kernel = SimpleNamespace(phase=SimpleNamespace(value="bootstrapped"),
                    bind_task=lambda **kw: None, record_context_recovery=lambda **kw: None)
                delattr(kernel, missing)
                with self.assertRaises(SpiralChatAdmissionError):
                    resume_authenticated_chat_in_apex(kernel, recovery,
                        task_instruction="resume", target_state="verified",
                        operation_class="mission", applied_to_action=True,
                        expected_mission_id="m",
                        apply_context=lambda r: effects.append(r.source_ref))
                self.assertEqual(effects, [])

if __name__ == "__main__":
    unittest.main()
