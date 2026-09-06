from __future__ import annotations

import pytest

from epistemic_risk_gate import (
    BlastRadius,
    CompletionEvidence,
    EpistemicState,
    ExecutionEvidence,
    GateDecision,
    Reversibility,
    evaluate_execution,
    validate_completion_claim,
)


def _evidence(**overrides) -> ExecutionEvidence:
    values = {
        "operation": "consolidate repository branches",
        "epistemic_state": EpistemicState.OBSERVED,
        "blast_radius": BlastRadius.ESTATE,
        "reversibility": Reversibility.REVERSIBLE,
        "source_state_observed": True,
        "dependency_map_observed": True,
        "recovery_checkpoint_verified": True,
        "recovery_procedure_verified": True,
        "dry_run_verified": True,
        "staged_execution": True,
        "novel_operation": False,
        "operator_explicit_irreversible_authorization": False,
    }
    values.update(overrides)
    return ExecutionEvidence(**values)


def test_strong_estate_scale_execution_is_allowed_when_it_is_understood_and_recoverable() -> (
    None
):
    result = evaluate_execution(_evidence())
    assert result.decision is GateDecision.ALLOW
    assert result.allowed is True


@pytest.mark.parametrize("state", [EpistemicState.HYPOTHESIZED, EpistemicState.UNKNOWN])
def test_guess_cannot_be_promoted_into_high_impact_execution(
    state: EpistemicState,
) -> None:
    result = evaluate_execution(_evidence(epistemic_state=state))
    assert result.decision is GateDecision.RESEARCH_REQUIRED
    assert any("hypothesis or unknown" in reason for reason in result.reasons)


def test_unobserved_source_state_routes_to_research() -> None:
    result = evaluate_execution(_evidence(source_state_observed=False))
    assert result.decision is GateDecision.RESEARCH_REQUIRED
    assert any("source state" in reason for reason in result.reasons)


def test_estate_scale_mutation_without_recovery_is_blocked() -> None:
    result = evaluate_execution(
        _evidence(
            recovery_checkpoint_verified=False,
            recovery_procedure_verified=False,
        )
    )
    assert result.decision is GateDecision.BLOCK
    assert any("recovery checkpoint" in reason for reason in result.reasons)
    assert any("recovery procedure" in reason for reason in result.reasons)


def test_estate_scale_all_at_once_mutation_is_blocked() -> None:
    result = evaluate_execution(_evidence(staged_execution=False))
    assert result.decision is GateDecision.BLOCK
    assert any("staged" in reason for reason in result.reasons)


def test_novel_high_impact_operation_requires_rehearsal_and_staging() -> None:
    result = evaluate_execution(
        _evidence(
            blast_radius=BlastRadius.MULTI_OBJECT,
            novel_operation=True,
            dry_run_verified=False,
            staged_execution=False,
        )
    )
    assert result.decision is GateDecision.BLOCK
    assert any("verified rehearsal" in reason for reason in result.reasons)
    assert any("one unobserved batch" in reason for reason in result.reasons)


def test_irreversible_action_requires_operator_authorization_and_preservation() -> None:
    result = evaluate_execution(
        _evidence(
            reversibility=Reversibility.IRREVERSIBLE,
            operator_explicit_irreversible_authorization=False,
            recovery_checkpoint_verified=False,
        )
    )
    assert result.decision is GateDecision.BLOCK
    assert any("explicit Operator authorization" in reason for reason in result.reasons)
    assert any("preservation checkpoint" in reason for reason in result.reasons)


def test_irreversible_action_can_proceed_when_operator_authorizes_and_recovery_is_verified() -> (
    None
):
    result = evaluate_execution(
        _evidence(
            reversibility=Reversibility.IRREVERSIBLE,
            operator_explicit_irreversible_authorization=True,
            recovery_checkpoint_verified=True,
        )
    )
    assert result.decision is GateDecision.ALLOW


def test_completion_requires_receipt_readback_verification_and_no_active_work() -> None:
    errors = validate_completion_claim(
        CompletionEvidence(
            execution_receipt=True,
            terminal_readback=False,
            verification_passed=False,
            active_operations=1,
        )
    )
    assert any("terminal-state readback" in error for error in errors)
    assert any("verification" in error for error in errors)
    assert any("still active" in error for error in errors)


def test_failure_cannot_be_narrated_into_completion_before_recovery_state_is_observed() -> (
    None
):
    errors = validate_completion_claim(
        CompletionEvidence(
            execution_receipt=True,
            terminal_readback=True,
            verification_passed=True,
            active_operations=0,
            failure_detected=True,
            recovery_state_observed=False,
        )
    )
    assert any("recovery state" in error for error in errors)


def test_verified_terminal_state_can_be_claimed_complete() -> None:
    assert (
        validate_completion_claim(
            CompletionEvidence(
                execution_receipt=True,
                terminal_readback=True,
                verification_passed=True,
                active_operations=0,
                failure_detected=False,
                recovery_state_observed=True,
            )
        )
        == ()
    )
