"""Hierarchical epistemology and quota-aware strategy selection for APEX.

This module is intentionally provider-neutral and stdlib-only.  It gives an
agent a small, inspectable control kernel instead of another personality layer:
claims stay typed, strategies escalate only when evidence justifies the cost,
and progress means target-state or evidence movement rather than paperwork.

Easter egg: the duck is a sentinel, not a decision-maker.  If the sentinel
quacks, inspect the receipt; do not promote the quack to a fact.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class EpistemicLevel(str, Enum):
    MISSION = "mission"
    AUTHORITY = "authority"
    CLAIM = "claim"
    EVIDENCE = "evidence"
    STRATEGY = "strategy"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    LEARNING = "learning"


class ClaimState(str, Enum):
    UNKNOWN = "UNKNOWN"
    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    HYPOTHESIZED = "HYPOTHESIZED"
    PROPOSED = "PROPOSED"
    ATTEMPTED = "ATTEMPTED"
    EXECUTED = "EXECUTED"
    VERIFIED = "VERIFIED"
    COMMITTED = "COMMITTED"
    DEPLOYED = "DEPLOYED"
    OBSERVED_IN_OPERATION = "OBSERVED_IN_OPERATION"


class Strategy(str, Enum):
    REACT = "react"
    PLAN_EXECUTE = "plan_and_execute"
    REFLECTION = "reflection"
    TREE_OF_THOUGHTS = "tree_of_thoughts"
    REFLEXION = "reflexion"
    DEBATE = "debate"


class Lane(str, Enum):
    COLD = "cold"
    WARM = "warm"
    HOT = "hot"


_TRANSITION_RECEIPT: dict[tuple[ClaimState, ClaimState], str] = {
    (ClaimState.PROPOSED, ClaimState.ATTEMPTED): "authorization_ref",
    (ClaimState.ATTEMPTED, ClaimState.EXECUTED): "execution_receipt",
    (ClaimState.EXECUTED, ClaimState.VERIFIED): "verification_receipt",
    (ClaimState.VERIFIED, ClaimState.COMMITTED): "commit_receipt",
    (ClaimState.COMMITTED, ClaimState.DEPLOYED): "deployment_receipt",
    (ClaimState.DEPLOYED, ClaimState.OBSERVED_IN_OPERATION): "runtime_observation",
}


@dataclass(frozen=True)
class Claim:
    text: str
    state: ClaimState
    provenance: str
    receipt: str | None = None

    def promote(self, target: ClaimState, *, receipt: str) -> "Claim":
        required = _TRANSITION_RECEIPT.get((self.state, target))
        if required is None:
            raise ValueError(f"unauthorized claim transition: {self.state}->{target}")
        if not receipt or ":" not in receipt:
            raise ValueError(f"{required} must be a provider/path receipt")
        return Claim(self.text, target, self.provenance, receipt)


@dataclass(frozen=True)
class TaskSpec:
    intent: str
    well_defined: bool = False
    tools_central: bool = False
    long_horizon: bool = False
    quality_paramount: bool = False
    multiple_plausible_paths: bool = False
    contested_evidence: bool = False
    high_consequence: bool = False
    target_state: str = ""


@dataclass(frozen=True)
class BudgetPlan:
    lane: Lane
    strategy: Strategy
    max_workers: int
    max_rounds: int
    max_retrievals: int
    max_synthesis_passes: int


@dataclass(frozen=True)
class WorkerResult:
    worker_id: str
    unique_signal: bool
    conflict: bool = False
    verified: bool = False
    retrievals: int = 0
    quota_units: int = 0


@dataclass
class DispatchLedger:
    plan: BudgetPlan
    dispatched: list[str] = field(default_factory=list)
    retrievals: int = 0
    quota_units: int = 0
    unique_signal_count: int = 0
    no_signal_streak: int = 0
    conflicts: int = 0
    verified: bool = False

    def can_dispatch(self, worker_id: str) -> tuple[bool, str]:
        if worker_id in self.dispatched:
            return False, "duplicate worker identity"
        if len(self.dispatched) >= self.plan.max_workers:
            return False, "worker budget exhausted"
        if self.retrievals >= self.plan.max_retrievals:
            return False, "retrieval budget exhausted"
        return True, "admitted"

    def record(self, result: WorkerResult) -> None:
        allowed, reason = self.can_dispatch(result.worker_id)
        if not allowed:
            raise ValueError(f"worker rejected: {reason}")
        if result.retrievals < 0 or result.quota_units < 0:
            raise ValueError("worker costs cannot be negative")
        if self.retrievals + result.retrievals > self.plan.max_retrievals:
            raise ValueError("worker rejected: retrieval budget would be exceeded")
        self.dispatched.append(result.worker_id)
        self.retrievals += result.retrievals
        self.quota_units += result.quota_units
        self.conflicts += int(result.conflict)
        self.verified = self.verified or result.verified
        if result.unique_signal:
            self.unique_signal_count += 1
            self.no_signal_streak = 0
        else:
            self.no_signal_streak += 1

    def should_stop(self) -> tuple[bool, str]:
        if self.verified:
            return True, "verification achieved"
        if len(self.dispatched) >= self.plan.max_workers:
            return True, "worker budget exhausted"
        if self.retrievals >= self.plan.max_retrievals:
            return True, "retrieval budget exhausted"
        if self.no_signal_streak >= 2 and self.conflicts == 0:
            return True, "marginal signal collapsed"
        return False, "continue"


@dataclass(frozen=True)
class ProgressAssessment:
    target_state_changed: bool
    evidence_added: bool
    artifact_only: bool

    @property
    def forward_progress(self) -> bool:
        return (self.target_state_changed or self.evidence_added) and not self.artifact_only


@dataclass(frozen=True)
class Correction:
    failure: str
    failed_assumption: str
    objective_function_change: str
    preserve: tuple[str, ...]
    next_action: str
    bounded_retry: bool = True


class HierarchicalEpistemology:
    """The APEX decision kernel: route cheaply, deepen deliberately, verify hard."""

    authority = "operator_intent"
    objective = "maximum_coherent_advance"

    @staticmethod
    def choose_strategy(task: TaskSpec) -> Strategy:
        if task.contested_evidence:
            return Strategy.DEBATE
        if task.high_consequence and task.multiple_plausible_paths:
            return Strategy.TREE_OF_THOUGHTS
        if task.long_horizon:
            return Strategy.PLAN_EXECUTE
        if not task.well_defined and task.quality_paramount:
            return Strategy.REFLECTION
        return Strategy.REACT

    @classmethod
    def budget(cls, task: TaskSpec) -> BudgetPlan:
        strategy = cls.choose_strategy(task)
        if task.high_consequence or task.contested_evidence:
            lane, workers, rounds, retrievals = Lane.HOT, 5, 2, 8
        elif task.long_horizon or not task.well_defined:
            lane, workers, rounds, retrievals = Lane.WARM, 3, 2, 6
        else:
            lane, workers, rounds, retrievals = Lane.COLD, 1, 1, 2
        return BudgetPlan(lane, strategy, workers, rounds, retrievals, 1)

    @staticmethod
    def assess_progress(*, target_state_changed: bool, evidence_added: bool, artifact_only: bool) -> ProgressAssessment:
        return ProgressAssessment(target_state_changed, evidence_added, artifact_only)

    @staticmethod
    def correct(*, failure: str, failed_assumption: str, preserve: tuple[str, ...]) -> Correction:
        if not failure.strip() or not failed_assumption.strip():
            raise ValueError("failure and failed_assumption are required")
        return Correction(
            failure=failure,
            failed_assumption=failed_assumption,
            objective_function_change="prefer evidence-bearing progress over activity, repetition, or narrative completion",
            preserve=preserve,
            next_action="isolate the failed transition, retry once with changed routing, then escalate with the receipt",
        )

    @classmethod
    def packet(cls, task: TaskSpec, *, pointers: tuple[str, ...] = ()) -> dict[str, Any]:
        plan = cls.budget(task)
        return {
            "schema": "glaciereq.hierarchical-epistemology.v1",
            "authority": cls.authority,
            "objective": cls.objective,
            "intent": task.intent,
            "target_state": task.target_state,
            "lane": plan.lane.value,
            "strategy": plan.strategy.value,
            "pointers": list(pointers),
            "budget": {
                "max_workers": plan.max_workers,
                "max_rounds": plan.max_rounds,
                "max_retrievals": plan.max_retrievals,
                "max_synthesis_passes": plan.max_synthesis_passes,
            },
            "stop_rules": [
                "verification achieved",
                "budget exhausted",
                "two consecutive workers add no unique signal and no conflict exists",
            ],
            "state_rule": "UNKNOWN != FALSE; GENERATED != EXECUTED != VERIFIED",
            "easter_egg": "The duck watches the receipt; it never signs the receipt.",
        }


def validate_packet(packet: Mapping[str, Any]) -> tuple[str, ...]:
    errors: list[str] = []
    if packet.get("schema") != "glaciereq.hierarchical-epistemology.v1":
        errors.append("schema mismatch")
    if packet.get("authority") != "operator_intent":
        errors.append("authority must be operator_intent")
    budget = packet.get("budget")
    if not isinstance(budget, Mapping):
        errors.append("budget must be an object")
    else:
        for key in ("max_workers", "max_rounds", "max_retrievals", "max_synthesis_passes"):
            if not isinstance(budget.get(key), int) or budget[key] < 1:
                errors.append(f"budget.{key} must be a positive integer")
    if not packet.get("target_state"):
        errors.append("target_state is required")
    return tuple(errors)
