#!/usr/bin/env python3
"""Canonical APEX control-plane entrypoint with mandatory continuity boot.

When executed, this wrapper proves the Notion-first continuity/integration
preflight and the existing Casey continuity + GlacierEQ Prime Directive
contracts before it loads the preserved runtime. When imported by tests or
other modules, it re-exports the legacy runtime API without starting the boot
gate.
"""
from __future__ import annotations

import json
from pathlib import Path
import runpy
import sys


if __name__ == "__main__":
    from auto_boot import EXIT_BOOT_BLOCKED
    from notion_continuity_gate import (
        automatic_notion_continuity_preflight,
        get_in_process_notion_validation,
    )
    from prime_directive_boot import (
        automatic_prime_directive_boot,
        get_in_process_boot_validation,
    )

    # Caller-controlled environment variables are status projections, not proof.
    # Skip only when this Python process already produced the matching sealed
    # validation object.
    try:
        if get_in_process_notion_validation() is None:
            automatic_notion_continuity_preflight()
        if get_in_process_boot_validation() is None:
            automatic_prime_directive_boot()
    except SystemExit:
        raise
    except Exception as exc:
        payload = {
            "boot_status": "blocked",
            "notion_continuity_status": "blocked",
            "prime_directive_status": "blocked",
            "error": f"{type(exc).__name__}: {exc}",
            "external_action_authorized": False,
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        sys.stderr.flush()
        raise SystemExit(EXIT_BOOT_BLOCKED) from None

    runpy.run_path(
        str(Path(__file__).with_name("control_plane_runtime.py")),
        run_name="__main__",
    )
else:
    from control_plane_runtime import *  # noqa: F401,F403
