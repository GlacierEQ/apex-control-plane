#!/usr/bin/env python3
"""
APEX Autonomous Daily Runner
Zero-confirm. Self-approving. Runs without human intervention.
All actions are auto-approved based on severity rules.
"""

import argparse
import json
import os
import random
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List

try:
    import requests
except ImportError:
    requests = None

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

APEX_VERSION = "3.0.0-autonomous"
RUN_TS = datetime.now(timezone.utc).isoformat()


@dataclass
class Finding:
    severity: str
    domain: str
    title: str
    evidence: str
    action: str
    auto_execute: bool = True
    status: str = "open"
    resolved: bool = False


@dataclass
class ConnectorStatus:
    name: str
    declared: bool = False
    authenticated: bool = False
    reachable: bool = False
    action_capable: bool = False
    notes: str = ""

    def score(self) -> int:
        return sum([self.declared, self.authenticated, self.reachable, self.action_capable])

    def state(self) -> str:
        if self.score() == 4:
            return "✅ FULLY OPERATIONAL"
        if self.score() == 3:
            return "🟡 ACTION BLOCKED"
        if self.score() >= 1:
            return "🔴 DEGRADED"
        return "⚫ OFFLINE"


@dataclass
class AuditRun:
    run_id: str
    timestamp: str
    findings: List[Finding] = field(default_factory=list)
    connectors: List[ConnectorStatus] = field(default_factory=list)
    actions_executed: List[str] = field(default_factory=list)
    p0_count: int = 0
    p1_count: int = 0
    auto_approved: bool = True


# ─── Connector Validation ────────────────────────────────────────────────────
def validate_connectors() -> List[ConnectorStatus]:
    connectors = []

    github = ConnectorStatus(name="GitHub", declared=True)
    github_token = os.environ.get("GITHUB_TOKEN", "")
    if github_token and requests:
        try:
            response = requests.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {github_token}"},
                timeout=10,
            )
            if response.status_code == 200:
                github.authenticated = True
                github.reachable = True
                github.action_capable = True
                github.notes = f"login={response.json().get('login')}"
            else:
                github.notes = f"http_status={response.status_code}"
        except requests.RequestException as error:
            github.notes = str(error)
    elif github_token:
        github.notes = "requests dependency unavailable"
    else:
        github.notes = "GITHUB_TOKEN missing"
    connectors.append(github)

    notion = ConnectorStatus(name="Notion", declared=True)
    notion_token = os.environ.get("NOTION_TOKEN", "")
    if notion_token and requests:
        try:
            response = requests.get(
                "https://api.notion.com/v1/users/me",
                headers={
                    "Authorization": f"Bearer {notion_token}",
                    "Notion-Version": "2022-06-28",
                },
                timeout=10,
            )
            if response.status_code == 200:
                notion.authenticated = True
                notion.reachable = True
                notion.action_capable = True
            else:
                notion.notes = f"http_status={response.status_code}"
        except requests.RequestException as error:
            notion.notes = str(error)
    elif notion_token:
        notion.notes = "requests dependency unavailable"
    else:
        notion.notes = "NOTION_TOKEN missing"
    connectors.append(notion)

    supabase = ConnectorStatus(name="Supabase", declared=True)
    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_KEY", "")
    if supabase_url and supabase_key and requests:
        try:
            response = requests.get(
                f"{supabase_url.rstrip('/')}/rest/v1/",
                headers={"apikey": supabase_key},
                timeout=10,
            )
            if response.status_code in (200, 404):
                supabase.authenticated = True
                supabase.reachable = True
                supabase.action_capable = True
            else:
                supabase.notes = f"http_status={response.status_code}"
        except requests.RequestException as error:
            supabase.notes = str(error)
    elif supabase_url and supabase_key:
        supabase.notes = "requests dependency unavailable"
    else:
        supabase.notes = "SUPABASE_URL or SUPABASE_KEY missing"
    connectors.append(supabase)

    return connectors


