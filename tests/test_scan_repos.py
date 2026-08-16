import json
from datetime import datetime, timezone

import pytest

from scripts import scan_repos
from scripts.scan_repos import (
    build_registry,
    classify,
    diff_registry,
    lifecycle,
    load_previous,
    name_signature,
    to_entry,
    write_json,
)


def repo(repo_id, name, **overrides):
    data = {
        "id": repo_id,
        "name": name,
        "full_name": f"GlacierEQ/{name}",
        "owner": {"login": "GlacierEQ"},
        "private": True,
        "fork": False,
        "archived": False,
        "disabled": False,
        "default_branch": "main",
        "language": "Python",
        "description": "test",
        "pushed_at": "2026-08-07T00:00:00Z",
        "updated_at": "2026-08-07T00:00:00Z",
        "visibility": "private",
        "html_url": f"https://github.com/GlacierEQ/{name}",
    }
    data.update(overrides)
    return data


def test_classification_priority_and_backup_detection():
    assert classify(repo(1, "apex-control-plane")) == "apex-control-plane"
    assert classify(repo(2, "unified-memory-mcp")) == "memory-connector"
    assert classify(repo(3, "apex-legal-ops")) == "legal-process"
    assert classify(repo(4, "gateway-probe")) == "experimental"
    assert classify(repo(5, "Z-BACKUP-apex-control-plane")) == "archived"
    assert classify({}) == "unknown-ownership"


def test_classification_matches_tokens_not_substrings():
    assert classify(repo(6, "capital-project")) == "unknown-ownership"
    assert classify(repo(7, "contest-results")) == "unknown-ownership"
    assert classify(repo(8, "api-gateway")) == "production-runtime"
    assert classify(repo(9, "apex_control_plane_runtime")) == "apex-control-plane"


def test_registry_declares_classification_is_not_project_authority():
    registry = build_registry([repo(10, "apex-control-plane")])
    assert (
        registry["classification_semantics"]
        == "descriptive_topology_only_not_project_authority"
    )


def test_name_signature_collapses_backup_and_version_suffixes():
    assert name_signature("Z-BACKUP-apex-memory-v2") == "apexmemory"
    assert name_signature("apex_memory") == "apexmemory"
    assert name_signature("apex-memory-v2-backup") == "apexmemory"
    assert name_signature("apex-memory-backup-v2") == "apexmemory"


def test_delta_tracks_stable_id_rename_and_state_change():
    previous = build_registry([repo(10, "old-name")])
    current = build_registry([repo(10, "new-name", archived=True)])
    delta = diff_registry(previous, current)
    assert delta["renamed_or_transferred"] == [
        {
            "repository_id": 10,
            "before": "GlacierEQ/old-name",
            "after": "GlacierEQ/new-name",
        }
    ]
    assert delta["state_changes"]
    assert delta["state_changes"][0]["changes"]["archived"] == {
        "before": False,
        "after": True,
    }


def test_delta_rejects_duplicate_repository_ids() -> None:
    current = build_registry([repo(10, "alpha")])
    previous = {
        "repositories": [
            {"repository_id": 10, "full_name": "GlacierEQ/alpha"},
            {"repository_id": 10, "full_name": "GlacierEQ/duplicate"},
        ]
    }
    with pytest.raises(TypeError, match="duplicate repository_id 10"):
        diff_registry(previous, current)


def test_registry_reports_duplicate_candidates():
    registry = build_registry(
        [
            repo(20, "apex-memory"),
            repo(21, "Z-BACKUP-apex-memory"),
        ]
    )
    assert registry["repository_count"] == 2
    assert registry["duplicate_candidates"]["apexmemory"] == [
        "GlacierEQ/apex-memory",
        "GlacierEQ/Z-BACKUP-apex-memory",
    ]


def test_required_identity_validation_and_full_name_fallback():
    now = datetime(2026, 8, 8, tzinfo=timezone.utc)
    entry = to_entry(repo(30, "fallback", full_name=None), now)
    assert entry["full_name"] == "GlacierEQ/fallback"
    with pytest.raises(ValueError, match="valid id"):
        to_entry(repo(None, "broken"), now)
    with pytest.raises(ValueError, match="valid name"):
        to_entry(repo(31, None), now)


def test_future_timestamp_has_nonnegative_age(monkeypatch):
    monkeypatch.setenv("REPO_STALE_DAYS", "180")
    now = datetime(2026, 8, 8, tzinfo=timezone.utc)
    future = repo(40, "future", pushed_at="2026-08-09T00:00:00Z")
    assert lifecycle(future, now) == "active"
    assert to_entry(future, now)["age_days"] == 0


def test_invalid_stale_days_fails_cleanly(monkeypatch):
    monkeypatch.setenv("REPO_STALE_DAYS", "not-an-int")
    with pytest.raises(RuntimeError, match="must be an integer"):
        scan_repos.stale_days()


def test_load_previous_rejects_corrupt_registry(tmp_path, monkeypatch):
    registry_path = tmp_path / "repo_registry.json"
    registry_path.write_text('{"schema_version": 1, "owner": "GlacierEQ"}')
    monkeypatch.setattr(scan_repos, "REGISTRY_PATH", registry_path)
    with pytest.raises(TypeError, match="Invalid registry state"):
        load_previous()


def test_load_previous_returns_none_only_when_absent(tmp_path, monkeypatch):
    registry_path = tmp_path / "repo_registry.json"
    monkeypatch.setattr(scan_repos, "REGISTRY_PATH", registry_path)
    assert load_previous() is None


def test_atomic_write_produces_complete_json(tmp_path):
    path = tmp_path / "nested" / "registry.json"
    payload = {"schema_version": 1, "items": list(range(100))}
    write_json(path, payload)
    assert json.loads(path.read_text()) == payload
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))
