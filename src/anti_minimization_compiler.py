"""Semantic anti-minimization compiler for APEX execution vectors.

Structured receipt flags such as ``minimum_scope_default=false`` are necessary
but not sufficient. A caller can set compliant booleans while selected-path
prose still says "take the safest slice" or "freeze architecture".

This module closes that assertion bypass. It detects product-level downward
routing and supplies deterministic upward rewrites while preserving legitimate
engineering concepts such as least privilege, minimal defect reproducers, and
rollback checkpoints. Exceptions are phrase-precise, never clause-wide, so a
valid security phrase cannot camouflage minimization elsewhere in the sentence.

Only selected execution language should be scanned. Literal Operator words may
quote rejected phrases and must remain intact for provenance.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class MinimizationRule:
    code: str
    pattern: re.Pattern[str]
    replacement: str


@dataclass(frozen=True, slots=True)
class MinimizationFinding:
    code: str
    matched_text: str
    replacement: str
    clause: str

    @property
    def message(self) -> str:
        return (
            f"downward-routing language rejected [{self.code}]: "
            f"{self.matched_text!r}; compile upward to {self.replacement!r}"
        )


# Product-level downward routing. Patterns are phrase-oriented. Legitimate
# constructs such as "least privilege", "minimum necessary permissions", and
# "minimal reproducer" do not match these rules at all, which is safer than a
# broad exception that could accidentally exempt neighboring bad language.
_RULES: Final[tuple[MinimizationRule, ...]] = (
    MinimizationRule(
        "SMALLEST_DEFAULT",
        re.compile(
            r"\b(?:smallest|least|minimal)\s+(?:possible\s+|useful\s+|safe\s+)?"
            r"(?:change|step|task|implementation|slice|scope|solution|feature|move|patch)\b",
            re.IGNORECASE,
        ),
        "largest coherent executable tranche",
    ),
    MinimizationRule(
        "MVP_DEFAULT",
        re.compile(
            r"\b(?:minimum\s+viable|mvp)\s*"
            r"(?:plan|product|implementation|slice|scope|feature|solution|version)?\b",
            re.IGNORECASE,
        ),
        "complete central mechanism + hardening + proof",
    ),
    MinimizationRule(
        "SAFEST_SLICE_DEFAULT",
        re.compile(
            r"\b(?:safest|most\s+conservative)\s+(?:slice|step|task|change|path|option|move)\b",
            re.IGNORECASE,
        ),
        "control risk without reducing the target",
    ),
    MinimizationRule(
        "BOUNDED_SLICE_DEFAULT",
        re.compile(
            r"\b(?:bounded|narrow(?:est)?)\s+(?:slice|scope|implementation|task|change|path|move)\b",
            re.IGNORECASE,
        ),
        "maximum coherent executable tranche",
    ),
    MinimizationRule(
        "LEAST_CAPABILITY_DEFAULT",
        re.compile(
            r"\bleast\s+(?:capable|ambitious|powerful|complex)\s+"
            r"(?:implementation|solution|architecture|design|option|path|version)\b",
            re.IGNORECASE,
        ),
        "strongest justified capability",
    ),
    MinimizationRule(
        "FREEZE_PRODUCT",
        re.compile(
            r"\b(?:freeze|lock|hold)\s+(?:the\s+)?"
            r"(?:scope|architecture|implementation|capability|feature\s+set|design)\b",
            re.IGNORECASE,
        ),
        "preserve a known-good rollback checkpoint and continue evolution",
    ),
    MinimizationRule(
        "FEATURE_FREEZE_DELIVERY",
        re.compile(r"\bfeature\s+freeze\b", re.IGNORECASE),
        "preserve verified gains while continuing frontier expansion",
    ),
    MinimizationRule(
        "GOVERNANCE_FIRST",
        re.compile(
            r"\b(?:governance|policy|gates?|receipts?|registry)\s+first\b",
            re.IGNORECASE,
        ),
        "make governance serve functional advance",
    ),
    MinimizationRule(
        "PRESERVE_INSTEAD_OF_ACT",
        re.compile(
            r"\bpreserv(?:e|ing)\s+(?:the\s+)?(?:state|system|code|repo|repository)\s+"
            r"(?:instead\s+of|rather\s+than)\s+(?:act|build|implement|change|advance|execute)\b",
            re.IGNORECASE,
        ),
        "preserve valid gains and advance the requested function",
    ),
)


# These are documented invariants and a regression corpus. They are not broad
# bypass patterns. If a future forbidden rule overlaps one of these exact local
# quality mechanisms, the rule must become more precise instead of skipping a
# whole clause.
PERMITTED_LOCAL_NARROWING: Final[tuple[str, ...]] = (
    "debugging or diagnostic isolation",
    "minimal reproduction of a defect",
    "least privilege security",
    "minimum necessary permissions",
    "immutable rollback checkpoint",
    "known-good snapshot",
)


def supported_rule_codes() -> tuple[str, ...]:
    """Return the exact semantic enforcement surface for policy drift checks."""
    return tuple(rule.code for rule in _RULES)


def _clauses(text: str) -> tuple[str, ...]:
    """Split prose for precise findings and readable repair receipts."""
    return tuple(
        part.strip()
        for part in re.split(r"(?:[\n\r]+|(?<=[.!?;])\s+)", text)
        if part.strip()
    )


def inspect_execution_text(
    text: str,
    *,
    operator_directed_reduction: bool = False,
) -> tuple[MinimizationFinding, ...]:
    """Return semantic downward-routing findings for selected-path prose.

    Explicit Operator-directed reduction is authoritative. Otherwise every
    product-level regression phrase is rejected, even when a legitimate local
    quality phrase appears in the same clause.
    """
    if operator_directed_reduction or not text.strip():
        return ()

    findings: list[MinimizationFinding] = []
    for clause in _clauses(text):
        for rule in _RULES:
            for match in rule.pattern.finditer(clause):
                findings.append(
                    MinimizationFinding(
                        code=rule.code,
                        matched_text=match.group(0),
                        replacement=rule.replacement,
                        clause=clause,
                    )
                )

    unique: dict[tuple[str, str, str], MinimizationFinding] = {}
    for finding in findings:
        key = (finding.code, finding.matched_text.lower(), finding.clause.lower())
        unique.setdefault(key, finding)
    return tuple(unique.values())


def compile_upward(text: str) -> str:
    """Rewrite product-level downward-routing language toward APEX objectives.

    Only matched regression phrases are replaced. Legitimate local engineering
    language is naturally preserved because the forbidden patterns are precise.
    Runtime authorization should still inspect the compiled result.
    """
    if not text.strip():
        return text

    compiled: list[str] = []
    for clause in _clauses(text):
        rewritten = clause
        for rule in _RULES:
            rewritten = rule.pattern.sub(rule.replacement, rewritten)
        compiled.append(rewritten)
    return "\n".join(compiled)
