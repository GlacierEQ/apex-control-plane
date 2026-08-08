#!/usr/bin/env python3
"""
APEX Daily Audit Loop — Zero-Confirmation Autonomous Execution
Runs every day via GitHub Actions. No human approval required.
Owner: GlacierEQ / Casey Barton
"""

import os
import json
import subprocess
from datetime import datetime, timezone
from dataclasses import dataclass, asdict, field
from typing import List, Optional

GITHUB_TOKEN = os.environ.get("APEX_GITHUB_TOKEN", "")
NOTION_TOKEN = os.environ.get("APEX_NOTION_TOKEN", "")
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


@dataclass
class Finding:
    severity: str  # P0, P1, P2, P3
    domain: str
    title: str
    evidence: str
    action: str
    auto_execute: bool = False
    status: str = "open"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class AuditRun:
    run_id: str
    started_at: str
    completed_at: Optional[str] = None
    findings: List[Finding] = field(default_factory=list)
    actions_executed: List[str] = field(default_factory=list)
    connectors_validated: dict = field(default_factory=dict)
    status: str = "running"


def log(msg: str):
    print(f"[APEX {RUN_ID}] {msg}")


# ─────────────────────────────────────────────────────────────
# LAYER 1: Connector Validation
# ─────────────────────────────────────────────────────────────
def validate_connectors() -> dict:
    results = {}

    checks = {
        "github": bool(GITHUB_TOKEN),
        "notion": bool(NOTION_TOKEN),
    }

    for name, auth_ok in checks.items():
        results[name] = {
            "declared": True,
            "authenticated": auth_ok,
            "reachable": auth_ok,  # simplified; expand with actual HTTP check
            "action_capable": auth_ok,
            "status": "GREEN" if auth_ok else "RED",
        }
        log(f"Connector [{name}]: {'GREEN' if auth_ok else 'RED — NO TOKEN'}")

    return results


# ─────────────────────────────────────────────────────────────
# LAYER 2: Secret Leakage Scan
# ─────────────────────────────────────────────────────────────
SECRET_PATTERNS = [
    "sk-", "ghp_", "ghs_", "xai-", "ntn_", "AKIA", "bearer ",
    "api_key", "apikey", "token", "password", "secret",
    "-----BEGIN",
]

EXCLUDE_DIRS = {"__pycache__", ".git", "node_modules", "venv", ".venv"}


def scan_secrets(root: str = ".") -> List[Finding]:
    findings = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fname in filenames:
            if not fname.endswith((".py", ".ts", ".js", ".env", ".yaml", ".yml", ".json", ".md")):
                continue
            fpath = os.path.join(dirpath, fname)
            try:
                with open(fpath, "r", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        low = line.lower()
                        for pat in SECRET_PATTERNS:
                            if pat in low and "os.environ" not in line and "example" not in low:
                                findings.append(Finding(
                                    severity="P0",
                                    domain="security",
                                    title=f"Potential secret in {fname}:{i}",
                                    evidence=f"Pattern '{pat}' found: {line.strip()[:80]}",
                                    action="Rotate credential, remove from source, inject via env",
                                    auto_execute=False,
                                ))
                                break
            except Exception:
                pass
    log(f"Secret scan: {len(findings)} potential leaks found")
    return findings


# ─────────────────────────────────────────────────────────────
# LAYER 3: Drift Detection — look for stale / broken workflows
# ─────────────────────────────────────────────────────────────
def detect_drift() -> List[Finding]:
    findings = []
    # Check GitHub Actions workflows for common issues
    workflows_dir = ".github/workflows"
    if os.path.isdir(workflows_dir):
        for fname in os.listdir(workflows_dir):
            fpath = os.path.join(workflows_dir, fname)
            with open(fpath, "r", errors="ignore") as f:
                content = f.read()
            if "GITHUB_TOKEN" in content and "secrets." not in content:
                findings.append(Finding(
                    severity="P1",
                    domain="cicd",
                    title=f"Workflow {fname} may use default token insecurely",
                    evidence="GITHUB_TOKEN referenced without secrets.GITHUB_TOKEN pattern",
                    action="Audit and tighten permissions in workflow",
                    auto_execute=False,
                ))
    log(f"Drift detection: {len(findings)} issues")
    return findings


# ─────────────────────────────────────────────────────────────
# LAYER 4: Action Queue — ranked by severity
# ─────────────────────────────────────────────────────────────
def build_action_queue(findings: List[Finding]) -> dict:
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    ranked = sorted(findings, key=lambda f: order.get(f.severity, 9))
    return {
        "immediate": [asdict(f) for f in ranked if f.severity == "P0"],
        "strategic": [asdict(f) for f in ranked if f.severity in ("P1", "P2")],
        "backlog": [asdict(f) for f in ranked if f.severity == "P3"],
    }


# ─────────────────────────────────────────────────────────────
# LAYER 5: Write Audit Log
# ─────────────────────────────────────────────────────────────
def write_audit_log(run: AuditRun, queue: dict):
    os.makedirs("audit_logs", exist_ok=True)
    path = f"audit_logs/run_{run.run_id}.json"
    payload = {
        "run": asdict(run),
        "action_queue": queue,
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    log(f"Audit log written → {path}")
    return path


# ─────────────────────────────────────────────────────────────
# MAIN — runs automatically, no confirmation
# ─────────────────────────────────────────────────────────────
def main():
    log("=== APEX DAILY AUDIT START — AUTO MODE ===")
    run = AuditRun(
        run_id=RUN_ID,
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    # Layer 1
    run.connectors_validated = validate_connectors()

    # Layer 2
    secret_findings = scan_secrets(".")
    run.findings.extend(secret_findings)

    # Layer 3
    drift_findings = detect_drift()
    run.findings.extend(drift_findings)

    # Layer 4
    queue = build_action_queue(run.findings)

    # Layer 5
    run.completed_at = datetime.now(timezone.utc).isoformat()
    run.status = "completed"
    log_path = write_audit_log(run, queue)

    # Summary
    p0 = len(queue["immediate"])
    p1p2 = len(queue["strategic"])
    log(f"=== AUDIT COMPLETE: P0={p0} P1+P2={p1p2} | Log={log_path} ===")

    if p0 > 0:
        log("⚠️  P0 ISSUES REQUIRE IMMEDIATE MANUAL REMEDIATION")
        for f in queue["immediate"]:
            log(f"  → [{f['domain']}] {f['title']}")
            log(f"    ACTION: {f['action']}")

    return run


if __name__ == "__main__":
    main()
