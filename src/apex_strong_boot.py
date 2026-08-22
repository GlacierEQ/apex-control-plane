"""Single fail-closed boot path for every compatible APEX runtime entrypoint.

This module composes the existing continuity, Prime Directive, Operator-fidelity,
and APEX startup proofs with the verified post-boot runtime kernel. It does not
replace those mechanisms. It removes a weaker condition that previously existed:
`control_plane.py` created the verified runtime kernel, while `sitecustomize.py`
only ran the startup gates.

A successful strong boot therefore means one thing everywhere: all five sealed
in-process startup gates are complete and the verified runtime kernel exists.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import os
from typing import Any, Callable
from uuid import uuid4

from apex_enforced_startup import (
    automatic_apex_enforced_startup,
    get_in_process_apex_validation,
)
from apex_runtime_kernel import ApexRuntimeKernel, create_verified_runtime_kernel
from notion_continuity_gate import (
    automatic_notion_continuity_preflight,
    get_in_process_notion_validation,
)
from operator_fidelity_lock import (
    automatic_operator_fidelity_lock,
    get_in_process_operator_fidelity_lock,
)
from operator_fidelity_preflight import (
    automatic_operator_fidelity_preflight,
    get_in_process_operator_fidelity_validation,
)
from prime_directive_boot import (
    automatic_prime_directive_boot,
    get_in_process_boot_validation,
)


EXIT_BOOT_BLOCKED = 78
EXPECTED_GATES = (
    "notion_continuity",
    "prime_directive",
    "operator_fidelity_lock",
    "operator_fidelity",
    "apex_startup",
)
_SESSION_SEAL = object()
_IN_PROCESS: StrongBootSession | None = None


class StrongBootViolation(RuntimeError):
    """Raised when the complete boot chain cannot be proved in-process."""


@dataclass(frozen=True, slots=True)
class StrongBootSession:
    """Sealed proof that the complete APEX boot chain and runtime kernel exist."""

    session_id: str
    status: str
    created_at: datetime
    gates: tuple[str, ...]
    runtime_kernel: ApexRuntimeKernel = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _SESSION_SEAL:
            raise TypeError("StrongBootSession must be issued by apply_strongest_boot")
        if self.status != "complete":
            raise ValueError("StrongBootSession status must be complete")
        if self.created_at.tzinfo is None:
            raise ValueError("StrongBootSession.created_at must be timezone-aware")
        if self.gates != EXPECTED_GATES:
            raise ValueError("StrongBootSession gate sequence is incomplete")

    @property
    def runtime_id(self) -> str:
        return self.runtime_kernel.runtime_id


def get_in_process_strong_boot() -> StrongBootSession | None:
    return _IN_PROCESS


def apply_strongest_boot() -> StrongBootSession:
    """Run or recover the one complete APEX boot path and return its sealed session.

    The function is idempotent inside a process. No caller-controlled environment
    status can satisfy a stage. Each stage must expose a complete in-process
    validation object, and the runtime kernel factory independently checks those
    same gate objects again before it can construct the kernel.
    """
    global _IN_PROCESS
    if _IN_PROCESS is not None:
        _validate_existing_session(_IN_PROCESS)
        return _IN_PROCESS

    completed: list[str] = []
    for name, automatic, getter in _gate_sequence():
        validation = getter()
        if validation is None:
            validation = automatic()
        current = getter()
        if current is None:
            raise StrongBootViolation(f"{name}: in-process validation missing after boot")
        if validation is not None and current is not validation:
            raise StrongBootViolation(f"{name}: boot validation identity changed in-process")
        _require_complete_validation(name, current)
        completed.append(name)

    gates = tuple(completed)
    if gates != EXPECTED_GATES:
        raise StrongBootViolation(
            "strong boot gate sequence mismatch: " + ", ".join(gates)
        )

    runtime_kernel = create_verified_runtime_kernel()
    snapshot = runtime_kernel.snapshot()
    if snapshot.phase != "bootstrapped":
        raise StrongBootViolation(
            f"runtime kernel must begin bootstrapped; received {snapshot.phase!r}"
        )
    if snapshot.task_id is not None:
        raise StrongBootViolation("new runtime kernel unexpectedly contains a bound task")
    if snapshot.startup_gates != EXPECTED_GATES:
        raise StrongBootViolation("runtime kernel startup-gate proof does not match strong boot")

    session = StrongBootSession(
        session_id=str(uuid4()),
        status="complete",
        created_at=datetime.now(UTC),
        gates=gates,
        runtime_kernel=runtime_kernel,
        _seal=_SESSION_SEAL,
    )
    _IN_PROCESS = session
    os.environ["GLACIEREQ_STRONG_BOOT_STATUS"] = "complete"
    return session


def require_strong_boot() -> StrongBootSession:
    """Return the current complete session or fail closed without running boot."""
    session = get_in_process_strong_boot()
    if session is None:
        raise StrongBootViolation("strong boot session has not been established")
    _validate_existing_session(session)
    return session


def _validate_existing_session(session: StrongBootSession) -> None:
    if not isinstance(session, StrongBootSession) or session._seal is not _SESSION_SEAL:
        raise StrongBootViolation("strong boot session is not authentic")
    if session.status != "complete" or session.gates != EXPECTED_GATES:
        raise StrongBootViolation("strong boot session is incomplete")
    snapshot = session.runtime_kernel.snapshot()
    if snapshot.startup_gates != EXPECTED_GATES:
        raise StrongBootViolation("strong boot runtime kernel lost startup-gate binding")


def _require_complete_validation(name: str, validation: Any) -> None:
    if getattr(validation, "ok", None) is not True:
        raise StrongBootViolation(f"{name}: validation ok is not true")
    if getattr(validation, "status", None) != "complete":
        raise StrongBootViolation(
            f"{name}: validation status is {getattr(validation, 'status', None)!r}"
        )


def _gate_sequence() -> tuple[
    tuple[str, Callable[[], Any], Callable[[], Any]], ...
]:
    return (
        (
            "notion_continuity",
            automatic_notion_continuity_preflight,
            get_in_process_notion_validation,
        ),
        (
            "prime_directive",
            automatic_prime_directive_boot,
            get_in_process_boot_validation,
        ),
        (
            "operator_fidelity_lock",
            automatic_operator_fidelity_lock,
            get_in_process_operator_fidelity_lock,
        ),
        (
            "operator_fidelity",
            automatic_operator_fidelity_preflight,
            get_in_process_operator_fidelity_validation,
        ),
        (
            "apex_startup",
            automatic_apex_enforced_startup,
            get_in_process_apex_validation,
        ),
    )
