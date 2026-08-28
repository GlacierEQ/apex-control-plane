#!/usr/bin/env python3
"""Python startup hook for combined APEX enforcement.

The primary enforcement path is ``src/control_plane.py``. This hook supplies the
same continuity, Prime Directive, non-bypassable Operator-fidelity lock,
Operator-fidelity preflight, and APEX Genesis enforcement when ``src`` is on
``PYTHONPATH`` or another entrypoint is forced with ``CASEY_AUTO_BOOT=1``.

Verifier CLIs and pytest are excluded so tests can exercise the enforcement code.
A real runtime cannot disable Operator fidelity with CASEY_AUTO_BOOT_DISABLE or
CASEY_AUTO_BOOT_MODE=off; the hard lock rejects those bypass attempts.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import NoReturn

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


def _should_boot() -> bool:
    entrypoint = _entrypoint_name()
    if (
        entrypoint
        in {
            "auto_boot.py",
            "apex_enforced_startup.py",
            "operator_fidelity_lock.py",
            "operator_fidelity_preflight.py",
            "notion_continuity_gate.py",
            "prime_directive_boot.py",
            "prime_directive_enforcer.py",
        }
        or _is_pytest_startup()
    ):
        return False

    if os.getenv("CASEY_AUTO_BOOT", "0") == "1":
        return True

    return entrypoint == "control_plane.py"


def _fail_closed(exc: Exception) -> NoReturn:
    payload = {
        "boot_status": "blocked",
        "notion_continuity_status": "blocked",
        "prime_directive_status": "blocked",
        "operator_fidelity_lock_status": "blocked",
        "operator_fidelity_status": "blocked",
        "apex_startup_status": "blocked",
        "error": f"{type(exc).__name__}: {exc}",
        "entrypoint": _entrypoint_path(),
        "runtime_authorized": False,
        "external_action_authorized": False,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
    sys.stderr.flush()
    raise SystemExit(_BOOT_BLOCKED_EXIT) from None


if _should_boot():
    try:
        from apex_enforced_startup import automatic_apex_enforced_startup
        from notion_continuity_gate import automatic_notion_continuity_preflight
        from operator_fidelity_lock import automatic_operator_fidelity_lock
        from operator_fidelity_preflight import automatic_operator_fidelity_preflight
        from prime_directive_boot import automatic_prime_directive_boot

        automatic_notion_continuity_preflight()
        automatic_prime_directive_boot()
        automatic_operator_fidelity_lock()
        automatic_operator_fidelity_preflight()
        automatic_apex_enforced_startup()
    except SystemExit:
        raise
    except Exception as exc:  # startup boundary must never fail open
        _fail_closed(exc)
