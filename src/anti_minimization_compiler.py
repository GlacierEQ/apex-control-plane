"""Semantic anti-minimization compiler for APEX execution vectors.

The operator-fidelity receipt already carries structured booleans such as
``minimum_scope_default=false``. Those booleans are necessary, but they are not
sufficient: a caller could set them correctly while the human-readable path
still says "take the safest slice" or "freeze architecture".

This module closes that assertion bypass. It inspects execution-path language,
distinguishes legitimate local narrowing (debugging, least privilege, rollback
checkpoints) from product-level scope reduction, and produces an upward rewrite
for every rejected route.

It intentionally scans *selected execution language*, not literal operator
constraints. Quoting a rejected phrase while preserving the Operator's words is
not itself a regression.
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


# Product-level downward routing. Patterns are deliberately phrase-oriented so
# ordinary words such as "minimum" in "minimum necessary permissions" are not
# treated as violations by themselves.
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
            r"\b(?:minimum\s+viable|\bmvp\b)\s*"
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


# Narrowing is legitimate when it is clearly local to diagnosis, security, or
# recovery. These clauses protect engineering rigor from being mistaken for a
# product-level ambition ceiling.
_LOCAL_NARROWING: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\b(?:debug|debugging|diagnostic|fault\s+isolation|bisect(?:ion)?)\b", re.IGNORECASE),
    re.compile(r"\bminimal\s+(?:repro|reproduction|reproducer|test\s+case)\b", re.IGNORECASE),
    re.compile(r"\bleast\s+privilege\b", re.IGNORECASE),
    re.compile(r"\bminimum\s+necessary\s+permissions?\b", re.IGNORECASE),
    re.compile(r"\b(?:rollback|recovery)\s+(?:checkpoint|snapshot|path)\b", re.IGNORECASE),
    re.compile(r"\bknown[- ]good\s+(?:checkpoint|snapshot|state)\b", re.IGNORECASE),
    re.compile(r"\bimmutable\s+(?:checkpoint|snapshot)\b", re.IGNORECASE),
)


def _clauses(text: str) -> tuple[str, ...]:
    """Split prose finely enough to keep local exceptions local."""
    return tuple(
        part.strip()
        for part in re.split(r"(?:[\n\r]+|(?<=[.!?;])\s+)", text)
        if part.strip()
    )


def _is_local_narrowing(clause: str) -> bool:
    return any(pattern.search(clause) for pattern in _LOCAL_NARROWING)


def inspect_execution_text(
    text: str,
    *,
    operator_directed_reduction: bool = False,
) -> tuple[MinimizationFinding, ...]:
    """Return semantic downward-routing findings for selected-path prose.

    Explicit Operator-directed reduction is authoritative and therefore not a
    policy violation. Local diagnostic/security/recovery narrowing is also
    preserved. Everything else matching the product-level regression lexicon is
    rejected.
    """
    if operator_directed_reduction or not text.strip():
        return ()

    findings: list[MinimizationFinding] = []
    for clause in _clauses(text):
        if _is_local_narrowing(clause):
            continue
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

    # Preserve order while deduplicating overlapping/duplicate signals.
    unique: dict[tuple[str, str, str], MinimizationFinding] = {}
    for finding in findings:
        key = (finding.code, finding.matched_text.lower(), finding.clause.lower())
        unique.setdefault(key, finding)
    return tuple(unique.values())


def compile_upward(text: str) -> str:
    """Rewrite product-level downward-routing language toward APEX objectives.

    This is deterministic and conservative: only matched regression phrases are
    replaced, and clauses containing legitimate local narrowing are left intact.
    The function is suitable for planners that want repair instead of rejection.
    Runtime authorization should still call :func:`inspect_execution_text` on
    the resulting path.
    """
    if not text.strip():
        return text

    compiled: list[str] = []
    for clause in _clauses(text):
        if _is_local_narrowing(clause):
            compiled.append(clause)
            continue
        rewritten = clause
        for rule in _RULES:
            rewritten = rule.pattern.sub(rule.replacement, rewritten)
        compiled.append(rewritten)
    return "\n".join(compiled)
