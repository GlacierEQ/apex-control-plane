#!/usr/bin/env python3
"""Reconcile the core Genius repositories into the existing Buildkite execution fabric.

This mutation-capable tool reuses the established Buildkite organization and cluster
lineage, creates or updates the three Genius pipelines, ensures GitHub webhook
delivery, resolves each repository's exact main SHA, and optionally triggers a
verification build for that exact commit.

Credentials are never embedded in source or receipts.

Credential resolution:
- Buildkite: BUILDKITE_API_TOKEN, else ~/.config/buildkite/api-token
- GitHub: optional GITHUB_TOKEN for higher API rate limits; public reads work
  without it because the core Genius repositories are public.

Required Buildkite scopes:
- read_pipelines
- write_pipelines
- write_builds
- read_clusters only when the donor pipeline does not expose a cluster_id
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API_ROOT = "https://api.buildkite.com/v2"
GITHUB_API_ROOT = "https://api.github.com"
ROOT = Path(__file__).resolve().parents[1]
TARGETS_PATH = ROOT / "config" / "genius_buildkite_targets.json"
BUILD_URL_RE = re.compile(
    r"^https://buildkite\.com/(?P<org>[^/]+)/(?P<slug>[^/]+)/builds/(?P<number>\d+)(?:/.*)?$"
)


def load_target_registry(path: Path = TARGETS_PATH) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise RuntimeError("Unsupported Genius Buildkite target registry schema.")
    targets = data.get("targets")
    if not isinstance(targets, list) or not targets:
        raise RuntimeError("Genius Buildkite target registry must contain targets.")
    required = {
        "name",
        "slug",
        "repository",
        "github_repository",
        "status_context",
        "pipeline_file",
        "role",
    }
    seen_slugs: set[str] = set()
    seen_repos: set[str] = set()
    for target in targets:
        if not isinstance(target, dict) or not required.issubset(target):
            raise RuntimeError(f"Invalid Genius Buildkite target: {target!r}")
        slug = str(target["slug"])
        github_repository = str(target["github_repository"]).casefold()
        if slug in seen_slugs:
            raise RuntimeError(f"Duplicate Genius Buildkite slug: {slug}")
        if github_repository in seen_repos:
            raise RuntimeError(
                f"Duplicate Genius Buildkite repository: {target['github_repository']}"
            )
        seen_slugs.add(slug)
        seen_repos.add(github_repository)
    return data


REGISTRY = load_target_registry()
ORG = os.getenv("BUILDKITE_ORG", str(REGISTRY["organization"]))
DONOR_PIPELINE = os.getenv(
    "BUILDKITE_DONOR_PIPELINE", str(REGISTRY["donor_pipeline"])
)
DEFAULT_BRANCH = str(REGISTRY["default_branch"])
DEFAULT_QUEUE = os.getenv(
    "BUILDKITE_GENIUS_QUEUE", str(REGISTRY["default_queue"])
)
PIPELINES: tuple[dict[str, str], ...] = tuple(REGISTRY["targets"])

RECEIPT_PATH = Path(
    os.getenv(
        "BUILDKITE_GENIUS_RECEIPT",
        "artifacts/buildkite/genius-reconciliation.json",
    )
)
if not RECEIPT_PATH.is_absolute():
    RECEIPT_PATH = ROOT / RECEIPT_PATH

# Agent v3 exposes --reject-secrets. Agent v4 rejects secret-bearing uploads by
# default and removed the flag, so the upload step feature-detects the v3 option.
PIPELINE_UPLOAD_CONFIGURATION = f"""agents:
  queue: {DEFAULT_QUEUE}
steps:
  - label: ":pipeline: Load repository pipeline"
    key: upload-repository-pipeline
    timeout_in_minutes: 5
    command: |
      set -euo pipefail
      actual="$(git rev-parse HEAD)"
      requested="${BUILDKITE_COMMIT:-}"
      resolved="${BUILDKITE_COMMIT_RESOLVED:-}"
      case "$requested" in
        HEAD)
          if [ -n "$resolved" ]; then
            test "$actual" = "$resolved"
          fi
          ;;
        "$actual")
          ;;
        *)
          echo "checkout mismatch: actual=$actual requested=$requested resolved=$resolved" >&2
          exit 42
          ;;
      esac
      help="$(buildkite-agent pipeline upload --help 2>&1)"
      set -- pipeline upload .buildkite/pipeline.yml
      printf '%s' "$help" | grep -q -- '--reject-parse-warnings' && set -- "$@" --reject-parse-warnings || true
      printf '%s' "$help" | grep -q -- '--reject-secrets' && set -- "$@" --reject-secrets || true
      if printf '%s' "$help" | grep -q -- '--dry-run'; then
        buildkite-agent "$@" --dry-run >/dev/null
      fi
      buildkite-agent "$@"
