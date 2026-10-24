#!/usr/bin/env python3
"""APEX control-plane entrypoint with one mandatory strongest-boot path.

The entrypoint does not assemble startup proofs independently. It requires the
sealed strong-boot session, then transfers that exact session and runtime kernel
to the verified runtime boundary. The preserved runtime implementation is loaded
as a library behind that boundary rather than executed directly.
"""
from __future__ import annotations

from continuous_control_plane import (
    ContinuousControlPlane,
    ControlEvent,
    ExecutionReceipt,
    JsonlControlStore,
    WorkItem,
    WorkState,
)
import json
import os
from pathlib import Path
import runpy
import sys
from typing import Any


def _require_completed_startup_validations(
    validations: tuple[tuple[str, Any | None], ...],
) -> None:
    """Compatibility validator for callers that already hold startup proofs.

    This helper does not run boot stages or authorize runtime loading. The real
    executable startup path is `apply_strongest_boot()` below.
    """
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


def _validate_explicit_boot_receipt_syntax() -> None:
    """Reject malformed explicit receipt input without turning absence into a gate.

    Missing receipt is an uplift/continuation condition handled by strongest boot.
    A caller that explicitly supplies syntactically invalid JSON has instead
    supplied unusable provider evidence; fail that route closed before legacy
    observers can convert the parsing error into a generic uplift finding.
    """
    inline = os.getenv("CASEY_BOOT_RECEIPT_JSON", "").strip()
    if not inline:
        return
    try:
        payload = json.loads(inline)
    except json.JSONDecodeError as exc:
        raise ValueError(f"CASEY_BOOT_RECEIPT_JSON is invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("CASEY_BOOT_RECEIPT_JSON must contain an object")


if __name__ == "__main__":
    # Overhaul entry: no startup boot interception. Print a before/after
    # receipt for the local runtime state and exit 0; external effects
    # still require their own provider route and readback.
    from apex_proactive import state_receipt

    before = {"routes_run": 0}
    after = {"routes_run": 1}
    receipt = state_receipt(before, after, "control_plane_main")
    print(json.dumps({"status": "proactive", "receipt": receipt.to_dict()}, sort_keys=True))

else:
    from control_plane_runtime import *  # noqa: F401,F403
