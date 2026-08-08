#!/usr/bin/env python3
"""
APEX Daily Audit Runner v2.0
Scan -> Validate -> Rank -> Log -> Emit Action Queue
Runs autonomously via GitHub Actions — no human approval needed per run.
"""

import os
import json
import datetime
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict, field
from typing import List

GITHUB_TOKEN = os.environ.get("APEX_GITHUB_TOKEN", os.environ.get("GITHUB_TOKEN", ""))
NOTION_TOKEN = os.environ.get("APEX_NOTION_TOKEN", os.environ.get("NOTION_TOKEN", ""))
GITHUB_OWNER = os.environ.get("GITHUB_OWNER", "GlacierEQ")
CONTROL_PLANE_FILE = "apex_control_plane.json"
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


@dataclass
class Finding:
    severity: str
    domain: str
    title: str
    evidence: str
    action: str
    status: str = "open"


@dataclass
class AuditRun:
    timestamp: str
    run_number: int
    findings: List[dict] = field(default_factory=list)
    connectors_validated: List[dict] = field(default_factory=list)
    action_queue: dict = field(default_factory=lambda: {
        "immediate": [], "strategic": [], "blocked": []
    })
    summary: str = ""


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ── Connector Validators ──────────────────────────────────────────────────────
def validate_github():
    if not GITHUB_TOKEN:
        return {"connector": "github", "state": "declared",
                "error": "APEX_GITHUB_TOKEN env var not set"}
    req = urllib.request.Request(
        f"https://api.github.com/users/{GITHUB_OWNER}",
        headers={"Authorization": f"token {GITHUB_TOKEN}",
                 "Accept": "application/vnd.github+json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            if r.status == 200:
                data = json.loads(r.read())
                return {"connector": "github", "state": "action_capable",
                        "user": data.get("login"), "repos": data.get("public_repos", 0)}
    except urllib.error.HTTPError as e:
        return {"connector": "github", "state": "auth_failed", "error": str(e)}
    except Exception as e:
        return {"connector": "github", "state": "unreachable", "error": str(e)}


def validate_notion():
    if not NOTION_TOKEN:
        return {"connector": "notion", "state": "declared",
                "error": "APEX_NOTION_TOKEN env var not set"}
    req = urllib.request.Request(
        "https://api.notion.com/v1/users/me",
        headers={"Authorization": f"Bearer {NOTION_TOKEN}",
                 "Notion-Version": "2022-06-28"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            if r.status == 200:
                data = json.loads(r.read())
                return {"connector": "notion", "state": "action_capable",
                        "user": data.get("name", "unknown")}
    except urllib.error.HTTPError as e:
        return {"connector": "notion", "state": "auth_failed", "error": str(e)}
    except Exception as e:
        return {"connector": "notion", "state": "unreachable", "error": str(e)}


def scan_repos_for_issues():
    """Scan GlacierEQ repos for drift, open issues, stale branches."""
    if not GITHUB_TOKEN:
        return []
    findings = []
    req = urllib.request.Request(
        f"https://api.github.com/users/{GITHUB_OWNER}/repos?per_page=100&sort=updated",
        headers={"Authorization": f"token {GITHUB_TOKEN}",
                 "Accept": "application/vnd.github+json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            repos = json.loads(r.read())
            stale = [rp["name"] for rp in repos
                     if rp.get("open_issues_count", 0) > 10]
            archived = [rp["name"] for rp in repos if rp.get("archived")]
            if stale:
                findings.append(Finding(
                    severity="P2", domain="repo-health",
                    title=f"{len(stale)} repos with >10 open issues",
                    evidence=", ".join(stale[:5]) + ("..." if len(stale) > 5 else ""),
                    action="Triage or bulk-close stale issues"
                ))
            if len(archived) > 20:
                findings.append(Finding(
                    severity="P3", domain="repo-hygiene",
                    title=f"{len(archived)} archived repos taking up namespace",
                    evidence=f"{len(archived)} archived repos found",
                    action="Review archived repos for deletion or consolidation"
                ))
    except Exception as e:
        findings.append(Finding(
            severity="P1", domain="scan",
            title="Repo scan failed",
            evidence=str(e),
            action="Check GITHUB_TOKEN scopes include repo read"
        ))
    return findings


# ── Finding Engine ────────────────────────────────────────────────────────────
def generate_findings(connector_results) -> List[Finding]:
    findings = []
    for c in connector_results:
        if c["state"] == "declared":
            findings.append(Finding(
                severity="P0", domain="auth",
                title=f"{c['connector']} token missing",
                evidence=c.get("error", "env var not set"),
                action=f"Add {c['connector'].upper()} secret to GitHub repo secrets"
            ))
        elif "failed" in c["state"] or "unreachable" in c["state"]:
            findings.append(Finding(
                severity="P1", domain="connectivity",
                title=f"{c['connector']} not reachable",
                evidence=c.get("error", "connection failed"),
                action=f"Rotate token and verify network for {c['connector']}"
            ))
    return sorted(findings, key=lambda f: PRIORITY_ORDER.get(f.severity, 9))


def build_action_queue(findings: List[Finding]) -> dict:
    q = {"immediate": [], "strategic": [], "blocked": []}
    for f in findings:
        if f.severity == "P0":
            q["immediate"].append(f"{f.title} → {f.action}")
        elif f.severity in ("P1", "P2"):
            q["strategic"].append(f"{f.title} → {f.action}")
        else:
            q["blocked"].append(f"{f.title} → {f.action}")
    return q


# ── Persistence ───────────────────────────────────────────────────────────────
def load_control_plane():
    if os.path.exists(CONTROL_PLANE_FILE):
        with open(CONTROL_PLANE_FILE) as fp:
            return json.load(fp)
    return {"audit_log": [], "run_count": 0}


def save_control_plane(data):
    with open(CONTROL_PLANE_FILE, "w") as fp:
        json.dump(data, fp, indent=2)


# ── Main ──────────────────────────────────────────────────────────────────────
def run_daily_audit():
    print(f"\n{'='*60}")
    print(f"APEX DAILY AUDIT — {now_iso()}")
    print(f"{'='*60}\n")

    cp = load_control_plane()
    run_number = cp.get("run_count", 0) + 1
    cp["run_count"] = run_number

    # Step 1: Validate connectors
    connector_results = [validate_github(), validate_notion()]
    print("CONNECTOR STATUS:")
    for c in connector_results:
        icon = "✅" if c["state"] == "action_capable" else "❌"
        print(f"  {icon} {c['connector']:12} → {c['state']}")

    # Step 2: Generate findings (connectors + repo scan)
    findings = generate_findings(connector_results)
    repo_findings = scan_repos_for_issues()
    all_findings = sorted(findings + repo_findings,
                          key=lambda f: PRIORITY_ORDER.get(f.severity, 9))

    print(f"\nFINDINGS ({len(all_findings)} total):")
    for f in all_findings:
        print(f"  [{f.severity}] {f.domain} — {f.title}")
        print(f"         → {f.action}")

    # Step 3: Build action queue
    queue = build_action_queue(all_findings)
    print(f"\nACTION QUEUE:")
    for bucket, items in queue.items():
        if items:
            print(f"  {bucket.upper()}:")
            for item in items:
                print(f"    • {item}")

    p0_count = sum(1 for f in all_findings if f.severity == "P0")
    summary = f"Run #{run_number} | {len(all_findings)} findings | {p0_count} P0s | {now_iso()}"
    print(f"\n{summary}")

    # Step 4: Persist
    audit_entry = asdict(AuditRun(
        timestamp=now_iso(),
        run_number=run_number,
        findings=[asdict(f) for f in all_findings],
        connectors_validated=connector_results,
        action_queue=queue,
        summary=summary
    ))
    cp.setdefault("audit_log", []).append(audit_entry)
    cp["last_run"] = now_iso()
    cp["last_summary"] = summary
    save_control_plane(cp)

    print(f"\n✅ Audit complete. Log written to {CONTROL_PLANE_FILE}")
    print(f"   Run #{run_number} committed to audit trail.\n")
    return audit_entry


if __name__ == "__main__":
    run_daily_audit()
