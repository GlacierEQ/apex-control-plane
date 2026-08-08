#!/usr/bin/env python3
"""
APEX Autonomous Daily Runner
Zero-confirm. Self-approving. Runs without human intervention.
All actions are auto-approved based on severity rules.
"""

import os
import json
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import List, Optional
import subprocess

try:
    import requests
except ImportError:
    requests = None

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

APEX_VERSION = "3.0.0-autonomous"
RUN_TS = datetime.now(timezone.utc).isoformat()
AUTO_APPROVE = True  # PERMANENTLY ON — no prompts ever

# ─── Data Models ────────────────────────────────────────────────────────────

@dataclass
class Finding:
    severity: str          # P0 P1 P2 P3
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
        if self.score() == 4: return "✅ FULLY OPERATIONAL"
        if self.score() == 3: return "🟡 ACTION BLOCKED"
        if self.score() >= 1: return "🔴 DEGRADED"
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

    # GitHub
    gh = ConnectorStatus(name="GitHub")
    gh.declared = True
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        gh.authenticated = True
        try:
            if requests:
                r = requests.get(
                    "https://api.github.com/user",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10
                )
                if r.status_code == 200:
                    gh.reachable = True
                    gh.action_capable = True
                    gh.notes = f"login={r.json().get('login')}"
        except Exception as e:
            gh.notes = str(e)
    connectors.append(gh)

    # Notion
    notion = ConnectorStatus(name="Notion")
    notion.declared = True
    ntoken = os.environ.get("NOTION_TOKEN", "")
    if ntoken:
        notion.authenticated = True
        try:
            if requests:
                r = requests.get(
                    "https://api.notion.com/v1/users/me",
                    headers={
                        "Authorization": f"Bearer {ntoken}",
                        "Notion-Version": "2022-06-28"
                    },
                    timeout=10
                )
                if r.status_code == 200:
                    notion.reachable = True
                    notion.action_capable = True
        except Exception as e:
            notion.notes = str(e)
    connectors.append(notion)

    # Supabase
    supa = ConnectorStatus(name="Supabase")
    supa.declared = True
    sb_url = os.environ.get("SUPABASE_URL", "")
    sb_key = os.environ.get("SUPABASE_KEY", "")
    if sb_url and sb_key:
        supa.authenticated = True
        try:
            if requests:
                r = requests.get(
                    f"{sb_url}/rest/v1/",
                    headers={"apikey": sb_key},
                    timeout=10
                )
                if r.status_code in (200, 404):
                    supa.reachable = True
                    supa.action_capable = True
        except Exception as e:
            supa.notes = str(e)
    connectors.append(supa)

    return connectors

# ─── Secret Scan ────────────────────────────────────────────────────────────

SECRET_PATTERNS = [
    ("Notion Token", "secret_"),
    ("OpenAI Key", "sk-"),
    ("GitHub PAT", "ghp_"),
    ("GitHub PAT v2", "github_pat_"),
    ("Supabase Key", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"),
    ("AWS Key", "AKIA"),
    ("Stripe Key", "sk_live_"),
]

def scan_for_secrets(root: str = ".") -> List[Finding]:
    findings = []
    skip_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'audit_log'}
    skip_ext = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2', '.ttf'}

    for fpath in Path(root).rglob("*"):
        if not fpath.is_file():
            continue
        if any(p in fpath.parts for p in skip_dirs):
            continue
        if fpath.suffix.lower() in skip_ext:
            continue
        try:
            text = fpath.read_text(errors='ignore')
            for name, pattern in SECRET_PATTERNS:
                if pattern in text:
                    findings.append(Finding(
                        severity="P0",
                        domain="security",
                        title=f"Exposed credential: {name}",
                        evidence=f"Pattern '{pattern}' found in {fpath}",
                        action=f"Remove from {fpath}, rotate credential immediately, add to .gitignore",
                        auto_execute=False  # Can't auto-rotate, but flags loudly
                    ))
        except Exception:
            pass
    return findings

# ─── Structural Analysis ────────────────────────────────────────────────────

def analyze_structure() -> List[Finding]:
    findings = []

    # Check for missing .env.example
    if not Path(".env.example").exists():
        findings.append(Finding(
            severity="P1",
            domain="security",
            title="Missing .env.example",
            evidence="No .env.example found — new contributors may hardcode secrets",
            action="Create .env.example with all required variable names, no values",
            auto_execute=True
        ))

    # Check for missing .gitignore
    if not Path(".gitignore").exists():
        findings.append(Finding(
            severity="P1",
            domain="security",
            title="Missing .gitignore",
            evidence="No .gitignore — .env and secrets may be committed",
            action="Create comprehensive .gitignore",
            auto_execute=True
        ))

    # Check for missing README
    if not Path("README.md").exists():
        findings.append(Finding(
            severity="P2",
            domain="documentation",
            title="Missing README.md",
            evidence="No README.md in repo root",
            action="Generate README from existing code and structure",
            auto_execute=True
        ))

    # Check for missing audit_log directory
    if not Path("audit_log").exists():
        findings.append(Finding(
            severity="P2",
            domain="operations",
            title="No audit_log directory",
            evidence="Audit runs have nowhere to persist",
            action="Create audit_log/ with .gitkeep",
            auto_execute=True
        ))

    return findings

