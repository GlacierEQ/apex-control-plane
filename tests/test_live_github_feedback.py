"""GitHub-native source-feedback adapter, with isolated provider fixtures."""
from __future__ import annotations

import pytest

from scripts import verify_live_github_feedback as bridge
from src.continuous_impact_selection import ImpactSelectionViolation


def _fake_github(resource: str, *, wrong_readback: bool = False):
    if resource.startswith("commits/"):
        commit_id = resource.removeprefix("commits/")
        return {
            "sha": commit_id, "parents": [{"sha": "previous"}],
            "files": [{"filename": "scripts/fix.py", "status": "modified"}],
        }
    if resource == "contents/scripts/fix.py?ref=previous":
        return {"sha": "a" * 40}
    if resource.startswith("contents/scripts/fix.py?ref="):
        return {"sha": ("b" if not wrong_readback else "c") * 40}
    raise AssertionError(f"unexpected provider request: {resource}")


def test_real_provider_adapter_persists_verified_learning_across_instances(monkeypatch):
    calls = []
    def native(_repo, resource, _token):
        calls.append(resource)
        return _fake_github(resource)
    monkeypatch.setattr(bridge, "github_get", native)
    result = bridge.prove_live_source_feedback("GlacierEQ/apex-control-plane", "current", "token")
    assert result["status"] == "GITHUB_NATIVE_CODE_DELTA_VERIFIED"
    assert result["model_reloaded"] is True
    assert result["human_mission_complete"] is False
    assert calls.count("commits/current") == 2
    assert calls.count("contents/scripts/fix.py?ref=current") == 2


def test_readback_disagreement_rejects_learning_without_false_success(monkeypatch):
    calls = []
    def native(_repo, resource, _token):
        calls.append(resource)
        if resource == "contents/scripts/fix.py?ref=current":
            return {"sha": ("b" if calls.count(resource) == 1 else "c") * 40}
        return _fake_github(resource)
    monkeypatch.setattr(bridge, "github_get", native)
    with pytest.raises(ImpactSelectionViolation, match="independent readback"):
        bridge.prove_live_source_feedback("GlacierEQ/apex-control-plane", "current", "token")


def test_no_material_code_change_is_explicitly_inapplicable(monkeypatch):
    monkeypatch.setattr(bridge, "github_get", lambda *_: {
        "sha": "current", "parents": [{"sha": "previous"}],
        "files": [{"filename": "README.md", "status": "modified"}],
    })
    result = bridge.prove_live_source_feedback("GlacierEQ/apex-control-plane", "current", "token")
    assert result["status"] == "NO_RELEVANT_CODE_DELTA"
    assert "model_reloaded" not in result


def test_wrong_native_commit_identity_fails(monkeypatch):
    monkeypatch.setattr(bridge, "github_get", lambda *_: {
        "sha": "different", "parents": [{"sha": "previous"}], "files": [],
    })
    with pytest.raises(ValueError, match="different commit"):
        bridge.prove_live_source_feedback("GlacierEQ/apex-control-plane", "current", "token")


def test_cross_run_feedback_reuses_checkpoint_and_prevents_duplicate_learning(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, "github_get", lambda _repo, resource, _token: _fake_github(resource))
    model = tmp_path / "model.json"
    sha = "1" * 40
    first = bridge.prove_live_source_feedback(
        "GlacierEQ/apex-control-plane", sha, "token", model_state_path=model,
    )
    assert first["status"] == "GITHUB_NATIVE_CODE_DELTA_VERIFIED"
    assert first["prior_model_restored"] is False
    state_after_first = model.read_bytes()
    second = bridge.prove_live_source_feedback(
        "GlacierEQ/apex-control-plane", sha, "token", model_state_path=model,
    )
    assert second["status"] == "GITHUB_NATIVE_FEEDBACK_ALREADY_APPLIED"
    assert second["prior_model_restored"] is True
    assert second["duplicate_learning_prevented"] is True
    assert model.read_bytes() == state_after_first


def test_cross_run_new_commit_builds_on_prior_learning(tmp_path, monkeypatch):
    def native(_repo, resource, _token):
        if resource.startswith("commits/"):
            commit = resource.partition("/")[2]
            return {"sha": commit, "parents": [{"sha": "previous"}],
                    "files": [{"filename": "scripts/fix.py", "status": "modified"}]}
        if resource.startswith("contents/scripts/fix.py?ref="):
            revision = resource.partition("ref=")[2]
            return {"sha": ("a" if revision == "previous" else "b") * 40}
        raise AssertionError(resource)
    monkeypatch.setattr(bridge, "github_get", native)
    model = tmp_path / "model.json"
    first = bridge.prove_live_source_feedback(
        "GlacierEQ/apex-control-plane", "1" * 40, "token", model_state_path=model,
    )
    second = bridge.prove_live_source_feedback(
        "GlacierEQ/apex-control-plane", "2" * 40, "token", model_state_path=model,
    )
    assert first["applied_commit_count"] == 1
    assert second["applied_commit_count"] == 2
    assert second["prior_model_restored"] is True
    import json
    checkpoint = json.loads((tmp_path / "github-feedback-checkpoint.json").read_text())
    assert checkpoint["applied_commits"] == ["1" * 40, "2" * 40]


def test_bad_cached_checkpoint_is_not_silently_accepted(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, "github_get", lambda _repo, resource, _token: _fake_github(resource))
    from src.continuous_impact_selection import ContinuousImpactSelector
    model = tmp_path / "model.json"
    checkpoint = tmp_path / "github-feedback-checkpoint.json"
    checkpoint.write_text('{"schema_version":1,"applied_commits":["bad"]}')
    with pytest.raises(ValueError, match="incompatible persisted"):
        bridge.prove_live_source_feedback(
            "GlacierEQ/apex-control-plane", "current", "token", model_state_path=model,
        )


def test_missing_cached_model_is_not_falsely_restored(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, "github_get", lambda _repo, resource, _token: _fake_github(resource))
    model = tmp_path / "model.json"
    checkpoint = tmp_path / "github-feedback-checkpoint.json"
    checkpoint.write_text('{"schema_version":1,"applied_commits":[]}')
    with pytest.raises(ValueError, match="without its learned model"):
        bridge.prove_live_source_feedback(
            "GlacierEQ/apex-control-plane", "current", "token", model_state_path=model,
        )
