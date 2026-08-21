"""Epistemic and blast-radius control for APEX execution.

APEX means strongest justified execution, not largest mutation.

The gate separates what is observed from what is inferred or guessed, then
scales execution controls with uncertainty, blast radius, irreversibility, and
novelty. High-impact work is not weakened; it is researched, staged, recovered,
and verified strongly enough to deserve its power.

Core sequence:
    RESEARCH -> STUDY -> MODEL CONSEQUENCES -> CHECKPOINT -> EXECUTE
    -> READ BACK -> VERIFY -> CONTINUE

The module is intentionally independent of any one branch or repository tool so
it can be reused by branch consolidation, data migration, deployment, cleanup,
refactoring, and other consequential mutation paths.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum


class EpistemicState(StrEnum):
    OBSERVED = "observed"
    INFERRED = "inferred"
    HYPOTHESIZED = "hypothesized"
    UNKNOWN = "unknown"


class BlastRadius(IntEnum):
    LOCAL = 1
    MULTI_OBJECT = 2
    ESTATE = 3


class Reversibility(IntEnum):
    REVERSIBLE = 1
    CONDITIONAL = 2
    IRREVERSIBLE = 3


class GateDecision(StrEnum):
    ALLOW = "allow"
    RESEARCH_REQUIRED = "research_required"
    BLOCK = "block"


@dataclass(frozen=True, slots=True)
class ExecutionEvidence:
    operation: str
    epistemic_state: EpistemicState
    blast_radius: BlastRadius
    reversibility: Reversibility
    source_state_observed: bool
    dependency_map_observed: bool
    recovery_checkpoint_verified: bool
    recovery_procedure_verified: bool
    dry_run_verified: bool
    staged_execution: bool
    novel_operation: bool = False
    operator_explicit_irreversible_authorization: bool = False


@dataclass(frozen=True, slots=True)
class GateResult:
    decision: GateDecision
    reasons: tuple[str, ...]

    @property
    def allowed(self) -> bool:
        return self.decision is GateDecision.ALLOW


def evaluate_execution(evidence: ExecutionEvidence) -> GateResult:
    """Decide whether the proposed mutation is epistemically ready to execute.

    The gate never treats uncertainty as authority to shrink the objective.
    Instead, uncertainty routes to research and staged proof. Large blast radius
    increases the evidence burden because a wrong assumption propagates farther.
    """
    research_reasons: list[str] = []
    block_reasons: list[str] = []

    if not evidence.source_state_observed:
        research_reasons.append("source state has not been observed")

    if evidence.blast_radius >= BlastRadius.MULTI_OBJECT and not evidence.dependency_map_observed:
        research_reasons.append("dependency and lineage impact has not been observed")

    if (
        evidence.epistemic_state in {EpistemicState.HYPOTHESIZED, EpistemicState.UNKNOWN}
        and evidence.blast_radius >= BlastRadius.MULTI_OBJECT
    ):
        research_reasons.append(
            "high-impact execution is still based on hypothesis or unknown state"
        )

    if evidence.blast_radius is BlastRadius.ESTATE:
        if not evidence.recovery_checkpoint_verified:
            block_reasons.append("estate-scale mutation lacks a verified recovery checkpoint")
        if not evidence.recovery_procedure_verified:
            block_reasons.append("estate-scale mutation lacks a verified recovery procedure")
        if not evidence.staged_execution:
            block_reasons.append("estate-scale mutation is not staged with readback boundaries")

    if evidence.novel_operation and evidence.blast_radius >= BlastRadius.MULTI_OBJECT:
        if not evidence.dry_run_verified:
            research_reasons.append("novel high-impact operation has no verified rehearsal")
        if not evidence.staged_execution:
            block_reasons.append("novel high-impact operation cannot run as one unobserved batch")

    if evidence.reversibility is Reversibility.IRREVERSIBLE:
        if not evidence.operator_explicit_irreversible_authorization:
            block_reasons.append("irreversible mutation lacks explicit Operator authorization")
        if not evidence.recovery_checkpoint_verified:
            block_reasons.append("irreversible mutation lacks a verified preservation checkpoint")

    if block_reasons:
        return GateResult(GateDecision.BLOCK, tuple(dict.fromkeys(block_reasons + research_reasons)))
    if research_reasons:
        return GateResult(GateDecision.RESEARCH_REQUIRED, tuple(dict.fromkeys(research_reasons)))
    return GateResult(GateDecision.ALLOW, ())


@dataclass(frozen=True, slots=True)
class CompletionEvidence:
    execution_receipt: bool
    terminal_readback: bool
    verification_passed: bool
    active_operations: int = 0
    failure_detected: bool = False
    recovery_state_observed: bool = True


def validate_completion_claim(evidence: CompletionEvidence) -> tuple[str, ...]:
    """Reject false completion and cover-up states.

    A worker cannot say COMPLETE while work is still running, while the terminal
    state has not been read back, or after a failure whose recovery state is
    still unknown. Failure is reported as failure, then repaired from observed
    state. It is never rewritten into success by narration.
    """
    errors: list[str] = []
    if not evidence.execution_receipt:
        errors.append("completion requires an execution receipt")
    if not evidence.terminal_readback:
        errors.append("completion requires terminal-state readback")
    if not evidence.verification_passed:
        errors.append("completion requires verification")
    if evidence.active_operations:
        errors.append("completion is impossible while operations are still active")
    if evidence.failure_detected and not evidence.recovery_state_observed:
        errors.append("failure recovery state must be observed before any completion claim")
    return tuple(errors)
