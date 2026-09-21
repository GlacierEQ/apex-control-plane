#!/usr/bin/env python3
"""Reconcile the existing Job-App Helix Buildkite pipeline to repository-owned CI."""
from __future__ import annotations

import json
import sys
import time
import urllib.parse

import reconcile_genius_buildkite as core

SLUG = "job-app-helix"
REPOSITORY = "https://github.com/GlacierEQ/job-app-helix.git"
GITHUB_REPOSITORY = "GlacierEQ/job-app-helix"
STATUS_CONTEXT = "buildkite/job-app-helix"

BOOTSTRAP = """agents:
  queue: linux-small
steps:
  - label: ":pipeline: Load repository pipeline"
    key: upload-repository-pipeline
    timeout_in_minutes: 5
    command: |
      set -euo pipefail
      actual="$(git rev-parse HEAD)"
      requested="${BUILDKITE_COMMIT:-}"
      resolved="${BUILDKITE_COMMIT_RESOLVED:-}"
      if [ "$requested" = "HEAD" ] && [ -n "$resolved" ]; then
        test "$actual" = "$resolved"
      else
        test "$actual" = "$requested"
      fi
      buildkite-agent pipeline upload .buildkite/pipeline.yml
"""


def main() -> int:
    token, _ = core.resolve_buildkite_token()
    api = core.BuildkiteAPI(token)
    core.inspect_api_token(api)
    pipelines = core.list_all(api, f"/organizations/{urllib.parse.quote(core.ORG)}/pipelines")
    matches = [p for p in pipelines if p.get("slug") == SLUG]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one {SLUG} pipeline, found {len(matches)}")
    current = matches[0]
    if core.normalize_repository(current.get("repository")) != core.normalize_repository(REPOSITORY):
        raise RuntimeError(f"Refusing to repoint {SLUG}: repository mismatch")

    desired = {
        "name": current.get("name") or "job-app-helix",
        "description": current.get("description") or "Public CI control plane for Job-App Helix.",
        "repository": REPOSITORY,
        "cluster_id": current.get("cluster_id"),
        "configuration": BOOTSTRAP,
        "default_branch": "main",
        "branch_configuration": None,
        "cancel_running_branch_builds": True,
        "skip_queued_branch_builds": True,
        "visibility": current.get("visibility") or "public",
        "provider_settings": {
            "build_branches": True,
            "build_pull_requests": True,
            "build_pull_request_forks": False,
            "build_tags": False,
            "publish_commit_status": True,
            "publish_commit_status_per_step": False,
        },
    }
    path = f"/organizations/{urllib.parse.quote(core.ORG)}/pipelines/{SLUG}"
    updated = api.request("PATCH", path, desired)
    if not isinstance(updated, dict):
        raise RuntimeError("Buildkite returned invalid Helix pipeline update")

    commit = core.github_main_sha(GITHUB_REPOSITORY)
    build = core.trigger_build(api, SLUG, GITHUB_REPOSITORY, commit)
    if not build:
        raise RuntimeError("Buildkite returned no Helix build")
    number = int(build["number"])

    terminal = {"passed", "failed", "canceled", "skipped", "not_run"}
    deadline = time.monotonic() + 1200
    while True:
        observed = api.request("GET", f"{path}/builds/{number}")
        state = str((observed or {}).get("state") or "")
        if state in terminal:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Timed out waiting for Helix build #{number}; state={state}")
        time.sleep(5)

    projection = core.github_buildkite_projection(GITHUB_REPOSITORY, commit, STATUS_CONTEXT)
    receipt = {
        "pipeline": SLUG,
        "repository": GITHUB_REPOSITORY,
        "commit": commit,
        "build_number": number,
        "build_state": state,
        "configuration": "repository-owned:.buildkite/pipeline.yml",
        "github_projection": projection,
    }
    print(json.dumps(receipt, indent=2, sort_keys=True))
    if state != "passed":
        raise RuntimeError(f"Helix Buildkite #{number} finished {state}")
    if not projection or projection.get("state") != "success":
        raise RuntimeError(f"Helix GitHub projection is not success: {projection}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Helix Buildkite reconciliation failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
