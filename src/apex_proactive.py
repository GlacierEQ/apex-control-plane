"""Proactive engine for the overhauled APEX control plane.

Counter-design, in code, from the Operator's 2026-10-23 definitions:
- A trigger runs a route; it does not wait for a tap.
- A receipt is a before/after state diff, not a narrative about work.
- "Unverified" is a route that runs until it verifies or reroutes.
- Escalation survives only for: a genuine judgment call, an offer or
  acceptance, a fact only the Operator holds, or a Tier-2 log matter
  (court, agency, administration, PACT). Everything else runs.
- A worker never grades its own work. A work item is done only on a
  grader verdict, and a grader that is not the worker.
- Missing evidence renders as no value, never as an invented number.

Nothing here is a claim about an external system. Every function below
is exercised by tests/test_apex_proactive.py, and every verdict in that
file comes from a run, not from prose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Callable, Sequence


# ---------------------------------------------------------------- triggers

@dataclass(frozen=True)
class Trigger:
    """An event that starts a route, with its escalation surface named."""

    event_type: str
    route: str
    escalation: str = ""  # "", "judgment", "offer_acceptance", "operator_fact", "tier2_log"

    def escalates(self) -> bool:
        return self.escalation in ("judgment", "offer_acceptance", "operator_fact", "tier2_log")


@dataclass
class RouteResult:
    route: str
    verified: bool
    value: Any = None
    attempts: tuple[str, ...] = ()
    error: str = ""


def run_until_verified(routes: Sequence[tuple[str, Callable[[], Any]]]) -> RouteResult:
    """Run routes in order until one verifies; record every attempt.

    A route verifies by returning a non-None value without raising.
    A route that raises, or returns None, is an unverified attempt and
    the next route runs. If no route verifies, the result carries
    value=None -- never an invented value.
    """
    attempts: list[str] = []
    for name, fn in routes:
        attempts.append(name)
        try:
            value = fn()
        except Exception as exc:  # route failed; reroute, do not stop
            if attempts and name == routes[-1][0]:
                return RouteResult(route=name, verified=False, value=None, attempts=tuple(attempts), error=str(exc))
            continue
        if value is not None:
            return RouteResult(route=name, verified=True, value=value, attempts=tuple(attempts))
    return RouteResult(route=routes[-1][0] if routes else "", verified=False, value=None, attempts=tuple(attempts))


# ---------------------------------------------------------------- receipts

@dataclass(frozen=True)
class StateReceipt:
    before: dict[str, int]
    after: dict[str, int]
    label: str = ""

    @property
    def diff(self) -> dict[str, int]:
        keys = set(self.before) | set(self.after)
        return {k: self.after.get(k, 0) - self.before.get(k, 0) for k in keys}

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "before": dict(self.before), "after": dict(self.after), "diff": self.diff}


def state_receipt(before: dict[str, int], after: dict[str, int], label: str = "") -> StateReceipt:
    return StateReceipt(before=dict(before), after=dict(after), label=label)


# ------------------------------------------------------- worker / grader

class GraderIdentityError(ValueError):
    """A worker attempted to grade its own work."""


@dataclass
class WorkItem:
    work_id: str
    worker_id: str
    evidence: dict[str, Any] = field(default_factory=dict)
    state: str = "open"  # open | done | blocked | held


def grade(work: WorkItem, *, grader_id: str, verdict: str) -> WorkItem:
    """Flip state only on a non-worker grader verdict.

    verdict in {"PASS", "BLOCK", "HOLD"}. Anything else raises.
    A grader with the worker's identity raises, in code, not prose.
    """
    if grader_id == work.worker_id:
        raise GraderIdentityError("grader must not be the worker")
    if verdict == "PASS":
        work.state = "done"
    elif verdict == "BLOCK":
        work.state = "blocked"
    elif verdict == "HOLD":
        work.state = "held"
    else:
        raise ValueError(f"unknown verdict: {verdict!r}")
    return work


def render_value(value: Any) -> str:
    """Refuse-to-guess rendering: missing evidence renders empty, never 0."""
    if value is None:
        return ""
    return str(value)


# ------------------------------------------------- structured workflow

def run_phases(phases: Sequence[Callable[[dict[str, Any]], dict[str, Any]]], initial: dict[str, Any]) -> dict[str, Any]:
    """Pass structured dicts phase to phase; no phase re-parses prose.

    A phase that returns prose instead of a dict fails loudly, so a
    silent corruption of the kind narration invites cannot pass through.
    """
    state = dict(initial)
    for phase in phases:
        state = phase(state)
        if not isinstance(state, dict):
            raise TypeError(f"phase {getattr(phase, '__name__', phase)!r} must return a dict, got {type(state).__name__}")
    return state


# ------------------------------------------------------------- breadcrumb

@dataclass
class Breadcrumb:
    task: str
    last_step: str
    next_step: str
    decisions: tuple[str, ...] = ()
    open_question: str = ""
    blocked_by: str = ""
    artifact: str = ""

    def to_markdown(self) -> str:
        lines = [f"task: {self.task}", f"last_step: {self.last_step}", f"next_step: {self.next_step}"]
        for i, d in enumerate(self.decisions, 1):
            lines.append(f"decision_{i}: {d}")
        lines += [f"open_question: {self.open_question}", f"blocked_by: {self.blocked_by}", f"artifact: {self.artifact}"]
        return "\n".join(lines) + "\n"

    @classmethod
    def from_markdown(cls, text: str) -> "Breadcrumb":
        fields: dict[str, str] = {}
        decisions: list[str] = []
        for line in text.splitlines():
            if ": " not in line:
                continue
            key, value = line.split(": ", 1)
            if key.startswith("decision_"):
                decisions.append(value)
            else:
                fields[key] = value
        return cls(
            task=fields.get("task", ""),
            last_step=fields.get("last_step", ""),
            next_step=fields.get("next_step", ""),
            decisions=tuple(decisions),
            open_question=fields.get("open_question", ""),
            blocked_by=fields.get("blocked_by", ""),
            artifact=fields.get("artifact", ""),
        )


# ------------------------------------------------------------ tool search

def top_k_tools(tools: Sequence[dict[str, str]], query: str, k: int = 3) -> list[dict[str, str]]:
    """Keyword-overlap top-k, so only k tool descriptions load, not all.

    Returns tools in ranked order. This is a deterministic stand-in for
    a real ranker: its accuracy is a floor, not a claim about an LLM.
    """
    words = {w.strip(".,!?").lower() for w in query.split() if w.strip(".,!?")}
    scored: list[tuple[int, int, dict[str, str]]] = []
    for i, tool in enumerate(tools):
        hay = f"{tool.get('name', '')} {tool.get('description', '')}".lower()
        score = sum(1 for w in words if w in hay)
        scored.append((-score, i, tool))
    scored.sort(key=lambda row: (row[0], row[1]))
    return [tool for _, _, tool in scored[:k]]


# -------------------------------------------------------- skill trigger

class SkillRegistry:
    """Forced invocation only. A generic reminder adds no signal."""

    def __init__(self) -> None:
        self._skills: dict[str, str] = {}

    def register(self, name: str, description: str) -> None:
        self._skills[name] = description

    def invoke(self, name: str) -> str | None:
        """Explicit invocation: returns the skill description, or None."""
        return self._skills.get(name)

    def generic_reminder(self) -> None:
        """Deliberately a no-op: prose reminders do not activate skills."""
        return None


# ------------------------------------------------------------ test gate

def snapshot_files(paths: Sequence[Path | str]) -> dict[str, str]:
    snap: dict[str, str] = {}
    for p in paths:
        path = Path(p)
        if path.is_file():
            snap[str(path)] = sha256(path.read_bytes()).hexdigest()
    return snap


def changed_test_files(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Files whose test bytes changed, added, or disappeared.

    A CI run that is green but changed a test file fails this gate:
    the gate checks bytes, not exit codes.
    """
    changed = [k for k in set(before) | set(after) if before.get(k) != after.get(k)]
    return sorted(changed)


def gate_json(changed: Sequence[str]) -> str:
    return json.dumps({"changed_test_files": list(changed), "gate": "fail" if changed else "pass"}, sort_keys=True)