"""



def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def env_truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"", "0", "false", "no", "off"}


def resolve_buildkite_token() -> tuple[str, str]:
    value = os.getenv("BUILDKITE_API_TOKEN", "").strip()
    if value:
        return value, "environment"
    path = Path.home() / ".config" / "buildkite" / "api-token"
    try:
        value = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Buildkite API token unavailable. Set BUILDKITE_API_TOKEN or restore "
            f"{path}."
        ) from exc
    if not value:
        raise RuntimeError(f"Buildkite API token file is empty: {path}")
    return value, "config_file"


@dataclass
class BuildkiteAPI:
    token: str

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        body = None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "GlacierEQ-APEX-Genius-Buildkite/1",
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            f"{API_ROOT}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                detail: Any = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                detail = raw
            raise RuntimeError(
                f"Buildkite API {method} {path} failed with HTTP {exc.code}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Buildkite API transport failure for {method} {path}: {exc.reason}"
            ) from exc


def list_all(api: BuildkiteAPI, path: str) -> list[dict[str, Any]]:
    page = 1
    items: list[dict[str, Any]] = []
    while True:
        sep = "&" if "?" in path else "?"
        batch = api.request("GET", f"{path}{sep}per_page=100&page={page}")
        if not isinstance(batch, list):
            raise RuntimeError(f"Expected list from {path}, got {type(batch).__name__}")
        items.extend(item for item in batch if isinstance(item, dict))
        if len(batch) < 100:
            return items
        page += 1


def normalize_repository(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.strip().removesuffix(".git")
    for prefix in (
        "git@github.com:",
        "ssh://git@github.com/",
        "https://github.com/",
        "http://github.com/",
    ):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    return normalized.casefold()


def inspect_api_token(api: BuildkiteAPI) -> dict[str, Any]:
    details = api.request("GET", "/access-token")
    if not isinstance(details, dict):
        raise RuntimeError("Buildkite returned invalid current-token metadata.")
    scopes = {str(scope) for scope in details.get("scopes", [])}
    required = {"read_pipelines", "write_pipelines", "write_builds"}
    missing = sorted(required - scopes)
    if missing:
        raise RuntimeError(
            "Buildkite API token missing required scopes: " + ", ".join(missing)
        )
    return {
        "uuid": details.get("uuid"),
        "description": details.get("description"),
        "created_at": details.get("created_at"),
        "expires_at": details.get("expires_at"),
        "scopes": sorted(scopes),
    }


def require_scope(token_meta: dict[str, Any], scope: str, reason: str) -> None:
    if scope not in set(token_meta.get("scopes", [])):
        raise RuntimeError(f"Buildkite API token requires {scope} to {reason}.")


def resolve_cluster_id(
    api: BuildkiteAPI,
    token_meta: dict[str, Any],
) -> tuple[str, str]:
    explicit = os.getenv("BUILDKITE_CLUSTER_ID", "").strip()
    if explicit:
        return explicit, "BUILDKITE_CLUSTER_ID"

    donor_path = (
        f"/organizations/{urllib.parse.quote(ORG)}/pipelines/"
        f"{urllib.parse.quote(DONOR_PIPELINE)}"
    )
    donor = api.request("GET", donor_path)
    donor_cluster = (donor or {}).get("cluster_id") if isinstance(donor, dict) else None
    if donor_cluster:
        return str(donor_cluster), f"donor_pipeline:{DONOR_PIPELINE}"

    require_scope(
        token_meta,
        "read_clusters",
        "discover a cluster because the donor pipeline is unclustered",
    )
    clusters = list_all(api, f"/organizations/{urllib.parse.quote(ORG)}/clusters")
    requested_name = os.getenv("BUILDKITE_CLUSTER_NAME", "").strip()
    if requested_name:
        matches = [c for c in clusters if c.get("name") == requested_name]
        if len(matches) != 1:
            raise RuntimeError(
                f"BUILDKITE_CLUSTER_NAME={requested_name!r} matched "
                f"{len(matches)} clusters; refusing to guess."
            )
        return str(matches[0]["id"]), f"cluster_name:{requested_name}"
    if len(clusters) == 1:
        return str(clusters[0]["id"]), "sole_cluster"
    names = [str(c.get("name")) for c in clusters]
    raise RuntimeError(
        "Cluster choice is ambiguous. Set BUILDKITE_CLUSTER_ID or "
        f"BUILDKITE_CLUSTER_NAME. Available clusters: {names}"
    )


def find_existing_pipeline(
    pipelines: list[dict[str, Any]],
    spec: dict[str, str],
) -> dict[str, Any] | None:
    expected_repo = normalize_repository(spec["repository"])
    repo_matches = [
        p for p in pipelines if normalize_repository(p.get("repository")) == expected_repo
    ]
    if len(repo_matches) > 1:
        raise RuntimeError(
            f"Multiple Buildkite pipelines target {spec['github_repository']}: "
            + ", ".join(str(p.get("slug")) for p in repo_matches)
        )
    if repo_matches:
        candidate = repo_matches[0]
        if candidate.get("slug") != spec["slug"]:
            raise RuntimeError(
                f"Repository {spec['github_repository']} is already attached to "
                f"pipeline {candidate.get('slug')!r}; refusing an implicit rename."
            )
        return candidate

    slug_matches = [p for p in pipelines if p.get("slug") == spec["slug"]]
    if len(slug_matches) > 1:
        raise RuntimeError(f"Duplicate Buildkite pipeline slug: {spec['slug']}")
    if slug_matches:
        candidate = slug_matches[0]
        actual_repo = normalize_repository(candidate.get("repository"))
        if actual_repo and actual_repo != expected_repo:
            raise RuntimeError(
                f"Pipeline slug {spec['slug']} points at {candidate.get('repository')!r}, "
                f"not {spec['repository']!r}; refusing to repoint it."
            )
        return candidate
    return None


def desired_pipeline(spec: dict[str, str], cluster_id: str) -> dict[str, Any]:
    return {
        "name": spec["name"],
        "slug": spec["slug"],
        "description": f"GlacierEQ Genius family CI for {spec['name']}",
        "repository": spec["repository"],
        "cluster_id": cluster_id,
        "configuration": PIPELINE_UPLOAD_CONFIGURATION,
        "default_branch": DEFAULT_BRANCH,
        "branch_configuration": None,
        "cancel_running_branch_builds": bool(
            REGISTRY["superseded_build_policy"]["cancel_running_branch_builds"]
        ),
        "skip_queued_branch_builds": bool(
            REGISTRY["superseded_build_policy"]["skip_queued_branch_builds"]
        ),
        "visibility": "private",
        "provider_settings": {
            "build_branches": True,
            "build_pull_requests": True,
            "build_pull_request_forks": False,
            "build_tags": False,
            "publish_commit_status": True,
            "publish_commit_status_per_step": True,
        },
    }


def reconcile_pipeline(
    api: BuildkiteAPI,
    all_pipelines: list[dict[str, Any]],
    spec: dict[str, str],
    cluster_id: str,
) -> tuple[dict[str, Any], str]:
    existing = find_existing_pipeline(all_pipelines, spec)
    desired = desired_pipeline(spec, cluster_id)
    org_path = f"/organizations/{urllib.parse.quote(ORG)}"
    if existing is None:
        created = api.request("POST", f"{org_path}/pipelines", desired)
        if not isinstance(created, dict) or not created.get("slug"):
            raise RuntimeError(f"Buildkite returned no pipeline slug for {spec['name']}.")
        all_pipelines.append(created)
        return created, "CREATED"

    slug = str(existing["slug"])
    updated = api.request(
        "PATCH",
        f"{org_path}/pipelines/{urllib.parse.quote(slug)}",
        desired,
    )
    if not isinstance(updated, dict):
        raise RuntimeError(f"Invalid Buildkite update response for {slug}.")
    return updated, "RECONCILED"


def ensure_webhook(api: BuildkiteAPI, slug: str) -> dict[str, Any]:
    path = (
        f"/organizations/{urllib.parse.quote(ORG)}/pipelines/"
        f"{urllib.parse.quote(slug)}/webhook"
    )
    try:
        api.request("POST", path)
        return {"status": "CREATED"}
    except RuntimeError as exc:
        detail = str(exc)
        if "HTTP 422" in detail:
            return {"status": "ALREADY_PRESENT_OR_PROVIDER_MANAGED"}
        raise


def github_json(path: str) -> Any:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "GlacierEQ-APEX-Genius-Buildkite/2",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{GITHUB_API_ROOT}{path}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GitHub read failed for {path} with HTTP {exc.code}: {raw[:500]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub transport failure for {path}: {exc.reason}") from exc


def github_main_sha(repository: str) -> str:
    payload = github_json(f"/repos/{repository}/commits/{DEFAULT_BRANCH}")
    sha = str((payload or {}).get("sha") or "")
    if len(sha) != 40:
        raise RuntimeError(f"GitHub returned invalid main SHA for {repository}: {sha!r}")
    return sha


def github_buildkite_projection(
    repository: str,
    commit: str,
    context: str,
) -> dict[str, Any] | None:
    payload = github_json(f"/repos/{repository}/commits/{commit}/status")
    matches = [
        item
        for item in (payload or {}).get("statuses") or []
        if isinstance(item, dict) and item.get("context") == context
    ]
    if not matches:
        return None
    item = max(matches, key=lambda value: str(value.get("updated_at") or ""))
    return {
        "context": context,
        "state": item.get("state"),
        "description": item.get("description"),
        "target_url": item.get("target_url"),
        "updated_at": item.get("updated_at"),
    }


def should_trigger_for_projection(projection: dict[str, Any] | None) -> bool:
    if projection is None:
        return True
    reusable = set(REGISTRY["trigger_policy"]["reuse_projection_states"])
    return str(projection.get("state") or "") not in reusable

def trigger_build(
    api: BuildkiteAPI,
    slug: str,
    repository: str,
    commit: str,
) -> dict[str, Any] | None:
    if not env_truthy("BUILDKITE_TRIGGER_BUILD", default=True):
        return None
    payload = {
        "commit": commit,
        "branch": DEFAULT_BRANCH,
        "clean_checkout": True,
        "message": f"APEX: verify {repository} on Buildkite",
        "env": {
            "APEX_EXECUTION_SURFACE": "buildkite",
            "APEX_GENIUS_RECONCILIATION": "api-v1",
        },
        "meta_data": {
            "apex_mission": "genius-family-ci-verification",
            "source_repository": repository,
            "source_commit": commit,
        },
    }
    path = (
        f"/organizations/{urllib.parse.quote(ORG)}/pipelines/"
        f"{urllib.parse.quote(slug)}/builds"
    )
    result = api.request("POST", path, payload)
    if not isinstance(result, dict) or not result.get("number"):
        raise RuntimeError(f"Buildkite returned no build receipt for {slug}.")
    return result


def verify_returned_build_commit(
    build: dict[str, Any] | None,
    requested_commit: str,
) -> None:
    """Reject only an explicit conflicting SHA.

    Buildkite may preserve a symbolic ref in some response surfaces even when the
    requested build resolves to the exact SHA. GitHub commit-status projection is
    the independent exact-SHA readback. A different 40-character SHA is a hard
    contradiction and remains fatal.
    """
    if not build:
        return
    returned = str(build.get("commit") or "")
    if len(returned) == 40 and returned != requested_commit:
        raise RuntimeError(
            "Build commit mismatch: "
            f"requested={requested_commit} returned={returned}"
        )


def parse_buildkite_build_url(value: str, expected_slug: str) -> int:
    match = BUILD_URL_RE.fullmatch(value)
    if not match:
        raise RuntimeError(f"Invalid Buildkite build URL: {value!r}")
    if match.group("org") != ORG:
        raise RuntimeError(
            f"Buildkite organization mismatch in URL: {match.group('org')!r}"
        )
    if match.group("slug") != expected_slug:
        raise RuntimeError(
            f"Buildkite pipeline mismatch in URL: {match.group('slug')!r}"
        )
    return int(match.group("number"))


def resolve_build_number(result: dict[str, Any]) -> int:
    build = result.get("build")
    if isinstance(build, dict) and build.get("number") is not None:
        return int(build["number"])
    projection = result.get("preexisting_projection")
    if not isinstance(projection, dict):
        raise RuntimeError(
            f"No Buildkite build reference for {result.get('repository')}"
        )
    target_url = str(projection.get("target_url") or "")
    slug = str((result.get("pipeline") or {}).get("slug") or "")
    return parse_buildkite_build_url(target_url, slug)


def await_terminal_child_builds(
    api: BuildkiteAPI,
    results: list[dict[str, Any]],
) -> None:
    policy = REGISTRY["verification_policy"]
    if not bool(policy.get("wait_for_terminal_builds", True)):
        return

    interval = max(1.0, float(policy["poll_interval_seconds"]))
    success_states = {str(value) for value in policy["build_success_states"]}
    failure_states = {str(value) for value in policy["build_failure_states"]}

    for result in results:
        result["build_number"] = resolve_build_number(result)

    pending = set(range(len(results)))
    deadline = time.monotonic() + float(policy["build_timeout_seconds"])
    while pending:
        for index in list(pending):
            result = results[index]
            slug = str(result["pipeline"]["slug"])
            number = int(result["build_number"])
            path = (
                f"/organizations/{urllib.parse.quote(ORG)}/pipelines/"
                f"{urllib.parse.quote(slug)}/builds/{number}"
            )
            build = api.request("GET", path)
            if not isinstance(build, dict):
                raise RuntimeError(f"Invalid Buildkite build readback for {slug} #{number}")
            state = str(build.get("state") or "")
            result["terminal_build"] = compact_build(build)
            if state in success_states:
                verify_returned_build_commit(build, str(result["source_commit"]))
                if str(build.get("branch") or "") != DEFAULT_BRANCH:
                    raise RuntimeError(
                        f"Buildkite branch mismatch for {slug} #{number}: "
                        f"{build.get('branch')!r}"
                    )
                pending.remove(index)
            elif state in failure_states:
                raise RuntimeError(
                    f"Buildkite child failed: {slug} #{number} state={state}"
                )
        if pending:
            if time.monotonic() >= deadline:
                names = [str(results[index]["pipeline"]["slug"]) for index in pending]
                raise RuntimeError(
                    "Timed out waiting for Buildkite child builds: " + ", ".join(names)
                )
            time.sleep(interval)

    projection_success = {
        str(value) for value in policy["projection_success_states"]
    }
    projection_failure = {
        str(value) for value in policy["projection_failure_states"]
    }
    pending = set(range(len(results)))
    deadline = time.monotonic() + float(policy["projection_timeout_seconds"])
    while pending:
        for index in list(pending):
            result = results[index]
            projection = github_buildkite_projection(
                str(result["repository"]),
                str(result["source_commit"]),
                str(result["status_context"]),
            )
            result["terminal_projection"] = projection
            if projection is None:
                continue
            state = str(projection.get("state") or "")
            if state in projection_failure:
                raise RuntimeError(
                    f"GitHub Buildkite projection failed for {result['repository']}: "
                    f"state={state}"
                )
            if state in projection_success:
                slug = str(result["pipeline"]["slug"])
                projected_number = parse_buildkite_build_url(
                    str(projection.get("target_url") or ""),
                    slug,
                )
                if projected_number != int(result["build_number"]):
                    raise RuntimeError(
                        f"GitHub projection points to wrong Buildkite build for {slug}: "
                        f"expected={result['build_number']} actual={projected_number}"
                    )
                result["verification_status"] = "VERIFIED_TERMINAL_SUCCESS"
                pending.remove(index)
        if pending:
            if time.monotonic() >= deadline:
                names = [str(results[index]["repository"]) for index in pending]
                raise RuntimeError(
                    "Timed out waiting for GitHub Buildkite success projection: "
                    + ", ".join(names)
                )
            time.sleep(interval)


def verify_pipeline_readback(
    pipeline: dict[str, Any],
    spec: dict[str, str],
    cluster_id: str,
) -> None:
    desired = desired_pipeline(spec, cluster_id)
    failures: list[str] = []
    if normalize_repository(pipeline.get("repository")) != normalize_repository(
        spec["repository"]
    ):
        failures.append("repository")
    if str(pipeline.get("cluster_id") or "") != cluster_id:
        failures.append("cluster_id")
    if pipeline.get("default_branch") != DEFAULT_BRANCH:
        failures.append("default_branch")
    for key in ("cancel_running_branch_builds", "skip_queued_branch_builds"):
        if bool(pipeline.get(key)) != bool(desired[key]):
            failures.append(key)
    configuration = str(pipeline.get("configuration") or "")
    if "buildkite-agent pipeline upload" not in configuration:
        failures.append("configuration")
    if failures:
        raise RuntimeError(
            f"Buildkite pipeline readback mismatch for {spec['slug']}: "
            + ", ".join(failures)
        )


def compact_pipeline(pipeline: dict[str, Any]) -> dict[str, Any]:
    provider = (
        pipeline.get("provider") if isinstance(pipeline.get("provider"), dict) else {}
    )
    settings = (
        provider.get("settings") if isinstance(provider.get("settings"), dict) else {}
    )
    return {
        "id": pipeline.get("id"),
        "name": pipeline.get("name"),
        "slug": pipeline.get("slug"),
        "repository": pipeline.get("repository"),
        "cluster_id": pipeline.get("cluster_id"),
        "default_branch": pipeline.get("default_branch"),
        "web_url": pipeline.get("web_url"),
        "provider": provider.get("id"),
        "provider_settings": {
            key: settings.get(key)
            for key in (
                "build_branches",
                "build_pull_requests",
                "build_pull_request_forks",
                "build_tags",
                "publish_commit_status",
                "publish_commit_status_per_step",
            )
        },
    }


def compact_build(build: dict[str, Any] | None) -> dict[str, Any] | None:
    if not build:
        return None
    return {
        "id": build.get("id"),
        "number": build.get("number"),
        "state": build.get("state"),
        "branch": build.get("branch"),
        "commit": build.get("commit"),
        "source": build.get("source"),
        "web_url": build.get("web_url"),
        "created_at": build.get("created_at"),
    }


def write_receipt(payload: dict[str, Any]) -> None:
    RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = RECEIPT_PATH.with_suffix(RECEIPT_PATH.suffix + ".tmp")
    temp.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp.replace(RECEIPT_PATH)


def main() -> int:
    token, token_source = resolve_buildkite_token()
    api = BuildkiteAPI(token)
    token_meta = inspect_api_token(api)
    cluster_id, cluster_source = resolve_cluster_id(api, token_meta)

    org_path = f"/organizations/{urllib.parse.quote(ORG)}"
    pipelines = list_all(api, f"{org_path}/pipelines")
    results: list[dict[str, Any]] = []

    for spec in PIPELINES:
        main_sha = github_main_sha(spec["github_repository"])
        pipeline, mutation = reconcile_pipeline(api, pipelines, spec, cluster_id)
        slug = str(pipeline["slug"])
        webhook = ensure_webhook(api, slug)

        readback = api.request("GET", f"{org_path}/pipelines/{urllib.parse.quote(slug)}")
        if not isinstance(readback, dict):
            raise RuntimeError(f"Buildkite pipeline readback failed for {slug}.")
        verify_pipeline_readback(readback, spec, cluster_id)

        projection = github_buildkite_projection(
            spec["github_repository"],
            main_sha,
            spec["status_context"],
        )
        build = None
        execution_action = "REUSED_GITHUB_PROJECTION"
        if should_trigger_for_projection(projection):
            build = trigger_build(api, slug, spec["github_repository"], main_sha)
            verify_returned_build_commit(build, main_sha)
            execution_action = (
                "TRIGGERED"
                if build is not None
                else "TRIGGER_DISABLED"
            )

        results.append(
            {
                "repository": spec["github_repository"],
                "role": spec["role"],
                "status_context": spec["status_context"],
                "source_commit": main_sha,
                "mutation": mutation,
                "pipeline": compact_pipeline(readback),
                "webhook": webhook,
                "execution_action": execution_action,
                "preexisting_projection": projection,
                "build": compact_build(build),
            }
        )

    await_terminal_child_builds(api, results)

    receipt = {
        "schema": "glaciereq.apex.genius-buildkite-reconciliation.v1",
        "generated_at": utc_now(),
        "status": "PIPELINES_RECONCILED_AND_HEADS_VERIFIED",
        "organization": ORG,
        "target_registry": {
            "path": str(TARGETS_PATH.relative_to(ROOT)),
            "sha256": hashlib.sha256(TARGETS_PATH.read_bytes()).hexdigest(),
        },
        "cluster": {"id": cluster_id, "source": cluster_source, "queue": DEFAULT_QUEUE},
        "api_token": {
            "uuid": token_meta.get("uuid"),
            "description": token_meta.get("description"),
            "created_at": token_meta.get("created_at"),
            "expires_at": token_meta.get("expires_at"),
            "scopes": token_meta.get("scopes"),
            "source": token_source,
            "value_recorded": False,
        },
        "pipelines": results,
        "credentials_recorded": False,
    }
    write_receipt(receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"APEX Genius Buildkite reconciliation failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