# ─── Secret Scan ─────────────────────────────────────────────────────────────
CREDENTIAL_PATTERNS = (
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{40,})\b")),
    ("OpenAI-style API key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("Notion token", re.compile(r"\bntn_[A-Za-z0-9]{20,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Stripe live key", re.compile(r"\bsk_live_[A-Za-z0-9]{16,}\b")),
    (
        "JWT credential",
        re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b"),
    ),
    (
        "private key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
    (
        "password assignment",
        re.compile(
            r"\bpassword\s*=\s*(?:[\"'][^\"'\n]{8,}[\"']|[^\s#\"']{8,})",
            re.IGNORECASE,
        ),
    ),
)

SECRET_SCAN_EXCLUDED_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "audit_log",
    "audit_logs",
    "action_queue",
    "findings",
}
SECRET_SCAN_BINARY_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".zip",
    ".pdf",
}


def scan_for_secrets(root: str = ".") -> List[Finding]:
    findings = []
    for file_path in Path(root).rglob("*"):
        if not file_path.is_file():
            continue
        if any(part in SECRET_SCAN_EXCLUDED_DIRS for part in file_path.parts):
            continue
        if file_path.suffix.lower() in SECRET_SCAN_BINARY_SUFFIXES:
            continue
        try:
            text = file_path.read_text(errors="ignore", encoding="utf-8")
        except OSError:
            continue
        for label, pattern in CREDENTIAL_PATTERNS:
            if pattern.search(text):
                findings.append(
                    Finding(
                        severity="P0",
                        domain="security",
                        title=f"Credential-shaped value: {label}",
                        evidence=f"{label} pattern matched in {file_path}; value redacted from audit output",
                        action=f"Remove the credential from {file_path}, rotate it if live, and inject it through the approved secret path",
                        auto_execute=False,
                    )
                )
    return findings


# ─── Structural Analysis ─────────────────────────────────────────────────────
def analyze_structure() -> List[Finding]:
    findings = []

    if not Path(".env.example").exists():
        findings.append(
            Finding(
                severity="P1",
                domain="security",
                title="Missing .env.example",
                evidence="No .env.example found — new contributors may hardcode secrets",
                action="Create .env.example with all required variable names, no values",
                auto_execute=True,
            )
        )

    if not Path(".gitignore").exists():
        findings.append(
            Finding(
                severity="P1",
                domain="security",
                title="Missing .gitignore",
                evidence="No .gitignore — .env and secrets may be committed",
                action="Create comprehensive .gitignore",
                auto_execute=True,
            )
        )

    if not Path("README.md").exists():
        findings.append(
            Finding(
                severity="P2",
                domain="documentation",
                title="Missing README.md",
                evidence="No README.md in repo root",
                action="Generate README from existing code and structure",
                auto_execute=True,
            )
        )

    if not Path("audit_log").exists():
        findings.append(
            Finding(
                severity="P2",
                domain="operations",
                title="No audit_log directory",
                evidence="Audit runs have nowhere to persist",
                action="Create audit_log/ with .gitkeep",
                auto_execute=True,
            )
        )

    return findings


# ─── Auto-Execute Remediations ───────────────────────────────────────────────
def auto_execute(findings: List[Finding]) -> List[str]:
    """Execute auto_execute=True findings immediately. No prompts."""
    executed = []

    for finding in findings:
        if not finding.auto_execute:
            continue

        if finding.title == "Missing .gitignore":
            Path(".gitignore").write_text(
                ".env\n.env.*\n!.env.example\n"
                "__pycache__/\n*.pyc\n.DS_Store\n"
                "audit_log/*.json\nfindings/*.json\n"
                "*.log\n*.tmp\n.venv/\nvenv/\nnode_modules/\n",
                encoding="utf-8",
            )
            executed.append("Created .gitignore")

        elif finding.title == "Missing .env.example":
            Path(".env.example").write_text(
                "# APEX Control Plane — Required Secrets\n"
                "# Copy to .env and populate. NEVER commit .env\n\n"
                "GITHUB_TOKEN=\n"
                "NOTION_TOKEN=\n"
                "SUPABASE_URL=\n"
                "SUPABASE_KEY=\n"
                "OPENAI_API_KEY=\n",
                encoding="utf-8",
            )
            executed.append("Created .env.example")

        elif finding.title == "No audit_log directory":
            Path("audit_log").mkdir(exist_ok=True)
            Path("audit_log/.gitkeep").touch()
            Path("findings").mkdir(exist_ok=True)
            Path("findings/.gitkeep").touch()
            Path("action_queue").mkdir(exist_ok=True)
            Path("action_queue/.gitkeep").touch()
            executed.append("Created audit_log/, findings/, action_queue/")

    return executed


