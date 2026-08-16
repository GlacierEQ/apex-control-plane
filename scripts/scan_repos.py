"""
GlacierEQ repository estate scanner.

Enumerates repositories visible to the authenticated GitHub identity, filters to
the configured owner, writes a durable identity registry, and emits a delta
against the prior registry.

Repository classes are descriptive topology labels only. They do not confer
project-direction authority; APEX binds that authority to OPERATOR_INTENT.

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
    "apex-control-plane",
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
    """Return a descriptive estate class, never an authority designation."""
    name = str(repo.get("name") or "").casefold()
    if repo.get("archived"):
        return "archived"
    if name.startswith(("z-backup", "backup-", "archive-")):
        return "archived"
    if _has_marker(name, EXPERIMENT_MARKERS):
        return "experimental"
    if _has_marker(name, CONTROL_MARKERS):
        return "apex-control-plane"
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
    while True:
        previous = value
        value = re.sub(r"[-_]?v\d+(?:[-_.]\d+)*$", "", value)
        value = re.sub(r"[-_](copy|old|legacy|deprecated|archive|backup)$", "", value)
        if value == previous:
            break
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
        key=lambda row: (CLASS_ORDER.index(row["class"]), row["full_name"].casefold()),
    )
    classes = Counter(row["class"] for row in entries)
    signatures: dict[str, list[str]] = defaultdict(list)
    for row in entries:
        signatures[row["name_signature"]].append(row["full_name"])
    duplicates = {
        signature: sorted(names, key=str.casefold)
        for signature, names in sorted(signatures.items())
        if signature and len(names) > 1
    }
    return {
        "schema_version": 2,
        "owner": OWNER,
        "generated_at": now.isoformat(),
        "repository_count": len(entries),
        "classification_semantics": "descriptive_topology_only_not_project_authority",
        "class_counts": dict(classes),
        "duplicate_candidates": duplicates,
        "repositories": entries,
    }


def _index_by_id(registry: dict[str, Any]) -> dict[int, dict[str, Any]]:
    repositories = registry.get("repositories")
    if not isinstance(repositories, list):
        raise TypeError("Invalid registry state: repositories must be a list")
    indexed: dict[int, dict[str, Any]] = {}
    for row in repositories:
        if not isinstance(row, dict):
            raise TypeError(
                "Invalid registry state: repository entry must be an object"
            )
        repo_id = row.get("repository_id")
        if isinstance(repo_id, bool) or not isinstance(repo_id, int) or repo_id <= 0:
            raise TypeError(
                "Invalid registry state: repository_id must be a positive integer"
            )
        indexed[repo_id] = row
    return indexed


def diff_registry(
    previous: dict[str, Any] | None, current: dict[str, Any]
) -> dict[str, Any]:
    if previous is None:
        return {
            "schema_version": 2,
            "generated_at": current["generated_at"],
            "baseline": True,
            "added": [row["full_name"] for row in current["repositories"]],
            "removed": [],
            "renamed_or_transferred": [],
            "state_changes": [],
        }

    before = _index_by_id(previous)
    after = _index_by_id(current)
    before_ids = set(before)
    after_ids = set(after)
    changes = []
    for repo_id in sorted(before_ids & after_ids):
        old = before[repo_id]
        new = after[repo_id]
        fields = (
            "full_name",
            "class",
            "lifecycle",
            "archived",
            "disabled",
            "default_branch",
        )
        delta = {
            field: {"before": old.get(field), "after": new.get(field)}
            for field in fields
            if old.get(field) != new.get(field)
        }
        if delta:
            changes.append({"repository_id": repo_id, "changes": delta})

    return {
        "schema_version": 2,
        "generated_at": current["generated_at"],
        "baseline": False,
        "added": [after[i]["full_name"] for i in sorted(after_ids - before_ids)],
        "removed": [before[i]["full_name"] for i in sorted(before_ids - after_ids)],
        "renamed_or_transferred": [
            {
                "repository_id": i,
                "before": before[i]["full_name"],
                "after": after[i]["full_name"],
            }
            for i in sorted(before_ids & after_ids)
            if before[i]["full_name"] != after[i]["full_name"]
        ],
        "state_changes": changes,
    }


def load_previous() -> dict[str, Any] | None:
    if not REGISTRY_PATH.exists():
        return None
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Invalid registry state at {REGISTRY_PATH}") from error
    if not isinstance(data, dict) or not isinstance(data.get("repositories"), list):
        raise TypeError(f"Invalid registry state at {REGISTRY_PATH}")
    return data


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            tmp_path = Path(handle.name)
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def main() -> int:
    try:
        repos = fetch_repos()
        previous = load_previous()
        current = build_registry(repos)
        delta = diff_registry(previous, current)
        write_json(SCAN_PATH, {"schema_version": 2, "repositories": repos})
        write_json(REGISTRY_PATH, current)
        write_json(DELTA_PATH, delta)
    except (RuntimeError, ValueError, TypeError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
