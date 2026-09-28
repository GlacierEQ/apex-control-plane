from __future__ import annotations
import importlib.util, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'scripts/buildkite_master_inventory.py'; s=importlib.util.spec_from_file_location('bmi',p); m=importlib.util.module_from_spec(s); sys.modules[s.name]=m; s.loader.exec_module(m)

def test_redact_removes_sensitive_keys():
    x=m.redact({'token':'abc','nested':{'secret':'x','key':'SAFE'}})
    assert 'token' not in x and 'secret' not in x['nested'] and x['nested']['key']=='SAFE'

def test_compact_agent_keeps_current_job_without_credentials():
    x=m.compact_agent({'id':'a','queue':'oracle-arm64','job':{'id':'j','state':'running','web_url':'u','env':{'SECRET':'x'}}})
    assert x['current_job']=={'id':'j','state':'running','web_url':'u'}

def test_scope_state_preserves_unknown():
    assert m.scope_state({'read_builds'},'read_agents')['status']=='UNVERIFIED_MISSING_SCOPE'
