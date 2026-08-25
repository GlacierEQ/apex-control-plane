from __future__ import annotations
import importlib.util, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'scripts/reconcile_buildkite_github_status.py'; s=importlib.util.spec_from_file_location('rbg',p); m=importlib.util.module_from_spec(s); sys.modules[s.name]=m; s.loader.exec_module(m)

def test_success_projection():
    r=m.reconcile({'statuses':[{'context':'buildkite/apex-control-plane','state':'success','target_url':'https://buildkite.com/casey-1/apex-control-plane/builds/79'}]},'buildkite/apex-control-plane')
    assert r.status=='VERIFIED_SUCCESS_PROJECTION' and r.build_number==79 and r.organization=='casey-1'

def test_missing_projection():
    assert m.reconcile({'statuses':[]},'buildkite/x').status=='MISSING'

def test_non_success_projection():
    assert m.reconcile({'statuses':[{'context':'buildkite/x','state':'pending','target_url':'https://buildkite.com/o/p/builds/1'}]},'buildkite/x').status=='NON_SUCCESS'

def test_invalid_buildkite_target():
    assert m.reconcile({'statuses':[{'context':'buildkite/x','state':'success','target_url':'https://example.com/x'}]},'buildkite/x').status=='INVALID_TARGET'
