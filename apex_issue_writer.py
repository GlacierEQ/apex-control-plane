"""Publish one exact APEX audit run to the durable GitHub audit ledger.

The publisher refuses newest/today fallbacks. It first verifies the local digest-bound
run receipt, then appends or updates one idempotent run entry and reads it back from
GitHub before reporting success.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from audit_engine import AuditInvariantError, verify_run_receipt

LEDGER_TITLE = "APEX audit ledger"


def _safe_run_id(run_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", run_id).strip("._") or "unknown-run"


def _queue_path(run_id: str) -> Path:
    return Path("action_queue") / f"queue_{_safe_run_id(run_id)}.json"


def _log_path(run_id: str) -> Path:
    return Path("audit_log") / f"run_{_safe_run_id(run_id)}.json"


def _marker(run_id: str) -> str:
    return f"<!-- apex-audit-run:{_safe_run_id(run_id)} -->"


def _request(method: str, url: str, *, token: str, **kwargs: Any):
    if requests is None:
        raise RuntimeError("requests dependency unavailable")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    return requests.request(method, url, headers=headers, timeout=15, **kwargs)


def _json_object(response: Any, *, operation: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as error:
        raise RuntimeError(f"{operation} returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise TypeError(f"{operation} returned invalid JSON shape")
    return payload


def _load_run(run_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    log_path = _log_path(run_id)
    queue_path = _queue_path(run_id)
    if not log_path.is_file() or not queue_path.is_file():
        raise RuntimeError(f"exact audit receipt missing for run {run_id}")
    log = json.loads(log_path.read_text(encoding="utf-8"))
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    run = log.get("run") if isinstance(log, dict) else None
    if not isinstance(run, dict):
        raise TypeError("audit log is missing run object")
    if not isinstance(queue, list) or not all(isinstance(item, dict) for item in queue):
        raise TypeError("audit queue must be a list of objects")
    return run, queue


def _entry_body(
    *,
    run_id: str,
    run: dict[str, Any],
    queue: list[dict[str, Any]],
    log_sha256: str,
    queue_sha256: str,
) -> str:
    material = [item for item in queue if item.get("severity") in {"P0", "P1"}]
    lines = [
        _marker(run_id),
        f"## APEX audit run `{run_id}`",
        "",
        f"- **Status:** `{run.get('status', 'unknown')}`",
        f"- **Source SHA:** `{run.get('source_sha') or 'unbound'}`",
        f"- **Started:** `{run.get('started_at', 'unknown')}`",
        f"- **Completed:** `{run.get('completed_at', 'unknown')}`",
        f"- **P0:** `{run.get('p0_count', 0)}`",
        f"- **P1:** `{run.get('p1_count', 0)}`",
        f"- **Log SHA-256:** `{log_sha256}`",
        f"- **Queue SHA-256:** `{queue_sha256}`",
        "- **External action authorized by audit:** `false`",
    ]
    if material:
        lines.extend(["", "### Material findings"])
        for item in material:
            lines.extend(
                [
                    (
                        f"- **{item.get('severity', 'unknown')} · "
                        f"{item.get('domain', 'unknown')}**: {item.get('title', 'untitled')}"
                    ),
                    f"  - Action: {item.get('action', 'unspecified')}",
                ]
            )
    else:
        lines.extend(["", "No P0/P1 findings were present in this exact run."])
    lines.extend(
        [
            "",
            (
                "This entry was generated only after local receipt verification and was read "
                "back from GitHub after publication."
            ),
        ]
    )
    return "\n".join(lines)


def _find_or_create_ledger(*, base: str, token: str) -> int:
    for page in range(1, 11):
        response = _request(
            "GET",
            f"{base}/issues",
            token=token,
            params={"state": "open", "per_page": 100, "page": page},
        )
        if response.status_code != 200:
            raise RuntimeError(f"ledger lookup failed: http_status={response.status_code}")
        payload = response.json()
        if not isinstance(payload, list):
            raise TypeError("ledger lookup returned invalid JSON shape")
        existing = next(
            (issue for issue in payload if issue.get("title") == LEDGER_TITLE), None
        )
        if existing is not None:
            number = existing.get("number")
            if not isinstance(number, int):
                raise TypeError("ledger issue is missing a numeric issue number")
            return number
        if len(payload) < 100:
            break

    create = _request(
        "POST",
        f"{base}/issues",
        token=token,
        json={
            "title": LEDGER_TITLE,
            "body": (
                "Durable APEX audit execution ledger. Each comment is bound to one exact "
                "run ID and digest-verified receipt. The issue body points to the latest run."
            ),
        },
    )
    if create.status_code != 201:
        raise RuntimeError(f"ledger creation failed: http_status={create.status_code}")
    payload = _json_object(create, operation="ledger creation")
    number = payload.get("number")
    if not isinstance(number, int):
        raise TypeError("created ledger is missing a numeric issue number")
    return number


def _find_run_comment(
    *, base: str, token: str, issue_number: int, marker: str
) -> dict[str, Any] | None:
    for page in range(1, 21):
        response = _request(
            "GET",
            f"{base}/issues/{issue_number}/comments",
            token=token,
            params={"per_page": 100, "page": page},
        )
        if response.status_code != 200:
            raise RuntimeError(f"ledger comment lookup failed: http_status={response.status_code}")
        payload = response.json()
        if not isinstance(payload, list):
            raise TypeError("ledger comment lookup returned invalid JSON shape")
        existing = next(
            (comment for comment in payload if marker in str(comment.get("body") or "")), None
        )
        if existing is not None:
            return existing
        if len(payload) < 100:
            return None
    raise RuntimeError("ledger comment search exceeded supported history window")


def _write_and_readback_comment(
    *,
    base: str,
    token: str,
    issue_number: int,
    body: str,
    run_id: str,
) -> int:
    marker = _marker(run_id)
    existing = _find_run_comment(
        base=base,
        token=token,
        issue_number=issue_number,
        marker=marker,
    )
    if existing is None:
        write = _request(
            "POST",
            f"{base}/issues/{issue_number}/comments",
            token=token,
            json={"body": body},
        )
        expected_status = 201
    else:
        comment_id = existing.get("id")
        if not isinstance(comment_id, int):
            raise TypeError("existing ledger comment is missing numeric id")
        write = _request(
            "PATCH",
            f"{base}/issues/comments/{comment_id}",
            token=token,
            json={"body": body},
        )
        expected_status = 200
    if write.status_code != expected_status:
        raise RuntimeError(f"ledger write failed: http_status={write.status_code}")
    written = _json_object(write, operation="ledger write")
    comment_id = written.get("id")
    if not isinstance(comment_id, int):
        raise TypeError("ledger write is missing numeric comment id")

    readback = _request(
        "GET",
        f"{base}/issues/comments/{comment_id}",
        token=token,
    )
    if readback.status_code != 200:
        raise RuntimeError(f"ledger readback failed: http_status={readback.status_code}")
    observed = _json_object(readback, operation="ledger readback")
    if observed.get("body") != body or marker not in str(observed.get("body") or ""):
        raise RuntimeError("ledger readback did not match the exact published run entry")
    return comment_id


def _update_latest_pointer(
    *, base: str, token: str, issue_number: int, run_id: str, body: str
) -> None:
    summary_lines = body.splitlines()
    summary = "\n".join(summary_lines[:12])
    latest_body = (
        "Durable APEX audit execution ledger. Historical runs are preserved as comments.\n\n"
        f"### Latest verified run\n\n{summary}\n"
    )
    update = _request(
        "PATCH",
        f"{base}/issues/{issue_number}",
        token=token,
        json={"body": latest_body},
    )
    if update.status_code != 200:
        raise RuntimeError(f"ledger pointer update failed: http_status={update.status_code}")
    readback = _request("GET", f"{base}/issues/{issue_number}", token=token)
    if readback.status_code != 200:
        raise RuntimeError(f"ledger pointer readback failed: http_status={readback.status_code}")
    observed = _json_object(readback, operation="ledger pointer readback")
    if observed.get("body") != latest_body or _marker(run_id) not in latest_body:
        raise RuntimeError("ledger latest pointer did not read back exactly")


def publish_run(*, run_id: str, token: str, repo: str) -> int:
    verified = verify_run_receipt(run_id)
    run, queue = _load_run(run_id)
    body = _entry_body(
        run_id=run_id,
        run=run,
        queue=queue,
        log_sha256=verified.log_sha256,
        queue_sha256=verified.queue_sha256,
    )
    base = f"https://api.github.com/repos/{repo}"
    issue_number = _find_or_create_ledger(base=base, token=token)
    comment_id = _write_and_readback_comment(
        base=base,
        token=token,
        issue_number=issue_number,
        body=body,
        run_id=run_id,
    )
    _update_latest_pointer(
        base=base,
        token=token,
        issue_number=issue_number,
        run_id=run_id,
        body=body,
    )
    print(
        json.dumps(
            {
                "event": "apex_audit_ledger_readback_verified",
                "run_id": run_id,
                "issue_number": issue_number,
                "comment_id": comment_id,
                "log_sha256": verified.log_sha256,
                "queue_sha256": verified.queue_sha256,
                "external_action_authorized_by_audit": False,
            },
            sort_keys=True,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=os.environ.get("RUN_DATE", ""))
    args = parser.parse_args(argv)
    run_id = args.run_id.strip()
    if not run_id:
        print("RUN_DATE/--run-id is required; refusing newest-file fallback.")
        return 2
    if not _queue_path(run_id).is_file() or not _log_path(run_id).is_file():
        print(f"Exact audit receipt missing for run {run_id}; refusing stale fallback.")
        return 2
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPO", "GlacierEQ/apex-control-plane")
    if not token:
        print("GITHUB_TOKEN is required for durable audit-ledger publication.")
        return 2
    try:
        return publish_run(run_id=run_id, token=token, repo=repo)
    except (
        AuditInvariantError,
        RuntimeError,
        TypeError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        print(f"APEX audit ledger failure: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
