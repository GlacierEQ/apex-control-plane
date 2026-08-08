"""
APEX Daily Audit Runner v2.0
Scan -> Validate -> Rank -> Log -> Emit Action Queue
Runs autonomously via GitHub Actions — no human approval needed per run.
"""

import datetime
import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field

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
    findings: list[dict] = field(default_factory=list)
    connectors_validated: list[dict] = field(default_factory=list)
    action_queue: dict = field(
        default_factory=lambda: {"immediate": [], "strategic": [], "blocked": []}
    )
    summary: str = ""


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ── Connector Validators ──────────────────────────────────────────────────────
def validate_github():
    if not GITHUB_TOKEN:
        return {
            "connector": "github",
            "state": "declared",
            "error": "APEX_GITHUB_TOKEN env var not set",
        }
    req = urllib.request.Request(
        f"https://api.github.com/users/{GITHUB_OWNER}",
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read())
                return {
                    "connector": "github",
                    "state": "action_capable",
                    "user": data.get("login"),
                    "repos": data.get("public_repos", 0),
                }
    except urllib.error.HTTPError as error:
        return {"connector": "github", "state": "auth_failed", "error": str(error)}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        return {"connector": "github", "state": "unreachable", "error": str(error)}
    return {"connector": "github", "state": "unreachable", "error": "unexpected response"}


def validate_notion():
    if not NOTION_TOKEN:
        return {
            "connector": "notion",
            "state": "declared",
            "error": "APEX_NOTION_TOKEN env var not set",
        }
    req = urllib.request.Request(
        "https://api.notion.com/v1/users/me",
        headers={
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": "2022-06-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read())
                return {
                    "connector": "notion",
                    "state": "action_capable",
                    "user": data.get("name", "unknown"),
                }
    except urllib.error.HTTPError as error:
        return {"connector": "notion", "state": "auth_failed", "error": str(error)}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        return {"connector": "notion", "state": "unreachable", "error": str(error)}
    return {"connector": "notion", "state": "unreachable", "error": "unexpected response"}


def scan_repos_for_issues():
    """Scan GlacierEQ repos for drift, open issues, stale branches."""
    if not GITHUB_TOKEN:
        return []
    findings = []
    req = urllib.request.Request(
        f"https://api.github.com/users/{GITHUB_OWNER}/repos?per_page=100&sort=updated",
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            repos = json.loads(response.read())
            stale = [repo["name"] for repo in repos if repo.get("open_issues_count", 0) > 10]
            archived = [repo["name"] for repo in repos if repo.get("archived")]
            if stale:
                findings.append(
                    Finding(
                        severity="P2",
                        domain="repo-health",
                        title=f"{len(stale)} repos with >10 open issues",
                        evidence=", ".join(stale[:5]) + ("..." if len(stale) > 5 else ""),
                        action="Triage or bulk-close stale issues",
                    )
                )
            if len(archived) > 20:
                findings.append(
                    Finding(
                        severity="P3",
                        domain="repo-hygiene",
                        title=f"{len(archived)} archived repos taking up namespace",
                        evidence=f"{len(archived)} archived repos found",
                        action="Review archived repos for deletion or consolidation",
                    )
                )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        findings.append(
            Finding(
                severity="P1",
                domain="scan",
                title="Repo scan failed",
                evidence=str(error),
                action="Check GITHUB_TOKEN scopes include repo read",
            )
        )
    return findings


# ── Finding Engine ────────────────────────────────────────────────────────────
def generate_findings(connector_results) -> list[Finding]:
    findings = []
    for connector in connector_results:
        if connector["state"] == "declared":
            findings.append(
                Finding(
                    severity="P0",
                    domain="auth",
                    title=f"{connector['connector']} token missing",
                    evidence=connector.get("error", "env var not set"),
                    action=f"Add {connector['connector'].upper()} secret to GitHub repo secrets",
                )
            )
        elif "failed" in connector["state"] or "unreachable" in connector["state"]:
            findings.append(
                Finding(
                    severity="P1",
                    domain="connectivity",
                    title=f"{connector['connector']} not reachable",
                    evidence=connector.get("error", "connection failed"),
                    action=f"Rotate token and verify network for {connector['connector']}",
                )
            )
    return sorted(findings, key=lambda finding: PRIORITY_ORDER.get(finding.severity, 9))


def build_action_queue(findings: list[Finding]) -> dict:
    queue = {"immediate": [], "strategic": [], "blocked": []}
    for finding in findings:
        if finding.severity == "P0":
            queue["immediate"].append(f"{finding.title} → {finding.action}")
        elif finding.severity in ("P1", "P2"):
            queue["strategic"].append(f"{finding.title} → {finding.action}")
        else:
            queue["blocked"].append(f"{finding.title} → {finding.action}")
    return queue


# ── Persistence ───────────────────────────────────────────────────────────────
def load_control_plane():
    if os.path.exists(CONTROL_PLANE_FILE):
        with open(CONTROL_PLANE_FILE) as handle:
            return json.load(handle)
    return {"audit_log": [], "run_count": 0}


def save_control_plane(data):
    with open(CONTROL_PLANE_FILE, "w") as handle:
        json.dump(data, handle, indent=2)


# ── Main ──────────────────────────────────────────────────────────────────────
def run_daily_audit():
    print(f"\n{'=' * 60}")
    print(f"APEX DAILY AUDIT — {now_iso()}")
    print(f"{'=' * 60}\n")

    control_plane = load_control_plane()
    run_number = control_plane.get("run_count", 0) + 1
    control_plane["run_count"] = run_number

    connector_results = [validate_github(), validate_notion()]
    print("CONNECTOR STATUS:")
    for connector in connector_results:
        icon = "✅" if connector["state"] == "action_capable" else "❌"
        print(f"  {icon} {connector['connector']:12} → {connector['state']}")

    findings = generate_findings(connector_results)
    repo_findings = scan_repos_for_issues()
    all_findings = sorted(
        findings + repo_findings,
        key=lambda finding: PRIORITY_ORDER.get(finding.severity, 9),
    )

    print(f"\nFINDINGS ({len(all_findings)} total):")
    for finding in all_findings:
        print(f"  [{finding.severity}] {finding.domain} — {finding.title}")
        print(f"         → {finding.action}")

    queue = build_action_queue(all_findings)
    print("\nACTION QUEUE:")
    for bucket, items in queue.items():
        if items:
            print(f"  {bucket.upper()}:")
            for item in items:
                print(f"    • {item}")

    p0_count = sum(1 for finding in all_findings if finding.severity == "P0")
    summary = (
        f"Run #{run_number} | {len(all_findings)} findings | "
        f"{p0_count} P0s | {now_iso()}"
    )
    print(f"\n{summary}")

    audit_entry = asdict(
        AuditRun(
            timestamp=now_iso(),
            run_number=run_number,
            findings=[asdict(finding) for finding in all_findings],
            connectors_validated=connector_results,
            action_queue=queue,
            summary=summary,
        )
    )
    control_plane.setdefault("audit_log", []).append(audit_entry)
    control_plane["last_run"] = now_iso()
    control_plane["last_summary"] = summary
    save_control_plane(control_plane)

    print(f"\n✅ Audit complete. Log written to {CONTROL_PLANE_FILE}")
    print(f"   Run #{run_number} committed to audit trail.\n")
    return audit_entry


if __name__ == "__main__":
    run_daily_audit()
