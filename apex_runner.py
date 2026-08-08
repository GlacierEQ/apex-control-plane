"""
APEX Autonomous Daily Runner
Zero-confirm. Self-approving. Runs without human intervention.
All actions are auto-approved based on severity rules.
"""

import argparse
import json
import os
import random
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

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
AUTO_APPROVE = True  # PERMANENTLY ON — no prompts ever


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
    findings: list[Finding] = field(default_factory=list)
    connectors: list[ConnectorStatus] = field(default_factory=list)
    actions_executed: list[str] = field(default_factory=list)
    p0_count: int = 0
    p1_count: int = 0
    auto_approved: bool = True


def validate_connectors() -> list[ConnectorStatus]:
    connectors = []

    github = ConnectorStatus(name="GitHub", declared=True)
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        github.authenticated = True
        if requests:
            try:
                response = requests.get(
                    "https://api.github.com/user",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10,
                )
                if response.status_code == 200:
                    github.reachable = True
                    github.action_capable = True
                    github.notes = f"login={response.json().get('login')}"
            except requests.RequestException as error:
                github.notes = str(error)
    connectors.append(github)

    notion = ConnectorStatus(name="Notion", declared=True)
    notion_token = os.environ.get("NOTION_TOKEN", "")
    if notion_token:
        notion.authenticated = True
        if requests:
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
                    notion.reachable = True
                    notion.action_capable = True
            except requests.RequestException as error:
                notion.notes = str(error)
    connectors.append(notion)

    supabase = ConnectorStatus(name="Supabase", declared=True)
    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_KEY", "")
    if supabase_url and supabase_key:
        supabase.authenticated = True
        if requests:
            try:
                response = requests.get(
                    f"{supabase_url}/rest/v1/",
                    headers={"apikey": supabase_key},
                    timeout=10,
                )
                if response.status_code in (200, 404):
                    supabase.reachable = True
                    supabase.action_capable = True
            except requests.RequestException as error:
                supabase.notes = str(error)
    connectors.append(supabase)

    return connectors


SECRET_PATTERNS = [
    ("Notion Token", "secret_"),
    ("OpenAI Key", "sk-"),
    ("GitHub PAT", "ghp_"),
    ("GitHub PAT v2", "github_pat_"),
    ("Supabase Key", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"),
    ("AWS Key", "AKIA"),
    ("Stripe Key", "sk_live_"),
]


def scan_for_secrets(root: str = ".") -> list[Finding]:
    findings = []
    skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", "audit_log"}
    skip_ext = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2", ".ttf"}

    for file_path in Path(root).rglob("*"):
        if not file_path.is_file():
            continue
        if any(part in file_path.parts for part in skip_dirs):
            continue
        if file_path.suffix.lower() in skip_ext:
            continue
        try:
            text = file_path.read_text(errors="ignore")
        except OSError:
            continue
        for name, pattern in SECRET_PATTERNS:
            if pattern in text:
                findings.append(
                    Finding(
                        severity="P0",
                        domain="security",
                        title=f"Exposed credential: {name}",
                        evidence=f"Pattern '{pattern}' found in {file_path}",
                        action=(
                            f"Remove from {file_path}, rotate credential immediately, "
                            "add to .gitignore"
                        ),
                        auto_execute=False,
                    )
                )
    return findings


def analyze_structure() -> list[Finding]:
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


def auto_execute(findings: list[Finding]) -> list[str]:
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
                "*.log\n*.tmp\n.venv/\nvenv/\nnode_modules/\n"
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
                "OPENAI_API_KEY=\n"
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
        )
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
        )
    )

    console.print(f"[dim]📁 Persisted: {log_path}[/dim]")


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
        table.add_row(connector.name, connector.state(), f"{connector.score()}/4", connector.notes)
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
            f"[bold]Findings:[/bold] P0={run.p0_count}  P1={run.p1_count}  "
            f"Total={len(run.findings)}\n"
            f"[bold]Actions executed:[/bold] {len(run.actions_executed)}\n"
            f"[bold]Connectors operational:[/bold] "
            f"{sum(1 for connector in run.connectors if connector.score() == 4)}/"
            f"{len(run.connectors)}\n"
            "[green]Auto-approved: YES — No human intervention required[/green]",
            title="✅ APEX RUN COMPLETE",
            border_style="green",
        )
    )

    if run.p0_count > 0:
        console.print(
            "[red bold]⚠️  P0 findings require manual credential rotation — see action queue[/red bold]"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
