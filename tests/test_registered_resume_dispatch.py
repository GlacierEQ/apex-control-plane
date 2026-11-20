"""Source-gated consumer dispatch cannot precede authenticated receipt readback."""
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import run_owned_continuity as host

class RegisteredResumeDispatchTests(unittest.TestCase):
    def setUp(self):
        self.path = Path('/private/profile.json')
        self.profile = {'startup_registered_action': 'VERIFY_REQUIRED_RETRIEVED_SOURCES'}
        self.outcome = {'status': 'STARTUP_PRIOR_ACTION_APPLIED',
                        'startup_receipt_digest': 'sha256:one',
                        'retrieval_digest': 'sha256:two',
                        'action_source_ids': ['source:a']}
        self.receipt = {'status': 'STARTUP_DECISION_VERIFIED',
                        'registered_action': 'VERIFY_REQUIRED_RETRIEVED_SOURCES',
                        'action_result': 'REQUIRED_RETRIEVED_SOURCES_VERIFIED',
                        'startup_receipt_digest': 'sha256:one',
                        'retrieval_digest': 'sha256:two',
                        'action_source_ids': ['source:a']}

    def invoke(self, handler):
        return host.run_registered_resume(self.path, session_id='s', invocation_id='i',
            previous_session_id='old', previous_invocation_id='prior',
            handlers={'VERIFY_REQUIRED_RETRIEVED_SOURCES': handler})

    def test_authenticated_receipt_reaches_real_consumer(self):
        calls = []
        with (patch.object(host, 'load_profile', return_value=self.profile),
              patch.object(host, 'run_profile', return_value=self.outcome),
              patch.object(host, 'read_startup_decision', return_value=self.receipt)):
            result = self.invoke(lambda receipt: calls.append(receipt['retrieval_digest']) or 'executed')
        self.assertEqual(result, 'executed')
        self.assertEqual(calls, ['sha256:two'])

    def test_mismatched_readback_blocks_consumer(self):
        for field, value in [('retrieval_digest', 'sha256:tampered'),
                             ('action_result', 'UNVERIFIED'),
                             ('startup_receipt_digest', 'sha256:changed'),
                             ('action_source_ids', ['source:other'])]:
            calls = []
            with (patch.object(host, 'load_profile', return_value=self.profile),
                  patch.object(host, 'run_profile', return_value=self.outcome),
                  patch.object(host, 'read_startup_decision', return_value={**self.receipt, field:value})):
                with self.assertRaises(ValueError):
                    self.invoke(lambda receipt: calls.append(receipt))
            self.assertEqual(calls, [])

    def test_no_registration_or_recovery_blocks_consumer(self):
        with patch.object(host, 'load_profile', return_value={}):
            with self.assertRaises(ValueError):
                self.invoke(lambda _: None)
        with (patch.object(host, 'load_profile', return_value=self.profile),
              patch.object(host, 'run_profile', return_value={'status':'NEW_INDEX'})):
            with self.assertRaises(ValueError):
                self.invoke(lambda _: None)

if __name__ == '__main__':
    unittest.main()
