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
import sys
import tempfile
import urllib.error
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
LEGAL_MARKERS = (
    "legal",
    "casebrain",
    "case-brain",
    "court",
    "docket",
    "motion",
    "evidence",
)
MEMORY_MARKERS = (
    "memory",
    "mcp",
    "connector",
    "supermemory",
    "mem0",
    "pinecone",
    "qdrant",
    "smithery",
    "broker",
    "contextstream",
)
RUNTIME_MARKERS = (
    "gateway",
    "runtime",
    "worker",
    "server",
    "api",
    "relay",
    "proxy",
    "web",
)
EXPERIMENT_MARKERS = (
    "probe",
    "test",
    "experiment",
    "sandbox",
    "prototype",
    "poc",
    "fragment",
)
MAX_REPOSITORY_PAGES = 100


def stale_days() -> int:
    raw = os.environ.get("REPO_STALE_DAYS", "180")
    try:
        value = int(raw)
    except ValueError as error:
        raise RuntimeError("REPO_STALE_DAYS must be an integer") from error
    if value < 0:
        raise RuntimeError("REPO_STALE_DAYS must be non-negative")
    return value


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
    for page in range(1, MAX_REPOSITORY_PAGES + 1):
        url = (
            "https://api.github.com/user/repos"
            f"?per_page=100&page={page}&affiliation=owner,collaborator,organization_member"
            "&sort=full_name&direction=asc"
        )
        try:
            with urllib.request.urlopen(_request(url), timeout=30) as response:
                batch = json.loads(response.read())
        except (
            urllib.error.URLError,
            TimeoutError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as error:
            raise RuntimeError(
                f"GitHub repository enumeration failed on page {page}"
            ) from error
        if not isinstance(batch, list):
            raise TypeError(
                f"GitHub repository enumeration returned invalid page {page}"
            )
        if not batch:
            return repos
        repos.extend(
            repo
            for repo in batch
            if isinstance(repo, dict)
            and repo.get("owner", {}).get("login", "").casefold() == OWNER.casefold()
        )
        if len(batch) < 100:
            return repos
    raise RuntimeError("GitHub repository enumeration exceeded page limit")


def _normalized_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def _has_marker(name: str, markers: tuple[str, ...]) -> bool:
    normalized_name = _normalized_name(name)
    padded_name = f"-{normalized_name}-"
    return any(
        f"-{_normalized_name(marker)}-" in padded_name
        for marker in markers
        if _normalized_name(marker)
    )


def classify(repo: dict[str, Any]) -> str:
    name = str(repo.get("name") or "").casefold()
    if repo.get("archived"):
        return "archived"
    if name.startswith(("z-backup", "backup-", "archive-")):
        return "archived"
    if _has_marker(name, EXPERIMENT_MARKERS):
        return "experimental"
    if _has_marker(name, CONTROL_MARKERS):
        return "canonical-control-plane"
    if _has_marker(name, LEGAL_MARKERS):
        return "legal-process"
    if _has_marker(name, MEMORY_MARKERS):
        return "memory-connector"
    if _has_marker(name, RUNTIME_MARKERS):
        return "production-runtime"
    return "unknown-ownership"


def _parse_repo_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"Invalid repository timestamp: {value}") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def lifecycle(repo: dict[str, Any], now: datetime) -> str:
    name = str(repo.get("name") or "").casefold()
    if repo.get("archived") or name.startswith(("z-backup", "backup-", "archive-")):
        return "archived"
    pushed = _parse_repo_timestamp(repo.get("pushed_at") or repo.get("updated_at"))
    if pushed is None:
        return "unknown"
    age_days = max(0, (now - pushed).days)
    return "stale-candidate" if age_days > stale_days() else "active"


def name_signature(name: str) -> str:
    value = name.casefold()
    value = re.sub(r"^(z-?backup[-_]*|backup[-_]*|archive[-_]*)", "", value)
    value = re.sub(r"[-_]?v\d+(?:[-_.]\d+)*$", "", value)
    value = re.sub(r"[-_](copy|old|legacy|deprecated|archive|backup)$", "", value)
    return re.sub(r"[^a-z0-9]+", "", value)


def _identity(repo: dict[str, Any]) -> tuple[int, str, str]:
    repo_id = repo.get("id")
    name = repo.get("name")
    if isinstance(repo_id, bool) or not isinstance(repo_id, int) or repo_id <= 0:
        raise ValueError(f"Repository missing valid id: {repo_id!r}")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Repository missing valid name: {name!r}")
    full_name = repo.get("full_name")
    if not isinstance(full_name, str) or not full_name.strip():
        full_name = f"{OWNER}/{name}"
    return repo_id, name, full_name


def to_entry(repo: dict[str, Any], now: datetime) -> dict[str, Any]:
    repo_id, name, full_name = _identity(repo)
    pushed_at = repo.get("pushed_at") or repo.get("updated_at")
    pushed = _parse_repo_timestamp(pushed_at)
    age_days = max(0, (now - pushed).days) if pushed else None
    return {
        "repository_id": repo_id,
        "full_name": full_name,
        "name": name,
        "class": classify(repo),
        "lifecycle": lifecycle(repo, now),
        "visibility": repo.get(
            "visibility", "private" if repo.get("private") else "public"
        ),
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
        "name_signature": name_signature(name),
        "html_url": repo.get("html_url"),
    }


