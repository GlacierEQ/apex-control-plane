#!/usr/bin/env python3
"""Discover the current GlacierEQ peer mesh from live GitHub repository state.

This is intentionally a discovery tool, not a topology authority. It records what
exists at the queried source heads and emits a task-scoped snapshot.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_CONFIG = Path(__file__).with_name("cognitive_mesh.json")
API_ROOT = "https://api.github.com"
CANDIDATE_NAMES = {
    "README.md", "AGENTS.md", "SKILL.md", "HIERARCHY.md",
    "ASPEN_GROVE_CONSTELLATION.json", "APEX_POINTER_INDEX.json",
    "connector_registry.json", "GROVE_MANIFEST.json", "SKILLS_MANIFEST.json",
}
CANDIDATE_DIRS = {
    "registry", "generated", "integration", "config", "skills", "combo-skills",
    "mega-skills", "connectors", "mcp", "memory", "machine", ".glaciereq",
}


def _request_json(url: str, token: str | None) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "glaciereq-cognitive-mesh-discovery/1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, headers=headers)
    with urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def discover_repo(repo: str, token: str | None) -> dict[str, Any]:
    out: dict[str, Any] = {"repo": repo, "status": "unresolved"}
    try:
        meta = _request_json(f"{API_ROOT}/repos/{repo}", token)
        branch = meta["default_branch"]
        branch_meta = _request_json(f"{API_ROOT}/repos/{repo}/branches/{branch}", token)
        head_sha = branch_meta["commit"]["sha"]
        root = _request_json(f"{API_ROOT}/repos/{repo}/contents?ref={head_sha}", token)
        roots = []
        for item in root if isinstance(root, list) else []:
            name = item.get("name")
            if name in CANDIDATE_NAMES or name in CANDIDATE_DIRS:
                roots.append({
                    "name": name,
                    "path": item.get("path"),
                    "type": item.get("type"),
                    "sha": item.get("sha"),
                })
        out.update({
            "status": "resolved",
            "default_branch": branch,
            "head_sha": head_sha,
            "visibility": meta.get("visibility"),
            "updated_at": meta.get("updated_at"),
            "discovery_roots": roots,
        })
    except HTTPError as exc:
        out.update({
            "status": "blocked",
            "error": f"HTTP {exc.code}",
            "reason": "auth/permission/not-found or API policy",
        })
    except (URLError, TimeoutError) as exc:
        out.update({
            "status": "blocked",
            "error": type(exc).__name__,
            "reason": str(exc),
        })
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        out.update({
            "status": "invalid-response",
            "error": type(exc).__name__,
            "reason": str(exc),
        })
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    peers = config.get("peers", [])
    if not peers or not all(isinstance(repo, str) and "/" in repo for repo in peers):
        raise SystemExit("cognitive mesh config must contain non-empty repo strings")

    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    snapshot = {
        "schema": "glaciereq.cognitive-mesh.snapshot.v1",
        "authority": (
            "task-scoped observation only; rediscover before subsequent routing "
            "after material change"
        ),
        "peers": [discover_repo(repo, token) for repo in peers],
    }
    payload = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0 if any(p["status"] == "resolved" for p in snapshot["peers"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
