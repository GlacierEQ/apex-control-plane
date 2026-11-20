"""A timed-out child cannot force an unbounded parent wait."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(os.name != 'posix', reason='POSIX process-group timeout')
def test_timeout_path_never_uses_unbounded_child_wait(tmp_path):
    skill = tmp_path / 'skills' / 'agent' / 'SKILL.md'
    skill.parent.mkdir(parents=True)
    skill.write_text('# agent\n')
    injection = tmp_path / 'injection'
    injection.mkdir()
    (injection / 'sitecustomize.py').write_text(
        'import subprocess\n'
        '_wait=subprocess.Popen.wait\n'
        'def bounded_wait(self, timeout=None):\n'
        '    if timeout is None: raise AssertionError("unbounded wait after timeout")\n'
        '    return _wait(self, timeout=timeout)\n'
        'subprocess.Popen.wait=bounded_wait\n'
    )
    env = dict(os.environ, PYTHONPATH=str(injection))
    command = [sys.executable, str(ROOT / 'src' / 'control_plane.py'),
               '--exec-capability', '--skills-root', str(skill.parent.parent),
               '--select', 'skill:agent', '--sha256', hashlib.sha256(skill.read_bytes()).hexdigest(),
               '--timeout-seconds', '0.2', '--', sys.executable, '-S', '-c',
               'import time;time.sleep(8)']
    start = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=5)
    assert time.monotonic() - start < 3
    assert result.returncode == 124, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt['timed_out'] is True
    assert receipt['status'] == 'failed'