# ─── Report & Persist ────────────────────────────────────────────────────────
def persist_run(run: AuditRun):
    Path("audit_log").mkdir(exist_ok=True)
    Path("findings").mkdir(exist_ok=True)
    Path("action_queue").mkdir(exist_ok=True)

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_path = Path(f"audit_log/run_{date_str}.json")
    log_path.write_text(
        json.dumps(
            {
                "run_id": run.run_id,
                "timestamp": run.timestamp,
                "auto_approved": run.auto_approved,
                "p0_count": run.p0_count,
                "p1_count": run.p1_count,
                "connectors": [asdict(connector) for connector in run.connectors],
                "findings": [asdict(finding) for finding in run.findings],
                "actions_executed": run.actions_executed,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    queue_path = Path(f"action_queue/queue_{date_str}.json")
    queue_path.write_text(
        json.dumps(
            [
                {
                    "severity": finding.severity,
                    "title": finding.title,
                    "action": finding.action,
                    "auto_execute": finding.auto_execute,
                }
                for finding in run.findings
                if not finding.resolved
            ],
            indent=2,
        ),
        encoding="utf-8",
    )

    console.print(f"[dim]📁 Persisted: {log_path}[/dim]")


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="APEX Autonomous Daily Runner")
    parser.add_argument("--auto-approve", action="store_true", default=True)
    parser.add_argument("--full-audit", action="store_true", default=True)
    parser.parse_args()

    run_id = f"apex-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{random.randint(1000, 9999)}"

    console.print(
        Panel(
            f"[bold cyan]APEX AUTONOMOUS RUNNER v{APEX_VERSION}[/bold cyan]\n"
            f"Run ID: {run_id}\n"
            f"Time:   {RUN_TS}\n"
            f"Mode:   [green]FULLY AUTONOMOUS — ZERO CONFIRMS[/green]",
            title="🔥 APEX DAILY LOOP",
            border_style="cyan",
        )
    )

    run = AuditRun(run_id=run_id, timestamp=RUN_TS)

    console.print("\n[bold]Step 1: Connector Validation[/bold]")
    run.connectors = validate_connectors()
    table = Table(title="Connector Registry")
    table.add_column("Connector")
    table.add_column("State")
    table.add_column("Score")
    table.add_column("Notes")
    for connector in run.connectors:
        table.add_row(
            connector.name,
            connector.state(),
            f"{connector.score()}/4",
            connector.notes,
        )
    console.print(table)

    console.print("\n[bold]Step 2: Secret Leakage Scan[/bold]")
    secret_findings = scan_for_secrets(".")
    for finding in secret_findings:
        console.print(f"  [red]🚨 {finding.severity} — {finding.title}[/red]")
        console.print(f"     {finding.evidence}")
    run.findings.extend(secret_findings)

    console.print("\n[bold]Step 3: Structural Analysis[/bold]")
    structural_findings = analyze_structure()
    for finding in structural_findings:
        icon = "🔴" if finding.severity == "P1" else "🟡"
        console.print(f"  {icon} {finding.severity} — {finding.title}")
    run.findings.extend(structural_findings)

    console.print("\n[bold]Step 4: Auto-Execute Remediations (zero confirms)[/bold]")
    run.actions_executed = auto_execute(run.findings)
    for action in run.actions_executed:
        console.print(f"  [green]✅ AUTO-EXECUTED: {action}[/green]")
    if not run.actions_executed:
        console.print("  [dim]No auto-executable actions needed.[/dim]")

    run.p0_count = sum(1 for finding in run.findings if finding.severity == "P0")
    run.p1_count = sum(1 for finding in run.findings if finding.severity == "P1")
    persist_run(run)

    console.print(
        Panel(
            f"[bold]Findings:[/bold] P0={run.p0_count}  P1={run.p1_count}  Total={len(run.findings)}\n"
            f"[bold]Actions executed:[/bold] {len(run.actions_executed)}\n"
            f"[bold]Connectors operational:[/bold] {sum(1 for connector in run.connectors if connector.score() == 4)}/{len(run.connectors)}\n"
            "[green]Auto-approved: YES — No human intervention required[/green]",
            title="✅ APEX RUN COMPLETE",
            border_style="green",
        )
    )

    if run.p0_count > 0:
        console.print(
            "[red bold]⚠️  P0 findings require manual credential rotation — see action queue[/red bold]"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
