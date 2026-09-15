"""Operator-sovereign APEX boot and runtime binding.

Boot checks protect fidelity, continuity, provenance, and observability, but ordinary
missing/stale proof is not permission to work. The boot path therefore runs every
existing check in request/degraded mode, records what is proven and what remains
unresolved, and still creates the runtime so the system can recover while working.

An explicit attempt to disable the Operator-fidelity hard lock remains terminal.
That is an integrity boundary: it protects the Operator's instruction rather than
making the Operator service the system.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
import os
from threading import RLock
from typing import Any, Callable, Iterator
from uuid import uuid4

from apex_enforced_startup import (
    automatic_apex_enforced_startup,
    get_in_process_apex_validation,
)
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
from operator_sovereign_runtime import create_operator_sovereign_runtime_kernel
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
    """Raised only when boot/runtime integrity itself cannot be established."""


@dataclass(frozen=True, slots=True)
class StrongBootSession:
    """Sealed boot observation bound to the process-owned runtime kernel."""

    session_id: str
    status: str
    created_at: datetime
    gates: tuple[str, ...]
    observations: tuple[str, ...]
    runtime_kernel: OutcomeFidelityRuntime = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _SESSION_SEAL:
            raise TypeError("StrongBootSession must be issued by apply_strongest_boot")
        if self.status not in {"complete", "degraded"}:
            raise ValueError("StrongBootSession status must be complete or degraded")
        if self.created_at.tzinfo is None:
            raise ValueError("StrongBootSession.created_at must be timezone-aware")
        unknown = [name for name in self.gates if name not in EXPECTED_GATES]
        if unknown:
            raise ValueError("StrongBootSession contains unknown startup observations")
        expected_subset = tuple(name for name in EXPECTED_GATES if name in self.gates)
        if self.gates != expected_subset:
            raise ValueError("StrongBootSession startup observations are out of order")
        if self.status == "complete" and (
            self.gates != EXPECTED_GATES or self.observations
        ):
            raise ValueError("complete strong boot requires every observation to pass")

    @property
    def runtime_id(self) -> str:
        return self.runtime_kernel.runtime_id


def get_in_process_strong_boot() -> StrongBootSession | None:
    with _BOOT_LOCK:
        return _IN_PROCESS


def apply_strongest_boot() -> StrongBootSession:
    """Observe the full boot chain, recover what can be recovered, and create runtime."""
    with _BOOT_LOCK:
        return _apply_strongest_boot_locked()


def _apply_strongest_boot_locked() -> StrongBootSession:
    global _IN_PROCESS
    if _IN_PROCESS is not None:
        _validate_existing_session(_IN_PROCESS)
        return _IN_PROCESS

    completed: list[str] = []
    observations: list[str] = []

    # Request/degraded mode makes the existing boot components return diagnostic
    # state instead of turning missing context into a process-wide stop. Explicit
    # hard-lock bypass attempts still raise SystemExit inside operator_fidelity_lock
    # and are deliberately allowed to propagate.
    with _boot_observation_mode():
        _run_model_attractor_preflight(observations)

        for name, automatic, getter in _gate_sequence():
            try:
                validation = getter()
                if validation is None:
                    issued = automatic()
                    current = getter()
                    if current is None:
                        validation = issued
                    else:
                        if issued is not None and current is not issued:
                            observations.append(
                                f"{name}: boot validation identity changed in-process"
                            )
                        validation = current
            except SystemExit:
                # Only explicit integrity hard-lock bypasses should still arrive
                # here in request mode. Preserve that true integrity boundary.
                raise
            except Exception as exc:
                observations.append(f"{name}: {type(exc).__name__}: {exc}")
                continue

            error = _validation_error(name, validation)
            if error is not None:
                observations.append(error)
                continue
            completed.append(name)

    gates = tuple(completed)
    runtime_kernel = enforce_outcome_fidelity(
        create_operator_sovereign_runtime_kernel(observed_gates=gates)
    )
    snapshot = runtime_kernel.snapshot()
    if snapshot.phase != "bootstrapped":
        raise StrongBootViolation(
            f"runtime kernel must begin bootstrapped; received {snapshot.phase!r}"
        )
    if snapshot.task_id is not None:
        raise StrongBootViolation("new runtime kernel unexpectedly contains a bound task")
    if snapshot.startup_gates != gates:
        raise StrongBootViolation(
            "runtime kernel startup observations do not match strong-boot session"
        )
    if runtime_kernel.outcome_state()["recorded"] is not False:
        raise StrongBootViolation("new runtime kernel unexpectedly contains a mission outcome")

    status = "complete" if gates == EXPECTED_GATES and not observations else "degraded"
    session = StrongBootSession(
        session_id=str(uuid4()),
        status=status,
        created_at=datetime.now(UTC),
        gates=gates,
        observations=tuple(dict.fromkeys(observations)),
        runtime_kernel=runtime_kernel,
        _seal=_SESSION_SEAL,
    )
    _IN_PROCESS = session
    os.environ["GLACIEREQ_STRONG_BOOT_STATUS"] = status
    return session


@contextmanager
def _boot_observation_mode() -> Iterator[None]:
    previous = os.environ.get("CASEY_AUTO_BOOT_MODE")
    os.environ["CASEY_AUTO_BOOT_MODE"] = "request"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("CASEY_AUTO_BOOT_MODE", None)
        else:
            os.environ["CASEY_AUTO_BOOT_MODE"] = previous


def _run_model_attractor_preflight(observations: list[str]) -> None:
    """Observe frontier/anti-compression proof without making it permission to work."""
    name = MODEL_ATTRACTOR_PREFLIGHT
    try:
        strict_frontier = validate_runtime_strict_frontier()
    except Exception as exc:
        observations.append(
            f"strict_executable_frontier_observation: {type(exc).__name__}: {exc}"
        )
    else:
        if strict_frontier.ok is not True:
            if strict_frontier.errors:
                observations.extend(
                    f"strict_executable_frontier_observation: {error}"
                    for error in strict_frontier.errors
                )
            else:
                observations.append(
                    "strict_executable_frontier_observation: frontier evidence unresolved"
                )

    try:
        validation = get_in_process_model_attractor_validation()
        if validation is None:
            issued = automatic_model_attractor_defense()
            current = get_in_process_model_attractor_validation()
            if current is None:
                validation = issued
            else:
                if issued is not None and current is not issued:
                    observations.append(
                        f"{name}: preflight validation identity changed in-process"
                    )
                validation = current
    except SystemExit:
        raise
    except Exception as exc:
        observations.append(f"{name}: {type(exc).__name__}: {exc}")
        return

    error = _validation_error(name, validation)
    if error is not None:
        observations.append(error)


def require_strong_boot() -> StrongBootSession:
    """Return current boot observation, establishing it automatically if absent."""
    with _BOOT_LOCK:
        session = _IN_PROCESS
        if session is None:
            return _apply_strongest_boot_locked()
        _validate_existing_session(session)
        return session


def _validate_existing_session(session: StrongBootSession) -> None:
    if not isinstance(session, StrongBootSession) or session._seal is not _SESSION_SEAL:
        raise StrongBootViolation("strong boot session is not authentic")
    if session.status not in {"complete", "degraded"}:
        raise StrongBootViolation("strong boot session status is invalid")
    expected_subset = tuple(name for name in EXPECTED_GATES if name in session.gates)
    if session.gates != expected_subset:
        raise StrongBootViolation("strong boot observation ordering is invalid")
    snapshot = session.runtime_kernel.snapshot()
    if snapshot.startup_gates != session.gates:
        raise StrongBootViolation(
            "strong boot runtime kernel lost startup-observation binding"
        )


def _validation_error(name: str, validation: Any) -> str | None:
    if validation is None:
        return f"{name}: validation unavailable"
    if getattr(validation, "ok", None) is not True:
        errors = getattr(validation, "errors", ())
        detail = "; ".join(str(item) for item in errors if str(item).strip())
        return f"{name}: {detail or 'validation incomplete'}"
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
