#!/usr/bin/env python3
"""Canonical APEX control-plane entrypoint with mandatory Prime Directive boot.

When executed, this wrapper proves the combined Casey continuity and GlacierEQ
Prime Directive contracts before it loads the preserved runtime. When imported
by tests or other modules, it re-exports the legacy runtime API without starting
the boot gate.
"""
from __future__ import annotations

import os
from pathlib import Path
import runpy


if __name__ == "__main__":
    from prime_directive_boot import automatic_prime_directive_boot

    # The optional site hook may already have completed the combined gate.
    if os.getenv("GLACIEREQ_PRIME_DIRECTIVE_GATE_STATUS") not in {
        "complete",
        "degraded",
    }:
        automatic_prime_directive_boot()

    runpy.run_path(
        str(Path(__file__).with_name("control_plane_runtime.py")),
        run_name="__main__",
    )
else:
    from control_plane_runtime import *  # noqa: F401,F403
