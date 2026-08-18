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

# Downward-routing language is not merely advisory. When newly introduced as an
# active engineering directive, it is a policy regression and must fail closed.
DOWNWARD_SCOPE_RE = re.compile(
    r"(smallest\s+(?:possible|useful|change|slice|step|implementation|scope|solution|version)|"
    r"minimum\s+viable(?:\s+(?:product|plan|slice|scope|implementation|change))?|"
    r"bounded\s+slice|safe(?:st)?\s+slice|"
    r"least\s+(?:ambitious|capable|complex|scope|change|work|effort|powerful)|"
    r"freeze\s+(?:scope|architecture|design|implementation|features?|capability|development)|"
    r"(?:scope|architecture|design|implementation|features?|capability|development)\s+freeze)",
    re.IGNORECASE,
)
DIRECTIVE_RE = re.compile(
    r"\b(must|shall|should|always|default|prefer|choose|select|use|take|limit|reduce|"
    r"minimi[sz]e|constrain|cap|freeze|keep|make|optimi[sz]e|target|objective)\b",
    re.IGNORECASE,
)
ANTI_DOWNWARD_RE = re.compile(
    r"\b(do\s+not|don't|never|must\s+not|shall\s+not|reject|forbid|prohibit|"
    r"retire(?:d)?|deprecated|historical|anti[-_ ]minimi[sz]ation|no[-_ ]minimum|"
    r"not\s+the\s+(?:goal|objective|target|mission|default)|zero\s+intrinsic\s+(?:score|priority))\b",
    re.IGNORECASE,
)
DEBUG_EXCEPTION_RE = re.compile(
    r"\b(debug|diagnos|reproduc|bisect|isolate|experiment|probe|test\s+fixture|"
    r"failure\s+reproduction|minimal\s+reproducer)\b",
    re.IGNORECASE,
)
ROLLBACK_EXCEPTION_RE = re.compile(
    r"\b(rollback|checkpoint|snapshot|known[- ]good|restore\s+point|immutable\s+reference|"
    r"baseline\s+capture)\b",
    re.IGNORECASE,
)
SECURITY_EXCEPTION_RE = re.compile(
    r"\bleast\s+privilege\b|\bminimum\s+permissions?\b|\bminimum\s+necessary\s+access\b",
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


def classify_downward_directive(line: str) -> str | None:
    """Return a fatal regression code for active minimization directives.

    Narrowing is permitted only as a local uncertainty-reduction technique, never
    as the product objective. Security least-privilege language and immutable
    rollback/checkpoint language are deliberately exempt because they increase
    system quality rather than suppress capability.
    """
    if not DOWNWARD_SCOPE_RE.search(line):
        return None
    if SECURITY_EXCEPTION_RE.search(line):
        return None
    if ANTI_DOWNWARD_RE.search(line):
        return None
    if DEBUG_EXCEPTION_RE.search(line):
        return None
    if ROLLBACK_EXCEPTION_RE.search(line):
        return None
    if DIRECTIVE_RE.search(line) or re.search(r"[:=]\s*[\"']?(?:smallest|minimum|least|freeze)", line, re.IGNORECASE):
        return "DOWNWARD_SCOPE_DIRECTIVE"
    # Policy prose can omit an imperative verb while still declaring a target,
    # e.g. "the smallest useful implementation." Fail closed on that ambiguity.
    return "DOWNWARD_SCOPE_SIGNAL_UNQUALIFIED"


def tree_conflicts(head: str) -> list[dict[str, str]]:
    """Scan the complete resulting tree for exact Git conflict-marker lines."""
    proc = subprocess.run(
        [
            "git",
            "grep",
            "-n",
            "-I",
            "-E",
            r"^(<<<<<<< .+|=======$|>>>>>>> .+)$",
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

        for line_number, line in enumerate(parts["added"], start=1):
            code = classify_downward_directive(line)
            if code:
                failures.append(
                    {
                        "code": code,
                        "file": name,
                        "added_line": str(line_number),
                        "signal": line.strip()[:240],
                    }
                )

        if STATE_DEMOTION_RE.search(added):
            warnings.append({"code": "STATE_DEMOTION_SIGNAL", "file": name})

    # Exact-diff authorization may release a deliberate capability reduction. It
    # never legalizes unresolved merge corruption. The authorization must be
    # explicit because downward routing is now a hard failure, not a suggestion.
    if authorized:
        failures = [
            finding
            for finding in failures
            if finding["code"] == "MERGE_CONFLICT_MARKER"
        ]

    failures = list({json.dumps(item, sort_keys=True): item for item in failures}.values())
    warnings = list({json.dumps(item, sort_keys=True): item for item in warnings}.values())

    payload = {
        "schema": "apex.estate-non-regression.v3",
        "base": args.base,
        "head": args.head,
        "diff_sha256": digest,
        "operator_reduction_authorization_bound": authorized,
        "full_tree_conflict_scan": True,
        "exact_conflict_marker_matching": True,
        "anti_minimization_fail_closed": True,
        "downward_scope_exceptions": [
            "local_debug_or_diagnostic_isolation",
            "least_privilege_security",
            "rollback_or_known_good_checkpoint",
        ],
        "failures": failures,
        "warnings": warnings,
        "status": "FAIL" if failures else "PASS",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))

    if failures:
        print(
            "APEX non-regression rejected this change. Repair forward into a stronger "
            "coherent implementation or bind an exact-diff Operator reduction authorization. "
            "Downward scope routing and merge-conflict corruption fail closed.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
