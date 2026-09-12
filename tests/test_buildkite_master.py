from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "validate_buildkite_master.py"
SPEC = importlib.util.spec_from_file_location("validate_buildkite_master", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def policy() -> dict:
    return json.loads((ROOT / "config" / "buildkite_master_policy.json").read_text())


def test_policy_contract_passes() -> None:
    results = MODULE.validate_policy(policy())
    assert results
    assert all(item.passed for item in results), results


def test_pipeline_contract_passes() -> None:
    text = (ROOT / ".buildkite" / "pipeline.yml").read_text()
    results = MODULE.validate_pipeline(text, policy())
    assert results
    assert all(item.passed for item in results), results


def test_buildkite_source_fidelity_covers_model_attractor_defense() -> None:
    text = (ROOT / ".buildkite" / "pipeline.yml").read_text()
    assert "config/model_attractor_defense_policy.json" in text
    assert "src/model_attractor_defense.py" in text
    assert "tests/test_model_attractor_defense.py" in text


def test_evidence_scripts_use_worker_local_verified_python_runtime() -> None:
    text = (ROOT / ".buildkite" / "pipeline.yml").read_text()
    assert "PYTHON_BIN: \"/usr/local/bin/python3.12\"" not in text
    assert "PYTHON_BIN: \"/opt/homebrew/bin/python3.12\"" not in text
    resolver = 'PYTHON_BIN="$$(bash scripts/resolve_python312.sh)"'
    assert text.count(resolver) == 6
    critical_scripts = (
        "scripts/reconcile_genius_buildkite.py",
        "scripts/reconcile_mastermind_buildkite.py",
        "scripts/verify_buildkite_evidence_chain.py",
    )
    for script in critical_scripts:
        assert f'"$$PYTHON_BIN" {script}' in text
        assert f"python3 {script}" not in text


def test_python_resolver_probes_worker_local_candidates_and_fails_typed() -> None:
    text = (ROOT / "scripts" / "resolve_python312.sh").read_text()
    assert "GLACIEREQ_PYTHON312" in text
    assert "/opt/homebrew/bin/python3.12" in text
    assert "/usr/local/bin/python3.12" in text
    assert "command -v python3.12" in text
    assert "sys.version_info[:2] == (3, 12)" in text
    assert "PYTHON_RUNTIME_UNRESOLVED" in text
    assert "exit 78" in text


def test_inline_secret_literal_is_rejected() -> None:
    text = """
steps:
  - label: "bad"
    key: bad
    timeout_in_minutes: 5
    agents:
      queue: macos-self
    command: |
      set -euo pipefail
      API_TOKEN=plaintext-secret
      actual="$(git rev-parse HEAD)"
      test "$actual" = "$BUILDKITE_COMMIT"
      touch verified-ci-receipt.json SHA256SUMS
"""
    results = {item.name: item for item in MODULE.validate_pipeline(text, policy())}
    assert not results["pipeline.no_inline_secrets"].passed


def test_missing_queue_is_rejected() -> None:
    text = """
steps:
  - label: "bad"
    key: bad
    timeout_in_minutes: 5
    command: |
      set -euo pipefail
      actual="$(git rev-parse HEAD)"
      test "$actual" = "$BUILDKITE_COMMIT"
      touch verified-ci-receipt.json SHA256SUMS
"""
    results = {item.name: item for item in MODULE.validate_pipeline(text, policy())}
    assert not results["pipeline.steps_have_queues"].passed
