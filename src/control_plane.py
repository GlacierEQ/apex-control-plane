#!/usr/bin/env python3
"""Canonical APEX control-plane entrypoint with mandatory continuity auto-boot.

When executed, this wrapper proves the Casey continuity boot contract before it
loads the runtime. When imported by tests or other modules, it re-exports the
legacy runtime API without starting the boot gate.
"""
from __future__ import annotations

import os
from pathlib import Path
import runpy


if __name__ == "__main__":
    from auto_boot import automatic_boot

    # ``sitecustomize`` may already have run when ``src`` is on PYTHONPATH.
    # Do not emit a second request or revalidate the same receipt.
    if os.getenv("CASEY_BOOT_STATUS") not in {"complete", "degraded"}:
        automatic_boot()

    runpy.run_path(
        str(Path(__file__).with_name("control_plane_runtime.py")),
        run_name="__main__",
    )
else:
    from control_plane_runtime import *  # noqa: F401,F403
