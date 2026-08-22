#!/usr/bin/env python3
"""Python startup hook for the single APEX strongest-boot path.

When this hook is active, it establishes the same sealed boot session used by
`src/control_plane.py`: continuity, Prime Directive, Operator-fidelity hard lock,
Operator-fidelity preflight, APEX startup, and the verified runtime kernel.

Verifier CLIs and pytest are excluded so enforcement code can be tested directly.
Strict runtime startup is fail-closed. Request mode remains a diagnostic lane:
it may continue only without a strong-boot session or runtime kernel, with all
execution authorization remaining false.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

_BOOT_BLOCKED_EXIT = 78


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
        "notion_continuity_gate.py",
        "prime_directive_boot.py",
        "prime_directive_enforcer.py",
    } or _is_pytest_startup():
        return False

    if os.getenv("CASEY_AUTO_BOOT", "0") == "1":
        return True

    return entrypoint in {"control_plane.py", "verified_runtime_entrypoint.py"}


def _record_blocked_startup(exc: BaseException) -> None:
    """Persist exact recovery evidence without granting execution authority."""
    from startup_continuation import emit_startup_continuation, record_startup_continuation

    payload = {
        "boot_status": "blocked",
        "strong_boot_status": "blocked",
        "error": f"{type(exc).__name__}: {exc}",
        "entrypoint": _entrypoint_path(),
        "runtime_authorized": False,
        "external_action_authorized": False,
    }
    continuation = record_startup_continuation(
        "strong_boot",
        (payload["error"],),
        request=payload,
        environment_key="GLACIEREQ_STRONG_BOOT_STATUS",
    )
    emit_startup_continuation(continuation)


def _terminate_blocked(code: int = _BOOT_BLOCKED_EXIT) -> None:
    """Exit from interpreter startup without CPython rewriting the status to 1.

    Raising SystemExit from `sitecustomize` can be treated as a fatal site-import
    error by the interpreter. Diagnostics are flushed first, then `_exit` preserves
    the fail-closed status code exactly.
    """
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    finally:
        os._exit(code)


APEX_STRONG_BOOT_SESSION = None
APEX_RUNTIME_KERNEL = None

# `control_plane_runtime.py` is the preserved implementation library, not an
# executable authorization boundary. Direct execution would bypass the verified
# lifecycle wrapper, so it is rejected and callers are routed to control_plane.py.
if _entrypoint_name() == "control_plane_runtime.py" and not _is_pytest_startup():
    _record_blocked_startup(
        RuntimeError(
            "direct control_plane_runtime execution is disabled; use control_plane.py"
        )
    )
    _terminate_blocked()

if _should_boot():
    try:
        from apex_strong_boot import apply_strongest_boot

        APEX_STRONG_BOOT_SESSION = apply_strongest_boot()
        APEX_RUNTIME_KERNEL = APEX_STRONG_BOOT_SESSION.runtime_kernel
    except SystemExit as exc:
        # Explicit hard-lock bypass attempts remain terminal even in diagnostic mode.
        code = exc.code if isinstance(exc.code, int) and exc.code else _BOOT_BLOCKED_EXIT
        _terminate_blocked(code)
    except Exception as exc:
        _record_blocked_startup(exc)
        if not _request_mode():
            _terminate_blocked()
