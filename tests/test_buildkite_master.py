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


def test_serializing_required_parallel_lane_is_rejected() -> None:
    text = (ROOT / ".buildkite" / "pipeline.yml").read_text()
    text = text.replace(
        "key: registry-audit\n    depends_on: buildkite-master",
        "key: registry-audit\n    depends_on: source-fidelity",
        1,
    )
    results = {item.name: item for item in MODULE.validate_pipeline(text, policy())}
    assert not results["pipeline.parallel_fanout"].passed


def test_receipt_must_wait_for_every_parallel_lane() -> None:
    text = (ROOT / ".buildkite" / "pipeline.yml").read_text()
    receipt_start = text.index("key: verified-receipt")
    prefix = text[:receipt_start]
    receipt = text[receipt_start:].replace("      - automation-safety\n", "", 1)
    results = {
        item.name: item
        for item in MODULE.validate_pipeline(prefix + receipt, policy())
    }
    assert not results["pipeline.receipt_fanin"].passed
