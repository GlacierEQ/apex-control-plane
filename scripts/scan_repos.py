"""
GlacierEQ repository estate scanner.

Enumerates repositories visible to the authenticated GitHub identity, filters to
the configured owner, writes a durable identity registry, and emits a delta
against the prior registry.

Outputs:
  repo_scan.json
  repo_registry.json
  repo_registry_delta.json
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOKEN = os.environ.get("APEX_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
OWNER = os.environ.get("GITHUB_OWNER", "GlacierEQ")
REGISTRY_PATH = Path(os.environ.get("REPO_REGISTRY_PATH", "repo_registry.json"))
SCAN_PATH = Path(os.environ.get("REPO_SCAN_PATH", "repo_scan.json"))
DELTA_PATH = Path(os.environ.get("REPO_DELTA_PATH", "repo_registry_delta.json"))
STALE_DAYS = int(os.environ.get("REPO_STALE_DAYS", "180"))

CLASS_ORDER = (
    "canonical-control-plane",
    "production-runtime",
    "memory-connector",
    "legal-process",
    "experimental",
    "archived",
    "unknown-ownership",
)

CONTROL_MARKERS = ("control-plane", "control_plane", "command-center", "command_center")
LEGAL_MARKERS = ("legal", "casebrain", "case-brain", "court", "docket", "motion", "evidence")
MEMORY_MARKERS = (
    "memory", "mcp", "connector", "supermemory", "mem0", "pinecone",
    "qdrant", "smithery", "broker", "contextstream",
)
RUNTIME_MARKERS = ("gateway", "runtime", "worker", "server", "api", "relay", "proxy", "web")
EXPERIMENT_MARKERS = ("probe", "test", "experiment", "sandbox", "prototype", "poc", "fragment")


def _request(url: str) -> urllib.request.Request:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "GlacierEQ-Estate-Registry/1.0",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    return urllib.request.Request(url, headers=headers)


def fetch_repos() -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    page = 1
    while True:
        url = (
            "https://api.github.com/user/repos"
            f"?per_page=100&page={page}&affiliation=owner,collaborator,organization_member"
            "&sort=full_name&direction=asc"
        )
        with urllib.request.urlopen(_request(url), timeout=30) as response:
            batch = json.loads(response.read())
        if not batch:
            break
        repos.extend(r for r in batch if r.get("owner", {}).get("login", "").casefold() == OWNER.casefold())
        if len(batch) < 100:
            break
        page += 1
    return repos


def classify(repo: dict[str, Any]) -> str:
    name = repo["name"].casefold()
    if repo.get("archived"):
        return "archived"
    if name.startswith(("z-backup", "backup-", "archive-")):
        return "archived"
    if any(marker in name for marker in EXPERIMENT_MARKERS):
        return "experimental"
    if any(marker in name for marker in CONTROL_MARKERS):
        return "canonical-control-plane"
    if any(marker in name for marker in LEGAL_MARKERS):
        return "legal-process"
    if any(marker in name for marker in MEMORY_MARKERS):
        return "memory-connector"
    if any(marker in name for marker in RUNTIME_MARKERS):
        return "production-runtime"
    return "unknown-ownership"


def lifecycle(repo: dict[str, Any], now: datetime) -> str:
    if repo.get("archived") or repo["name"].casefold().startswith(("z-backup", "backup-", "archive-")):
        return "archived"
    pushed_at = repo.get("pushed_at") or repo.get("updated_at")
    if not pushed_at:
        return "unknown"
    pushed = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
    age_days = (now - pushed).days
    return "stale-candidate" if age_days > STALE_DAYS else "active"


def name_signature(name: str) -> str:
    value = name.casefold()
    value = re.sub(r"^(z-?backup[-_]*|backup[-_]*|archive[-_]*)", "", value)
    value = re.sub(r"[-_]?v\d+(?:[-_.]\d+)*$", "", value)
    value = re.sub(r"[-_](copy|old|legacy|deprecated|archive|backup)$", "", value)
    return re.sub(r"[^a-z0-9]+", "", value)


def to_entry(repo: dict[str, Any], now: datetime) -> dict[str, Any]:
    pushed_at = repo.get("pushed_at") or repo.get("updated_at")
    age_days = None
    if pushed_at:
        pushed = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
        age_days = max(0, (now - pushed).days)
    return {
        "repository_id": repo["id"],
        "full_name": repo["full_name"],
        "name": repo["name"],
        "class": classify(repo),
        "lifecycle": lifecycle(repo, now),
        "visibility": repo.get("visibility", "private" if repo.get("private") else "public"),
        "private": bool(repo.get("private")),
        "fork": bool(repo.get("fork")),
        "archived": bool(repo.get("archived")),
        "disabled": bool(repo.get("disabled")),
        "default_branch": repo.get("default_branch"),
        "language": repo.get("language"),
        "description": repo.get("description"),
        "pushed_at": pushed_at,
        "updated_at": repo.get("updated_at"),
        "age_days": age_days,
        "name_signature": name_signature(repo["name"]),
        "html_url": repo.get("html_url"),
    }


def build_registry(repos: list[dict[str, Any]]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    entries = sorted((to_entry(repo, now) for repo in repos), key=lambda x: x["full_name"].casefold())
    duplicate_map: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        duplicate_map[entry["name_signature"]].append(entry["full_name"])
    duplicate_candidates = {
        signature: members
        for signature, members in sorted(duplicate_map.items())
        if signature and len(members) > 1
    }
    class_counts = Counter(entry["class"] for entry in entries)
    lifecycle_counts = Counter(entry["lifecycle"] for entry in entries)
    return {
        "schema_version": 1,
        "owner": OWNER,
        "generated_at": now.isoformat(),
        "source": "GitHub /user/repos authenticated enumeration",
        "repository_count": len(entries),
        "class_counts": {key: class_counts.get(key, 0) for key in CLASS_ORDER},
        "lifecycle_counts": dict(sorted(lifecycle_counts.items())),
        "duplicate_candidates": duplicate_candidates,
        "repositories": entries,
    }


def load_previous() -> dict[str, Any] | None:
    if not REGISTRY_PATH.exists():
        return None
    try:
        data = json.loads(REGISTRY_PATH.read_text())
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def diff_registry(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    now = current["generated_at"]
    if not previous:
        return {
            "schema_version": 1,
            "generated_at": now,
            "baseline": True,
            "new": [r["full_name"] for r in current["repositories"]],
            "removed_or_transferred": [],
            "renamed_or_transferred": [],
            "state_changes": [],
        }

    old_by_id = {r["repository_id"]: r for r in previous.get("repositories", [])}
    new_by_id = {r["repository_id"]: r for r in current["repositories"]}

    new_ids = sorted(set(new_by_id) - set(old_by_id))
    removed_ids = sorted(set(old_by_id) - set(new_by_id))
    renamed = []
    state_changes = []

    for repo_id in sorted(set(old_by_id) & set(new_by_id)):
        old = old_by_id[repo_id]
        new = new_by_id[repo_id]
        if old.get("full_name") != new.get("full_name"):
            renamed.append({
                "repository_id": repo_id,
                "before": old.get("full_name"),
                "after": new.get("full_name"),
            })
        fields = ("archived", "disabled", "default_branch", "class", "lifecycle", "visibility", "fork")
        changes = {
            field: {"before": old.get(field), "after": new.get(field)}
            for field in fields
            if old.get(field) != new.get(field)
        }
        if changes:
            state_changes.append({
                "repository_id": repo_id,
                "full_name": new.get("full_name"),
                "changes": changes,
            })

    return {
        "schema_version": 1,
        "generated_at": now,
        "baseline": False,
        "new": [new_by_id[i]["full_name"] for i in new_ids],
        "removed_or_transferred": [old_by_id[i]["full_name"] for i in removed_ids],
        "renamed_or_transferred": renamed,
        "state_changes": state_changes,
    }


def legacy_scan(registry: dict[str, Any]) -> dict[str, Any]:
    buckets = {"total": registry["repository_count"], "stale": [], "backup": [], "no_description": [], "active": []}
    for entry in registry["repositories"]:
        compact = {
            "name": entry["name"],
            "age_days": entry["age_days"],
            "language": entry["language"],
            "private": entry["private"],
        }
        if entry["class"] == "archived":
            buckets["backup"].append(compact)
        elif entry["lifecycle"] == "stale-candidate":
            buckets["stale"].append(compact)
        elif not entry["description"]:
            buckets["no_description"].append(compact)
        else:
            buckets["active"].append(compact)
    return buckets


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")


def main() -> int:
    if not TOKEN:
        print("ERROR: APEX_GITHUB_TOKEN or GITHUB_TOKEN not set")
        return 1
    previous = load_previous()
    repos = fetch_repos()
    registry = build_registry(repos)
    delta = diff_registry(previous, registry)
    write_json(REGISTRY_PATH, registry)
    write_json(DELTA_PATH, delta)
    write_json(SCAN_PATH, legacy_scan(registry))
    print(f"Owner: {OWNER}")
    print(f"Repositories: {registry['repository_count']}")
    print("Classes: " + ", ".join(f"{k}={v}" for k, v in registry["class_counts"].items()))
    print(
        "Delta: "
        f"new={len(delta['new'])}, "
        f"removed_or_transferred={len(delta['removed_or_transferred'])}, "
        f"renamed_or_transferred={len(delta['renamed_or_transferred'])}, "
        f"state_changes={len(delta['state_changes'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
