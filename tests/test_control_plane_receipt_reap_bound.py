"""Real CLI: a failed durable launch receipt cannot release the gated command."""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(os.name != 'posix', reason='POSIX launch gate')
def test_failed_launch_receipt_aborts_without_executing(tmp_path):
    skill = tmp_path / 'skills' / 'agent' / 'SKILL.md'
    skill.parent.mkdir(parents=True)
    skill.write_text('# agent\n')
    receipt = tmp_path / 'receipt.json'
    marker = tmp_path / 'executed'
    injection = tmp_path / 'injection'
    injection.mkdir()
    (injection / 'sitecustomize.py').write_text(
        'import os\n_original=os.replace\n'
        'def failed_replace(src,dst):\n'
        '    if str(dst).endswith("receipt.json"):\n'
        '        raise OSError("injected launched receipt failure")\n'
        '    return _original(src,dst)\n'
        'os.replace=failed_replace\n'
    )
    env = dict(os.environ, PYTHONPATH=str(injection))
    command = [sys.executable, str(ROOT / 'src' / 'control_plane.py'),
               '--exec-capability', '--skills-root', str(skill.parent.parent),
               '--select', 'skill:agent', '--sha256', hashlib.sha256(skill.read_bytes()).hexdigest(),
               '--receipt-path', str(receipt), '--timeout-seconds', '1', '--',
               sys.executable, '-c', 'import pathlib,sys;pathlib.Path(sys.argv[1]).touch()', str(marker)]
    start = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=5)
    assert time.monotonic() - start < 3
    assert result.returncode != 0
    assert 'injected launched receipt failure' in result.stderr
    assert not marker.exists()
    assert json.loads(receipt.read_text())['status'] == 'pending_unverified'
