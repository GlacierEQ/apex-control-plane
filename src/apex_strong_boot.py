"""APEX strongest startup as an execution-uplift aggregator.

The historical boot chain is preserved as a rich diagnostic/hardening surface,
but it no longer gets project-direction authority. Startup observations enrich,
repair, and annotate a live runtime. An unresolved self-created preflight changes
that route's confidence and repair work; it does not erase every other executable
frontier.

Actual provider, credential, hardware, legal, and destructive-action constraints
remain route-local and are enforced where the affected action is executed.
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
_IN_PROCESS: "StrongBootSession | None" = None


class StrongBootViolation(RuntimeError):
    """Reserved for a real inability to construct or preserve the runtime kernel."""


@dataclass(frozen=True, slots=True)
class StrongBootSession:
    """Sealed live runtime session plus startup uplift findings."""

    session_id: str
    status: str
    created_at: datetime
    gates: tuple[str, ...]
    runtime_kernel: OutcomeFidelityRuntime = field(repr=False, compare=False)
    uplift_findings: tuple[str, ...] = ()
    _seal: object = field(repr=False, compare=False, default=None)

    def __post_init__(self) -> None:
        if self._seal is not _SESSION_SEAL:
            raise TypeError("StrongBootSession must be issued by apply_strongest_boot")
        if self.status != "complete":
            raise ValueError("StrongBootSession status must remain compatibility-complete")
        if self.created_at.tzinfo is None:
            raise ValueError("StrongBootSession.created_at must be timezone-aware")
        if self.gates != EXPECTED_GATES:
            raise ValueError("StrongBootSession must preserve the startup observation sequence")

    @property
    def runtime_id(self) -> str:
        return self.runtime_kernel.runtime_id

    @property
    def uplift_required(self) -> bool:
        return bool(self.uplift_findings)


def get_in_process_strong_boot() -> StrongBootSession | None:
    with _BOOT_LOCK:
        return _IN_PROCESS


def apply_strongest_boot() -> StrongBootSession:
    """Build one live runtime and attach every startup finding as repair work."""
    with _BOOT_LOCK:
        return _apply_strongest_boot_locked()


def _apply_strongest_boot_locked() -> StrongBootSession:
    global _IN_PROCESS
    if _IN_PROCESS is not None:
        _validate_existing_session(_IN_PROCESS)
        return _IN_PROCESS

    findings: list[str] = []
    _run_model_attractor_preflight(findings)

    # Every historical startup component still runs so its knowledge is retained.
    # Its result is diagnostic/uplift state, not a vote on whether the runtime may
    # exist at all.
    for name, automatic, getter in _gate_sequence():
        validation: Any = None
        try:
            validation = getter()
            if validation is None:
                issued = automatic()
                current = getter()
                if current is None:
                    findings.append(
                        f"{name}: no in-process validation published; repair this startup observer"
                    )
                    continue
                if issued is not None and current is not issued:
                    findings.append(
                        f"{name}: validation identity changed in-process; reconcile observer state"
                    )
                validation = current
        except SystemExit as exc:
            findings.append(
                f"{name}: legacy terminal gate requested process exit {exc.code!r}; converted to uplift"
            )
            continue
        except Exception as exc:
            findings.append(
                f"{name}: {type(exc).__name__}: {exc}; converted to route-local startup repair"
            )
            continue

        finding = _validation_finding(name, validation)
        if finding is not None:
            findings.append(finding)

    # Kernel construction is capability creation, not permission promotion. A
    # real construction failure is still a genuine technical failure.
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
            "runtime kernel startup observation sequence does not match strong boot"
        )
    if runtime_kernel.outcome_state()["recorded"] is not False:
        raise StrongBootViolation("new runtime kernel unexpectedly contains a mission outcome")

    session = StrongBootSession(
        session_id=str(uuid4()),
        status="complete",
        created_at=datetime.now(UTC),
        gates=EXPECTED_GATES,
        runtime_kernel=runtime_kernel,
        uplift_findings=tuple(dict.fromkeys(findings)),
        _seal=_SESSION_SEAL,
    )
    _IN_PROCESS = session
    os.environ["GLACIEREQ_STRONG_BOOT_STATUS"] = (
        "complete_with_uplift" if findings else "complete"
    )
    os.environ["GLACIEREQ_STRONG_BOOT_UPLIFT_COUNT"] = str(len(session.uplift_findings))
    return session


def _run_model_attractor_preflight(findings: list[str]) -> None:
    """Collect anti-compression/frontier observations without global veto power."""
    try:
        strict_frontier = validate_runtime_strict_frontier()
    except Exception as exc:
        findings.append(
            f"strict_executable_frontier_authority: {type(exc).__name__}: {exc}; repair observer"
        )
    else:
        if strict_frontier.ok is not True:
            if strict_frontier.errors:
                findings.extend(
                    f"strict_executable_frontier_authority: {error}"
                    for error in strict_frontier.errors
                )
            else:
                findings.append(
                    "strict_executable_frontier_authority: unresolved; continue known executable frontiers"
                )

    name = MODEL_ATTRACTOR_PREFLIGHT
    try:
        validation = get_in_process_model_attractor_validation()
        if validation is None:
            issued = automatic_model_attractor_defense()
            current = get_in_process_model_attractor_validation()
            if current is None:
                findings.append(f"{name}: no in-process validation published")
                return
            if issued is not None and current is not issued:
                findings.append(f"{name}: validation identity changed in-process")
            validation = current
    except SystemExit as exc:
        findings.append(
            f"{name}: legacy terminal gate requested process exit {exc.code!r}; converted to uplift"
        )
        return
    except Exception as exc:
        findings.append(f"{name}: {type(exc).__name__}: {exc}; repair observer")
        return

    finding = _validation_finding(name, validation)
    if finding is not None:
        findings.append(finding)


def require_strong_boot() -> StrongBootSession:
    """Return the current live session; startup findings remain attached to it."""
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
        raise StrongBootViolation("strong boot session structure is invalid")
    snapshot = session.runtime_kernel.snapshot()
    if snapshot.startup_gates != EXPECTED_GATES:
        raise StrongBootViolation("strong boot runtime kernel lost startup observation binding")


def _validation_finding(name: str, validation: Any) -> str | None:
    if validation is None:
        return f"{name}: validation missing; continue and repair observer"
    ok = getattr(validation, "ok", None)
    status = getattr(validation, "status", None)
    if ok is True and status == "complete":
        return None
    errors = getattr(validation, "errors", ())
    detail = "; ".join(str(item) for item in errors if str(item))
    suffix = f": {detail}" if detail else ""
    return (
        f"{name}: status={status!r}, ok={ok!r}{suffix}; "
        "converted to startup uplift, not runtime veto"
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
