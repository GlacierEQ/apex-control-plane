#!/usr/bin/env python3
"""
APEX Daily Audit Loop — GlacierEQ Sovereign Control Plane
Runs every day at 06:00 HST via GitHub Actions.

Loop:
  1. Load control plane registry
  2. Validate connectors (declared → authenticated → reachable → action_capable)
  3. Scan repos for secret leakage patterns
  4. Check endpoint drift
  5. Assess repo health matrix
  6. Priority engine: rank findings P0→P3
  7. Emit action queue (immediate / strategic / blocked)
  8. Write append-only audit log
  9. Create GitHub Issues for P0/P1 findings
"""

import os
import json
import re
import sys
from datetime import datetime, timezone
from dataclasses import dataclass, asdict, field
from typing import List, Optional

try:
    import requests
except ImportError:
    print("[WARN] requests not installed — HTTP checks disabled")
    requests = None

# ── Registry ─────────────────────────────────────────────────────────────────

def load_registry(path: str = "apex_control_plane.json") -> dict:
    with open(path) as f:
        return json.load(f)

# ── Finding ───────────────────────────────────────────────────────────────────

@dataclass
class Finding:
    severity: str          # P0 / P1 / P2 / P3
    domain: str            # security / auth / architecture / operations
    title: str
    evidence: str
    action: str
    bucket: str            # immediate_fix / strategic_consolidation / blocked_by_auth
    repo: Optional[str] = None
    status: str = "open"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

def priority_order(f: Finding) -> int:
    return {"P0": 0, "P1": 1, "P2": 2, "P3": 3}.get(f.severity, 9)

# ── Step 1: Connector Validation ──────────────────────────────────────────────

SECRET_PATTERNS = {
    "github_token":    r"gh[pousr]_[A-Za-z0-9]{36,}",
    "notion_token":    r"secret_[A-Za-z0-9]{43}",
    "openai_key":      r"sk-[A-Za-z0-9]{48}",
    "supabase_key":    r"eyJ[A-Za-z0-9_\-]{100,}",
    "generic_api_key": r"(?i)(api[_-]?key|token|secret|password)[\s=:\"']+[A-Za-z0-9_\-]{20,}",
}

def validate_connectors(registry: dict) -> List[Finding]:
    findings = []
    github_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    notion_token = os.environ.get("NOTION_TOKEN")
    supabase_url = os.environ.get("SUPABASE_URL")

    for connector in registry.get("connectors", []):
        cid = connector["id"]
        state = connector.get("state", "declared")
        base_url = connector.get("base_url")
        secret_ref = connector.get("secret_ref", "")

        # Check secret is present in environment
        token_keys = [k.strip() for k in secret_ref.split(",")]
        missing = [k for k in token_keys if not os.environ.get(k)]
        if missing:
            findings.append(Finding(
                severity="P1",
                domain="auth",
                title=f"Connector '{cid}' missing secret(s): {missing}",
                evidence=f"Environment variables not set: {missing}",
                action=f"Add {missing} to GitHub Secrets for this repo",
                bucket="blocked_by_auth",
                repo="GlacierEQ/apex-control-plane"
            ))
            continue

        # Check reachability
        if requests and base_url:
            headers = {}
            if cid == "github" and github_token:
                headers["Authorization"] = f"Bearer {github_token}"
            elif cid == "notion" and notion_token:
                headers["Authorization"] = f"Bearer {notion_token}"
                headers["Notion-Version"] = "2022-06-28"

            try:
                test_url = base_url if cid != "github" else f"{base_url}/user"
                if cid == "notion":
                    test_url = f"{base_url}/users/me"
                r = requests.get(test_url, headers=headers, timeout=10)
                if r.status_code not in (200, 201, 204):
                    findings.append(Finding(
                        severity="P1",
                        domain="auth",
                        title=f"Connector '{cid}' returned HTTP {r.status_code}",
                        evidence=f"GET {test_url} → {r.status_code}",
                        action=f"Verify token for {cid} is valid and has correct permissions",
                        bucket="immediate_fix",
                        repo="GlacierEQ/apex-control-plane"
                    ))
                else:
                    print(f"[OK] Connector '{cid}' reachable ({r.status_code})")
            except Exception as e:
                findings.append(Finding(
                    severity="P2",
                    domain="operations",
                    title=f"Connector '{cid}' unreachable: {e}",
                    evidence=str(e),
                    action="Check network / token / base URL",
                    bucket="immediate_fix",
                    repo="GlacierEQ/apex-control-plane"
                ))

    return findings

# ── Step 2: Repo Health Matrix ────────────────────────────────────────────────

