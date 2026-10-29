"""GitHub-native source-feedback adapter, with isolated provider fixtures."""
from __future__ import annotations

import pytest

from scripts import verify_live_github_feedback as bridge
from src.continuous_impact_selection import ImpactSelectionViolation


def _fake_github(resource: str, *, wrong_readback: bool = False):
    if resource == "commits/current":
        return {
            "sha": "current", "parents": [{"sha": "previous"}],
            "files": [{"filename": "scripts/fix.py", "status": "modified"}],
        }
    if resource == "contents/scripts/fix.py?ref=previous":
        return {"sha": "a" * 40}
    if resource == "contents/scripts/fix.py?ref=current":
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
