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


def test_upload_configuration_accepts_exact_or_symbolic_commit_and_guards_agent_versions():
    config = mod.PIPELINE_UPLOAD_CONFIGURATION
    assert "key: upload-repository-pipeline" in config
    assert 'requested="${BUILDKITE_COMMIT:-}"' in config
    assert 'resolved="${BUILDKITE_COMMIT_RESOLVED:-}"' in config
    assert 'HEAD)' in config
    assert 'test "$actual" = "$resolved"' in config
    assert '"$actual")' in config
    assert 'exit 42' in config
    assert "--reject-secrets" in config
    assert "set -- pipeline upload .buildkite/pipeline.yml" in config
    assert 'buildkite-agent "$@"' in config
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


def test_verify_returned_build_commit_accepts_symbolic_ref():
    mod.verify_returned_build_commit({"commit": "HEAD"}, "a" * 40)


def test_verify_returned_build_commit_accepts_requested_sha():
    requested = "a" * 40
    mod.verify_returned_build_commit({"commit": requested}, requested)


def test_verify_returned_build_commit_rejects_conflicting_sha():
    with pytest.raises(RuntimeError, match="Build commit mismatch"):
        mod.verify_returned_build_commit({"commit": "b" * 40}, "a" * 40)


def test_target_registry_is_explicit_unique_and_status_addressable():
    targets = mod.PIPELINES
    assert {item["slug"] for item in targets} == {
        "genius-mastery",
        "genius-code",
        "genius-verification",
    }
    assert len({item["github_repository"] for item in targets}) == len(targets)
    for item in targets:
        assert item["status_context"] == f"buildkite/{item['slug']}"
        assert item["pipeline_file"] == ".buildkite/pipeline.yml"
        assert item["role"] in {"mastery-kernel", "code-domain", "verification-domain"}


def test_superseded_builds_are_cancelled_and_skipped():
    desired = mod.desired_pipeline(mod.PIPELINES[0], "cluster-123")
    assert desired["cancel_running_branch_builds"] is True
    assert desired["skip_queued_branch_builds"] is True


def test_upload_configuration_rejects_parse_warnings_and_dry_runs_first():
    config = mod.PIPELINE_UPLOAD_CONFIGURATION
    assert "--reject-parse-warnings" in config
    assert "--dry-run" in config
    assert "grep -q -- '--dry-run'" in config


@pytest.mark.parametrize("state", ["pending", "success"])
def test_existing_healthy_projection_is_reused(state):
    assert mod.should_trigger_for_projection({"state": state}) is False


@pytest.mark.parametrize("state", ["error", "failure"])
def test_failed_projection_is_retried(state):
    assert mod.should_trigger_for_projection({"state": state}) is True


def test_missing_projection_triggers_initial_build():
    assert mod.should_trigger_for_projection(None) is True


def test_pipeline_readback_accepts_exact_reconciled_state():
    spec_data = mod.PIPELINES[0]
    desired = mod.desired_pipeline(spec_data, "cluster-123")
    readback = {
        **desired,
        "repository": "https://github.com/GlacierEQ/Genius-Mastery.git",
    }
    mod.verify_pipeline_readback(readback, spec_data, "cluster-123")


def test_pipeline_readback_rejects_stale_build_policy_drift():
    spec_data = mod.PIPELINES[0]
    readback = mod.desired_pipeline(spec_data, "cluster-123")
    readback["cancel_running_branch_builds"] = False
    with pytest.raises(RuntimeError, match="cancel_running_branch_builds"):
        mod.verify_pipeline_readback(readback, spec_data, "cluster-123")


def test_terminal_verification_policy_is_fail_closed():
    policy = mod.REGISTRY["verification_policy"]
    assert policy["wait_for_terminal_builds"] is True
    assert policy["build_timeout_seconds"] > 0
    assert policy["projection_timeout_seconds"] > 0
    assert "passed" in policy["build_success_states"]
    assert {"failed", "canceled", "skipped"}.issubset(
        set(policy["build_failure_states"])
    )
    assert "success" in policy["projection_success_states"]
    assert {"failure", "error"}.issubset(
        set(policy["projection_failure_states"])
    )


def test_parse_buildkite_build_url_requires_expected_org_and_pipeline():
    assert (
        mod.parse_buildkite_build_url(
            "https://buildkite.com/casey-1/genius-code/builds/42",
            "genius-code",
        )
        == 42
    )
    with pytest.raises(RuntimeError, match="organization mismatch"):
        mod.parse_buildkite_build_url(
            "https://buildkite.com/not-casey/genius-code/builds/42",
            "genius-code",
        )
    with pytest.raises(RuntimeError, match="pipeline mismatch"):
        mod.parse_buildkite_build_url(
            "https://buildkite.com/casey-1/wrong/builds/42",
            "genius-code",
        )


def test_resolve_build_number_prefers_triggered_build():
    result = {
        "build": {"number": 19},
        "preexisting_projection": {
            "target_url": "https://buildkite.com/casey-1/genius-code/builds/18"
        },
        "pipeline": {"slug": "genius-code"},
        "repository": "GlacierEQ/Genius-Code",
    }
    assert mod.resolve_build_number(result) == 19


def test_resolve_build_number_uses_verified_projection_when_reusing():
    result = {
        "build": None,
        "preexisting_projection": {
            "target_url": "https://buildkite.com/casey-1/genius-verification/builds/7"
        },
        "pipeline": {"slug": "genius-verification"},
        "repository": "GlacierEQ/Genius-Verification",
    }
    assert mod.resolve_build_number(result) == 7
