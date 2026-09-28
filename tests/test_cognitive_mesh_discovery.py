from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "integration" / "discover_cognitive_mesh.py"
CONFIG = ROOT / "integration" / "cognitive_mesh.json"


def _module():
    spec = importlib.util.spec_from_file_location("discover_cognitive_mesh", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bootstrap_is_explicitly_non_authoritative() -> None:
    config = json.loads(CONFIG.read_text())
    assert config["schema"] == "glaciereq.cognitive-mesh.bootstrap.v1"
    assert "only a peer bootstrap list" in config["rule"]
    assert "current head" in config["rule"]
    assert "never treat this file as a capability map" in config["rule"]


def test_discovery_resolves_provider_default_head_and_selected_roots(monkeypatch) -> None:
    module = _module()
    responses = {
        "https://api.github.com/repos/GlacierEQ/example": {
            "default_branch": "main",
            "visibility": "private",
            "updated_at": "2026-09-22T00:00:00Z",
        },
        "https://api.github.com/repos/GlacierEQ/example/branches/main": {
            "commit": {"sha": "abc123"},
        },
        "https://api.github.com/repos/GlacierEQ/example/contents?ref=abc123": [
            {"name": "README.md", "path": "README.md", "type": "file", "sha": "r1"},
            {"name": "integration", "path": "integration", "type": "dir", "sha": "d1"},
            {"name": "noise.txt", "path": "noise.txt", "type": "file", "sha": "n1"},
        ],
    }
    monkeypatch.setattr(module, "_request_json", lambda url, token: responses[url])

    result = module.discover_repo("GlacierEQ/example", None)

    assert result["status"] == "resolved"
    assert result["default_branch"] == "main"
    assert result["head_sha"] == "abc123"
    assert {row["name"] for row in result["discovery_roots"]} == {"README.md", "integration"}


def test_provider_failure_is_recorded_as_blocked_not_absent(monkeypatch) -> None:
    module = _module()

    def fail(url, token):
        raise HTTPError(url, 403, "forbidden", hdrs=None, fp=None)

    monkeypatch.setattr(module, "_request_json", fail)
    result = module.discover_repo("GlacierEQ/example", None)

    assert result["status"] == "blocked"
    assert result["error"] == "HTTP 403"
    assert "not-found" in result["reason"]
    assert "discovery_roots" not in result
