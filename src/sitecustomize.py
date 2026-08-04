#!/usr/bin/env python3
"""Python startup hook for the Casey continuity gate.

Python imports ``sitecustomize`` automatically when this directory is on
``sys.path``. Running ``python src/control_plane.py`` therefore invokes the
continuity boot gate before the control-plane module executes.

The hook is intentionally narrow:
- it runs automatically for ``control_plane.py``;
- it can be forced for another entrypoint with ``CASEY_AUTO_BOOT=1``;
- it skips the verifier CLI and pytest;
- it fails closed with exit code 78 unless the boot mode is explicitly
  ``request`` or ``off``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

_BOOT_BLOCKED_EXIT = 78


def _entrypoint_name() -> str:
    if not sys.argv:
        return ""
    return Path(sys.argv[0]).name.lower()


def _should_boot() -> bool:
    if os.getenv("CASEY_AUTO_BOOT_DISABLE", "0") == "1":
        return False

    entrypoint = _entrypoint_name()
    if entrypoint in {"auto_boot.py", "pytest", "py.test"} or "pytest" in entrypoint:
        return False

    if os.getenv("CASEY_AUTO_BOOT", "0") == "1":
        return True

    return entrypoint == "control_plane.py"


def _fail_closed(exc: BaseException) -> None:
    payload = {
        "boot_status": "blocked",
        "error": f"{type(exc).__name__}: {exc}",
        "entrypoint": _entrypoint_name(),
        "external_action_authorized": False,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
    os._exit(_BOOT_BLOCKED_EXIT)


if _should_boot():
    try:
        from auto_boot import automatic_boot

        automatic_boot()
    except SystemExit:
        raise
    except BaseException as exc:  # startup boundary must never fail open
        _fail_closed(exc)
