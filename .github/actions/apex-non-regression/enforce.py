#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

FATAL_PATTERNS = (
    (
        "HARD_EXECUTION_DISABLE",
        re.compile(
            r"(execution_rejected\s*=\s*true|REJECTED_NOT_RUNTIME|"
            r"runtime_orchestration_available[\"']?\s*[:=]\s*(?:false|False)|"
            r"not a runtime orchestrator|executes no subsystem|"
            r"performs no network or external action)",
            re.IGNORECASE,
        ),
    ),
)
RESTRICTION_RE = re.compile(
    r"(read[-_ ]only|non[-_ ]execution|not a runtime|metadata (?:only|router)|"
    r"compatibility facade|proposal engine|receipt router|historical_non_authoritative)",
    re.IGNORECASE,
)
EXECUTION_RE = re.compile(
    r"\b(async\s+def\s+(?:run|tick|execute|dispatch|submit|assign)|"
    r"def\s+(?:run|tick|execute|dispatch|submit|assign)|await\s+|\.execute\(|\.run\(|"
    r"dynamic import|importlib|subprocess|httpx|requests\.|urllib|socket|webhook)\b",
    re.IGNORECASE,
)
MINIMIZE_RE = re.compile(
    r"(smallest (?:possible|useful|change|slice)|minimum viable|bounded slice|safe(?:st)? slice)",
    re.IGNORECASE,
)
STATE_DEMOTION_RE = re.compile(
    r"(?:\"state\"|principal_state|status)\s*[:=]\s*[\"']?(?:TESTED|PENDING|READ_ONLY|REJECTED)",
    re.IGNORECASE,
)


def output(*args: str) -> str:
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT)


def ensure_ref(ref: str) -> None:
    try:
        subprocess.check_call(
            ["git", "cat-file", "-e", f"{ref}^{{commit}}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        subprocess.check_call(
            ["git", "fetch", "--no-tags", "origin", ref],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def diff_hash(diff: str) -> str:
    return hashlib.sha256(diff.encode("utf-8")).hexdigest()


def load_authorization(path: Path, expected: str) -> bool:
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return bool(
        data.get("schema") == "apex.operator-reduction-authorization.v1"
        and data.get("operator_authorized") is True
        and data.get("diff_sha256") == expected
        and isinstance(data.get("reason"), str)
        and data["reason"].strip()
    )


def parse_file_patches(diff: str) -> dict[str, dict[str, list[str]]]:
    patches: dict[str, dict[str, list[str]]] = {}
    current: str | None = None
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            current = line.split(" b/", 1)[-1]
            patches[current] = {"added": [], "deleted": []}
        elif current and line.startswith("+") and not line.startswith("+++"):
            patches[current]["added"].append(line[1:])
        elif current and line.startswith("-") and not line.startswith("---"):
            patches[current]["deleted"].append(line[1:])
    return patches


def tree_conflicts(head: str) -> list[dict[str, str]]:
    """Scan the complete resulting tree, not only this diff, for live conflict markers."""
    proc = subprocess.run(
        [
            "git",
            "grep",
            "-n",
            "-I",
            "-E",
            r"^(<<<<<<< |=======|>>>>>>> )",
            head,
            "--",
            ".",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode not in {0, 1}:
        raise RuntimeError(f"git grep failed: {proc.stderr.strip()}")
    findings: list[dict[str, str]] = []
    for line in proc.stdout.splitlines():
        # Typical shape: <head>:path:line:marker text
        parts = line.split(":", 3)
        if len(parts) < 4:
            continue
        _, path, line_no, marker = parts
        findings.append(
            {
                "code": "MERGE_CONFLICT_MARKER",
                "file": path,
                "line": line_no,
                "marker": marker[:120],
            }
        )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument(
        "--authorization",
        default=".apex/operator-reduction-authorization.json",
    )
    args = parser.parse_args()

    ensure_ref(args.base)
    ensure_ref(args.head)
    diff = output("git", "diff", "--unified=3", f"{args.base}...{args.head}")
    digest = diff_hash(diff)
    authorized = load_authorization(Path(args.authorization), digest)

    failures: list[dict[str, str]] = tree_conflicts(args.head)
    warnings: list[dict[str, str]] = []

    for name, parts in parse_file_patches(diff).items():
        added = "\n".join(parts["added"])
        deleted = "\n".join(parts["deleted"])

        for code, pattern in FATAL_PATTERNS:
            if pattern.search(added):
                failures.append({"code": code, "file": name})

        if RESTRICTION_RE.search(added) and EXECUTION_RE.search(deleted):
            failures.append(
                {"code": "EXECUTION_TO_RESTRICTION_CONTRACTION", "file": name}
            )

        if MINIMIZE_RE.search(added):
            warnings.append({"code": "MINIMUM_SCOPE_SIGNAL", "file": name})

        if STATE_DEMOTION_RE.search(added):
            warnings.append({"code": "STATE_DEMOTION_SIGNAL", "file": name})

    # Exact-diff authorization may release deliberate capability reduction, but it
    # never legalizes unresolved merge-conflict markers.
    if authorized:
        failures = [
            finding
            for finding in failures
            if finding["code"] == "MERGE_CONFLICT_MARKER"
        ]

    # Keep one result per exact finding while retaining line-level conflict evidence.
    failures = list({json.dumps(item, sort_keys=True): item for item in failures}.values())
    warnings = list({json.dumps(item, sort_keys=True): item for item in warnings}.values())

    payload = {
        "schema": "apex.estate-non-regression.v2",
        "base": args.base,
        "head": args.head,
        "diff_sha256": digest,
        "operator_reduction_authorization_bound": authorized,
        "full_tree_conflict_scan": True,
        "failures": failures,
        "warnings": warnings,
        "status": "FAIL" if failures else "PASS",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))

    if failures:
        print(
            "APEX non-regression rejected this change. Repair forward or bind an "
            "exact-diff Operator reduction authorization. Merge-conflict corruption "
            "must always be repaired.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
