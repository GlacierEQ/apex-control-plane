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
        self.assertFalse((self.root/'provider.sqlite').exists(),
                         'readback must never create a missing provider')

    def test_real_provider_effect_changes_handler_selection(self):
        with patch.object(owner, 'run_registered_resume',
                          side_effect=lambda *args, **kw: kw['handlers']['VERIFY_REQUIRED_RETRIEVED_SOURCES'](self.receipt)):
            result = owner.select_verified_next_handler(Path('profile'), session_id='s', invocation_id='i',
                        output_dir=self.root, database=self.root/'provider.sqlite')
            self.assertEqual(result['selection'], 'VERIFY_REQUIRED_RETRIEVED_SOURCES')
            again = owner.select_verified_next_handler(Path('profile'), session_id='s', invocation_id='i',
                        output_dir=self.root, database=self.root/'provider.sqlite')
            self.assertEqual(again['selection'], result['selection'])
        with sqlite3.connect(self.root/'provider.sqlite') as db:
            self.assertEqual(db.execute('SELECT count(*) FROM applied_cursor').fetchone()[0], 1)

    def test_conflicting_recovered_cursor_rejected(self):
        self.execute()
        with self.assertRaises(ValueError):
            self.execute({**self.receipt, 'recovered_cursor':'continue:forged'})

class CursorEffectCLITest(unittest.TestCase):
    def test_cli_invokes_real_registered_effect_entrypoint(self):
        import io
        import json
        from contextlib import redirect_stdout
        with patch('sys.argv', ['continuity', 'cursor-effect', '--profile', '/tmp/profile',
                                '--session-id', 's', '--invocation-id', 'i',
                                '--output-dir', '/tmp/handoff', '--database', '/tmp/provider',
                                '--auto-resume']):
            with patch.object(owner, 'run_verified_cursor_effect', return_value={'status': 'OPERATION_EFFECT_PROVIDER_VERIFIED'}) as call:
                with redirect_stdout(io.StringIO()) as out:
                    owner.main()
        self.assertEqual(json.loads(out.getvalue())['status'], 'OPERATION_EFFECT_PROVIDER_VERIFIED')
        self.assertEqual(call.call_args.kwargs['database'], Path('/tmp/provider'))
        self.assertTrue(call.call_args.kwargs['auto_resume'])

class VerifiedNextHandlerTest(unittest.TestCase):
    def test_verified_provider_selects_registered_handler(self):
        with patch.object(owner, 'run_verified_cursor_effect', return_value={'status': 'OPERATION_EFFECT_PROVIDER_VERIFIED'}):
            result = owner.select_verified_next_handler(Path('profile'), session_id='s', invocation_id='i', output_dir=Path('/tmp/a'), database=Path('/tmp/b'))
        self.assertEqual(result['selection'], 'VERIFY_REQUIRED_RETRIEVED_SOURCES')

    def test_ambiguous_or_missing_provider_never_selects_handler(self):
        for status in ('OPERATION_RECONCILIATION_REQUIRED', 'OPERATION_NOT_CLAIMED', None):
            with self.subTest(status=status), patch.object(owner, 'run_verified_cursor_effect', return_value={'status': status}):
                result = owner.select_verified_next_handler(Path('profile'), session_id='s', invocation_id='i', output_dir=Path('/tmp/a'), database=Path('/tmp/b'))
                self.assertEqual(result['selection'], 'HALT_UNVERIFIED_CONTEXT')

