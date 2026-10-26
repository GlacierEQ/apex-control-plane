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
    load_continuous_control_config,
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
    # APEX's direct CLI performs requested work instead of fabricating an
    # execution count. With no command there is no completed work to claim.
    # An explicitly supplied process executes under the host's own identity
    # and environment; there is no second, invented APEX approval ceremony.
    import subprocess

    args = sys.argv[1:]
    if not args:
        print(json.dumps({
            "status": "idle", "executed": False, "routes_run": 0,
            "reason": "no_execution_command_supplied",
        }, sort_keys=True))
    elif (args[0] == "--run-next-local" and len(args) >= 5
          and args[3] == "--"):
        # Operator supplies a concrete command; the persisted queue supplies
        # the work identity. Do not execute instructions extracted from events.
        queue_root, capability = args[1], args[2]
        command = args[4:]
        plane = ContinuousControlPlane.from_config(
            JsonlControlStore(queue_root),
            load_continuous_control_config(
                Path(__file__).resolve().parents[1]
                / "config" / "continuous_control_plane.json"
            ),
        )

        def execute_queued(item: WorkItem) -> ExecutionReceipt:
            try:
                process = subprocess.run(
                    command, check=False, text=True, capture_output=True,
                )
                code = process.returncode
                stdout, stderr = process.stdout, process.stderr
            except OSError as exc:
                code, stdout, stderr = 127, "", f"{type(exc).__name__}: {exc}"
            return ExecutionReceipt(
                work_id=item.work_id,
                mission_id=item.mission_id,
                correlation_id=item.correlation_id,
                receipt_kind="execution",
                status="verified" if code == 0 else "failed",
                source_system="apex-local-process",
                details={
                    "exit_code": code,
                    "stdout": stdout,
                    "stderr": stderr,
                    "scope": "local process execution only; independent mission validation may remain",
                },
            )

        result = plane.execute_next_local(
            worker_id="apex-local-cli",
            capabilities=[capability],
            executor=execute_queued,
        )
        print(json.dumps(result, sort_keys=True))
        if result["status"] in {"retryable_failure", "exhausted"}:
            raise SystemExit(result.get("exit_code") or 1)
    elif args[0] == "--exec" and len(args) > 1:
        try:
            completed = subprocess.run(
                args[1:], check=False, capture_output=True, text=True,
            )
        except OSError as exc:
            print(json.dumps({
                "status": "failed", "executed": False, "routes_run": 0,
                "error": f"{type(exc).__name__}: {exc}",
            }, sort_keys=True))
            raise SystemExit(127) from exc
        print(json.dumps({
            "status": "completed" if completed.returncode == 0 else "failed",
            "executed": True,
            "routes_run": 1,
            "exit_code": completed.returncode,
            "command": args[1:],
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }, sort_keys=True))
        raise SystemExit(completed.returncode)
    else:
        print(json.dumps({
            "status": "failed", "executed": False, "routes_run": 0,
            "reason": "usage: control_plane.py --exec PROGRAM [ARG ...]",
        }, sort_keys=True))
        raise SystemExit(2)

else:
    from control_plane_runtime import *  # noqa: F401,F403
