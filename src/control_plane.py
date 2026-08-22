#!/usr/bin/env python3
"""APEX control-plane entrypoint with one mandatory strongest-boot path.

The entrypoint does not assemble startup proofs independently. It requires the
sealed strong-boot session, which proves all mandatory in-process startup gates
and creates the verified post-boot runtime kernel before the preserved runtime
can load.
"""
from __future__ import annotations

import json
from pathlib import Path
import runpy
import sys


if __name__ == "__main__":
    from apex_strong_boot import apply_strongest_boot
    from auto_boot import EXIT_BOOT_BLOCKED

    try:
        boot_session = apply_strongest_boot()
        runtime_kernel = boot_session.runtime_kernel
    except SystemExit:
        raise
    except Exception as exc:
        payload = {
            "boot_status": "blocked",
            "strong_boot_status": "blocked",
            "runtime_kernel_status": "blocked",
            "error": f"{type(exc).__name__}: {exc}",
            "runtime_authorized": False,
            "external_action_authorized": False,
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        sys.stderr.flush()
        raise SystemExit(EXIT_BOOT_BLOCKED) from None

    runpy.run_path(
        str(Path(__file__).with_name("control_plane_runtime.py")),
        run_name="__main__",
        init_globals={
            "APEX_STRONG_BOOT_SESSION": boot_session,
            "APEX_RUNTIME_KERNEL": runtime_kernel,
        },
    )
else:
    from control_plane_runtime import *  # noqa: F401,F403
