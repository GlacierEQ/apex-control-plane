from scripts.scan_repos import build_registry, classify, diff_registry, name_signature


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
    assert classify(repo(1, "apex-control-plane")) == "canonical-control-plane"
    assert classify(repo(2, "unified-memory-mcp")) == "memory-connector"
    assert classify(repo(3, "apex-legal-ops")) == "legal-process"
    assert classify(repo(4, "gateway-probe")) == "experimental"
    assert classify(repo(5, "Z-BACKUP-apex-control-plane")) == "archived"


def test_name_signature_collapses_backup_and_version_suffixes():
    assert name_signature("Z-BACKUP-apex-memory-v2") == "apexmemory"
    assert name_signature("apex_memory") == "apexmemory"


def test_delta_tracks_stable_id_rename_and_state_change():
    previous = build_registry([repo(10, "old-name")])
    current = build_registry([repo(10, "new-name", archived=True)])
    delta = diff_registry(previous, current)
    assert delta["renamed_or_transferred"] == [
        {"repository_id": 10, "before": "GlacierEQ/old-name", "after": "GlacierEQ/new-name"}
    ]
    assert delta["state_changes"]
    assert delta["state_changes"][0]["changes"]["archived"] == {"before": False, "after": True}


def test_registry_reports_duplicate_candidates():
    registry = build_registry([
        repo(20, "apex-memory"),
        repo(21, "Z-BACKUP-apex-memory"),
    ])
    assert registry["repository_count"] == 2
    assert registry["duplicate_candidates"]["apexmemory"] == [
        "GlacierEQ/apex-memory",
        "GlacierEQ/Z-BACKUP-apex-memory",
    ]
