#!/usr/bin/env python3
"""
APEX Daily Audit Runner
Operator: casey / GlacierEQ
Mission: Scan → Validate → Rank → Log → Emit Action Queue

Run: python apex_daily.py
Schedule: daily via .github/workflows/apex-daily.yml
"""

import os
import json
import datetime
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict, field
from typing import List, Dict

# --- Config ---
GITHUB_TOKEN   = os.environ.get("APEX_GITHUB_TOKEN", "")
NOTION_TOKEN   = os.environ.get("APEX_NOTION_TOKEN", "")
SUPABASE_URL   = os.environ.get("APEX_SUPABASE_URL", "")
SUPABASE_KEY   = os.environ.get("APEX_SUPABASE_KEY", "")
REDIS_URL      = os.environ.get("APEX_REDIS_URL", "")
GITHUB_OWNER   = os.environ.get("GITHUB_OWNER", "GlacierEQ")
CONTROL_FILE   = "apex_control_plane.json"
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
    findings: List[dict] = field(default_factory=list)
    connectors: List[dict] = field(default_factory=list)
    action_queue: dict = field(default_factory=lambda: {
        "immediate": [], "strategic": [], "blocked": []
    })
    summary: str = ""


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# =====================
# Connector Validators
# =====================

def validate_github() -> dict:
    if not GITHUB_TOKEN:
        return {"connector": "github", "state": "declared",
                "error": "APEX_GITHUB_TOKEN not set"}
    req = urllib.request.Request(
        f"https://api.github.com/user",
        headers={"Authorization": f"token {GITHUB_TOKEN}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            return {"connector": "github", "state": "action_capable",
                    "user": data.get("login"), "repos": data.get("public_repos", 0)}
    except urllib.error.HTTPError as e:
        return {"connector": "github", "state": "auth_failed", "error": str(e)}
    except Exception as e:
        return {"connector": "github", "state": "unreachable", "error": str(e)}


def validate_notion() -> dict:
    if not NOTION_TOKEN:
        return {"connector": "notion", "state": "declared",
                "error": "APEX_NOTION_TOKEN not set"}
    req = urllib.request.Request(
        "https://api.notion.com/v1/users/me",
        headers={"Authorization": f"Bearer {NOTION_TOKEN}",
                 "Notion-Version": "2022-06-28"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            return {"connector": "notion", "state": "action_capable",
                    "user": data.get("name", "unknown")}
    except urllib.error.HTTPError as e:
        return {"connector": "notion", "state": "auth_failed", "error": str(e)}
    except Exception as e:
        return {"connector": "notion", "state": "unreachable", "error": str(e)}


def validate_supabase() -> dict:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"connector": "supabase", "state": "declared",
                "error": "APEX_SUPABASE_URL or APEX_SUPABASE_KEY not set"}
    req = urllib.request.Request(
        f"{SUPABASE_URL.rstrip('/')}/rest/v1/",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return {"connector": "supabase", "state": "action_capable",
                    "status": r.status}
    except urllib.error.HTTPError as e:
        return {"connector": "supabase", "state": "auth_failed", "error": str(e)}
    except Exception as e:
        return {"connector": "supabase", "state": "unreachable", "error": str(e)}


def validate_redis() -> dict:
    if not REDIS_URL:
        return {"connector": "redis", "state": "declared",
                "error": "APEX_REDIS_URL not set"}
    # TCP reachability check without redis-py dependency
    try:
        import socket
        from urllib.parse import urlparse
        p = urlparse(REDIS_URL)
        host = p.hostname
        port = p.port or 6379
        s = socket.create_connection((host, port), timeout=5)
        s.close()
        return {"connector": "redis", "state": "reachable", "host": host, "port": port}
    except Exception as e:
        return {"connector": "redis", "state": "unreachable", "error": str(e)}


# =====================
# Finding Engine
# =====================

def generate_findings(connector_results: List[dict]) -> List[Finding]:
    findings = []
    for c in connector_results:
        state = c["state"]
        name = c["connector"]
        if state == "declared":
            findings.append(Finding(
                severity="P0", domain="auth",
                title=f"{name} token missing",
                evidence=c.get("error", "env var not set"),
                action=f"Set env var for {name} connector in GitHub Secrets"
            ))
        elif state in ("auth_failed", "unreachable"):
            findings.append(Finding(
                severity="P1", domain="connectivity",
                title=f"{name} not reachable ({state})",
                evidence=c.get("error", ""),
                action=f"Check token validity and network for {name}"
            ))
    return sorted(findings, key=lambda f: PRIORITY_ORDER.get(f.severity, 9))


def build_action_queue(findings: List[Finding]) -> dict:
    q = {"immediate": [], "strategic": [], "blocked": []}
    for f in findings:
        if f.severity == "P0":
            q["immediate"].append(f.action)
        elif f.severity == "P1":
            q["strategic"].append(f.action)
        else:
            q["blocked"].append(f.action)
    return q


# =====================
# Persistence
# =====================

def load_control_plane() -> dict:
    if os.path.exists(CONTROL_FILE):
        with open(CONTROL_FILE) as fp:
            return json.load(fp)
    return {"version": "1.0.0", "audit_log": [], "connectors": {}}


def save_control_plane(data: dict):
    with open(CONTROL_FILE, "w") as fp:
        json.dump(data, fp, indent=2)


# =====================
# Main
# =====================

def run_daily_audit() -> dict:
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"APEX DAILY AUDIT \u2014 {now_iso()}")
    print(f"Operator: casey / GlacierEQ")
    print(sep)

    # Step 1: Validate connectors
    print("\n[1] CONNECTOR VALIDATION")
    connectors = [
        validate_github(),
        validate_notion(),
        validate_supabase(),
        validate_redis(),
    ]
    for c in connectors:
        icon = "\u2705" if c["state"] == "action_capable" else (
               "\u26a0\ufe0f" if c["state"] == "reachable" else "\u274c")
        print(f"  {icon} {c['connector']:12} \u2192 {c['state']}")

    # Step 2: Generate findings
    print("\n[2] FINDINGS")
    findings = generate_findings(connectors)
    if not findings:
        print("  \u2705 No findings. All connectors healthy.")
    for f in findings:
        print(f"  [{f.severity}] {f.domain} \u2014 {f.title}")
        print(f"         Evidence: {f.evidence}")
        print(f"         Action:   {f.action}")

    # Step 3: Action queue
    print("\n[3] ACTION QUEUE")
    queue = build_action_queue(findings)
    for bucket, items in queue.items():
        if items:
            print(f"  {bucket.upper()}:")
            for item in items:
                print(f"    \u2022 {item}")
    if not any(queue.values()):
        print("  \u2705 Queue empty. No actions required.")

    # Step 4: Build audit entry
    healthy = sum(1 for c in connectors if c["state"] == "action_capable")
    total = len(connectors)
    summary = (f"{healthy}/{total} connectors healthy, "
               f"{len(findings)} findings, "
               f"{len(queue['immediate'])} immediate actions")
    print(f"\n[4] SUMMARY: {summary}")

    run_entry = asdict(AuditRun(
        timestamp=now_iso(),
        findings=[asdict(f) for f in findings],
        connectors=connectors,
        action_queue=queue,
        summary=summary
    ))

    # Step 5: Persist
    cp = load_control_plane()
    cp.setdefault("audit_log", []).append(run_entry)
    # Update connector states in registry
    for c in connectors:
        cp.setdefault("connectors", {})[c["connector"]] = {
            "state": c["state"],
            "last_checked": now_iso()
        }
    save_control_plane(cp)
    print(f"\n\u2705 Audit complete. Log written to {CONTROL_FILE}\n")
    return run_entry


if __name__ == "__main__":
    run_daily_audit()
