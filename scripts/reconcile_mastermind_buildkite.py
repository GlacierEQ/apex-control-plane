#!/usr/bin/env python3
"""Register, reconcile, trigger, and verify the Mastermind Buildkite pipeline.

Control-plane contract:
GitHub source -> Buildkite provider -> exact-SHA checkout -> repository-owned
.buildkite/pipeline.yml -> bounded receipt -> terminal Buildkite readback -> exact
GitHub status projection.

No credential value is written to source, logs, or receipts.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
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
CONFIG_PATH = ROOT / "config" / "mastermind_buildkite_target.json"
RECEIPT_PATH = ROOT / "artifacts" / "buildkite" / "mastermind-reconciliation.json"
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_config() -> dict[str, Any]:
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    required = {
        "schema_version", "organization", "donor_pipeline", "name", "slug",
        "repository", "github_repository", "default_branch", "pipeline_file",
        "queue", "status_context", "provider_settings", "superseded_build_policy",
    }
    if data.get("schema_version") != 1 or not required.issubset(data):
        raise RuntimeError("Invalid Mastermind Buildkite target registry")
    if data["queue"] != "macos-self":
        raise RuntimeError("Mastermind authoritative queue must remain macos-self until promoted")
    return data


CONFIG = load_config()
ORG = os.getenv("BUILDKITE_ORG", str(CONFIG["organization"]))


def resolve_buildkite_token() -> tuple[str, str]:
    value = os.getenv("BUILDKITE_API_TOKEN", "").strip()
    if value:
        return value, "environment"
    path = Path.home() / ".config" / "buildkite" / "api-token"
    try:
        value = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Buildkite token unavailable; set BUILDKITE_API_TOKEN or restore " + str(path)
        ) from exc
    if not value:
        raise RuntimeError(f"Buildkite token file is empty: {path}")
    return value, "config_file"


@dataclass
class BuildkiteAPI:
    token: str

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        body = None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "GlacierEQ-APEX-Mastermind-Buildkite/1",
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{API_ROOT}{path}", data=body, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Buildkite API {method} {path} failed with HTTP {exc.code}: {detail[:800]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Buildkite API transport failure: {exc.reason}") from exc


def list_all(api: BuildkiteAPI, path: str) -> list[dict[str, Any]]:
    page = 1
    rows: list[dict[str, Any]] = []
    while True:
        sep = "&" if "?" in path else "?"
        batch = api.request("GET", f"{path}{sep}per_page=100&page={page}")
        if not isinstance(batch, list):
            raise RuntimeError(f"Expected list from {path}")
        rows.extend(item for item in batch if isinstance(item, dict))
        if len(batch) < 100:
            return rows
        page += 1


def inspect_token(api: BuildkiteAPI) -> dict[str, Any]:
    details = api.request("GET", "/access-token")
    if not isinstance(details, dict):
        raise RuntimeError("Buildkite returned invalid token metadata")
    scopes = {str(item) for item in details.get("scopes", [])}
    required = {"read_pipelines", "write_pipelines", "write_builds"}
    missing = sorted(required - scopes)
    if missing:
        raise RuntimeError("Buildkite token missing scopes: " + ", ".join(missing))
    return {
        "uuid": details.get("uuid"),
        "description": details.get("description"),
        "expires_at": details.get("expires_at"),
        "scopes": sorted(scopes),
    }


def normalize_repository(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.strip().removesuffix(".git")
    for prefix in (
        "git@github.com:", "ssh://git@github.com/", "https://github.com/", "http://github.com/"
    ):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    return normalized.casefold()


def resolve_cluster_id(api: BuildkiteAPI, token_meta: dict[str, Any]) -> tuple[str, str]:
    explicit = os.getenv("BUILDKITE_CLUSTER_ID", "").strip()
    if explicit:
        return explicit, "BUILDKITE_CLUSTER_ID"
    donor = api.request(
        "GET",
        f"/organizations/{urllib.parse.quote(ORG)}/pipelines/"
        f"{urllib.parse.quote(str(CONFIG['donor_pipeline']))}",
    )
    if isinstance(donor, dict) and donor.get("cluster_id"):
        return str(donor["cluster_id"]), f"donor_pipeline:{CONFIG['donor_pipeline']}"
    if "read_clusters" not in set(token_meta.get("scopes", [])):
        raise RuntimeError("Buildkite token needs read_clusters because donor has no cluster_id")
    clusters = list_all(api, f"/organizations/{urllib.parse.quote(ORG)}/clusters")
    if len(clusters) != 1:
        raise RuntimeError("Cluster selection is ambiguous; set BUILDKITE_CLUSTER_ID")
    return str(clusters[0]["id"]), "sole_cluster"


def upload_configuration() -> str:
    queue = str(CONFIG["queue"])
    pipeline_file = str(CONFIG["pipeline_file"])
    return f'''agents:\n  queue: {queue}\nsteps:\n  - label: ":pipeline: Load Mastermind maintained pipeline"\n    key: upload-mastermind-pipeline\n    timeout_in_minutes: 5\n    command: |\n      set -euo pipefail\n      actual="$(git rev-parse HEAD)"\n      requested="${{BUILDKITE_COMMIT:-}}"\n      resolved="${{BUILDKITE_COMMIT_RESOLVED:-}}"\n      case "$requested" in\n        HEAD)\n          if [ -n "$resolved" ]; then test "$actual" = "$resolved"; fi\n          ;;\n        "$actual") ;;\n        *) echo "checkout mismatch: actual=$actual requested=$requested resolved=$resolved" >&2; exit 42 ;;\n      esac\n      buildkite-agent pipeline upload {pipeline_file}\n'''


def desired_pipeline(cluster_id: str) -> dict[str, Any]:
    return {
        "name": CONFIG["name"],
        "slug": CONFIG["slug"],
        "description": "GlacierEQ Mastermind crown-jewel verification pipeline",
        "repository": CONFIG["repository"],
        "cluster_id": cluster_id,
        "configuration": upload_configuration(),
        "default_branch": CONFIG["default_branch"],
        "branch_configuration": None,
        "cancel_running_branch_builds": bool(
            CONFIG["superseded_build_policy"]["cancel_running_branch_builds"]
        ),
        "skip_queued_branch_builds": bool(
            CONFIG["superseded_build_policy"]["skip_queued_branch_builds"]
        ),
        "visibility": "private",
        "provider_settings": dict(CONFIG["provider_settings"]),
    }


def find_pipeline(pipelines: list[dict[str, Any]]) -> dict[str, Any] | None:
    expected = normalize_repository(str(CONFIG["repository"]))
    by_repo = [p for p in pipelines if normalize_repository(p.get("repository")) == expected]
    if len(by_repo) > 1:
        raise RuntimeError("Multiple Buildkite pipelines target GlacierEQ/mastermind")
    if by_repo:
        if str(by_repo[0].get("slug")) != str(CONFIG["slug"]):
            raise RuntimeError("Existing Mastermind pipeline uses a conflicting slug")
        return by_repo[0]
    by_slug = [p for p in pipelines if p.get("slug") == CONFIG["slug"]]
    if len(by_slug) > 1:
        raise RuntimeError("Duplicate Buildkite mastermind pipeline slug")
    if by_slug and normalize_repository(by_slug[0].get("repository")) not in {"", expected}:
        raise RuntimeError("Buildkite mastermind slug points at a different repository")
    return by_slug[0] if by_slug else None


def reconcile_pipeline(api: BuildkiteAPI, cluster_id: str) -> tuple[dict[str, Any], str]:
    org_path = f"/organizations/{urllib.parse.quote(ORG)}"
    pipelines = list_all(api, f"{org_path}/pipelines")
    existing = find_pipeline(pipelines)
    desired = desired_pipeline(cluster_id)
    if existing is None:
        result = api.request("POST", f"{org_path}/pipelines", desired)
        mutation = "CREATED"
    else:
        result = api.request(
            "PATCH", f"{org_path}/pipelines/{urllib.parse.quote(str(CONFIG['slug']))}", desired
        )
        mutation = "RECONCILED"
    if not isinstance(result, dict):
        raise RuntimeError("Buildkite returned invalid pipeline mutation response")
    return result, mutation


def ensure_webhook(api: BuildkiteAPI) -> str:
    path = (
        f"/organizations/{urllib.parse.quote(ORG)}/pipelines/"
        f"{urllib.parse.quote(str(CONFIG['slug']))}/webhook"
    )
    try:
        api.request("POST", path)
        return "CREATED"
    except RuntimeError as exc:
        if "HTTP 422" in str(exc):
            return "ALREADY_PRESENT_OR_PROVIDER_MANAGED"
        raise


def verify_pipeline_readback(pipeline: dict[str, Any], cluster_id: str) -> None:
    desired = desired_pipeline(cluster_id)
    checks = {
        "repository": normalize_repository(pipeline.get("repository"))
        == normalize_repository(str(CONFIG["repository"])),
        "cluster_id": str(pipeline.get("cluster_id") or "") == cluster_id,
        "default_branch": pipeline.get("default_branch") == CONFIG["default_branch"],
        "configuration": "buildkite-agent pipeline upload" in str(pipeline.get("configuration") or ""),
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError("Buildkite pipeline readback mismatch: " + ", ".join(failed))
    for key in ("cancel_running_branch_builds", "skip_queued_branch_builds"):
        if bool(pipeline.get(key)) != bool(desired[key]):
            raise RuntimeError(f"Buildkite pipeline readback mismatch: {key}")


def resolve_source_ref() -> tuple[str, str]:
    ref = os.getenv("MASTERMIND_BUILD_REF", str(CONFIG["default_branch"])).strip()
    explicit = os.getenv("MASTERMIND_BUILD_COMMIT", "").strip().lower()
    if explicit:
        if not SHA40.fullmatch(explicit):
            raise RuntimeError("MASTERMIND_BUILD_COMMIT must be a full lowercase SHA")
        return ref, explicit
    output = subprocess.check_output(
        ["git", "ls-remote", str(CONFIG["repository"]), ref],
        text=True,
        stderr=subprocess.STDOUT,
    ).strip()
    matches = [line.split()[0].lower() for line in output.splitlines() if line.strip()]
    matches = [value for value in matches if SHA40.fullmatch(value)]
    if len(set(matches)) != 1:
        raise RuntimeError(f"Could not resolve exact Mastermind SHA for ref {ref!r}")
    return ref, matches[0]


def trigger_build(api: BuildkiteAPI, ref: str, commit: str) -> dict[str, Any]:
    payload = {
        "commit": commit,
        "branch": ref,
        "clean_checkout": True,
        "message": f"APEX: verify GlacierEQ/mastermind at {commit[:12]}",
        "env": {"APEX_EXECUTION_SURFACE": "buildkite", "APEX_MASTERMIND_RECONCILIATION": "api-v1"},
        "meta_data": {
            "apex_mission": "mastermind-resurrection-verification",
            "source_repository": CONFIG["github_repository"],
            "source_commit": commit,
        },
    }
    result = api.request(
        "POST",
        f"/organizations/{urllib.parse.quote(ORG)}/pipelines/"
        f"{urllib.parse.quote(str(CONFIG['slug']))}/builds",
        payload,
    )
    if not isinstance(result, dict) or result.get("number") is None:
        raise RuntimeError("Buildkite returned no build receipt")
    returned = str(result.get("commit") or "").lower()
    if SHA40.fullmatch(returned) and returned != commit:
        raise RuntimeError(f"Buildkite build commit mismatch: requested={commit} returned={returned}")
    return result


def await_build(api: BuildkiteAPI, number: int, commit: str) -> dict[str, Any]:
    deadline = time.monotonic() + float(os.getenv("MASTERMIND_BUILD_TIMEOUT_SECONDS", "1200"))
    failures = {"failed", "canceled", "canceling", "skipped", "not_run"}
    while True:
        result = api.request(
            "GET",
            f"/organizations/{urllib.parse.quote(ORG)}/pipelines/"
            f"{urllib.parse.quote(str(CONFIG['slug']))}/builds/{number}",
        )
        if not isinstance(result, dict):
            raise RuntimeError("Buildkite returned invalid build readback")
        state = str(result.get("state") or "")
        if state == "passed":
            returned = str(result.get("commit") or "").lower()
            if SHA40.fullmatch(returned) and returned != commit:
                raise RuntimeError("Terminal Buildkite build points at the wrong commit")
            return result
        if state in failures:
            raise RuntimeError(f"Mastermind Buildkite build #{number} ended {state}")
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Timed out waiting for Mastermind Buildkite build #{number}")
        time.sleep(5)


def github_projection(commit: str) -> dict[str, Any]:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required to verify private-repo Buildkite projection")
    request = urllib.request.Request(
        f"{GITHUB_API_ROOT}/repos/{CONFIG['github_repository']}/commits/{commit}/status",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "GlacierEQ-APEX-Mastermind-Buildkite/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub status read failed with HTTP {exc.code}") from exc
    matches = [
        item for item in payload.get("statuses", [])
        if isinstance(item, dict) and item.get("context") == CONFIG["status_context"]
    ]
    if not matches:
        raise RuntimeError(f"No {CONFIG['status_context']} projection on {commit}")
    result = max(matches, key=lambda item: str(item.get("updated_at") or ""))
    if result.get("state") != "success":
        raise RuntimeError(f"Buildkite GitHub projection is {result.get('state')!r}, not success")
    target = str(result.get("target_url") or "")
    if "buildkite.com/" not in target:
        raise RuntimeError("Buildkite GitHub projection target is not a Buildkite build")
    return {
        "context": result.get("context"),
        "state": result.get("state"),
        "target_url": target,
        "updated_at": result.get("updated_at"),
    }


def write_receipt(payload: dict[str, Any]) -> None:
    RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = hashlib.sha256(RECEIPT_PATH.read_bytes()).hexdigest()
    RECEIPT_PATH.with_suffix(RECEIPT_PATH.suffix + ".sha256").write_text(
        f"{digest}  {RECEIPT_PATH.name}\n", encoding="utf-8"
    )


def main() -> int:
    token, token_source = resolve_buildkite_token()
    api = BuildkiteAPI(token)
    token_meta = inspect_token(api)
    cluster_id, cluster_source = resolve_cluster_id(api, token_meta)
    pipeline, mutation = reconcile_pipeline(api, cluster_id)
    webhook = ensure_webhook(api)
    readback = api.request(
        "GET",
        f"/organizations/{urllib.parse.quote(ORG)}/pipelines/{urllib.parse.quote(str(CONFIG['slug']))}",
    )
    if not isinstance(readback, dict):
        raise RuntimeError("Buildkite Mastermind pipeline readback failed")
    verify_pipeline_readback(readback, cluster_id)

    ref, commit = resolve_source_ref()
    build = trigger_build(api, ref, commit)
    terminal = await_build(api, int(build["number"]), commit)
    projection = github_projection(commit)

    receipt = {
        "schema": "glaciereq.apex.mastermind-buildkite-reconciliation.v1",
        "status": "VERIFIED_TERMINAL_SUCCESS",
        "generated_at": utc_now(),
        "organization": ORG,
        "source": {"repository": CONFIG["github_repository"], "ref": ref, "commit": commit},
        "pipeline": {
            "id": readback.get("id"), "slug": readback.get("slug"),
            "web_url": readback.get("web_url"), "cluster_id": readback.get("cluster_id"),
            "queue": CONFIG["queue"], "mutation": mutation, "webhook": webhook,
        },
        "build": {
            "id": terminal.get("id"), "number": terminal.get("number"),
            "state": terminal.get("state"), "commit": terminal.get("commit"),
            "branch": terminal.get("branch"), "web_url": terminal.get("web_url"),
        },
        "github_projection": projection,
        "cluster": {"id": cluster_id, "source": cluster_source},
        "api_token": {
            "uuid": token_meta.get("uuid"), "description": token_meta.get("description"),
            "expires_at": token_meta.get("expires_at"), "scopes": token_meta.get("scopes"),
            "source": token_source, "value_recorded": False,
        },
        "config_sha256": hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest(),
        "credentials_recorded": False,
    }
    write_receipt(receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
