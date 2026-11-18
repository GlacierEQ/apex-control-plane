"""Runnable GLACIEREQ agent work-unit entrypoint.

Example:
  python -m src.agent_work_runner --database ./agent-state.sqlite \
      --workload-id demo-001 --objective "Inspect repository" \
      --command "python -m pytest -q tests/test_durable_agent_executor.py"

Commands are explicit local operator-provided work units, not model-generated shell.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from src.durable_agent_executor import DurableAgentExecutor
from src.dynamic_execution_fabric import SubstrateObservation, Workload


def run_work_unit(
    database: str | Path,
    workload_id: str,
    objective: str,
    command: list[str],
    *,
    timeout_seconds: int = 300,
) -> dict:
    if (not isinstance(command, list) or not command or not command[0]
            or any(not isinstance(arg, str) or "\\x00" in arg for arg in command)):
        raise ValueError("command must be a nonempty argv string list")
    if type(timeout_seconds) is not int or timeout_seconds <= 0:
        raise ValueError("timeout must be a positive integer")

    command_identity = hashlib.sha256(json.dumps({"argv": command, "timeout_seconds": timeout_seconds}, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    workload = Workload(workload_id, objective + " [argv-sha256:" + command_identity + "]", frozenset({"local_process"}))
    observation = SubstrateObservation(
        name="local_process",
        capabilities=frozenset({"local_process"}),
        health="healthy",
        health_score=1.0,
        private_repo=False,
        exact_source=False,
        receipts=False,
        terminal_readback=False,
        observed_at=datetime.now(UTC),
    )

    def invoke(_substrate: str, _workload: Workload) -> dict:
        # No shell=True, no interpolation. Each argument is passed literally.
        # Own the child process group so timeout cleanup includes descendants.
        # A timed-out process is still uncertain: cleanup does not prove that
        # its external side effects were rolled back.
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=(os.name == "posix"),
            )
        except OSError as error:
            # No child was started. Persist actionable failure evidence instead
            # of leaving an opaque invoking claim after an exception.
            return {
                "status": "failed",
                "error": "process_spawn_failed",
                "errno": error.errno,
                "detail": str(error)[:2000],
                "returncode": None,
                "stdout": "",
                "stderr": "",
            }
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
            stdout, stderr = process.communicate()
            return {
                "status": "unconfirmed",
                "error": "process_timeout",
                "returncode": process.returncode,
                "stdout": stdout[-16000:],
                "stderr": stderr[-16000:],
            }
        return {
            "status": "success" if process.returncode == 0 else "failed",
            "returncode": process.returncode,
            "stdout": stdout[-16000:],
            "stderr": stderr[-16000:],
        }

    durable = DurableAgentExecutor(database)
    outcome = durable.execute(workload, [observation], invoke)
    execution = outcome.execution
    durable_record = durable.readback(workload_id)
    # Failed provider outcomes are represented by the fabric as route_exhausted.
    # Preserve the actual subprocess evidence from the durable record rather
    # than presenting a missing result to the caller.
    persisted = (durable_record or {}).get("result") or {}
    provider_result = execution.result if execution and execution.result is not None else persisted.get("provider_result")
    return {
        "workload_id": workload_id,
        "state": outcome.state,
        "status": execution.status if execution else None,
        "result": provider_result,
        "attempted": list(execution.attempted) if execution else [],
        "durable_record": durable_record,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Execute a durable GLACIEREQ work unit")
    parser.add_argument("--database", required=True)
    parser.add_argument("--workload-id", required=True)
    parser.add_argument("--objective")
    parser.add_argument("--readback", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.readback:
        record = DurableAgentExecutor.inspect(args.database, args.workload_id)
        print(json.dumps(record, sort_keys=True))
        return 0 if record is not None else 1
    if not args.objective or not args.command:
        parser.error("--objective and --command required for execution")
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    output = run_work_unit(
        args.database, args.workload_id, args.objective, command,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(output, sort_keys=True))
    return 0 if output["state"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
