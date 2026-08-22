#!/usr/bin/env python3
"""APEX control-plane entrypoint with mandatory enforced startup.

When executed, this wrapper proves continuity, Prime Directive, the non-bypassable
Operator-fidelity lock, literal Operator fidelity, and APEX Genesis contracts,
then creates the verified post-boot runtime kernel before loading the preserved
runtime. When imported by tests or other modules, it re-exports the preserved
runtime API without starting the boot gate.
"""
from __future__ import annotations

import json
from pathlib import Path
import runpy
import sys
from typing import Any


def _require_completed_startup_validations(
    validations: tuple[tuple[str, Any | None], ...],
) -> None:
    """Refuse runtime loading unless every mandatory gate is complete in-process."""
    incomplete: list[str] = []
    for gate_name, validation in validations:
        if validation is None:
            incomplete.append(f"{gate_name}: validation missing")
            continue
        if validation.ok is not True or validation.status != "complete":
            incomplete.append(
                f"{gate_name}: status={validation.status!r}, ok={validation.ok!r}"
            )
    if incomplete:
        raise RuntimeError(
            "runtime authorization denied; mandatory startup gates incomplete: "
            + "; ".join(incomplete)
        )


if __name__ == "__main__":
    from auto_boot import EXIT_BOOT_BLOCKED
    from apex_enforced_startup import (
        automatic_apex_enforced_startup,
        get_in_process_apex_validation,
    )
    from apex_runtime_kernel import create_verified_runtime_kernel
    from notion_continuity_gate import (
        automatic_notion_continuity_preflight,
        get_in_process_notion_validation,
    )
    from operator_fidelity_lock import (
        automatic_operator_fidelity_lock,
        get_in_process_operator_fidelity_lock,
    )
    from operator_fidelity_preflight import (
        automatic_operator_fidelity_preflight,
        get_in_process_operator_fidelity_validation,
    )
    from prime_directive_boot import (
        automatic_prime_directive_boot,
        get_in_process_boot_validation,
    )

    # Caller-controlled environment variables are status projections, not proof.
    # Only in-process sealed validation objects can satisfy startup stages.
    try:
        if get_in_process_notion_validation() is None:
            automatic_notion_continuity_preflight()
        if get_in_process_boot_validation() is None:
            automatic_prime_directive_boot()
        if get_in_process_operator_fidelity_lock() is None:
            automatic_operator_fidelity_lock()
        if get_in_process_operator_fidelity_validation() is None:
            automatic_operator_fidelity_preflight()
        if get_in_process_apex_validation() is None:
            automatic_apex_enforced_startup()

        _require_completed_startup_validations(
            (
                ("notion_continuity", get_in_process_notion_validation()),
                ("prime_directive", get_in_process_boot_validation()),
                ("operator_fidelity_lock", get_in_process_operator_fidelity_lock()),
                ("operator_fidelity", get_in_process_operator_fidelity_validation()),
                ("apex_startup", get_in_process_apex_validation()),
            )
        )
        runtime_kernel = create_verified_runtime_kernel()
    except SystemExit:
        raise
    except Exception as exc:
        payload = {
            "boot_status": "blocked",
            "notion_continuity_status": "blocked",
            "prime_directive_status": "blocked",
            "operator_fidelity_lock_status": "blocked",
            "operator_fidelity_status": "blocked",
            "apex_startup_status": "blocked",
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
        init_globals={"APEX_RUNTIME_KERNEL": runtime_kernel},
    )
else:
    from control_plane_runtime import *  # noqa: F401,F403
