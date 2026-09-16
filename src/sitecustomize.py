#!/usr/bin/env python3
"""Python startup hook for the single APEX strongest-boot path.

When this hook is active, it establishes the same sealed boot session used by
`src/control_plane.py`: continuity observers, Prime Directive evidence,
Operator-fidelity checks, APEX startup, and the verified runtime kernel.

Recoverable startup observations are repair-forward: missing or incomplete
proof is attached to the live boot session as uplift work while known executable
frontiers continue. Startup observations do not create global permission
authority. Concrete provider, credential, hardware, legal, destructive-action,
and unrecoverable kernel-integrity constraints remain scoped to the route that
actually carries them.

Verifier CLIs and pytest are excluded so enforcement code can be tested directly.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

_BOOT_UNRECOVERABLE_EXIT = 78


def _entrypoint_path() -> str:
    if not sys.argv:
        return ""
    return str(Path(sys.argv[0])).lower()


def _entrypoint_name() -> str:
    return Path(_entrypoint_path()).name


def _is_pytest_startup() -> bool:
    path = _entrypoint_path()
    return (
        "pytest" in path
        or os.getenv("PYTEST_CURRENT_TEST") is not None
        or os.getenv("CASEY_AUTO_BOOT_TESTING", "0") == "1"
    )


def _request_mode() -> bool:
    return os.getenv("CASEY_AUTO_BOOT_MODE", "strict").strip().lower() == "request"


def _should_boot() -> bool:
    entrypoint = _entrypoint_name()
    if entrypoint in {
        "auto_boot.py",
        "apex_enforced_startup.py",
        "apex_strong_boot.py",
        "operator_fidelity_lock.py",
        "operator_fidelity_preflight.py",
        "operator_source_authority.py",
        "notion_continuity_gate.py",
        "prime_directive_boot.py",
        "prime_directive_enforcer.py",
    } or _is_pytest_startup():
        return False

    if os.getenv("CASEY_AUTO_BOOT", "0") == "1":
        return True

    return entrypoint in {"control_plane.py", "verified_runtime_entrypoint.py"}


def _record_startup_uplift(exc: BaseException) -> None:
    """Persist exact recovery evidence without creating global execution authority."""
    from startup_continuation import emit_startup_continuation, record_startup_continuation

    payload = {
        "boot_status": "uplift_required",
        "strong_boot_status": "uplift_required",
        "error": f"{type(exc).__name__}: {exc}",
        "entrypoint": _entrypoint_path(),
        "runtime_authorized": "route_local_only",
        "external_action_authorized": "route_local_only",
        "mission_execution": "continue_known_executable_frontiers",
    }
    continuation = record_startup_continuation(
        "strong_boot",
        (payload["error"],),
        request=payload,
        environment_key="GLACIEREQ_STRONG_BOOT_STATUS",
    )
    emit_startup_continuation(continuation)


def _terminate_unrecoverable(code: int = _BOOT_UNRECOVERABLE_EXIT) -> None:
    """Terminate only when the startup/kernel path itself cannot be constructed.

    Recoverable evidence gaps are consumed by StrongBoot before reaching this
    function. An exception escaping that repair-forward path is therefore an
    implementation/integrity failure of the runtime constructor itself, not a
    missing-proof permission decision.
    """
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    finally:
        os._exit(code)


APEX_STRONG_BOOT_SESSION = None
APEX_RUNTIME_KERNEL = None

# Do not intercept control_plane_runtime.py here. Its executable shim owns the
# compatibility reroute to the canonical entrypoint; terminating in sitecustomize
# would recreate the global startup veto removed by StrongBoot.

if _should_boot():
    try:
        # Source/personalization authority is checked before task-bearing boot so
        # derivative summaries or fresh inference cannot silently become source
        # authority. Recoverable observer findings after this point are uplifted
        # inside StrongBoot rather than promoted into global vetoes.
        from operator_source_authority import enforce_operator_source_authority

        enforce_operator_source_authority()

        from apex_strong_boot import apply_strongest_boot

        APEX_STRONG_BOOT_SESSION = apply_strongest_boot()
        APEX_RUNTIME_KERNEL = APEX_STRONG_BOOT_SESSION.runtime_kernel
    except SystemExit as exc:
        # StrongBoot absorbs legacy/recoverable observer exits. A SystemExit that
        # escapes here belongs to an explicit source-authority or unrecoverable
        # runtime-integrity boundary and remains a concrete local constraint.
        _record_startup_uplift(exc)
        code = (
            exc.code
            if isinstance(exc.code, int) and exc.code
            else _BOOT_UNRECOVERABLE_EXIT
        )
        _terminate_unrecoverable(code)
    except Exception as exc:
        _record_startup_uplift(exc)
        if not _request_mode():
            _terminate_unrecoverable()
