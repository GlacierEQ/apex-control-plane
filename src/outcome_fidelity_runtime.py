"""Mission-outcome measurement and uplift for APEX mutation work.

This wrapper preserves the crucial distinction between assistant activity and an
actual mission-state transition. The distinction now improves execution instead
of acting as a persistence gate:

* real mission transitions are recorded with source-bearing evidence;
* activity-only/intermediate gains are preserved but never mislabeled as the
  mission outcome;
* missing or weak outcome proof becomes an uplift finding that drives the next
  material frontier;
* persistence/readback remain available so useful verified work is not erased.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from apex_runtime_kernel import ApexRuntimeKernel, RuntimePhase, RuntimeViolation, TaskMode


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_PATH = REPO_ROOT / "config" / "outcome_fidelity_policy.json"


class OutcomeFidelityViolation(RuntimeViolation):
    """Raised only for malformed outcome inputs or impossible lifecycle usage."""


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

    semantics = str(payload.get("execution_semantics", "")).strip()
    if semantics and semantics != "measure_progress_enrich_next_action_never_erase_execution":
        raise OutcomeFidelityViolation("unsupported outcome fidelity execution_semantics")
    if payload.get("fail_closed") is True and semantics:
        raise OutcomeFidelityViolation(
            "outcome fidelity cannot retain fail-closed authority under uplift semantics"
        )

    allowed = payload.get("allowed_transition_kinds")
    activity = payload.get("activity_only_transition_kinds")
    prefixes = payload.get("activity_only_evidence_prefixes")
    if not isinstance(allowed, list) or not allowed:
        raise OutcomeFidelityViolation("allowed_transition_kinds must be non-empty")
    if not isinstance(activity, list) or not activity:
        raise OutcomeFidelityViolation("activity_only_transition_kinds must be non-empty")
    if not isinstance(prefixes, list) or not prefixes:
        raise OutcomeFidelityViolation("activity_only_evidence_prefixes must be non-empty")
    overlap = set(allowed) & set(activity)
    if overlap:
        raise OutcomeFidelityViolation(
            "transition kinds cannot be both mission outcomes and activity-only: "
            + ", ".join(sorted(overlap))
        )
    return payload


class OutcomeFidelityRuntime:
    """Verified-kernel proxy that measures mission progress and drives uplift."""

    def __init__(
        self,
        kernel: ApexRuntimeKernel,
        policy: Mapping[str, Any] | None = None,
    ) -> None:
        self._kernel = kernel
        self._policy = dict(policy or load_outcome_fidelity_policy())
        self._outcome_recorded = False
        self._outcome_kind: str | None = None
        self._outcome_reference: str | None = None
        self._outcome_findings: list[str] = []

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
        self._outcome_findings.clear()
        return self._kernel.bind_task(**kwargs)

    def _finding(
        self,
        message: str,
        *,
        reference: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        if message not in self._outcome_findings:
            self._outcome_findings.append(message)
        if reference is not None:
            self._kernel._record_receipt(
                "outcome_uplift",
                reference,
                False,
                {"finding": message, **dict(details or {})},
            )
        self._kernel._audit_event("mission_outcome_uplift_required")

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
        """Evaluate a candidate mission outcome without erasing useful work."""
        task = self._kernel.task
        if task.mode is not TaskMode.MUTATION:
            raise OutcomeFidelityViolation(
                "mission outcome receipt applies only to mutation work"
            )
        if self._kernel.phase is not RuntimePhase.VERIFIED:
            raise OutcomeFidelityViolation(
                "mission outcome is measured after verification and before persistence"
            )
        if self._outcome_recorded:
            raise OutcomeFidelityViolation("mission outcome already recorded for active task")

        ref = _require_ref(reference, "reference")
        kind = _require_text(transition_kind, "transition_kind").lower()
        before_ref = _require_ref(before_state_ref, "before_state_ref")
        evidence = _validated_refs(evidence_refs, "evidence_ref")
        normalized_after: str | None = None

        activity_only = set(self._policy["activity_only_transition_kinds"])
        allowed = set(self._policy["allowed_transition_kinds"])
        if kind in activity_only:
            self._finding(
                f"activity-only gain is not yet the mission outcome: {kind}",
                reference=ref,
                details={"transition_kind": kind},
            )
            return self._kernel.snapshot()
        if kind not in allowed:
            self._finding(
                f"unrecognized mission outcome kind requires classification: {kind}",
                reference=ref,
                details={"transition_kind": kind},
            )
            return self._kernel.snapshot()

        boundary_kind = str(self._policy["boundary_transition_kind"]).strip().lower()
        if kind == boundary_kind:
            if (
                self._policy["boundary_requires_routes_exhausted"] is True
                and routes_exhausted is not True
            ):
                self._finding(
                    "external-boundary claim needs evidence that meaningful internal routes were exhausted",
                    reference=ref,
                )
                return self._kernel.snapshot()
            if self._policy["boundary_requires_reason"] is True and not str(
                boundary_reason or ""
            ).strip():
                self._finding(
                    "external-boundary claim needs a concrete boundary reason",
                    reference=ref,
                )
                return self._kernel.snapshot()
            if self._policy["boundary_requires_evidence"] is True and not evidence:
                self._finding(
                    "external-boundary claim needs source-bearing evidence",
                    reference=ref,
                )
                return self._kernel.snapshot()
        else:
            normalized_after = _require_ref(after_state_ref or "", "after_state_ref")
            if (
                self._policy["state_transition_requires_distinct_before_after"] is True
                and normalized_after == before_ref
            ):
                self._finding(
                    "candidate outcome did not change mission state; preserve the gain and continue",
                    reference=ref,
                )
                return self._kernel.snapshot()
            if self._policy["state_transition_requires_evidence"] is True and not evidence:
                self._finding(
                    "candidate mission transition needs source-bearing evidence",
                    reference=ref,
                )
                return self._kernel.snapshot()
            if routes_exhausted:
                self._finding(
                    "routes_exhausted applies only to genuine external boundaries",
                    reference=ref,
                )
                return self._kernel.snapshot()

        if evidence:
            activity_prefixes = {
                str(value).strip().lower()
                for value in self._policy["activity_only_evidence_prefixes"]
            }
            evidence_prefixes = {
                item.split(":", 1)[0].strip().lower() for item in evidence
            }
            if evidence_prefixes and evidence_prefixes <= activity_prefixes:
                self._finding(
                    "candidate outcome is supported only by assistant-authored activity artifacts",
                    reference=ref,
                )
                return self._kernel.snapshot()

        receipt_details = {
            "transition_kind": kind,
            "before_state_ref": before_ref,
            "after_state_ref": normalized_after,
            "evidence_refs": list(evidence),
            "routes_exhausted": bool(routes_exhausted),
            "boundary_reason": boundary_reason,
            "details": dict(details or {}),
        }
        self._kernel._record_receipt("mission_outcome", ref, True, receipt_details)
        self._outcome_recorded = True
        self._outcome_kind = kind
        self._outcome_reference = ref
        self._kernel._audit_event("mission_outcome_recorded")
        return self._kernel.snapshot()

    def begin_persistence(self):
        task = self._kernel.task
        if task.mode is TaskMode.MUTATION and not self._outcome_recorded:
            self._finding(
                "mission outcome not yet demonstrated; persist verified intermediate gain and continue upward"
            )
        return self._kernel.begin_persistence()

    def record_readback(self, *args: Any, **kwargs: Any):
        task = self._kernel.task
        if task.mode is TaskMode.MUTATION and not self._outcome_recorded:
            self._finding(
                "mission outcome remains open after this intermediate execution; select next material frontier"
            )
        return self._kernel.record_readback(*args, **kwargs)

    def outcome_state(self) -> dict[str, Any]:
        return {
            "recorded": self._outcome_recorded,
            "transition_kind": self._outcome_kind,
            "reference": self._outcome_reference,
            "uplift_required": bool(self._outcome_findings),
            "findings": tuple(self._outcome_findings),
        }


def enforce_outcome_fidelity(
    kernel: ApexRuntimeKernel,
    policy: Mapping[str, Any] | None = None,
) -> OutcomeFidelityRuntime:
    """Wrap the kernel with mission-progress measurement, not a permission gate."""
    return OutcomeFidelityRuntime(kernel, policy)
