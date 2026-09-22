"""Hierarchical epistemology for APEX continuity and execution truth.

This module preserves useful epistemic machinery without imposing fixed
worker/retrieval ceilings or global stop semantics. Resources and strategy are
adaptive; claim promotion remains receipt-bound.
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
    repeated_failure: bool = False
    target_state: str = ""


@dataclass(frozen=True)
class StrategyPlan:
    strategy: Strategy
    intensity: str
    rationale: tuple[str, ...]
    resource_policy: str = "adaptive_evidence_driven"


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
    """Track work without converting heuristics into global execution ceilings."""

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
        return True, "admitted"

    def record(self, result: WorkerResult) -> None:
        allowed, reason = self.can_dispatch(result.worker_id)
        if not allowed:
            raise ValueError(f"worker rejected: {reason}")
        if result.retrievals < 0 or result.quota_units < 0:
            raise ValueError("worker costs cannot be negative")
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

    def continuation_signal(self) -> tuple[str, str]:
        if self.verified:
            return "verified", "target evidence verified; continue only if mission has remaining work"
        if self.conflicts:
            return "investigate", "unresolved contradiction remains visible"
        if self.no_signal_streak >= 2:
            return "reroute", "current path has low marginal signal; change method rather than truncate mission"
        return "continue", "continue coherent progress"


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
    retry_policy: str = "adaptive"


class HierarchicalEpistemology:
    """Route strategy without allowing lower layers to rewrite mission authority."""

    authority = "operator_intent"
    objective = "maximum_coherent_advance"

    @staticmethod
    def choose_strategy(task: TaskSpec) -> Strategy:
        if task.contested_evidence:
            return Strategy.DEBATE
        if task.repeated_failure:
            return Strategy.REFLEXION
        if task.high_consequence and task.multiple_plausible_paths:
            return Strategy.TREE_OF_THOUGHTS
        if task.long_horizon:
            return Strategy.PLAN_EXECUTE
        if not task.well_defined and task.quality_paramount:
            return Strategy.REFLECTION
        return Strategy.REACT

    @classmethod
    def plan(cls, task: TaskSpec) -> StrategyPlan:
        strategy = cls.choose_strategy(task)
        rationale: list[str] = []
        if task.contested_evidence:
            rationale.append("contested evidence")
        if task.repeated_failure:
            rationale.append("persisted failure memory")
        if task.high_consequence:
            rationale.append("high consequence")
        if task.multiple_plausible_paths:
            rationale.append("multiple plausible paths")
        if task.long_horizon:
            rationale.append("long horizon")
        if task.quality_paramount:
            rationale.append("quality paramount")
        intensity = "deep" if (task.high_consequence or task.contested_evidence or task.long_horizon) else "focused"
        return StrategyPlan(strategy, intensity, tuple(rationale) or ("direct tool-centered path",))

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
            objective_function_change="prefer evidence-bearing progress over activity, repetition, or unsupported promotion",
            preserve=preserve,
            next_action="select a materially different route and verify the target state",
        )

    @classmethod
    def execution_packet(cls, task: TaskSpec, *, known_state: Mapping[str, Any]) -> dict[str, Any]:
        plan = cls.plan(task)
        return {
            "schema_version": "1.1",
            "authority": cls.authority,
            "intent": task.intent,
            "target_state": task.target_state,
            "known_state": dict(known_state),
            "strategy": plan.strategy.value,
            "strategy_intensity": plan.intensity,
            "strategy_rationale": list(plan.rationale),
            "resource_policy": plan.resource_policy,
            "continuation_rule": "continue_until_target_or_evidenced_external_boundary",
            "retirement_rule": "unique_contribution_zero_and_provider_readback",
        }

    @staticmethod
    def validate_packet(packet: Mapping[str, Any]) -> None:
        required = {
            "schema_version",
            "authority",
            "intent",
            "target_state",
            "known_state",
            "strategy",
            "resource_policy",
            "continuation_rule",
            "retirement_rule",
        }
        missing = required - set(packet)
        if missing:
            raise ValueError(f"execution packet missing fields: {sorted(missing)}")
        if packet["authority"] != "operator_intent":
            raise ValueError("lower-level strategy cannot replace operator authority")
        if packet["resource_policy"] != "adaptive_evidence_driven":
            raise ValueError("fixed global execution ceilings are forbidden")
        if packet["continuation_rule"] != "continue_until_target_or_evidenced_external_boundary":
            raise ValueError("mission continuation rule was weakened")
        if packet["retirement_rule"] != "unique_contribution_zero_and_provider_readback":
            raise ValueError("retirement requires zero unique contribution plus readback")
