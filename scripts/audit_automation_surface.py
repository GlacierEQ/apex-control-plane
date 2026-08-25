#!/usr/bin/env python3
"""Audit active GitHub Actions for automation patterns that can rewrite source state.

This is intentionally conservative about scheduled automation. It does not block
manual, explicitly triggered write workflows merely because they can write; it
blocks unattended source mutation patterns and destructive Git operations.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = ROOT / ".github" / "workflows"

SCHEDULE_RE = re.compile(r"(?m)^\s{2}schedule:\s*$")
PUSH_RE = re.compile(r"(?m)^\s{2}push:\s*(?:$|\{)")
WORKFLOW_DISPATCH_RE = re.compile(r"(?m)^\s{2}workflow_dispatch:\s*(?:$|\{)")
CONTENTS_WRITE_RE = re.compile(r"(?m)^\s{2,}contents:\s*write\s*$")
PERSIST_CREDENTIALS_RE = re.compile(r"(?m)^\s+persist-credentials:\s*true\s*$")
STATIC_SECRET_RE = re.compile(r"\$\{\{\s*secrets\.[A-Za-z_][A-Za-z0-9_]*\s*\}\}")
GIT_PUSH_RE = re.compile(r"\bgit\s+push\b")

DESTRUCTIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("force_push", re.compile(r"\bgit\s+push\b[^\n]*(?:--force(?:-with-lease)?|-f(?:\s|$))")),
    ("hard_reset", re.compile(r"\bgit\s+reset\s+--hard\b")),
    ("aggressive_clean", re.compile(r"\bgit\s+clean\s+-[^\n]*f[^\n]*d")),
    ("forced_branch_delete", re.compile(r"\bgit\s+branch\s+-D\b")),
    ("working_tree_discard", re.compile(r"\bgit\s+(?:checkout\s+--\s+\.|restore\s+\.)(?:\s|$)")),
    ("repository_delete", re.compile(r"\bgh\s+repo\s+delete\b")),
)


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    workflow: str
    detail: str


def _workflow_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        path
        for path in root.iterdir()
        if path.is_file() and path.suffix.casefold() in {".yml", ".yaml"}
    )


def audit_workflow(path: Path) -> list[Finding]:
    text = path.read_text(encoding="utf-8", errors="replace")
    name = path.name
    scheduled = bool(SCHEDULE_RE.search(text))
    push_triggered = bool(PUSH_RE.search(text))
    manual = bool(WORKFLOW_DISPATCH_RE.search(text))
    contents_write = bool(CONTENTS_WRITE_RE.search(text))
    persists_credentials = bool(PERSIST_CREDENTIALS_RE.search(text))
    static_secrets = sorted(set(STATIC_SECRET_RE.findall(text)))
    git_push = bool(GIT_PUSH_RE.search(text))

    findings: list[Finding] = []

    if scheduled and contents_write:
        findings.append(
            Finding(
                "ERROR",
                "SCHEDULED_CONTENTS_WRITE",
                name,
                "scheduled workflow has repository contents: write permission",
            )
        )
    if scheduled and persists_credentials:
        findings.append(
            Finding(
                "ERROR",
                "SCHEDULED_PERSISTED_GIT_CREDENTIALS",
                name,
                "scheduled workflow persists checkout credentials",
            )
        )
    if scheduled and static_secrets:
        findings.append(
            Finding(
                "ERROR",
                "SCHEDULED_STATIC_REPOSITORY_SECRET",
                name,
                "scheduled workflow injects repository secrets instead of short-lived/runtime-scoped identity",
            )
        )
    if scheduled and git_push:
        findings.append(
            Finding(
                "ERROR",
                "SCHEDULED_GIT_PUSH",
                name,
                "scheduled workflow executes git push",
            )
        )
    if push_triggered and contents_write and git_push:
        findings.append(
            Finding(
                "ERROR",
                "PUSH_TRIGGERED_SELF_WRITE",
                name,
                "push-triggered workflow can push repository contents back to the repository",
            )
        )

    for code, pattern in DESTRUCTIVE_PATTERNS:
        if pattern.search(text):
            findings.append(
                Finding(
                    "ERROR",
                    f"DESTRUCTIVE_GIT_{code.upper()}",
                    name,
                    "active workflow contains a destructive repository-history/worktree command",
                )
            )

    if contents_write and not manual and not scheduled and not push_triggered:
        findings.append(
            Finding(
                "WARN",
                "WRITE_PERMISSION_WITHOUT_EXPLICIT_MANUAL_TRIGGER",
                name,
                "workflow can write repository contents without workflow_dispatch; inspect event scope",
            )
        )

    return findings


def audit(root: Path = WORKFLOW_ROOT) -> dict[str, object]:
    workflows = _workflow_files(root)
    findings = [finding for path in workflows for finding in audit_workflow(path)]
    errors = [finding for finding in findings if finding.severity == "ERROR"]
    warnings = [finding for finding in findings if finding.severity == "WARN"]
    return {
        "schema": "glaciereq.apex.automation-safety.v1",
        "status": "PASS" if not errors else "FAIL",
        "workflow_count": len(workflows),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "findings": [asdict(finding) for finding in findings],
        "policy": {
            "scheduled_repository_mutation": "forbidden",
            "scheduled_static_repository_secrets": "forbidden",
            "destructive_git_operations_in_active_workflows": "forbidden",
            "manual_explicit_write_workflows": "permitted_subject_to_local_contract",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow-root", type=Path, default=WORKFLOW_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = audit(args.workflow_root)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
