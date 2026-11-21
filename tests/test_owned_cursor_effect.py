import os
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import run_owned_continuity as owner


class OwnerCursorEffectTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        os.chmod(self.root, 0o700)
        self.receipt = dict(status='STARTUP_DECISION_VERIFIED',
            registered_action='VERIFY_REQUIRED_RETRIEVED_SOURCES',
            action_result='REQUIRED_RETRIEVED_SOURCES_VERIFIED',
            action_source_ids=['source-a'], key='mission:startup:s:i',
            startup_receipt_digest='sha256:'+'a'*64,
            retrieval_digest='sha256:'+'b'*64, recovered_cursor='continue:verified',
            checkpoint_digest='sha256:checkpoint', journal_source_ref='journal')

    def execute(self, receipt=None):
        with patch.object(owner, 'run_registered_resume',
                          side_effect=lambda *args, **kw: kw['handlers']['VERIFY_REQUIRED_RETRIEVED_SOURCES'](receipt or self.receipt)):
            return owner.run_verified_cursor_effect(Path('profile'), session_id='s', invocation_id='i',
                        output_dir=self.root, database=self.root/'provider.sqlite')

    def test_real_effect_and_repeat_readback(self):
        self.assertEqual(self.execute()['status'], 'OPERATION_EFFECT_PROVIDER_VERIFIED')
        self.assertEqual(self.execute()['status'], 'OPERATION_EFFECT_PROVIDER_VERIFIED')

    def test_interrupted_claim_does_not_replay(self):
        from scripts.continuity_verified_artifact import consume_once_verified_handoff
        consume_once_verified_handoff(self.receipt, output_dir=self.root,
            operation_name='apply_recovered_cursor', handler=lambda payload, identity: None)
        self.assertEqual(self.execute()['status'], 'OPERATION_RECONCILIATION_REQUIRED')
        with sqlite3.connect(self.root/'provider.sqlite') as db:
            self.assertEqual(db.execute('SELECT count(*) FROM applied_cursor').fetchone()[0], 0)

    def test_conflicting_recovered_cursor_rejected(self):
        self.execute()
        with self.assertRaises(ValueError):
            self.execute({**self.receipt, 'recovered_cursor':'continue:forged'})