def build_registry(repos: list[dict[str, Any]]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    entries = sorted(
        (to_entry(repo, now) for repo in repos),
        key=lambda entry: entry["full_name"].casefold(),
    )
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


def _validate_registry(data: Any, source: str) -> dict[str, Any]:
    if (
        not isinstance(data, dict)
        or data.get("schema_version") != 1
        or data.get("owner") != OWNER
        or not isinstance(data.get("repositories"), list)
    ):
        raise RuntimeError(f"Invalid registry state in {source}")
    seen_ids: set[int] = set()
    for index, entry in enumerate(data["repositories"]):
        if not isinstance(entry, dict):
            raise TypeError(f"Invalid repository entry {index} in {source}")
        repo_id = entry.get("repository_id")
        full_name = entry.get("full_name")
        if (
            isinstance(repo_id, bool)
            or not isinstance(repo_id, int)
            or repo_id <= 0
            or repo_id in seen_ids
            or not isinstance(full_name, str)
            or not full_name
        ):
            raise RuntimeError(
                f"Invalid repository identity at index {index} in {source}"
            )
        seen_ids.add(repo_id)
    return data


def load_previous() -> dict[str, Any] | None:
    if not REGISTRY_PATH.exists():
        return None
    try:
        data = json.loads(REGISTRY_PATH.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Cannot load {REGISTRY_PATH}") from error
    return _validate_registry(data, str(REGISTRY_PATH))


def diff_registry(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, Any]:
    current = _validate_registry(current, "current registry")
    if previous is not None:
        previous = _validate_registry(previous, "previous registry")
    now = current["generated_at"]
    if previous is None:
        return {
            "schema_version": 1,
            "generated_at": now,
            "baseline": True,
            "new": [repo["full_name"] for repo in current["repositories"]],
            "removed_or_transferred": [],
            "renamed_or_transferred": [],
            "state_changes": [],
        }

    old_by_id = {repo["repository_id"]: repo for repo in previous["repositories"]}
    new_by_id = {repo["repository_id"]: repo for repo in current["repositories"]}

    new_ids = sorted(set(new_by_id) - set(old_by_id))
    removed_ids = sorted(set(old_by_id) - set(new_by_id))
    renamed = []
    state_changes = []

    for repo_id in sorted(set(old_by_id) & set(new_by_id)):
        old = old_by_id[repo_id]
        new = new_by_id[repo_id]
        if old.get("full_name") != new.get("full_name"):
            renamed.append(
                {
                    "repository_id": repo_id,
                    "before": old.get("full_name"),
                    "after": new.get("full_name"),
                }
            )
        fields = (
            "archived",
            "disabled",
            "default_branch",
            "class",
            "lifecycle",
            "visibility",
            "fork",
        )
        changes = {
            field: {"before": old.get(field), "after": new.get(field)}
            for field in fields
            if old.get(field) != new.get(field)
        }
        if changes:
            state_changes.append(
                {
                    "repository_id": repo_id,
                    "full_name": new.get("full_name"),
                    "changes": changes,
                }
            )

    return {
        "schema_version": 1,
        "generated_at": now,
        "baseline": False,
        "new": [new_by_id[repo_id]["full_name"] for repo_id in new_ids],
        "removed_or_transferred": [
            old_by_id[repo_id]["full_name"] for repo_id in removed_ids
        ],
        "renamed_or_transferred": renamed,
        "state_changes": state_changes,
    }


def legacy_scan(registry: dict[str, Any]) -> dict[str, Any]:
    registry = _validate_registry(registry, "legacy scan input")
    buckets = {
        "total": registry["repository_count"],
        "stale": [],
        "backup": [],
        "no_description": [],
        "active": [],
    }
    for entry in registry["repositories"]:
        compact = {
            "name": entry.get("name"),
            "age_days": entry.get("age_days"),
            "language": entry.get("language"),
            "private": entry.get("private"),
        }
        if entry.get("class") == "archived":
            buckets["backup"].append(compact)
        elif entry.get("lifecycle") == "stale-candidate":
            buckets["stale"].append(compact)
        elif not entry.get("description"):
            buckets["no_description"].append(compact)
        else:
            buckets["active"].append(compact)
    return buckets


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(payload, handle, indent=2, sort_keys=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _failure(message: str) -> int:
    print(
        json.dumps({"ok": False, "error": message}, separators=(",", ":")),
        file=sys.stderr,
    )
    return 1


def main() -> int:
    if not TOKEN:
        return _failure("APEX_GITHUB_TOKEN or GITHUB_TOKEN not set")
    try:
        stale_days()
        previous = load_previous()
        repos = fetch_repos()
        registry = build_registry(repos)
        delta = diff_registry(previous, registry)
        scan = legacy_scan(registry)
        write_json(REGISTRY_PATH, registry)
        write_json(DELTA_PATH, delta)
        write_json(SCAN_PATH, scan)
    except (RuntimeError, TypeError, ValueError, OSError) as error:
        return _failure(str(error))

    print(f"Owner: {OWNER}")
    print(f"Repositories: {registry['repository_count']}")
    print(
        "Classes: "
        + ", ".join(f"{key}={value}" for key, value in registry["class_counts"].items())
    )
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
