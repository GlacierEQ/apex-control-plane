"""Process-entry router for the APEX runtime boundary.

`control_plane_runtime.py` is an implementation library. Historically, executing
that file directly terminated the process. The corrected behavior changes the
route, not the objective: direct invocation is transparently re-executed through
the canonical control-plane entrypoint so startup diagnostics can enrich the
runtime without becoming a global veto.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

EXIT_BOOT_BLOCKED = 78  # retained for compatibility with historical callers


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
    """Reroute direct legacy-runtime execution through the canonical entrypoint."""
    is_testing = _testing() if testing is None else bool(testing)
    if is_testing or not legacy_runtime_is_direct(argv0):
        return

    control_plane = Path(__file__).with_name("control_plane.py")
    payload = {
        "boot_status": "rerouting",
        "runtime_binding_status": "canonical_route_selected",
        "reason": (
            "direct control_plane_runtime execution requested; rerouting through "
            "control_plane.py instead of terminating"
        ),
        "runtime_authorized": True,
        "external_action_authorized": "route_local",
        "target": str(control_plane),
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
    sys.stderr.flush()

    # Replace the current process with the canonical route. This preserves the
    # requested mission and arguments while avoiding recursion: subsequent
    # library import occurs under control_plane.py/verified_runtime_entrypoint.py,
    # so legacy_runtime_is_direct() is false.
    try:
        os.execv(
            sys.executable,
            [sys.executable, str(control_plane), *sys.argv[1:]],
        )
    except OSError as exc:
        raise RuntimeError(
            f"canonical APEX runtime reroute failed: {exc.__class__.__name__}"
        ) from exc
