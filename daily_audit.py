"""
APEX Daily Audit Loop — Zero-Confirmation Autonomous Execution
Runs every day via GitHub Actions. No human approval required.
Owner: GlacierEQ / Casey Barton
"""

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from connectors.github_validator import validate as validate_github
from connectors.notion_validator import validate as validate_notion

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
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class AuditRun:
    run_id: str
    started_at: str
    completed_at: str | None = None
    findings: list[Finding] = field(default_factory=list)
    actions_executed: list[str] = field(default_factory=list)
    connectors_validated: dict = field(default_factory=dict)
    status: str = "running"


def log(msg: str) -> None:
    print(f"[APEX {RUN_ID}] {msg}")


def _connector_status(result: dict) -> dict:
    """Report health without converting a probe into external-action authority."""
    state = str(result.get("state") or "unknown")
    reachable = state == "action_capable"
    return {
        "declared": True,
        "authenticated": reachable,
        "reachable": reachable,
        "receipt_verified": False,
        "action_authorized": False,
        "action_capable": False,
        "status": "AMBER" if reachable else "RED",
        "state": state,
        "detail": result,
    }


def validate_connectors() -> dict:
    results = {
        "github": _connector_status(validate_github()),
        "notion": _connector_status(validate_notion()),
    }
    for name, result in results.items():
        log(f"Connector [{name}]: {result['status']} — {result['state']}")
    return results


CREDENTIAL_PATTERNS = (
    (
        "GitHub token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    ),
    ("OpenAI-style API key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("xAI API key", re.compile(r"\bxai-[A-Za-z0-9_-]{20,}\b")),
    ("Notion token", re.compile(r"\bntn_[A-Za-z0-9]{20,}\b")),
    ("Legacy Notion token", re.compile(r"\bsecret_[A-Za-z0-9]{20,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Stripe live key", re.compile(r"\bsk_live_[A-Za-z0-9]{16,}\b")),
    (
        "JWT credential",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b"
        ),
    ),
    (
        "private key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
    (
        "password assignment",
        re.compile(
            r"(?:^|[\s{,\"'])(?:[A-Za-z0-9_]*PASSWORD[A-Za-z0-9_]*|password|\"password\"|'password')"
            r"\s*(?:=|:)\s*(?:[\"'][^\"'\n]{8,}[\"']|[^\s,#}\]\"']{8,})",
            re.IGNORECASE,
        ),
    ),
)

EXCLUDE_DIRS = {
    "__pycache__",
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "audit_logs",
    "audit_log",
    "action_queue",
    "findings",
}
SCAN_SUFFIXES = {
    ".py",
    ".ts",
    ".js",
    ".go",
    ".env",
    ".yaml",
    ".yml",
    ".json",
    ".md",
    ".toml",
    ".sh",
    ".pem",
    ".key",
    ".ini",
    ".conf",
}
TOKEN_ASSIGNMENT = re.compile(r"(?m)^\s*GITHUB_TOKEN\s*:\s*(?P<value>.+?)\s*$")


def _should_scan_secret_file(filename: str) -> bool:
    normalized = filename.casefold()
    if normalized == ".env" or normalized.startswith(".env."):
        return True
    return Path(normalized).suffix in SCAN_SUFFIXES


def scan_secrets(root: str = ".") -> list[Finding]:
    findings: list[Finding] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            directory for directory in dirnames if directory not in EXCLUDE_DIRS
        ]
        for filename in filenames:
            if not _should_scan_secret_file(filename):
                continue
            file_path = os.path.join(dirpath, filename)
            try:
                with open(file_path, errors="ignore", encoding="utf-8") as handle:
                    for line_number, line in enumerate(handle, 1):
                        for label, pattern in CREDENTIAL_PATTERNS:
                            if pattern.search(line):
                                findings.append(
                                    Finding(
                                        severity="P0",
                                        domain="security",
                                        title=(
                                            f"Credential-shaped value in {file_path}:"
                                            f"{line_number}"
                                        ),
                                        evidence=(
                                            f"{label} pattern matched; value redacted "
                                            "from audit output"
                                        ),
                                        action=(
                                            "Rotate the credential if live, remove it from "
                                            "source, and inject it through the approved secret path"
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
    findings: list[Finding] = []
    workflows_dir = ".github/workflows"
    accepted_token_sources = ("secrets.", "github.token", "env.GITHUB_TOKEN")
    if os.path.isdir(workflows_dir):
        for filename in os.listdir(workflows_dir):
            file_path = os.path.join(workflows_dir, filename)
            try:
                with open(file_path, errors="ignore", encoding="utf-8") as handle:
                    content = handle.read()
            except OSError:
                continue
            for match in TOKEN_ASSIGNMENT.finditer(content):
                value = match.group("value")
                if any(source in value for source in accepted_token_sources):
                    continue
                line_number = content.count("\n", 0, match.start()) + 1
                findings.append(
                    Finding(
                        severity="P1",
                        domain="cicd",
                        title=f"Workflow {filename}:{line_number} has an unsafe token source",
                        evidence=(
                            "GITHUB_TOKEN assignment lacks an approved explicit token source"
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
        "immediate": [
            asdict(finding) for finding in ranked if finding.severity == "P0"
        ],
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

    p0 = len(queue["immediate"])
    p1p2 = len(queue["strategic"])
    log(f"=== AUDIT COMPLETE: P0={p0} P1+P2={p1p2} | Log={log_path} ===")

    if p0 > 0:
        log("⚠️  P0 ISSUES REQUIRE IMMEDIATE MANUAL REMEDIATION")
        for finding in queue["immediate"]:
            log(f"  → [{finding['domain']}] {finding['title']}")
            log(f"    ACTION: {finding['action']}")

    return run
