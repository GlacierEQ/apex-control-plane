"""Semantic anti-minimization compiler for APEX execution vectors.

Structured receipt flags such as ``minimum_scope_default=false`` are necessary
but not sufficient. A caller can set compliant booleans while selected-path
prose still says "take the safest slice" or "freeze architecture".

This module closes that assertion bypass. It detects product-level downward
routing and supplies deterministic upward rewrites while preserving legitimate
engineering concepts such as least privilege, minimal defect reproducers, and
rollback checkpoints. Exceptions are phrase-precise, never clause-wide, so a
valid security phrase cannot camouflage minimization elsewhere in the sentence.
Negation is match-local for the same reason: "never freeze architecture" remains
a prohibition, but it cannot excuse "take the safest slice" later in the text.

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


PERMITTED_LOCAL_NARROWING: Final[tuple[str, ...]] = (
    "debugging or diagnostic isolation",
    "minimal reproduction of a defect",
    "least privilege security",
    "minimum necessary permissions",
    "immutable rollback checkpoint",
    "known-good snapshot",
)

# Keep negation local to the specific matched phrase. A response-wide "never"
# or "forbidden" must not become an escape hatch for a later downward directive.
_NEGATION_PREFIX_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:\bdo\s+not\b|\bdon't\b|\bnever\b|\bmust\s+not\b|\bshall\s+not\b|"
    r"\breject\b|\bforbid(?:den)?\b|\bprohibit(?:ed)?\b|\bnot\s+the\s+"
    r"(?:goal|objective|target|mission|default)\b)\s*(?:\w+\s+){0,3}$",
    re.IGNORECASE,
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


def _locally_negated(clause: str, match_start: int) -> bool:
    prefix = clause[max(0, match_start - 96) : match_start]
    return bool(_NEGATION_PREFIX_RE.search(prefix))


def inspect_execution_text(
    text: str,
    *,
    operator_directed_reduction: bool = False,
) -> tuple[MinimizationFinding, ...]:
    """Return semantic downward-routing findings for selected-path prose.

    Explicit Operator-directed reduction is authoritative. Otherwise every
    product-level regression phrase is rejected, even when a legitimate local
    quality phrase appears in the same clause. Locally negated regression
    phrases remain valid prohibitions.
    """
    if operator_directed_reduction or not text.strip():
        return ()

    findings: list[MinimizationFinding] = []
    for clause in _clauses(text):
        for rule in _RULES:
            for match in rule.pattern.finditer(clause):
                if _locally_negated(clause, match.start()):
                    continue
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

    Only non-negated regression phrases are replaced. Legitimate local
    engineering language and explicit anti-minimization prohibitions survive.
    Runtime authorization should still inspect the compiled result.
    """
    if not text.strip():
        return text

    compiled: list[str] = []
    for clause in _clauses(text):
        rewritten = clause
        for rule in _RULES:
            matches = [
                match
                for match in rule.pattern.finditer(rewritten)
                if not _locally_negated(rewritten, match.start())
            ]
            for match in reversed(matches):
                rewritten = (
                    rewritten[: match.start()]
                    + rule.replacement
                    + rewritten[match.end() :]
                )
        compiled.append(rewritten)
    return "\n".join(compiled)
