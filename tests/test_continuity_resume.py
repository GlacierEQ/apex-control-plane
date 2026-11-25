from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import unittest
from scripts.continuity_resume import apply_registered_action


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.index = self.root / 'index.sqlite'
        self.profile = self.root / 'profile.json'
        self.bodies = {'box:a': 'alpha evidence beyond excerpt ' * 30,
                       'drive:b': 'beta evidence beyond excerpt ' * 30}
        self.evidence = []
        with closing(sqlite3.connect(self.index)) as db, db:
            db.execute('CREATE TABLE documents(namespace TEXT, source_id TEXT, revision TEXT, text_sha256 TEXT, title TEXT, url TEXT, extracted_text TEXT)')
            for source, body in self.bodies.items():
                digest = hashlib.sha256(body.encode()).hexdigest()
                row = ('architecture', source, 'v1', digest, source, 'https://example.org/source', body)
                db.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?)', row)
                self.evidence.append(dict(source_id=source, revision='v1', text_sha256=digest,
                                          title=source, url=row[5], excerpt=body[:240]))
        self.index.chmod(0o600)
        self.policy = dict(schema='glaciereq.owned-mission-profile/1', mission_id='test',
                           namespace='architecture', cloud_index_db=str(self.index),
                           expected_cursor='continue:alpha', required_corrections=['CONTEXT FIRST'],
                           source_ids=list(self.bodies),
                           continuity_resume_routes={'continue:alpha': ['box:a'], 'continue:beta': ['drive:b']})
        self.write_profile()

    def write_profile(self):
        self.profile.write_text(json.dumps(self.policy))
        self.profile.chmod(0o600)

    def context(self, cursor='continue:alpha'):
        return dict(status='MISSION_CONTEXT_READY', session_id='s', invocation_id='i',
                    packet_digest='sha256:'+'a'*64, native_chatgpt_startup_verified=False,
                    context=dict(status='CONTEXT_CONSUMED_PROVIDER_VERIFIED',
                                 next_transition='RESUME_FROM_VERIFIED_CURSOR',
                                 native_chatgpt_startup_verified=False,
                                 recovered_cursor=cursor, verified_corrections=['CONTEXT FIRST'],
                                 previously_completed_action=dict(action='index_cloud', namespace='architecture', source_ids=list(self.bodies)),
                                 source_evidence=self.evidence))

    def apply(self, context=None):
        return apply_registered_action(context or self.context(), profile=self.profile)

    def test_real_sqlite_returns_full_verified_source_selected_by_cursor(self):
        out = self.apply()
        self.assertEqual(out['status'], 'REGISTERED_ACTION_APPLIED')
        self.assertEqual([s['source_id'] for s in out['sources']], ['box:a'])
        self.assertEqual(out['sources'][0]['text'], self.bodies['box:a'])
        self.policy['expected_cursor'] = 'continue:beta'
        self.write_profile()
        second = self.apply(self.context('continue:beta'))
        self.assertEqual([s['source_id'] for s in second['sources']], ['drive:b'])
        self.assertNotEqual(out['effect_digest'], second['effect_digest'])

    def test_source_mutation_rejected(self):
        with closing(sqlite3.connect(self.index)) as db, db:
            db.execute("UPDATE documents SET extracted_text='changed' WHERE source_id='box:a'")
        with self.assertRaises(ValueError): self.apply()

    def test_route_without_recovered_cursor_rejected(self):
        with self.assertRaises(ValueError): self.apply(self.context('continue:unknown'))

    def test_source_not_in_packet_rejected(self):
        c = self.context()
        c['context']['source_evidence'] = [self.evidence[1]]
        with self.assertRaises(ValueError): self.apply(c)

    def test_missing_required_correction_rejected(self):
        c = self.context()
        c['context']['verified_corrections'] = []
        with self.assertRaises(ValueError): self.apply(c)

    def test_readonly_does_not_create_database(self):
        self.policy['cloud_index_db'] = str(self.root/'missing.sqlite')
        self.write_profile()
        with self.assertRaises((ValueError, OSError)): self.apply()
        self.assertFalse((self.root/'missing.sqlite').exists())

    def test_independent_process_readback(self):
        request = json.dumps(self.context())
        command = [sys.executable, '-c', 'import json,sys; from scripts.continuity_resume import apply_registered_action; print(json.dumps(apply_registered_action(json.load(sys.stdin), profile=sys.argv[1])))', str(self.profile)]
        first = json.loads(subprocess.check_output(command, input=request, text=True))
        second = json.loads(subprocess.check_output(command, input=request, text=True))
        self.assertEqual(first, second)
        self.assertEqual(first, self.apply())

    def test_profile_without_explicit_routes_rejected(self):
        del self.policy['continuity_resume_routes']
        self.write_profile()
        with self.assertRaises(ValueError): self.apply()

    def test_mcp_apply_routes_through_real_owner_entry(self):
        from unittest.mock import patch
        from scripts import continuity_mcp_stdio as m
        from scripts import continuity_resume as resume_module
        request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {
            'name': 'glaciereq_apply_mission_context', 'arguments': {'session_id': 's', 'invocation_id': 'i'}}}
        with patch.object(m, '_config', return_value=[self.profile, self.root, self.index]), \
             patch.object(resume_module, 'enter', return_value=self.context()) as enter_call:
            result = m.handle(request)['structuredContent']
        self.assertEqual(enter_call.call_count, 1)
        self.assertEqual(result['sources'][0]['text'], self.bodies['box:a'])

    def test_mcp_never_accepts_client_selected_sources(self):
        from scripts import continuity_mcp_stdio as m
        request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {
            'name': 'glaciereq_apply_mission_context', 'arguments': {'session_id': 's', 'invocation_id': 'i', 'source_ids': ['drive:b']}}}
        with self.assertRaises(ValueError): m.handle(request)

    def test_resume_rejects_policy_change_during_recovery(self):
        from unittest.mock import patch
        from scripts.continuity_resume import resume
        def recover(**kwargs):
            self.policy['continuity_resume_routes']['continue:alpha'] = ['drive:b']
            self.write_profile()
            return self.context()
        with patch('scripts.continuity_resume.enter', side_effect=recover):
            with self.assertRaisesRegex(ValueError, 'policy changed'):
                resume(owner_script='unused', profile=self.profile, session_id='s', invocation_id='i', output_dir=self.root, database=self.index)

    def test_actual_stdio_processes_use_cursor_to_select_different_text(self):
        # Synthetic upstream owner protocol fixture, real mission_enter subprocess
        # calls, actual MCP stdio transport and actual persistent SQLite reads.
        scripts = self.root / 'scripts'
        scripts.mkdir()
        for name in ('mission_enter.py', 'continuity_resume.py', 'continuity_mcp_stdio.py'):
            shutil.copy2(Path(__file__).resolve().parents[1] / 'scripts' / name, scripts / name)
        fixture = scripts / 'run_owned_continuity.py'
        fixture.write_text('''import json, sys
from pathlib import Path
args = sys.argv[1:]
if args[0] == 'mission-start':
    print(json.dumps({'status':'REGISTERED_HANDLER_EFFECT_VERIFIED','context_packet':{'status':'CONTEXT_PACKET_CREATED','next_transition':'RESUME_FROM_VERIFIED_CURSOR','path':'fixture-packet','digest':'sha256:'+'a'*64}}))
else:
    profile = Path(args[args.index('--profile')+1])
    print((profile.parent / 'upstream.json').read_text())
''')
        env = {**os.environ, 'GLACIEREQ_CONTINUITY_PROFILE': str(self.profile),
               'GLACIEREQ_CONTINUITY_OUTPUT_DIR': str(self.root),
               'GLACIEREQ_CONTINUITY_DATABASE': str(self.index)}
        def invoke(cursor, session):
            self.policy['expected_cursor'] = cursor
            self.write_profile()
            (self.root / 'upstream.json').write_text(json.dumps(self.context(cursor)['context']))
            req = {'jsonrpc':'2.0','id':1,'method':'tools/call','params': {
                'name':'glaciereq_apply_mission_context','arguments':{'session_id':session,'invocation_id':'turn'}}}
            process = subprocess.run([sys.executable, str(scripts / 'continuity_mcp_stdio.py')],
                input=json.dumps(req)+'\n', capture_output=True, text=True, env=env, cwd=self.root, timeout=10)
            self.assertEqual(process.returncode, 0, process.stderr)
            return json.loads(process.stdout)['result']['structuredContent']
        a = invoke('continue:alpha', 'fresh-a')
        self.assertEqual(a, invoke('continue:alpha', 'fresh-a'))
        b = invoke('continue:beta', 'fresh-b')
        self.assertEqual(a['sources'][0]['text'], self.bodies['box:a'])
        self.assertEqual(b['sources'][0]['text'], self.bodies['drive:b'])
        self.assertNotEqual(a['effect_digest'], b['effect_digest'])
        self.assertFalse(a['native_chatgpt_startup_verified'])
