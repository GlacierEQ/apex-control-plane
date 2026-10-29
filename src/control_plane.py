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
from hashlib import sha256
import os
from pathlib import Path
import runpy
import stat
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
    if args and args[0] == "run-internal":
        from execute_now import main as run_internal
        raise SystemExit(run_internal(args[1:]))
    if not args and os.getenv("GLACIEREQ_INTERNAL_MANIFEST"):
        from execute_now import main as run_internal
        manifest = Path(os.environ["GLACIEREQ_INTERNAL_MANIFEST"])
        raise SystemExit(run_internal([
            "--manifest", str(manifest),
            "--out-dir", str(manifest.parent / "results"),
            "--journal", str(manifest.parent / ".apex_direct_execution.sqlite3"),
        ]))
    if not args:
        print(json.dumps({
            "status": "idle", "executed": False, "routes_run": 0,
            "mission_complete": False,
            "reason": "no_execution_command_supplied",
        }, sort_keys=True))
        raise SystemExit(3)
    elif args[0] in {"--run-next-local", "--drain-local"} and len(args) >= 5:
        # Operator supplies a concrete command; the persisted queue supplies
        # the work identity. Never execute instructions extracted from events.
        queue_root, capability = args[1], args[2]
        verify_file = None
        if args[3] == "--":
            command = args[4:]
        elif len(args) >= 7 and args[3] == "--verify-file" and args[5] == "--":
            verify_file = Path(args[4])
            command = args[6:]
        else:
            print(json.dumps({
                "status": "failed", "executed": False, "routes_run": 0,
                "mission_complete": False,
                "reason": "usage: (--run-next-local | --drain-local) STORE CAPABILITY [--verify-file PATH] -- PROGRAM [ARG ...]",
            }, sort_keys=True))
            raise SystemExit(2)
        plane = ContinuousControlPlane.from_config(
            JsonlControlStore(queue_root),
            load_continuous_control_config(
                Path(__file__).resolve().parents[1]
                / "config" / "continuous_control_plane.json"
            ),
        )

        def _artifact_snapshot(path: Path | None) -> tuple[int, int, int, int, int] | None:
            """Read a regular file's identity without following a symbolic link."""
            if path is None:
                return None
            try:
                meta = path.lstat()
            except OSError:
                return None
            if not stat.S_ISREG(meta.st_mode):
                return None
            return (
                meta.st_dev, meta.st_ino, meta.st_size,
                meta.st_mtime_ns, meta.st_ctime_ns,
            )

        def execute_queued(item: WorkItem) -> ExecutionReceipt | list[ExecutionReceipt]:
            before_artifact = _artifact_snapshot(verify_file)
            try:
                process = subprocess.run(
                    command, check=False, text=True, capture_output=True,
                )
                code = process.returncode
                stdout, stderr = process.stdout, process.stderr
            except OSError as exc:
                code, stdout, stderr = 127, "", f"{type(exc).__name__}: {exc}"
            execution = ExecutionReceipt(
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
            if code != 0 or verify_file is None:
                return execution
            after_artifact = _artifact_snapshot(verify_file)
            if after_artifact is None or after_artifact == before_artifact:
                # Pre-existing unchanged output is not proof of this execution.
                return execution
            fd = -1
            try:
                fd = os.open(
                    verify_file,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                )
                opened = os.fstat(fd)
                opened_snapshot = (
                    opened.st_dev, opened.st_ino, opened.st_size,
                    opened.st_mtime_ns, opened.st_ctime_ns,
                )
                if not stat.S_ISREG(opened.st_mode) or opened_snapshot != after_artifact:
                    return execution
                with os.fdopen(fd, "rb") as handle:
                    fd = -1
                    actual = handle.read()
                    final = os.fstat(handle.fileno())
                    final_snapshot = (
                        final.st_dev, final.st_ino, final.st_size,
                        final.st_mtime_ns, final.st_ctime_ns,
                    )
                    if final_snapshot != opened_snapshot:
                        return execution
            except OSError:
                return execution
            finally:
                if fd >= 0:
                    os.close(fd)
            return [
                execution,
                ExecutionReceipt(
                    work_id=item.work_id,
                    mission_id=item.mission_id,
                    correlation_id=item.correlation_id,
                    receipt_kind="verification",
                    status="verified",
                    source_system="apex-local-artifact-readback",
                    details={
                        "path": str(verify_file),
                        "sha256": sha256(actual).hexdigest(),
                        "bytes": len(actual),
                        "freshness": "created_or_changed_during_this_command",
                        "scope": "current-run regular-file readback, not external provider completion",
                    },
                ),
            ]

        drain = args[0] == "--drain-local"
        executor_fn = plane.drain_local if drain else plane.execute_next_local
        result = executor_fn(
            worker_id="apex-local-cli",
            capabilities=[capability],
            executor=execute_queued,
        )
        # A single successful item is not a successful sweep if independent
        # work of this capability is still queued. Preserve the verified item
        # while returning an explicitly incomplete, nonzero invocation.
        if not drain and result["status"] == "complete":
            unfinished = sorted(
                item.work_id for item in plane.work.values()
                if item.capability == capability and not item.external_action
                and item.state is not WorkState.COMPLETE
            )
            if unfinished:
                result["status"] = "partial_local_completion"
                result["remaining_unverified_ids"] = unfinished
        # Verified local work and an entire mission are different outcomes.
        result["outcome_scope"] = "local_batch" if drain else "local_work_item"
        result["work_item_complete"] = result["status"] in {"complete", "partial_local_completion"}
        result["batch_complete"] = result["status"] == "local_batch_complete"
        result["mission_complete"] = False
        print(json.dumps(result, sort_keys=True))
        if result["status"] in {"complete", "local_batch_complete"}:
            raise SystemExit(0)
        # Exit zero must never silently certify an idle, unverified,
        # unfinished or scheduled-retry invocation as successful work.
        if result["status"] in {"retryable_failure", "exhausted", "retry_scheduled"}:
            raise SystemExit(result.get("exit_code") or 1)
        if result["status"] == "idle":
            raise SystemExit(3)
        if result["status"] in {"awaiting_receipts", "unfinished", "partial_local_completion"}:
            raise SystemExit(4)
        if result["status"] == "unconfirmed":
            raise SystemExit(5)
        raise SystemExit(2)
    elif args[0] == "--exec" and len(args) > 1:
        try:
            completed = subprocess.run(
                args[1:], check=False, capture_output=True, text=True,
            )
        except OSError as exc:
            print(json.dumps({
                "status": "failed", "executed": False, "routes_run": 0,
                "mission_complete": False, "outcome_verified": False,
                "error": f"{type(exc).__name__}: {exc}",
            }, sort_keys=True))
            raise SystemExit(127) from exc
        print(json.dumps({
            "status": "process_succeeded_unverified" if completed.returncode == 0 else "failed",
            "mission_complete": False,
            "outcome_verified": False,
            "outcome_scope": "subprocess_exit_only",
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
            "mission_complete": False,
            "reason": "usage: control_plane.py --exec PROGRAM [ARG ...]",
        }, sort_keys=True))
        raise SystemExit(2)

else:
    from control_plane_runtime import *  # noqa: F401,F403
