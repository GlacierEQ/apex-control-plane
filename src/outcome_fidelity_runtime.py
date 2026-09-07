"""Fail-closed postcondition gate for APEX mutation work.

The existing runtime proves that work was executed, tested, verified, persisted,
and read back. That lifecycle is necessary but insufficient: assistant-authored
artifacts can satisfy those mechanics while the Operator's underlying mission
state remains unchanged.

This wrapper closes that gap. Mutation work cannot enter persistence until it has
an explicit, source-bearing mission outcome proving either:

1. a substantive transition in the underlying mission state; or
2. exhaustion of materially available internal routes to a genuine external
   boundary.

Creating a ledger, matrix, packet, summary, report, plan, commit, or task update
is never accepted as the mission outcome merely because it is durable or tested.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from apex_runtime_kernel import ApexRuntimeKernel, RuntimePhase, RuntimeViolation, TaskMode


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_PATH = REPO_ROOT / "config" / "outcome_fidelity_policy.json"


class OutcomeFidelityViolation(RuntimeViolation):
    """Raised when assistant activity is presented as mission progress."""


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
    return payload


class OutcomeFidelityRuntime:
    """Verified-kernel proxy that hard-locks mission postconditions."""

    def __init__(
        self,
        kernel: ApexRuntimeKernel,
        policy: Mapping[str, Any] | None = None,
    ) -> None:
        # Production strong boot supplies ApexRuntimeKernel. Duck-typed test
        # doubles are deliberately allowed so the boot sequencing tests can stay
        # isolated from runtime internals; execution-path methods still fail if a
        # double lacks the verified kernel contract they call.
        self._kernel = kernel
        self._policy = dict(policy or load_outcome_fidelity_policy())
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
        return self._kernel.bind_task(**kwargs)

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
        """Record the mission-domain postcondition after verification.

        Normal transitions require distinct source-bearing before/after state and
        evidence beyond assistant activity. A genuine external boundary may leave
        domain state unchanged, but only after available internal routes are
        explicitly exhausted and the boundary itself is evidenced.
        """
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

    def outcome_state(self) -> dict[str, Any]:
        return {
            "recorded": self._outcome_recorded,
            "transition_kind": self._outcome_kind,
            "reference": self._outcome_reference,
        }


def enforce_outcome_fidelity(
    kernel: ApexRuntimeKernel,
    policy: Mapping[str, Any] | None = None,
) -> OutcomeFidelityRuntime:
    """Wrap the verified kernel in the mandatory mission postcondition boundary."""
    return OutcomeFidelityRuntime(kernel, policy)
