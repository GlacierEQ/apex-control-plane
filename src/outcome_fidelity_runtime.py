"""Fail-closed postcondition and route/scope fidelity runtime for APEX.

The verified kernel proves that work was executed, tested, verified, persisted,
and read back. This wrapper additionally proves two independent invariants:

1. assistant activity is not mission progress; and
2. a route is not the mission.

A tool/provider/path failure may mutate route state, but it cannot defer, remove,
skip, or otherwise narrow the Operator's objective. A temporary route skip is
sequencing only. Objective deferment/removal requires explicit source-bearing
Operator authority.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from apex_runtime_kernel import ApexRuntimeKernel, RuntimePhase, RuntimeViolation, TaskMode
from route_scope_fidelity import (
    ObjectiveState,
    RouteScopeFidelity,
    RouteScopeViolation,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_PATH = REPO_ROOT / "config" / "outcome_fidelity_policy.json"


class OutcomeFidelityViolation(RuntimeViolation):
    """Raised when assistant activity or route state is presented as mission state."""


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OutcomeFidelityViolation(f"{field_name} must be non-empty")
    return value.strip()


def _require_ref(value: str, field_name: str) -> str:
    ref = _require_text(value, field_name)
    prefix, sep, locator = ref.partition(":")
    if not sep or not prefix.strip() or not locator.strip():
        raise OutcomeFidelityViolation(
            f"{field_name} must use provider-or-kind:locator form"
        )
    return ref


def _validated_refs(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    return tuple(_require_ref(value, field_name) for value in values)


def load_outcome_fidelity_policy(
    path: str | Path = DEFAULT_POLICY_PATH,
) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise OutcomeFidelityViolation(
            f"outcome fidelity policy not found: {target}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise OutcomeFidelityViolation(
            f"invalid outcome fidelity policy JSON: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise OutcomeFidelityViolation("outcome fidelity policy must be a JSON object")
    required = {
        "schema_version",
        "fail_closed",
        "required_for_mutation",
        "allowed_transition_kinds",
        "activity_only_transition_kinds",
        "activity_only_evidence_prefixes",
        "boundary_transition_kind",
        "state_transition_requires_distinct_before_after",
        "state_transition_requires_evidence",
        "boundary_requires_routes_exhausted",
        "boundary_requires_reason",
        "boundary_requires_evidence",
        "route_scope_invariant",
    }
    missing = sorted(required - payload.keys())
    if missing:
        raise OutcomeFidelityViolation(
            "outcome fidelity policy missing: " + ", ".join(missing)
        )
    if payload.get("fail_closed") is not True:
        raise OutcomeFidelityViolation("outcome fidelity policy must fail closed")
    if payload.get("required_for_mutation") is not True:
        raise OutcomeFidelityViolation(
            "outcome fidelity must remain required for mutation"
        )

    allowed = payload.get("allowed_transition_kinds")
    activity = payload.get("activity_only_transition_kinds")
    prefixes = payload.get("activity_only_evidence_prefixes")
    if not isinstance(allowed, list) or not allowed:
        raise OutcomeFidelityViolation("allowed_transition_kinds must be non-empty")
    if not isinstance(activity, list) or not activity:
        raise OutcomeFidelityViolation(
            "activity_only_transition_kinds must be non-empty"
        )
    if not isinstance(prefixes, list) or not prefixes:
        raise OutcomeFidelityViolation(
            "activity_only_evidence_prefixes must be non-empty"
        )
    overlap = set(allowed) & set(activity)
    if overlap:
        raise OutcomeFidelityViolation(
            "transition kinds cannot be both allowed and activity-only: "
            + ", ".join(sorted(overlap))
        )

    route_policy = payload.get("route_scope_invariant")
    if not isinstance(route_policy, Mapping):
        raise OutcomeFidelityViolation("route_scope_invariant must be an object")
    try:
        RouteScopeFidelity(route_policy)
    except RouteScopeViolation as exc:
        raise OutcomeFidelityViolation(str(exc)) from exc
    return payload


class OutcomeFidelityRuntime:
    """Verified-kernel proxy that hard-locks mission and route/scope semantics."""

    def __init__(
        self,
        kernel: ApexRuntimeKernel,
        policy: Mapping[str, Any] | None = None,
    ) -> None:
        # Production strong boot supplies ApexRuntimeKernel. Duck-typed test
        # doubles are deliberately allowed so boot sequencing tests remain
        # isolated from runtime internals.
        self._kernel = kernel
        self._policy = dict(policy or load_outcome_fidelity_policy())
        route_policy = self._policy.get("route_scope_invariant")
        if not isinstance(route_policy, Mapping):
            raise OutcomeFidelityViolation("route_scope_invariant must be an object")
        try:
            self._route_scope = RouteScopeFidelity(route_policy)
        except RouteScopeViolation as exc:
            raise OutcomeFidelityViolation(str(exc)) from exc
        self._outcome_recorded = False
        self._outcome_kind: str | None = None
        self._outcome_reference: str | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._kernel, name)

    @property
    def runtime_id(self) -> str:
        return self._kernel.runtime_id

    @property
    def phase(self) -> RuntimePhase:
        return self._kernel.phase

    def bind_task(self, **kwargs: Any):
        self._outcome_recorded = False
        self._outcome_kind = None
        self._outcome_reference = None
        self._route_scope.reset()
        return self._kernel.bind_task(**kwargs)

    def select_execution_route(
        self,
        reference: str,
        *,
        route_ref: str,
        details: Mapping[str, Any] | None = None,
    ):
        """Select an execution route without changing Operator-owned mission state."""
        receipt_ref = _require_ref(reference, "reference")
        route = _require_ref(route_ref, "route_ref")
        try:
            state = self._route_scope.select_route(route)
        except RouteScopeViolation as exc:
            raise OutcomeFidelityViolation(str(exc)) from exc
        payload = dict(details or {})
        payload.update(
            {
                "route_ref": route,
                "route_state": "selected",
                "objective_state": state.objective_state,
            }
        )
        self._kernel._record_receipt("route_selection", receipt_ref, True, payload)
        self._kernel._audit_event("execution_route_selected")
        return self._kernel.snapshot()

    def record_route_failure(
        self,
        reference: str,
        *,
        route_ref: str,
        reason: str,
        alternate_route_ref: str | None = None,
        details: Mapping[str, Any] | None = None,
    ):
        """Mark only the failed route BLOCKED; leave the objective ACTIVE."""
        receipt_ref = _require_ref(reference, "reference")
        route = _require_ref(route_ref, "route_ref")
        reason_text = _require_text(reason, "reason")
        alternate = (
            _require_ref(alternate_route_ref, "alternate_route_ref")
            if alternate_route_ref is not None
            else None
        )
        try:
            state = self._route_scope.block_route(
                route,
                alternate_route_ref=alternate,
            )
        except RouteScopeViolation as exc:
            raise OutcomeFidelityViolation(str(exc)) from exc
        payload = dict(details or {})
        payload.update(
            {
                "route_ref": route,
                "route_state": "blocked",
                "reason": reason_text,
                "alternate_route_ref": alternate,
                "objective_state": state.objective_state,
                "scope_mutated": False,
            }
        )
        self._kernel._record_receipt("route_failure", receipt_ref, False, payload)
        if alternate is not None:
            self._kernel._record_receipt(
                "route_selection",
                f"route-selection:{alternate.split(':', 1)[1]}",
                True,
                {
                    "route_ref": alternate,
                    "objective_state": state.objective_state,
                    "selected_after_route_failure": True,
                },
            )
        self._kernel._audit_event("route_failure_recorded_objective_preserved")
        return self._kernel.snapshot()

    def record_temporary_route_skip(
        self,
        reference: str,
        *,
        route_ref: str,
        sequencing_reason: str,
        alternate_route_ref: str | None = None,
        details: Mapping[str, Any] | None = None,
    ):
        """Record sequencing change only; never infer deferment/removal."""
        receipt_ref = _require_ref(reference, "reference")
        route = _require_ref(route_ref, "route_ref")
        reason_text = _require_text(sequencing_reason, "sequencing_reason")
        alternate = (
            _require_ref(alternate_route_ref, "alternate_route_ref")
            if alternate_route_ref is not None
            else None
        )
        try:
            state = self._route_scope.temporarily_skip_route(
                route,
                alternate_route_ref=alternate,
            )
        except RouteScopeViolation as exc:
            raise OutcomeFidelityViolation(str(exc)) from exc
        payload = dict(details or {})
        payload.update(
            {
                "route_ref": route,
                "route_state": "temporarily_skipped",
                "sequencing_reason": reason_text,
                "alternate_route_ref": alternate,
                "objective_state": state.objective_state,
                "scope_mutated": False,
                "sequencing_only": True,
            }
        )
        self._kernel._record_receipt("route_temporary_skip", receipt_ref, True, payload)
        if alternate is not None:
            self._kernel._record_receipt(
                "route_selection",
                f"route-selection:{alternate.split(':', 1)[1]}",
                True,
                {
                    "route_ref": alternate,
                    "objective_state": state.objective_state,
                    "selected_after_temporary_skip": True,
                },
            )
        self._kernel._audit_event("route_temporarily_skipped_objective_preserved")
        return self._kernel.snapshot()

    def mutate_objective_scope(
        self,
        reference: str,
        *,
        new_state: str,
        operator_scope_mutation_ref: str,
        details: Mapping[str, Any] | None = None,
    ):
        """Apply explicit Operator deferment/removal as a separate authority event."""
        receipt_ref = _require_ref(reference, "reference")
        try:
            state = self._route_scope.mutate_objective(
                new_state,
                operator_scope_mutation_ref=operator_scope_mutation_ref,
            )
        except RouteScopeViolation as exc:
            raise OutcomeFidelityViolation(str(exc)) from exc
        payload = dict(details or {})
        payload.update(
            {
                "objective_state": state.objective_state,
                "operator_scope_mutation_ref": state.operator_scope_mutation_ref,
                "explicit_operator_scope_mutation": True,
            }
        )
        self._kernel._record_receipt(
            "objective_scope_mutation",
            receipt_ref,
            True,
            payload,
        )
        self._kernel._audit_event("objective_scope_mutated_by_operator")
        return self._kernel.snapshot()

    def block(
        self,
        reason: str,
        *,
        reference: str,
        blocker_class: str | None = None,
    ):
        """Block the task only for typed task/objective blockers.

        A declared route failure or route skip is rejected here because those
        transitions must use record_route_failure/record_temporary_route_skip,
        which preserve objective ACTIVE and keep the current execution phase.
        """
        classification = _require_text(blocker_class, "blocker_class").lower()
        if classification in {
            "route",
            "route_failure",
            "tool_failure",
            "provider_failure",
            "temporary_route_skip",
        }:
            raise OutcomeFidelityViolation(
                "route-level blocker cannot block the mission; record route state and continue/reroute"
            )
        if classification not in {
            "task_failure",
            "objective_blocker",
            "genuine_external_boundary",
        }:
            raise OutcomeFidelityViolation(
                "blocker_class must be task_failure, objective_blocker, or genuine_external_boundary"
            )
        return self._kernel.block(reason, reference=reference)

    def record_mission_outcome(
        self,
        reference: str,
        *,
        transition_kind: str,
        before_state_ref: str,
        after_state_ref: str | None = None,
        evidence_refs: Sequence[str] = (),
        routes_exhausted: bool = False,
        boundary_reason: str | None = None,
        details: Mapping[str, Any] | None = None,
    ):
        """Record the mission-domain postcondition after verification."""
        task = self._kernel.task
        if task.mode is not TaskMode.MUTATION:
            raise OutcomeFidelityViolation(
                "mission outcome receipt applies only to mutation work"
            )
        if self._kernel.phase is not RuntimePhase.VERIFIED:
            raise OutcomeFidelityViolation(
                "mission outcome must be recorded after successful verification and before persistence"
            )
        if self._outcome_recorded:
            raise OutcomeFidelityViolation(
                "mission outcome already recorded for active task"
            )
        if self._route_scope.objective_state is not ObjectiveState.ACTIVE:
            raise OutcomeFidelityViolation(
                "inactive Operator objective cannot be presented as newly completed mission progress"
            )

        ref = _require_ref(reference, "reference")
        kind = _require_text(transition_kind, "transition_kind").lower()
        before_ref = _require_ref(before_state_ref, "before_state_ref")
        evidence = _validated_refs(evidence_refs, "evidence_ref")

        activity_only = set(self._policy["activity_only_transition_kinds"])
        allowed = set(self._policy["allowed_transition_kinds"])
        if kind in activity_only:
            raise OutcomeFidelityViolation(
                f"assistant activity is not mission progress: {kind}"
            )
        if kind not in allowed:
            raise OutcomeFidelityViolation(
                f"transition_kind is not an allowed mission outcome: {kind}"
            )

        boundary_kind = str(self._policy["boundary_transition_kind"]).strip().lower()
        if kind == boundary_kind:
            if (
                self._policy["boundary_requires_routes_exhausted"] is True
                and routes_exhausted is not True
            ):
                raise OutcomeFidelityViolation(
                    "genuine external boundary requires routes_exhausted=true"
                )
            if self._policy["boundary_requires_reason"] is True:
                _require_text(boundary_reason, "boundary_reason")
            if self._policy["boundary_requires_evidence"] is True and not evidence:
                raise OutcomeFidelityViolation(
                    "genuine external boundary requires source-bearing evidence"
                )
            normalized_after = None
        else:
            normalized_after = _require_ref(after_state_ref or "", "after_state_ref")
            if (
                self._policy["state_transition_requires_distinct_before_after"] is True
                and normalized_after == before_ref
            ):
                raise OutcomeFidelityViolation(
                    "mission state did not change: before_state_ref equals after_state_ref"
                )
            if self._policy["state_transition_requires_evidence"] is True and not evidence:
                raise OutcomeFidelityViolation(
                    "mission state transition requires source-bearing evidence"
                )
            if routes_exhausted:
                raise OutcomeFidelityViolation(
                    "routes_exhausted is reserved for genuine external boundary outcomes"
                )

        if evidence:
            activity_prefixes = {
                str(value).strip().lower()
                for value in self._policy["activity_only_evidence_prefixes"]
            }
            evidence_prefixes = {
                item.split(":", 1)[0].strip().lower() for item in evidence
            }
            if evidence_prefixes and evidence_prefixes <= activity_prefixes:
                raise OutcomeFidelityViolation(
                    "mission outcome cannot be proved solely by assistant-authored activity artifacts"
                )

        receipt_details = {
            "transition_kind": kind,
            "before_state_ref": before_ref,
            "after_state_ref": normalized_after,
            "evidence_refs": list(evidence),
            "routes_exhausted": bool(routes_exhausted),
            "boundary_reason": boundary_reason,
            "details": dict(details or {}),
        }
        self._kernel._record_receipt(
            "mission_outcome",
            ref,
            True,
            receipt_details,
        )
        self._outcome_recorded = True
        self._outcome_kind = kind
        self._outcome_reference = ref
        self._kernel._audit_event("mission_outcome_recorded")
        return self._kernel.snapshot()

    def begin_persistence(self):
        task = self._kernel.task
        if task.mode is TaskMode.MUTATION and self._route_scope.objective_state is not ObjectiveState.ACTIVE:
            raise OutcomeFidelityViolation(
                "inactive/deferred Operator objective cannot persist as completed mission work"
            )
        if task.mode is TaskMode.MUTATION and not self._outcome_recorded:
            raise OutcomeFidelityViolation(
                "mutation cannot persist: no verified mission-state transition or genuine external boundary was recorded"
            )
        return self._kernel.begin_persistence()

    def record_readback(self, *args: Any, **kwargs: Any):
        task = self._kernel.task
        if task.mode is TaskMode.MUTATION and not self._outcome_recorded:
            raise OutcomeFidelityViolation(
                "mutation cannot complete: mission outcome postcondition is missing"
            )
        return self._kernel.record_readback(*args, **kwargs)

    def route_scope_state(self) -> dict[str, Any]:
        state = self._route_scope.snapshot()
        return {
            "objective_state": state.objective_state,
            "selected_route_ref": state.selected_route_ref,
            "route_states": dict(state.route_states),
            "operator_scope_mutation_ref": state.operator_scope_mutation_ref,
        }

    def outcome_state(self) -> dict[str, Any]:
        return {
            "recorded": self._outcome_recorded,
            "transition_kind": self._outcome_kind,
            "reference": self._outcome_reference,
            "route_scope": self.route_scope_state(),
        }


def enforce_outcome_fidelity(
    kernel: ApexRuntimeKernel,
    policy: Mapping[str, Any] | None = None,
) -> OutcomeFidelityRuntime:
    """Wrap the verified kernel in mandatory mission and route/scope boundaries."""
    return OutcomeFidelityRuntime(kernel, policy)
