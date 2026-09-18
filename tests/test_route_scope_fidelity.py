from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import apex_runtime_kernel as runtime
from apex_runtime_kernel import RuntimePhase, TaskMode, create_verified_runtime_kernel
from outcome_fidelity_runtime import (
    OutcomeFidelityViolation,
    enforce_outcome_fidelity,
    load_outcome_fidelity_policy,
)


_GATE_GETTERS = (
    "get_in_process_notion_validation",
    "get_in_process_boot_validation",
    "get_in_process_operator_fidelity_lock",
    "get_in_process_operator_fidelity_validation",
    "get_in_process_apex_validation",
)


def _arm(monkeypatch):
    valid = SimpleNamespace(ok=True, status="complete")
    for getter in _GATE_GETTERS:
        monkeypatch.setattr(runtime, getter, lambda valid=valid: valid)
    return enforce_outcome_fidelity(create_verified_runtime_kernel())


def _bind_lockfile_objective(kernel) -> None:
    kernel.bind_task(
        literal_instruction="repair the package lock and keep going",
        target_state="provider-proved package-lock restored to source and verified",
        operation_class="repair_package_lock",
        mode=TaskMode.MUTATION,
        action_scope="internal",
        operator_authorization_ref="operator-command:repair-lockfile",
        prior_state_ref="github:telecom-lockfile-inconsistent",
        source_refs=("supabase:buildkite-5-lock-receipt",),
        verification_plan=(
            "recover exact provider-proved lock bytes",
            "write exact bytes through source authority",
            "verify with clean npm ci",
        ),
    )
    kernel.begin()
    assert kernel.phase is RuntimePhase.EXECUTING


def test_policy_contains_fail_closed_route_scope_invariant() -> None:
    policy = load_outcome_fidelity_policy()
    invariant = policy["route_scope_invariant"]
    assert invariant["route_failure_preserves_objective"] is True
    assert invariant["temporary_skip_preserves_objective"] is True
    assert invariant["temporary_skip_is_sequence_only"] is True
    assert invariant["objective_mutation_requires_explicit_operator_ref"] is True
    assert set(invariant["forbidden_inferred_objective_states"]) >= {
        "blocked",
        "skipped",
    }


def test_desktop_commander_skip_preserves_lockfile_objective_and_reroutes(monkeypatch) -> None:
    """CASE A: skip the broken route, never the lockfile objective."""
    kernel = _arm(monkeypatch)
    _bind_lockfile_objective(kernel)

    kernel.select_execution_route(
        "route-selection:desktop-commander",
        route_ref="tool:desktop-commander",
    )
    snapshot = kernel.record_temporary_route_skip(
        "route-skip:desktop-commander",
        route_ref="tool:desktop-commander",
        sequencing_reason="Operator said skip that route for now and keep going",
        alternate_route_ref="control-plane:supabase",
    )

    assert snapshot.phase == "executing"
    state = kernel.route_scope_state()
    assert state["objective_state"] == "active"
    assert state["route_states"]["tool:desktop-commander"] == "temporarily_skipped"
    assert state["route_states"]["control-plane:supabase"] == "selected"
    assert state["selected_route_ref"] == "control-plane:supabase"
    assert state["operator_scope_mutation_ref"] is None

    with pytest.raises(OutcomeFidelityViolation, match="explicit operator-command"):
        kernel.mutate_objective_scope(
            "scope-mutation:bad-inference",
            new_state="deferred",
            operator_scope_mutation_ref="assistant-inference:desktop-route-failed",
        )


def test_provider_timeout_blocks_route_not_objective(monkeypatch) -> None:
    """CASE B: provider timeout is route state; X remains ACTIVE."""
    kernel = _arm(monkeypatch)
    _bind_lockfile_objective(kernel)

    kernel.select_execution_route(
        "route-selection:provider-a",
        route_ref="provider:provider-a",
    )
    snapshot = kernel.record_route_failure(
        "route-failure:provider-a-timeout",
        route_ref="provider:provider-a",
        reason="provider timed out",
        alternate_route_ref="provider:provider-b",
    )

    assert snapshot.phase == "executing"
    state = kernel.route_scope_state()
    assert state["objective_state"] == "active"
    assert state["route_states"]["provider:provider-a"] == "blocked"
    assert state["route_states"]["provider:provider-b"] == "selected"

    with pytest.raises(OutcomeFidelityViolation, match="cannot block the mission"):
        kernel.block(
            "provider A timed out",
            reference="provider-error:timeout",
            blocker_class="provider_failure",
        )

    with pytest.raises(OutcomeFidelityViolation, match="objective state must be active"):
        kernel.mutate_objective_scope(
            "scope-mutation:illegal-skip",
            new_state="skipped",
            operator_scope_mutation_ref="operator-command:keep-going",
        )


def test_explicit_operator_scope_removal_is_allowed(monkeypatch) -> None:
    """CASE C: an explicit Operator mission mutation is a separate legal transition."""
    kernel = _arm(monkeypatch)
    _bind_lockfile_objective(kernel)

    kernel.mutate_objective_scope(
        "scope-mutation:drop-lockfile",
        new_state="removed",
        operator_scope_mutation_ref="operator-command:drop-lockfile-work",
    )
    state = kernel.route_scope_state()
    assert state["objective_state"] == "removed"
    assert state["operator_scope_mutation_ref"] == "operator-command:drop-lockfile-work"

    with pytest.raises(OutcomeFidelityViolation, match="active objective"):
        kernel.record_route_failure(
            "route-failure:after-removal",
            route_ref="provider:any-provider",
            reason="must not continue a removed objective",
        )