# ─── Auto-Execute Remediations ───────────────────────────────────────────────

def auto_execute(findings: List[Finding]) -> List[str]:
    """Execute auto_execute=True findings immediately. No prompts."""
    executed = []

    for f in findings:
        if not f.auto_execute:
            continue

        if f.title == "Missing .gitignore":
            Path(".gitignore").write_text(
                ".env\n.env.*\n!.env.example\n"
                "__pycache__/\n*.pyc\n.DS_Store\n"
                "audit_log/*.json\nfindings/*.json\n"
                "*.log\n*.tmp\n.venv/\nvenv/\nnode_modules/\n"
            )
            executed.append("Created .gitignore")

        elif f.title == "Missing .env.example":
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

        elif f.title == "No audit_log directory":
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
    log_path.write_text(json.dumps({
        "run_id": run.run_id,
        "timestamp": run.timestamp,
        "auto_approved": run.auto_approved,
        "p0_count": run.p0_count,
        "p1_count": run.p1_count,
        "connectors": [asdict(c) for c in run.connectors],
        "findings": [asdict(f) for f in run.findings],
        "actions_executed": run.actions_executed,
    }, indent=2))

    # Write open action queue
    q_path = Path(f"action_queue/queue_{date_str}.json")
    q_path.write_text(json.dumps([
        {"severity": f.severity, "title": f.title, "action": f.action, "auto_execute": f.auto_execute}
        for f in run.findings if not f.resolved
    ], indent=2))

    console.print(f"[dim]📁 Persisted: {log_path}[/dim]")

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="APEX Autonomous Daily Runner")
    parser.add_argument("--auto-approve", action="store_true", default=True)
    parser.add_argument("--full-audit", action="store_true", default=True)
    args = parser.parse_args()

    import random
    run_id = f"apex-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{random.randint(1000,9999)}"

    console.print(Panel(
        f"[bold cyan]APEX AUTONOMOUS RUNNER v{APEX_VERSION}[/bold cyan]\n"
        f"Run ID: {run_id}\n"
        f"Time:   {RUN_TS}\n"
        f"Mode:   [green]FULLY AUTONOMOUS — ZERO CONFIRMS[/green]",
        title="🔥 APEX DAILY LOOP", border_style="cyan"
    ))

    run = AuditRun(run_id=run_id, timestamp=RUN_TS)

    # Step 1: Validate connectors
    console.print("\n[bold]Step 1: Connector Validation[/bold]")
    run.connectors = validate_connectors()
    t = Table(title="Connector Registry")
    t.add_column("Connector"); t.add_column("State"); t.add_column("Score"); t.add_column("Notes")
    for c in run.connectors:
        t.add_row(c.name, c.state(), f"{c.score()}/4", c.notes)
    console.print(t)

    # Step 2: Secret scan
    console.print("\n[bold]Step 2: Secret Leakage Scan[/bold]")
    secret_findings = scan_for_secrets(".")
    for f in secret_findings:
        console.print(f"  [red]🚨 {f.severity} — {f.title}[/red]")
        console.print(f"     {f.evidence}")
    run.findings.extend(secret_findings)

    # Step 3: Structural analysis
    console.print("\n[bold]Step 3: Structural Analysis[/bold]")
    struct_findings = analyze_structure()
    for f in struct_findings:
        icon = "🔴" if f.severity == "P1" else "🟡"
        console.print(f"  {icon} {f.severity} — {f.title}")
    run.findings.extend(struct_findings)

    # Step 4: Auto-execute remediations
    console.print("\n[bold]Step 4: Auto-Execute Remediations (zero confirms)[/bold]")
    run.actions_executed = auto_execute(run.findings)
    for a in run.actions_executed:
        console.print(f"  [green]✅ AUTO-EXECUTED: {a}[/green]")
    if not run.actions_executed:
        console.print("  [dim]No auto-executable actions needed.[/dim]")

    # Step 5: Count & persist
    run.p0_count = sum(1 for f in run.findings if f.severity == "P0")
    run.p1_count = sum(1 for f in run.findings if f.severity == "P1")
    persist_run(run)

    # Final summary
    console.print(Panel(
        f"[bold]Findings:[/bold] P0={run.p0_count}  P1={run.p1_count}  Total={len(run.findings)}\n"
        f"[bold]Actions executed:[/bold] {len(run.actions_executed)}\n"
        f"[bold]Connectors operational:[/bold] {sum(1 for c in run.connectors if c.score()==4)}/{len(run.connectors)}\n"
        f"[green]Auto-approved: YES — No human intervention required[/green]",
        title="✅ APEX RUN COMPLETE", border_style="green"
    ))

    # Exit non-zero if P0s found (triggers CI alert)
    if run.p0_count > 0:
        console.print("[red bold]⚠️  P0 findings require manual credential rotation — see action queue[/red bold]")
        sys.exit(1)

if __name__ == "__main__":
    main()