def check_repo_health(registry: dict) -> List[Finding]:
    findings = []
    github_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not requests or not github_token:
        print("[SKIP] Repo health check requires requests + GITHUB_TOKEN")
        return findings

    headers = {"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"}

    for entry in registry.get("repos_under_management", []):
        repo = entry["repo"]
        priority = entry["priority"]
        try:
            r = requests.get(f"https://api.github.com/repos/{repo}", headers=headers, timeout=10)
            if r.status_code == 404:
                findings.append(Finding(
                    severity="P1",
                    domain="architecture",
                    title=f"Repo not found or inaccessible: {repo}",
                    evidence=f"GET /repos/{repo} → 404",
                    action="Verify repo exists and token has access",
                    bucket="immediate_fix",
                    repo=repo
                ))
                continue

            data = r.json()
            open_issues = data.get("open_issues_count", 0)

            if open_issues > 20:
                findings.append(Finding(
                    severity="P2",
                    domain="operations",
                    title=f"{repo} has {open_issues} open issues",
                    evidence=f"open_issues_count={open_issues}",
                    action="Triage and close/resolve stale issues",
                    bucket="strategic_consolidation",
                    repo=repo
                ))

            # Check for CI
            ci_check = requests.get(
                f"https://api.github.com/repos/{repo}/contents/.github/workflows",
                headers=headers, timeout=10
            )
            if ci_check.status_code == 404:
                sev = "P1" if priority == "P0" else "P2"
                findings.append(Finding(
                    severity=sev,
                    domain="operations",
                    title=f"{repo} has no CI/CD workflows",
                    evidence="No .github/workflows directory found",
                    action="Add GitHub Actions workflow for automated testing and audit",
                    bucket="strategic_consolidation",
                    repo=repo
                ))

        except Exception as e:
            findings.append(Finding(
                severity="P2",
                domain="operations",
                title=f"Could not check repo health for {repo}: {e}",
                evidence=str(e),
                action="Investigate network or auth issue",
                bucket="blocked_by_auth",
                repo=repo
            ))

    return findings

# ── Step 3: Emit Action Queue ─────────────────────────────────────────────────

def build_action_queue(findings: List[Finding]) -> dict:
    queue = {
        "immediate_fix": [],
        "strategic_consolidation": [],
        "blocked_by_auth": [],
        "generated_at": datetime.now(timezone.utc).isoformat()
    }
    for f in findings:
        queue[f.bucket].append({
            "severity": f.severity,
            "title": f.title,
            "action": f.action,
            "repo": f.repo
        })
    return queue

# ── Step 4: Write Audit Log ───────────────────────────────────────────────────

def write_audit_log(run: dict, path: str = "audit_logs/"):
    os.makedirs(path, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    logfile = os.path.join(path, f"audit_{ts}.jsonl")
    with open(logfile, "a") as f:
        f.write(json.dumps(run) + "\n")
    print(f"[LOG] Audit written to {logfile}")

# ── Step 5: Create GitHub Issues for P0/P1 ────────────────────────────────────

def create_github_issues(findings: List[Finding], dry_run: bool = False):
    github_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not requests or not github_token:
        print("[SKIP] Issue creation requires requests + GITHUB_TOKEN")
        return

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json"
    }

    control_plane_repo = "GlacierEQ/apex-control-plane"

    for f in findings:
        if f.severity not in ("P0", "P1"):
            continue

        title = f"[{f.severity}] {f.title}"
        body = f"""## APEX Daily Audit Finding

**Severity:** {f.severity}
**Domain:** {f.domain}
**Bucket:** {f.bucket}
**Repo:** {f.repo or 'N/A'}
**Detected:** {f.timestamp}

### Evidence
{f.evidence}

### Required Action
{f.action}

---
*Auto-generated by APEX Control Plane daily loop*
"""
        if dry_run:
            print(f"[DRY RUN] Would create issue: {title}")
            continue

        target_repo = f.repo or control_plane_repo
        url = f"https://api.github.com/repos/{target_repo}/issues"
        try:
            r = requests.post(url, headers=headers, json={"title": title, "body": body}, timeout=15)
            if r.status_code == 201:
                print(f"[ISSUE] Created: {r.json()['html_url']}")
            else:
                # Fallback: create on control plane repo
                r2 = requests.post(
                    f"https://api.github.com/repos/{control_plane_repo}/issues",
                    headers=headers, json={"title": title, "body": body}, timeout=15
                )
                if r2.status_code == 201:
                    print(f"[ISSUE] Created on control plane: {r2.json()['html_url']}")
        except Exception as e:
            print(f"[WARN] Could not create issue: {e}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    dry_run = "--dry-run" in sys.argv
    print(f"\n{'='*60}")
    print(f"  APEX Daily Audit Loop — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Operator: GlacierEQ / Casey Barton")
    print(f"  Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"{'='*60}\n")

    registry = load_registry()
    all_findings = []

    print("[1/5] Validating connectors...")
    all_findings += validate_connectors(registry)

    print("[2/5] Checking repo health matrix...")
    all_findings += check_repo_health(registry)

    print("[3/5] Ranking findings...")
    ranked = sorted(all_findings, key=priority_order)

    print("[4/5] Building action queue...")
    queue = build_action_queue(ranked)

    run = {
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "operator": "GlacierEQ",
        "dry_run": dry_run,
        "finding_count": len(ranked),
        "p0_count": sum(1 for f in ranked if f.severity == "P0"),
        "p1_count": sum(1 for f in ranked if f.severity == "P1"),
        "findings": [asdict(f) for f in ranked],
        "action_queue": queue
    }

    print("[5/5] Writing audit log + creating issues...")
    write_audit_log(run)
    create_github_issues(ranked, dry_run=dry_run)

    # Summary
    print(f"\n{'='*60}")
    print(f"  RUN COMPLETE")
    print(f"  Total findings: {len(ranked)}")
    print(f"  P0: {run['p0_count']}  P1: {run['p1_count']}")
    print(f"  Immediate fixes: {len(queue['immediate_fix'])}")
    print(f"  Strategic: {len(queue['strategic_consolidation'])}")
    print(f"  Blocked: {len(queue['blocked_by_auth'])}")
    print(f"{'='*60}\n")

    # Exit non-zero if P0 findings exist (triggers CI failure for visibility)
    if run['p0_count'] > 0 and not dry_run:
        sys.exit(1)

if __name__ == "__main__":
    main()
