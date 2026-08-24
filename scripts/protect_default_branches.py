#!/usr/bin/env python3
"""Apply additive default-branch protection across the GlacierEQ estate.

This controller protects the living default branch without freezing development.
It creates or updates exactly one named repository ruleset and never weakens,
replaces, or deletes any other protection already configured.

Fleet baseline:
- target only ~DEFAULT_BRANCH;
- require changes to arrive through pull requests;
- require zero approving reviews at the fleet layer;
- block deletion of the default branch;
- block force pushes / non-fast-forward updates;
- DO NOT create fleet-wide required status-check names;
- DO NOT restrict pushes to a fixed actor list;
- DO NOT lock the branch.

Repository-specific CI/review requirements remain repo-specific. The fleet rule
is deliberately structural and additive so a renamed/deleted workflow cannot
strand a repository forever.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

API = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
OWNER = os.environ.get("GITHUB_OWNER", "GlacierEQ")
TOKEN = (
    os.environ.get("APEX_GITHUB_TOKEN")
    or os.environ.get("GH_ADMIN_TOKEN")
    or os.environ.get("GITHUB_ADMIN_TOKEN")
    or ""
).strip()
RULESET_NAME = "APEX Default Branch Assimilation Guard"
API_VERSION = "2022-11-28"
MAX_PAGES = 100
WRITE_DELAY_SECONDS = float(os.environ.get("APEX_RULESET_WRITE_DELAY", "1.05"))


class ProtectionError(RuntimeError):
    pass


def _request(method: str, url: str, payload: Mapping[str, Any] | None = None, *, attempts: int = 7) -> tuple[int, Any, Mapping[str, str]]:
    body = None
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "GlacierEQ-Default-Branch-Protection/1",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"

    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                raw = response.read()
                parsed = json.loads(raw.decode("utf-8")) if raw else None
                return response.status, parsed, dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            retryable = exc.code in {403, 429, 500, 502, 503, 504}
            if retryable and attempt < attempts:
                retry_after = exc.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else min(60.0, 2.0 ** (attempt - 1))
                time.sleep(max(1.0, delay))
                continue
            try:
                detail = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                detail = {"message": raw[:500]}
            raise ProtectionError(f"{method} {url} failed HTTP {exc.code}: {detail.get('message', raw[:300])}") from exc
        except (urllib.error.URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            if attempt < attempts:
                time.sleep(min(30.0, 2.0 ** (attempt - 1)))
                continue
            raise ProtectionError(f"{method} {url} failed: {exc}") from exc
    raise ProtectionError(f"{method} {url} exhausted retries")


def _next_link(headers: Mapping[str, str]) -> str | None:
    value = headers.get("Link") or headers.get("link") or ""
    for chunk in value.split(","):
        chunk = chunk.strip()
        if 'rel="next"' in chunk and chunk.startswith("<") and ">" in chunk:
            return chunk[1 : chunk.index(">")]
    return None


def list_owned_repositories() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    url: str | None = f"{API}/user/repos?per_page=100&affiliation=owner&sort=full_name&direction=asc"
    pages = 0
    while url:
        pages += 1
        if pages > MAX_PAGES:
            raise ProtectionError("repository enumeration exceeded page limit")
        _, payload, headers = _request("GET", url)
        if not isinstance(payload, list):
            raise ProtectionError("repository enumeration returned non-list payload")
        for repo in payload:
            if not isinstance(repo, dict):
                continue
            owner = repo.get("owner") or {}
            if str(owner.get("login") or "").casefold() == OWNER.casefold():
                rows.append(repo)
        url = _next_link(headers)
    return rows


def ruleset_payload() -> dict[str, Any]:
    return {
        "name": RULESET_NAME,
        "target": "branch",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {
                "type": "pull_request",
                "parameters": {
                    "allowed_merge_methods": ["merge", "squash", "rebase"],
                    "dismiss_stale_reviews_on_push": False,
                    "require_code_owner_review": False,
                    "require_last_push_approval": False,
                    "required_approving_review_count": 0,
                    "required_review_thread_resolution": False,
                },
            },
        ],
    }


def _rulesets_url(full_name: str) -> str:
    owner, repo = full_name.split("/", 1)
    return f"{API}/repos/{urllib.parse.quote(owner, safe='')}/{urllib.parse.quote(repo, safe='')}/rulesets"


def list_repo_rulesets(full_name: str) -> list[dict[str, Any]]:
    _, payload, _ = _request("GET", _rulesets_url(full_name) + "?per_page=100&includes_parents=false")
    if not isinstance(payload, list):
        raise ProtectionError(f"{full_name}: ruleset listing returned non-list payload")
    return [row for row in payload if isinstance(row, dict)]


def find_named_ruleset(full_name: str) -> dict[str, Any] | None:
    matches = [row for row in list_repo_rulesets(full_name) if str(row.get("name") or "") == RULESET_NAME]
    if len(matches) > 1:
        raise ProtectionError(f"{full_name}: multiple {RULESET_NAME!r} rulesets exist; refusing ambiguity")
    return matches[0] if matches else None


def get_ruleset(full_name: str, ruleset_id: int) -> dict[str, Any]:
    _, payload, _ = _request("GET", f"{_rulesets_url(full_name)}/{ruleset_id}?includes_parents=false")
    if not isinstance(payload, dict):
        raise ProtectionError(f"{full_name}: ruleset detail returned non-object payload")
    return payload


def apply_ruleset(full_name: str, *, dry_run: bool) -> tuple[str, int | None]:
    existing = find_named_ruleset(full_name)
    if dry_run:
        return ("would-update" if existing else "would-create"), (int(existing["id"]) if existing and existing.get("id") else None)

    if existing:
        ruleset_id = int(existing["id"])
        _request("PUT", f"{_rulesets_url(full_name)}/{ruleset_id}", ruleset_payload())
        action = "updated"
    else:
        _, created, _ = _request("POST", _rulesets_url(full_name), ruleset_payload())
        if not isinstance(created, dict) or not created.get("id"):
            raise ProtectionError(f"{full_name}: create response missing ruleset id")
        ruleset_id = int(created["id"])
        action = "created"
    time.sleep(max(0.0, WRITE_DELAY_SECONDS))
    return action, ruleset_id


def verify_ruleset(full_name: str, ruleset_id: int) -> dict[str, Any]:
    row = get_ruleset(full_name, ruleset_id)
    if row.get("name") != RULESET_NAME or row.get("target") != "branch" or row.get("enforcement") != "active":
        raise ProtectionError(f"{full_name}: ruleset identity/enforcement mismatch")

    conditions = row.get("conditions")
    ref_name = conditions.get("ref_name") if isinstance(conditions, dict) else None
    if not isinstance(ref_name, dict) or "~DEFAULT_BRANCH" not in (ref_name.get("include") or []):
        raise ProtectionError(f"{full_name}: ruleset no longer targets only the default branch")

    rules = row.get("rules")
    if not isinstance(rules, list):
        raise ProtectionError(f"{full_name}: rules missing after write")
    types = {str(rule.get("type") or "") for rule in rules if isinstance(rule, dict)}
    required = {"deletion", "non_fast_forward", "pull_request"}
    if types != required:
        raise ProtectionError(f"{full_name}: fleet ruleset contains unexpected rule types: {sorted(types)}")

    pr = next((rule for rule in rules if isinstance(rule, dict) and rule.get("type") == "pull_request"), None)
    params = pr.get("parameters") if isinstance(pr, dict) else None
    if not isinstance(params, dict) or int(params.get("required_approving_review_count", -1)) != 0:
        raise ProtectionError(f"{full_name}: fleet rule unexpectedly requires approvals")

    return {
        "ruleset_id": ruleset_id,
        "enforcement": "active",
        "target": "~DEFAULT_BRANCH",
        "rules": sorted(types),
        "required_status_checks_added": 0,
        "required_approvals_added": 0,
        "locked": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="perform writes; default is dry-run")
    parser.add_argument("--report", default="branch_protection_report.json")
    parser.add_argument("--max-repos", type=int, default=0)
    args = parser.parse_args()

    if args.apply and not TOKEN:
        print("ERROR: --apply requires an admin-capable token via APEX_GITHUB_TOKEN, GH_ADMIN_TOKEN, or GITHUB_ADMIN_TOKEN", file=sys.stderr)
        return 78

    try:
        repos = list_owned_repositories()
    except ProtectionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.max_repos > 0:
        repos = repos[: args.max_repos]

    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "owner": OWNER,
        "ruleset_name": RULESET_NAME,
        "mode": "apply" if args.apply else "dry-run",
        "policy": {
            "target": "~DEFAULT_BRANCH",
            "require_pull_request": True,
            "required_approvals_added": 0,
            "required_status_checks_added": 0,
            "block_deletion": True,
            "block_force_push": True,
            "lock_branch": False,
            "restrict_push_actors": False,
            "existing_protections": "left_intact_and_layered",
        },
        "repository_count": len(repos),
        "results": [],
    }

    failures = verified = skipped = 0
    for repo in repos:
        full_name = str(repo.get("full_name") or "")
        item: dict[str, Any] = {
            "repository": full_name,
            "default_branch": repo.get("default_branch"),
            "fork": bool(repo.get("fork")),
            "archived": bool(repo.get("archived")),
            "disabled": bool(repo.get("disabled")),
        }
        if repo.get("archived"):
            item["status"] = "skipped-archived-already-read-only"; skipped += 1
        elif repo.get("disabled"):
            item["status"] = "skipped-disabled"; skipped += 1
        elif not repo.get("default_branch"):
            item["status"] = "skipped-no-default-branch"; skipped += 1
        else:
            try:
                action, ruleset_id = apply_ruleset(full_name, dry_run=not args.apply)
                item["action"] = action
                if args.apply:
                    if ruleset_id is None:
                        raise ProtectionError(f"{full_name}: write returned no ruleset id")
                    item["verification"] = verify_ruleset(full_name, ruleset_id)
                    item["status"] = "verified"; verified += 1
                else:
                    item["status"] = "planned"
            except (ProtectionError, ValueError, KeyError) as exc:
                item["status"] = "failed"; item["error"] = str(exc); failures += 1
                print(f"FAIL {full_name}: {exc}", file=sys.stderr)
        report["results"].append(item)

    report["summary"] = {
        "verified": verified,
        "failed": failures,
        "skipped": skipped,
        "planned": sum(1 for row in report["results"] if row.get("status") == "planned"),
    }
    Path(args.report).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], sort_keys=True))
    return 1 if args.apply and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
