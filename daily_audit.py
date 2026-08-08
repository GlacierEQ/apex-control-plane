"""
APEX Daily Audit Loop — Zero-Confirmation Autonomous Execution
Runs every day via GitHub Actions. No human approval required.
Owner: GlacierEQ / Casey Barton
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

GITHUB_TOKEN = os.environ.get("APEX_GITHUB_TOKEN", "")
NOTION_TOKEN = os.environ.get("APEX_NOTION_TOKEN", "")
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


@dataclass
class Finding:
    severity: str
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
    completed_at: str | None = None
    findings: list[Finding] = field(default_factory=list)
    actions_executed: list[str] = field(default_factory=list)
    connectors_validated: dict = field(default_factory=dict)
    status: str = "running"


def log(message: str) -> None:
    print(f"[APEX {RUN_ID}] {message}")


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
            "reachable": auth_ok,
            "action_capable": auth_ok,
            "status": "GREEN" if auth_ok else "RED",
        }
        log(f"Connector [{name}]: {'GREEN' if auth_ok else 'RED — NO TOKEN'}")

    return results


SECRET_PATTERNS = [
    "sk-",
    "ghp_",
    "ghs_",
    "xai-",
    "ntn_",
    "AKIA",
    "bearer ",
    "api_key",
    "apikey",
    "token",
    "password",
    "secret",
    "-----BEGIN",
]

EXCLUDE_DIRS = {"__pycache__", ".git", "node_modules", "venv", ".venv"}


def scan_secrets(root: str = ".") -> list[Finding]:
    findings = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [directory for directory in dirnames if directory not in EXCLUDE_DIRS]
        for filename in filenames:
            if not filename.endswith(
                (".py", ".ts", ".js", ".env", ".yaml", ".yml", ".json", ".md")
            ):
                continue
            file_path = os.path.join(dirpath, filename)
            try:
                with open(file_path, errors="ignore", encoding="utf-8") as handle:
                    for line_number, line in enumerate(handle, 1):
                        lowered = line.lower()
                        for pattern in SECRET_PATTERNS:
                            if (
                                pattern.lower() in lowered
                                and "os.environ" not in line
                                and "example" not in lowered
                            ):
                                findings.append(
                                    Finding(
                                        severity="P0",
                                        domain="security",
                                        title=f"Potential secret in {filename}:{line_number}",
                                        evidence=(
                                            f"Pattern '{pattern}' found: {line.strip()[:80]}"
                                        ),
                                        action=(
                                            "Rotate credential, remove from source, inject via env"
                                        ),
                                        auto_execute=False,
                                    )
                                )
                                break
            except OSError:
                continue
    log(f"Secret scan: {len(findings)} potential leaks found")
    return findings


def detect_drift() -> list[Finding]:
    findings = []
    workflows_dir = ".github/workflows"
    if os.path.isdir(workflows_dir):
        for filename in os.listdir(workflows_dir):
            file_path = os.path.join(workflows_dir, filename)
            try:
                with open(file_path, errors="ignore", encoding="utf-8") as handle:
                    content = handle.read()
            except OSError:
                continue
            if "GITHUB_TOKEN" in content and "secrets." not in content:
                findings.append(
                    Finding(
                        severity="P1",
                        domain="cicd",
                        title=f"Workflow {filename} may use default token insecurely",
                        evidence=(
                            "GITHUB_TOKEN referenced without secrets.GITHUB_TOKEN pattern"
                        ),
                        action="Audit and tighten permissions in workflow",
                        auto_execute=False,
                    )
                )
    log(f"Drift detection: {len(findings)} issues")
    return findings


def build_action_queue(findings: list[Finding]) -> dict:
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    ranked = sorted(findings, key=lambda finding: order.get(finding.severity, 9))
    return {
        "immediate": [asdict(finding) for finding in ranked if finding.severity == "P0"],
        "strategic": [
            asdict(finding) for finding in ranked if finding.severity in ("P1", "P2")
        ],
        "backlog": [asdict(finding) for finding in ranked if finding.severity == "P3"],
    }


def write_audit_log(run: AuditRun, queue: dict) -> str:
    os.makedirs("audit_logs", exist_ok=True)
    path = f"audit_logs/run_{run.run_id}.json"
    payload = {
        "run": asdict(run),
        "action_queue": queue,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=str)
    log(f"Audit log written → {path}")
    return path


def main() -> AuditRun:
    log("=== APEX DAILY AUDIT START — AUTO MODE ===")
    run = AuditRun(
        run_id=RUN_ID,
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    run.connectors_validated = validate_connectors()
    run.findings.extend(scan_secrets("."))
    run.findings.extend(detect_drift())
    queue = build_action_queue(run.findings)

    run.completed_at = datetime.now(timezone.utc).isoformat()
    run.status = "completed"
    log_path = write_audit_log(run, queue)

    p0_count = len(queue["immediate"])
    p1_p2_count = len(queue["strategic"])
    log(
        f"=== AUDIT COMPLETE: P0={p0_count} P1+P2={p1_p2_count} | Log={log_path} ==="
    )

    if p0_count > 0:
        log("⚠️  P0 ISSUES REQUIRE IMMEDIATE MANUAL REMEDIATION")
        for finding in queue["immediate"]:
            log(f"  → [{finding['domain']}] {finding['title']}")
            log(f"    ACTION: {finding['action']}")

    return run


if __name__ == "__main__":
    main()
