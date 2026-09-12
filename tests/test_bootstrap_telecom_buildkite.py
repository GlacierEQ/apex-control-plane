from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "bootstrap_telecom_buildkite.py"

spec = importlib.util.spec_from_file_location("bootstrap_telecom_buildkite", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def test_telecom_bootstrap_targets_exact_feature_head() -> None:
    assert mod.TELECOM_BRANCH == "feat/telecom-foundation-boot-v1"
    assert mod.TELECOM_COMMIT == "651e51e2adc2e52e046e65362aa7c648c897fdd1"
    assert len(mod.TELECOM_COMMIT) == 40


def test_telecom_pipeline_identity_is_explicit() -> None:
    target = mod.TELECOM_SPEC
    assert target["slug"] == "telecom-valley-atlas-cabin-solar"
    assert target["github_repository"] == "GlacierEQ/Telecom-valley-atlas-cabin-solar"
    assert target["status_context"] == "buildkite/telecom-valley-atlas-cabin-solar"
    assert target["pipeline_file"] == ".buildkite/pipeline.yml"
    assert target["role"] == "telecommunications-domain"


def test_desired_pipeline_preserves_telecom_domain_authority() -> None:
    reconciler = mod.load_reconciler()
    desired = mod.desired_telecom_pipeline(reconciler, "cluster-123")
    assert desired["description"] == "GlacierEQ Telecommunications domain CI"
    assert "Genius" not in desired["description"]
    assert desired["default_branch"] == mod.TELECOM_BRANCH
    assert desired["repository"] == mod.TELECOM_SPEC["repository"]


def test_receipt_path_is_credential_free_artifact_location() -> None:
    assert mod.RECEIPT_PATH == ROOT / "artifacts" / "buildkite" / "telecom-bootstrap.json"
    assert mod.RECEIPT_SHA_PATH.name == "telecom-bootstrap.json.sha256"
