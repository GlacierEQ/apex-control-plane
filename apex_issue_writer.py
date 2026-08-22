#!/usr/bin/env python3
"""Publish P0/P1 findings from one exact APEX audit run.

The writer never selects "today's" or "newest" queue. It consumes the run-specific
queue named by RUN_DATE, preventing stale replay when an audit fails before persistence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

ROLLING_TITLE = "APEX audit findings"


def _safe_run_id(run_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", run_id).strip("._") or "unknown-run"


def _queue_path(run_id: str) -> Path:
    return Path("action_queue") / f"queue_{_safe_run_id(run_id)}.json"


def _material_findings(queue: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in queue if item.get("severity") in {"P0", "P1"}]


def _fingerprint(items: list[dict[str, Any]]) -> str:
    payload = json.dumps(items, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _request(method: str, url: str, *, token: str, **kwargs: Any):
    if requests is None:
        raise RuntimeError("requests dependency unavailable")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    return requests.request(method, url, headers=headers, timeout=15, **kwargs)


def publish_run(*, run_id: str, token: str, repo: str) -> int:
    path = _queue_path(run_id)
    if not path.is_file():
        raise RuntimeError(f"exact audit queue missing: {path}")
    queue = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(queue, list):
        raise RuntimeError("audit queue must be a list")
    findings = _material_findings(queue)
    if not findings:
        print(f"No P0/P1 findings for exact run {run_id}; no issue mutation needed.")
        return 0

    fingerprint = _fingerprint(findings)
    body_lines = [
        "## Current APEX audit findings",
        "",
        f"**Exact run:** `{run_id}`",
        f"**Finding fingerprint:** `{fingerprint}`",
        "",
    ]
    for item in findings:
        body_lines.extend(
            [
                (
                    f"### {item['severity']} · {item.get('domain', 'unknown')} · "
                    f"{item['title']}"
                ),
                f"**Action:** {item['action']}",
                "",
            ]
        )
    body_lines.append(
        "This issue is updated from one exact run-specific queue. "
        "Stale fallback is forbidden."
    )
    body = "\n".join(body_lines)

    base = f"https://api.github.com/repos/{repo}"
    response = _request(
        "GET",
        f"{base}/issues",
        token=token,
        params={"state": "open", "labels": "apex-audit", "per_page": 100},
    )
    if response.status_code != 200:
        raise RuntimeError(f"issue lookup failed: http_status={response.status_code}")
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("issue lookup returned invalid JSON shape")
    existing = next(
        (issue for issue in payload if issue.get("title") == ROLLING_TITLE), None
    )
    severity_label = "P0" if any(i["severity"] == "P0" for i in findings) else "P1"

    if existing:
        issue_number = existing.get("number")
        update = _request(
            "PATCH",
            f"{base}/issues/{issue_number}",
            token=token,
            json={"body": body, "labels": ["apex-audit", severity_label]},
        )
        if update.status_code != 200:
            raise RuntimeError(f"issue update failed: http_status={update.status_code}")
        print(f"Updated rolling audit issue #{issue_number} from exact run {run_id}.")
        return 0

    create = _request(
        "POST",
        f"{base}/issues",
        token=token,
        json={
            "title": ROLLING_TITLE,
            "body": body,
            "labels": ["apex-audit", severity_label],
        },
    )
    if create.status_code != 201:
        raise RuntimeError(f"issue creation failed: http_status={create.status_code}")
    created = create.json()
    print(f"Created rolling audit issue #{created.get('number')} from exact run {run_id}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--auto-approve", action="store_true", help="Deprecated compatibility flag"
    )
    parser.add_argument("--run-id", default=os.environ.get("RUN_DATE", ""))
    args = parser.parse_args(argv)
    run_id = args.run_id.strip()
    if not run_id:
        print("RUN_DATE/--run-id is required; refusing newest-file fallback.")
        return 2
    if not _queue_path(run_id).is_file():
        print(f"Exact audit queue missing for run {run_id}; refusing stale fallback.")
        return 2
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPO", "GlacierEQ/apex-control-plane")
    if not token:
        print(
            "No GITHUB_TOKEN; issue publication skipped without affecting audit receipt truth."
        )
        return 0
    try:
        return publish_run(run_id=run_id, token=token, repo=repo)
    except (RuntimeError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"APEX issue writer failure: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
