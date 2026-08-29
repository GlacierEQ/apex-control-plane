from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "reconcile_genius_buildkite.py"

spec = importlib.util.spec_from_file_location("reconcile_genius_buildkite", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def test_repository_normalization_equates_supported_github_forms():
    expected = "glaciereq/genius-code"
    assert mod.normalize_repository("git@github.com:GlacierEQ/Genius-Code.git") == expected
    assert mod.normalize_repository("https://github.com/GlacierEQ/Genius-Code") == expected
    assert mod.normalize_repository("ssh://git@github.com/GlacierEQ/Genius-Code.git") == expected


def test_desired_pipeline_is_exact_main_clustered_and_status_publishing():
    spec_data = mod.PIPELINES[0]
    desired = mod.desired_pipeline(spec_data, "cluster-123")
    assert desired["slug"] == "genius-mastery"
    assert desired["cluster_id"] == "cluster-123"
    assert desired["default_branch"] == "main"
    assert desired["branch_configuration"] is None
    assert desired["repository"] == spec_data["repository"]
    provider = desired["provider_settings"]
    assert provider["publish_commit_status"] is True
    assert provider["publish_commit_status_per_step"] is True
    assert provider["build_pull_requests"] is True
    assert provider["build_pull_request_forks"] is False


def test_upload_configuration_has_stable_key_exact_sha_and_agent_v3_v4_secret_guard():
    config = mod.PIPELINE_UPLOAD_CONFIGURATION
    assert "key: upload-repository-pipeline" in config
    assert 'test "$actual" = "$BUILDKITE_COMMIT"' in config
    assert "--reject-secrets" in config
    assert "buildkite-agent pipeline upload .buildkite/pipeline.yml" in config
    assert f"queue: {mod.DEFAULT_QUEUE}" in config


def test_find_existing_pipeline_matches_repository_and_slug():
    spec_data = mod.PIPELINES[1]
    existing = {
        "slug": spec_data["slug"],
        "repository": "https://github.com/GlacierEQ/Genius-Code.git",
    }
    assert mod.find_existing_pipeline([existing], spec_data) is existing


def test_find_existing_pipeline_rejects_repository_attached_to_different_slug():
    spec_data = mod.PIPELINES[1]
    existing = {
        "slug": "wrong-slug",
        "repository": spec_data["repository"],
    }
    with pytest.raises(RuntimeError, match="refusing an implicit rename"):
        mod.find_existing_pipeline([existing], spec_data)


def test_find_existing_pipeline_rejects_slug_pointing_to_another_repository():
    spec_data = mod.PIPELINES[2]
    existing = {
        "slug": spec_data["slug"],
        "repository": "git@github.com:GlacierEQ/Definitely-Not-Genius-Verification.git",
    }
    with pytest.raises(RuntimeError, match="refusing to repoint"):
        mod.find_existing_pipeline([existing], spec_data)


def test_find_existing_pipeline_rejects_duplicate_repository_targets():
    spec_data = mod.PIPELINES[0]
    pipelines = [
        {"slug": spec_data["slug"], "repository": spec_data["repository"]},
        {"slug": "duplicate", "repository": spec_data["repository"]},
    ]
    with pytest.raises(RuntimeError, match="Multiple Buildkite pipelines target"):
        mod.find_existing_pipeline(pipelines, spec_data)


def test_trigger_build_can_be_disabled_without_api_mutation(monkeypatch):
    monkeypatch.setenv("BUILDKITE_TRIGGER_BUILD", "0")

    class NoCalls:
        def request(self, *_args, **_kwargs):
            raise AssertionError("API must not be called when triggering is disabled")

    assert (
        mod.trigger_build(
            NoCalls(),
            "genius-code",
            "GlacierEQ/Genius-Code",
            "a" * 40,
        )
        is None
    )
