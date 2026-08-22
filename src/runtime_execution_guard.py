"""Process-entry guard for the verified APEX runtime boundary.

`control_plane_runtime.py` is an implementation library. Executing that file
itself would skip the strong-boot session handoff and verified runtime lifecycle.
This guard is deliberately standard-library-only and is imported by an early
runtime dependency, so it still applies when Python does not discover the local
`sitecustomize.py` during interpreter startup.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

EXIT_BOOT_BLOCKED = 78


def legacy_runtime_is_direct(argv0: str | None = None) -> bool:
    target = str(sys.argv[0] if argv0 is None and sys.argv else argv0 or "")
    return Path(target).name.lower() == "control_plane_runtime.py"


def _testing() -> bool:
    return (
        os.getenv("CASEY_AUTO_BOOT_TESTING", "0") == "1"
        or os.getenv("PYTEST_CURRENT_TEST") is not None
    )


def enforce_verified_runtime_boundary(
    *,
    argv0: str | None = None,
    testing: bool | None = None,
) -> None:
    """Terminate direct legacy-runtime execution before runtime work can begin."""
    is_testing = _testing() if testing is None else bool(testing)
    if is_testing or not legacy_runtime_is_direct(argv0):
        return

    payload = {
        "boot_status": "blocked",
        "runtime_binding_status": "blocked",
        "error": (
            "direct control_plane_runtime execution is disabled; "
            "use control_plane.py"
        ),
        "runtime_authorized": False,
        "external_action_authorized": False,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
    sys.stderr.flush()
    raise SystemExit(EXIT_BOOT_BLOCKED)
