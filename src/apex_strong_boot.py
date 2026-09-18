"""One composed APEX boot path with enrichment-first startup semantics.

This module executes the continuity, Prime Directive, Operator-fidelity,
model-attractor, and APEX startup checks before constructing the post-boot
runtime kernel. Those checks control evidence strength and recovery routing;
they do not acquire mission authority or become global permission gates.

A successful boot means the complete startup check set was attempted and a
runtime kernel exists. Unresolved checks remain attached as diagnostics. The
runtime's task-specific execution, verification, persistence, readback, and
provider/platform consequence controls remain strict.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import os
from threading import RLock
from typing import Any, Callable
from uuid import uuid4

from apex_enforced_startup import (
    automatic_apex_enforced_startup,
    get_in_process_apex_validation,
)
from apex_runtime_kernel import create_verified_runtime_kernel
from model_attractor_defense import (
    automatic_model_attractor_defense,
    get_in_process_model_attractor_validation,
)
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
from outcome_fidelity_runtime import (
    OutcomeFidelityRuntime,
    enforce_outcome_fidelity,
)
from prime_directive_boot import (
    automatic_prime_directive_boot,
    get_in_process_boot_validation,
)
from strict_frontier_preflight import validate_runtime_strict_frontier


MODEL_ATTRACTOR_PREFLIGHT = "model_attractor_defense"
EXPECTED_GATES = (
    "notion_continuity",
    "prime_directive",
    "operator_fidelity_lock",
    "operator_fidelity",
    "apex_startup",
)
EXPECTED_STARTUP_SEQUENCE = (MODEL_ATTRACTOR_PREFLIGHT,) + EXPECTED_GATES
_SESSION_SEAL = object()
_BOOT_LOCK = RLock()
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
    diagnostics: tuple[str, ...]
    runtime_kernel: OutcomeFidelityRuntime = field(repr=False, compare=False)
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
    with _BOOT_LOCK:
        return _IN_PROCESS


def apply_strongest_boot() -> StrongBootSession:
    """Run or recover the composed APEX boot path and return its sealed session.

    The complete check-to-create-to-publish sequence is serialized. Concurrent
    callers therefore observe one process-owned session and one runtime kernel,
    and startup side effects execute at most once after a successful first boot.
    """
    with _BOOT_LOCK:
        return _apply_strongest_boot_locked()


def _apply_strongest_boot_locked() -> StrongBootSession:
    """Build the boot session while `_BOOT_LOCK` is held."""
    global _IN_PROCESS
    if _IN_PROCESS is not None:
        _validate_existing_session(_IN_PROCESS)
        return _IN_PROCESS

    observed: list[str] = []
    diagnostics: list[str] = []

    _run_model_attractor_preflight(diagnostics)

    for name, automatic, getter in _gate_sequence():
        observed.append(name)
        try:
            validation = getter()
            if validation is None:
                issued = automatic()
                current = getter()
                if current is None:
                    if issued is None:
                        diagnostics.append(
                            f"{name}: validation missing after check"
                        )
                        continue
                    validation = issued
                else:
                    if issued is not None and current is not issued:
                        diagnostics.append(
                            f"{name}: check validation identity changed in-process"
                        )
                    validation = current
        except SystemExit as exc:
            diagnostics.append(f"{name}: SystemExit: {exc.code}")
            continue
        except Exception as exc:
            diagnostics.append(f"{name}: {type(exc).__name__}: {exc}")
            continue

        error = _validation_error(name, validation)
        if error is not None:
            diagnostics.append(error)

    gates = tuple(observed)
    if gates != EXPECTED_GATES:
        raise StrongBootViolation(
            "startup check sequence mismatch: " + ", ".join(gates)
        )

    runtime_kernel = enforce_outcome_fidelity(create_verified_runtime_kernel())
    snapshot = runtime_kernel.snapshot()
    if snapshot.phase != "bootstrapped":
        raise StrongBootViolation(
            f"runtime kernel must begin bootstrapped; received {snapshot.phase!r}"
        )
    if snapshot.task_id is not None:
        raise StrongBootViolation("new runtime kernel unexpectedly contains a bound task")
    if snapshot.startup_gates != EXPECTED_GATES:
        raise StrongBootViolation(
            "runtime kernel startup-check set does not match composed boot"
        )
    if runtime_kernel.outcome_state()["recorded"] is not False:
        raise StrongBootViolation("new runtime kernel unexpectedly contains a mission outcome")

    diagnostics.extend(snapshot.startup_diagnostics)
    session = StrongBootSession(
        session_id=str(uuid4()),
        status="complete",
        created_at=datetime.now(UTC),
        gates=gates,
        diagnostics=tuple(dict.fromkeys(diagnostics)),
        runtime_kernel=runtime_kernel,
        _seal=_SESSION_SEAL,
    )
    _IN_PROCESS = session
    os.environ["GLACIEREQ_STRONG_BOOT_STATUS"] = "complete"
    os.environ["GLACIEREQ_STRONG_BOOT_DIAGNOSTIC_COUNT"] = str(
        len(session.diagnostics)
    )
    return session

def _run_model_attractor_preflight(diagnostics: list[str]) -> None:
    """Run frontier/model-attractor checks and preserve unresolved evidence.

    These checks are mandatory observations, not global authorization predicates.
    """
    name = MODEL_ATTRACTOR_PREFLIGHT
    try:
        strict_frontier = validate_runtime_strict_frontier()
    except Exception as exc:
        diagnostics.append(
            f"strict_executable_frontier_authority: {type(exc).__name__}: {exc}"
        )
        return
    if strict_frontier.ok is not True:
        if strict_frontier.errors:
            diagnostics.extend(
                f"strict_executable_frontier_authority: {error}"
                for error in strict_frontier.errors
            )
        else:
            diagnostics.append(
                "strict_executable_frontier_authority: frontier evidence unresolved"
            )
        return

    try:
        validation = get_in_process_model_attractor_validation()
        if validation is None:
            issued = automatic_model_attractor_defense()
            current = get_in_process_model_attractor_validation()
            if current is None:
                if issued is None:
                    diagnostics.append(
                        f"{name}: validation missing after preflight"
                    )
                    return
                validation = issued
            else:
                if issued is not None and current is not issued:
                    diagnostics.append(
                        f"{name}: preflight validation identity changed in-process"
                    )
                validation = current
    except SystemExit as exc:
        diagnostics.append(f"{name}: SystemExit: {exc.code}")
        return
    except Exception as exc:
        diagnostics.append(f"{name}: {type(exc).__name__}: {exc}")
        return

    error = _validation_error(name, validation)
    if error is not None:
        diagnostics.append(error)

def require_strong_boot() -> StrongBootSession:
    """Return the current composed session without rerunning boot."""
    with _BOOT_LOCK:
        session = _IN_PROCESS
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


def _validation_error(name: str, validation: Any) -> str | None:
    if getattr(validation, "ok", None) is not True:
        return f"{name}: validation ok is not true"
    if getattr(validation, "status", None) != "complete":
        return f"{name}: validation status is {getattr(validation, 'status', None)!r}"
    return None


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
