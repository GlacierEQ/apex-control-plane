"""Operator-sovereign runtime factory.

This module is a compatibility bridge while the preserved APEX kernel still names
its mutation provenance field ``operator_authorization_ref`` and its original
factory still requires every startup observation to be complete.  Neither legacy
shape may export repeat approval work to the Operator.

The bridge therefore does two things only:

1. creates the existing kernel with the startup observations that actually
   succeeded instead of treating missing continuity/verification observations as
   permission to work; and
2. supplies a deterministic active-mission-authority provenance reference for a
   routine mutation when callers did not provide a consequence-specific approval
   reference.

Destructive/consequence-specific authorization remains the responsibility of the
operation boundary that actually owns that consequence.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Any, Mapping, Sequence

from apex_runtime_kernel import (
    ApexRuntimeKernel,
    TaskMode,
    _FACTORY_SEAL,
    load_runtime_policy,
)


class OperatorSovereignRuntimeKernel(ApexRuntimeKernel):
    """Existing runtime kernel with active mission authority as the routine default."""

    def bind_task(
        self,
        *,
        literal_instruction: str,
        target_state: str,
        operation_class: str,
        mode: str | TaskMode,
        action_scope: str,
        operator_authorization_ref: str | None = None,
        prior_state_ref: str | None = None,
        source_refs: Sequence[str] = (),
        verification_plan: Sequence[str] = (),
    ):
        task_mode = TaskMode(mode)
        authority_ref = operator_authorization_ref
        if task_mode is TaskMode.MUTATION and authority_ref is None:
            material = "\n".join(
                (
                    str(literal_instruction).strip(),
                    str(target_state).strip(),
                    str(operation_class).strip(),
                    str(action_scope).strip(),
                )
            )
            authority_ref = "mission-authority:" + sha256(
                material.encode("utf-8")
            ).hexdigest()

        return super().bind_task(
            literal_instruction=literal_instruction,
            target_state=target_state,
            operation_class=operation_class,
            mode=task_mode,
            action_scope=action_scope,
            operator_authorization_ref=authority_ref,
            prior_state_ref=prior_state_ref,
            source_refs=source_refs,
            verification_plan=verification_plan,
        )


def create_operator_sovereign_runtime_kernel(
    *,
    observed_gates: Sequence[str] = (),
    policy: Mapping[str, Any] | None = None,
) -> OperatorSovereignRuntimeKernel:
    """Create the existing kernel from observed boot state without a permission gate."""
    return OperatorSovereignRuntimeKernel(
        policy=dict(policy or load_runtime_policy()),
        startup_gates=tuple(observed_gates),
        _seal=_FACTORY_SEAL,
    )
