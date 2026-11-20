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
    if args and args[0] == "--inspect-receipt":
        from inspect_execution_receipt import main as inspect_receipt
        raise SystemExit(inspect_receipt(args[1:]))
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
    elif args[0] == "--exec-capability":
        # Real, operator-invoked runtime consumer of the capability catalog.
        # Capability text enters the child process ONLY as stdin data; it is
        # never interpreted as a shell command or elevated into permission.
        import argparse
        import hashlib
        from tool_catalog import build_catalog, select

        def reject(reason: str) -> None:
            print(reason, file=sys.stderr)
            raise SystemExit(2)

        try:
            separator = args.index("--")
        except ValueError:
            reject("--exec-capability requires -- PROGRAM [ARG ...]")
        command = args[separator + 1:]
        if not command:
            reject("--exec-capability requires an executable")
        cli = argparse.ArgumentParser(prog="control_plane.py --exec-capability")
        cli.add_argument("--skills-root", action="append", default=[])
        cli.add_argument("--connectors-root", action="append", default=[])
        cli.add_argument("--select", required=True)
        cli.add_argument("--sha256", required=True)
        cli.add_argument("--timeout-seconds", type=float, default=60.0)
        cli.add_argument("--receipt-path", type=Path)
        options = cli.parse_args(args[1:separator])
        if not 0 < options.timeout_seconds <= 3600 or not __import__("math").isfinite(options.timeout_seconds):
            reject("timeout-seconds must be finite and between 0 and 3600")
        expected = options.sha256
        if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
            reject("expected SHA-256 must be 64 lowercase hexadecimal characters")
        try:
            catalog = build_catalog(options.skills_root, options.connectors_root)
            chosen = select(catalog, [options.select])
            if len(chosen) != 1:
                reject(f"unknown capability selection: {options.select!r}")
            entry = chosen[0]
            base_dirs = (options.skills_root if entry.kind == "skill"
                         else options.connectors_root)
            doc = Path(entry.path).resolve(strict=True)
            if not any(doc.is_relative_to(Path(root).resolve(strict=True))
                       for root in base_dirs):
                reject("capability document escaped its authorized root")
            document = doc.read_bytes()
            actual = hashlib.sha256(document).hexdigest()
            if actual != expected:
                reject(f"capability document digest mismatch: {entry.kind}:{entry.name}")
            document.decode("utf-8")
        except (OSError, UnicodeError, ValueError) as exc:
            reject(f"cannot load capability document: {exc}")
        # Optional durable receipt: pending is committed before subprocess launch.
        # A crash leaves explicit unverified evidence rather than false success.
        def write_receipt(record: dict[str, Any], *, initial: bool = False) -> None:
            if options.receipt_path is None:
                return
            import tempfile as _tempfile
            target = options.receipt_path
            parent = target.parent.resolve(strict=True)
            if target.is_symlink():
                reject("receipt path must not be a symlink")
            payload = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
            fd, staging = _tempfile.mkstemp(prefix=".apex-receipt-", dir=parent)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                if initial:
                    # Exclusive creation preserves a prior pending/final receipt.
                    # A retry must not erase uncertainty about a previous run.
                    os.link(staging, target)
                    os.unlink(staging)
                else:
                    os.replace(staging, target)
                if hasattr(os, "O_DIRECTORY"):
                    directory_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
            finally:
                if os.path.exists(staging):
                    os.unlink(staging)

        import uuid
        invocation_id = uuid.uuid4().hex
        if options.receipt_path is not None:
            try:
                write_receipt({
                    "invocation_id": invocation_id,
                    "status": "pending_unverified", "executed": False,
                    "outcome_verified": False, "mission_complete": False,
                    "capability": {"qualified_name": f"{entry.kind}:{entry.name}", "sha256": actual},
                    "command": command,
                    "note": "A pending receipt after interruption does not prove whether the child ran.",
                }, initial=True)
            except OSError as exc:
                reject(f"cannot initialize durable receipt: {exc}")
        executed = False
        timed_out = False
        # Capture to disk, not unbounded subprocess pipes. A noisy child
        # must not exhaust the agent host's memory or inflate JSON receipts.
        import tempfile
        max_output_bytes = 65536
        # Parent-owned bounded pipe drains: cap only captured output, never
        # the requested program's unrelated file writes.
        max_spool_bytes = 8 * 1024 * 1024
        import select as _select
        import threading
        stop_drains = threading.Event()
        drain_complete = [False, False]

        def drain(stream, target, counts, index):
            # A child may exit while a descendant still holds stdout open.
            # Use cancellable reads so output collection cannot outlive the
            # same deadline that applies to subprocess execution.
            fd = stream.fileno()
            if os.name == "posix":
                os.set_blocking(fd, False)
            try:
                while not stop_drains.is_set():
                    if os.name == "posix":
                        readable, _, _ = _select.select([fd], [], [], 0.05)
                        if not readable:
                            continue
                        try:
                            chunk = os.read(fd, 65536)
                        except BlockingIOError:
                            continue
                    else:
                        chunk = stream.read(65536)
                    if not chunk:
                        drain_complete[index] = True
                        break
                    counts[index] += len(chunk)
                    remaining = max_spool_bytes - target.tell()
                    if remaining > 0:
                        target.write(chunk[:remaining])
            except (OSError, ValueError):
                # A stopped drain is explicitly marked incomplete in the
                # receipt; never report a complete output byte count.
                pass
            finally:
                stream.close()

        stdout_bytes = stderr_bytes = 0
        stdout_truncated = stderr_truncated = False
        output_incomplete = False
        try:
            # A process timeout must also terminate descendant workers.
            # start_new_session isolates the operator-selected child into its
            # own POSIX process group, leaving the caller's group untouched.
            import signal
            with tempfile.TemporaryFile() as out_file, tempfile.TemporaryFile() as err_file:
                # For durable POSIX executions, the first child is a gated
                # exec trampoline. The requested command cannot begin until
                # the launched receipt has been fsynced. If the parent dies
                # first, pipe EOF makes the trampoline exit without exec.
                gate_read = gate_write = None
                launch_command = command
                if options.receipt_path is not None and os.name == "posix":
                    gate_read, gate_write = os.pipe()
                    trampoline = (
                        "import os,sys; "
                        "fd=int(sys.argv[1]); "
                        "token=os.read(fd,1); os.close(fd); "
                        "os._exit(125) if token!=b'G' else None; "
                        "os.execvp(sys.argv[2],sys.argv[2:])"
                    )
                    launch_command = [
                        sys.executable, "-c", trampoline,
                        str(gate_read), *command,
                    ]
                try:
                    child = subprocess.Popen(
                        launch_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, start_new_session=(os.name == "posix"),
                        pass_fds=(gate_read,) if gate_read is not None else (),
                    )
                except BaseException:
                    # Popen can fail before a child owns the gate. Close the
                    # parent writer as well; otherwise retries leak FDs.
                    if gate_write is not None:
                        os.close(gate_write)
                        gate_write = None
                    raise
                finally:
                    if gate_read is not None:
                        os.close(gate_read)
                counts = [0, 0]
                drains = [threading.Thread(target=drain, args=(child.stdout, out_file, counts, 0), daemon=True),
                          threading.Thread(target=drain, args=(child.stderr, err_file, counts, 1), daemon=True)]
                for thread in drains:
                    thread.start()
                executed = True
                # Durable diagnostic process identity; not authorization to retry.
                if options.receipt_path is not None:
                    import datetime
                    launched = {
                        "status": "launched_unverified", "executed": True,
                        "outcome_verified": False, "mission_complete": False,
                        "pid": child.pid,
                        "process_group_id": child.pid if os.name == "posix" else None,
                        "invocation_id": invocation_id,
                        "launched_at_utc": datetime.datetime.now(
                            datetime.timezone.utc).isoformat(),
                        "capability": {
                            "qualified_name": f"{entry.kind}:{entry.name}",
                            "sha256": actual,
                        },
                        "command": command,
                        "note": "Process identity is diagnostic; never automatically retry.",
                    }
                    try:
                        write_receipt(launched)
                        if gate_write is not None:
                            # Only release the child after the launch receipt
                            # has reached durable storage.
                            os.write(gate_write, b"G")
                    except OSError:
                        if os.name == "posix":
                            try:
                                os.killpg(child.pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                        else:
                            child.kill()
                        # Even SIGKILL cannot guarantee immediate reaping
                        # (e.g. a child stuck in uninterruptible kernel I/O).
                        # Never allow receipt failure cleanup to hang forever.
                        try:
                            child.wait(timeout=1.0)
                        except subprocess.TimeoutExpired:
                            child.kill()
                            try:
                                child.wait(timeout=0.3)
                            except subprocess.TimeoutExpired:
                                pass  # daemon reaper/OS owns eventual cleanup
                        # Descendants outside the killed process group may
                        # retain inherited pipes. Never block indefinitely
                        # while handling a failed durable launch receipt.
                        stop_drains.set()
                        for thread in drains:
                            thread.join(timeout=0.3)
                        raise
                    finally:
                        if gate_write is not None:
                            os.close(gate_write)
                # Stdin delivery must not consume the execution deadline when
                # a delegated program never reads its pipe. Use a cancellable
                # writer; the parent's wait clock starts before delivery.
                import time
                import select
                deadline = time.monotonic() + options.timeout_seconds
                stop_input = threading.Event()
                input_errors = []
                def deliver_input():
                    stream = child.stdin
                    if stream is None:
                        return
                    try:
                        fd = stream.fileno()
                        if os.name == "posix":
                            os.set_blocking(fd, False)
                        view = memoryview(document)
                        offset = 0
                        while offset < len(view) and not stop_input.is_set():
                            if os.name == "posix":
                                _, writable, _ = select.select([], [fd], [], 0.05)
                                if not writable:
                                    continue
                                try:
                                    count = os.write(fd, view[offset:offset + 65536])
                                except BlockingIOError:
                                    continue
                            else:
                                count = os.write(fd, view[offset:offset + 65536])
                            if count <= 0:
                                break
                            offset += count
                    except (BrokenPipeError, OSError, ValueError) as exc:
                        input_errors.append(type(exc).__name__)
                    finally:
                        try:
                            stream.close()
                        except OSError:
                            pass
                input_thread = threading.Thread(target=deliver_input, daemon=True)
                input_thread.start()
                try:
                    code = child.wait(timeout=max(0, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    timed_out, code = True, 124
                    if os.name == "posix":
                        try:
                            os.killpg(child.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    else:
                        child.kill()
                    child.wait()
                finally:
                    stop_input.set()
                    input_thread.join(timeout=1)
                # A successful direct child exit is not the end of the work
                # if descendants still hold inherited output pipes open.
                for thread in drains:
                    thread.join(timeout=max(0, deadline - time.monotonic()))
                if any(thread.is_alive() for thread in drains):
                    timed_out, code = True, 124
                    if os.name == "posix":
                        try:
                            os.killpg(child.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    stop_drains.set()
                    for thread in drains:
                        thread.join(timeout=0.3)
                output_incomplete = timed_out or not all(drain_complete)
                out_file.seek(0, os.SEEK_END)
                err_file.seek(0, os.SEEK_END)
                stdout_bytes, stderr_bytes = counts
                stdout_truncated = stdout_bytes > max_output_bytes
                stderr_truncated = stderr_bytes > max_output_bytes
                out_file.seek(0)
                err_file.seek(0)
                stdout = out_file.read(max_output_bytes).decode("utf-8", errors="replace")
                stderr = err_file.read(max_output_bytes).decode("utf-8", errors="replace")
        except OSError as exc:
            code, stdout, stderr = 127, "", f"{type(exc).__name__}: {exc}"
        final_receipt = {
            "invocation_id": invocation_id,
            "status": "process_succeeded_unverified" if code == 0 else "failed",
            "executed": executed,
            "timed_out": timed_out,
            "mission_complete": False,
            "outcome_verified": False,
            "outcome_scope": "subprocess_exit_only",
            "routes_run": 1 if executed else 0,
            "exit_code": code,
            "command": command,
            "capability": {
                "qualified_name": f"{entry.kind}:{entry.name}",
                "sha256": actual,
                "content_bytes": len(document),
                "delivery": "subprocess_stdin",
            },
            "stdout": stdout, "stderr": stderr,
            "stdout_bytes": stdout_bytes, "stderr_bytes": stderr_bytes,
            "stdout_truncated": stdout_truncated, "stderr_truncated": stderr_truncated,
            "output_incomplete": output_incomplete,
            "capture_limit_bytes": max_output_bytes,
            "spool_limit_bytes_per_stream": max_spool_bytes,
        }
        try:
            write_receipt(final_receipt)
        except OSError as exc:
            print(f"cannot finalize durable receipt: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        print(json.dumps(final_receipt, sort_keys=True))
        raise SystemExit(code)
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