class DispatchNextTest(unittest.TestCase):
    def test_selected_handler_produces_durable_handoff(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            os.chmod(root, 0o700)
            receipt = dict(
                status='STARTUP_DECISION_VERIFIED', registered_action='VERIFY_REQUIRED_RETRIEVED_SOURCES',
                action_result='REQUIRED_RETRIEVED_SOURCES_VERIFIED', action_source_ids=['source-a'],
                key='mission:startup:s:i', startup_receipt_digest='sha256:'+'a'*64,
                retrieval_digest='sha256:'+'b'*64, recovered_cursor='continue:verified',
                checkpoint_digest='sha256:checkpoint', journal_source_ref='journal')
            with patch.object(owner, 'run_registered_resume', side_effect=lambda *a, **k: k['handlers']['VERIFY_REQUIRED_RETRIEVED_SOURCES'](receipt)), patch.object(owner, 'read_startup_decision', return_value=receipt):
                args = dict(session_id='s', invocation_id='i', output_dir=root, database=root/'provider.sqlite')
                first = owner.dispatch_verified_next_handler(Path('profile'), **args)
                second = owner.dispatch_verified_next_handler(Path('profile'), **args)
            self.assertEqual(first['status'], 'REGISTERED_HANDLER_EFFECT_VERIFIED')
            self.assertEqual(first['handoff']['status'], 'HANDOFF_REPLAY_VERIFIED')
            self.assertEqual(second['handoff']['status'], 'HANDOFF_REPLAY_VERIFIED')
            with sqlite3.connect(root/'provider.sqlite') as db:
                self.assertEqual(db.execute('SELECT count(*) FROM applied_cursor').fetchone()[0], 1)

    def test_substituted_verified_provider_identity_never_dispatches(self):
        receipt = {'status': 'STARTUP_DECISION_VERIFIED',
                   'registered_action': 'VERIFY_REQUIRED_RETRIEVED_SOURCES',
                   'startup_receipt_digest': 'sha256:' + 'a' * 64}
        for identity, reference in [('f' * 64, 'sqlite:applied_cursor:' + 'f' * 64),
                                    ('f' * 64, 'sqlite:applied_cursor:' + 'e' * 64)]:
            selection = {'selection': 'VERIFY_REQUIRED_RETRIEVED_SOURCES',
                         'provider_status': 'OPERATION_EFFECT_PROVIDER_VERIFIED',
                         'effect': {'identity': identity, 'provider_reference': reference}}
            with self.subTest(identity=identity, reference=reference), \
                 patch.object(owner, 'select_verified_next_handler', return_value=selection), \
                 patch.object(owner, 'read_startup_decision', return_value=receipt), \
                 patch('scripts.continuity_verified_artifact.apply_verified_handoff') as effect:
                with self.assertRaisesRegex(ValueError, 'provenance mismatch'):
                    owner.dispatch_verified_next_handler(Path('profile'), session_id='s',
                        invocation_id='i', output_dir=Path('/tmp/a'), database=Path('/tmp/b'))
                effect.assert_not_called()

    def test_unverified_context_never_dispatches(self):
        with patch.object(owner, 'select_verified_next_handler', return_value={'selection':'HALT_UNVERIFIED_CONTEXT'}), patch.object(owner, 'read_startup_decision') as read:
            result = owner.dispatch_verified_next_handler(Path('profile'), session_id='s', invocation_id='i', output_dir=Path('/tmp/a'), database=Path('/tmp/b'))
        self.assertEqual(result['status'], 'DISPATCH_HALTED_UNVERIFIED_CONTEXT')
        read.assert_not_called()

class MissionStartCLITest(unittest.TestCase):
    def test_one_command_dispatches_recovered_context_into_registered_handler(self):
        import io
        import json
        from contextlib import redirect_stdout
        argv = ['continuity', 'mission-start', '--profile', '/tmp/owner.json',
                '--session-id', 'new-session', '--invocation-id', 'new-invocation',
                '--output-dir', '/tmp/private-handoff', '--database', '/tmp/private-cursor.sqlite',
                '--auto-resume']
        with patch('sys.argv', argv), patch.object(owner, 'run_mission_start_with_context',
                return_value={'status':'REGISTERED_HANDLER_EFFECT_VERIFIED',
                              'selection':'VERIFY_REQUIRED_RETRIEVED_SOURCES'}) as handler:
            with redirect_stdout(io.StringIO()) as output:
                owner.main()
        self.assertEqual(json.loads(output.getvalue())['status'], 'REGISTERED_HANDLER_EFFECT_VERIFIED')
        self.assertTrue(handler.call_args.kwargs['auto_resume'])
        self.assertEqual(handler.call_args.kwargs['session_id'], 'new-session')
        self.assertEqual(handler.call_args.kwargs['database'], Path('/tmp/private-cursor.sqlite'))
