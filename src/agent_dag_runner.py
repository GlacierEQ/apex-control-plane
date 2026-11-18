"""Durable dependency-aware work-unit orchestration.

Consumes a JSON plan of explicitly authorized argv commands. Each node is
persistently claimed by the existing work runner. On restart, completed nodes
are read back; uncertain or failed nodes block dependents instead of replaying.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.agent_work_runner import run_work_unit
from src.durable_agent_executor import DurableAgentExecutor


def validate_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = plan.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise ValueError("plan.jobs must be a nonempty list")
    ids: set[str] = set()
    by_id: dict[str, dict[str, Any]] = {}
    for job in jobs:
        if not isinstance(job, dict):
            raise ValueError("each job must be an object")
        identifier = job.get("id")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in ids:
            raise ValueError("job ids must be unique nonempty strings")
        argv = job.get("command")
        if not isinstance(argv, list) or not argv or any(not isinstance(x, str) for x in argv):
            raise ValueError("command must be a nonempty argv string list")
        if not isinstance(job.get("objective"), str) or not job["objective"].strip():
            raise ValueError("job objective is required")
        deps = job.get("depends_on", [])
        if not isinstance(deps, list) or any(not isinstance(x, str) for x in deps) or len(deps) != len(set(deps)):
            raise ValueError("depends_on must contain unique job ids")
        ids.add(identifier)
        by_id[identifier] = job
    for job in jobs:
        if any(dep not in ids for dep in job.get("depends_on", [])):
            raise ValueError("unknown dependency")
    ordered: list[dict[str, Any]] = []
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(identifier: str) -> None:
        if identifier in visiting:
            raise ValueError("dependency cycle")
        if identifier in visited:
            return
        visiting.add(identifier)
        for dep in by_id[identifier].get("depends_on", []):
            visit(dep)
        visiting.remove(identifier)
        visited.add(identifier)
        ordered.append(by_id[identifier])

    for job in jobs:
        visit(job["id"])
    return ordered


def execute_plan(database: str | Path, plan: dict[str, Any]) -> dict[str, Any]:
    # Validate the entire DAG before executing any command.
    ordered = validate_plan(plan)
    namespace = plan.get("id")
    if not isinstance(namespace, str) or not namespace.strip():
        raise ValueError("plan.id is required")
    durable = DurableAgentExecutor(database)
    outcomes: dict[str, dict[str, Any]] = {}
    for job in ordered:
        identifier = job["id"]
        deps = job.get("depends_on", [])
        if any(outcomes[dep]["state"] != "succeeded" for dep in deps):
            outcomes[identifier] = {"state": "blocked_dependency", "dependencies": deps}
            continue
        workload_id = namespace + ":" + identifier
        result = run_work_unit(
            database, workload_id, job["objective"], job["command"],
            timeout_seconds=job.get("timeout_seconds", 300),
        )
        # A duplicate invocation is safe to consume only if the durable
        # record proves success; a claimed-but-unconfirmed node blocks the DAG.
        record = durable.readback(workload_id)
        state = record["state"] if record else "unconfirmed"
        outcomes[identifier] = {
            "state": state,
            "invocation": result["state"],
            "record": record,
        }
    return {
        "plan_id": namespace,
        "ok": all(item["state"] == "succeeded" for item in outcomes.values()),
        "jobs": outcomes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Execute a durable dependency DAG")
    parser.add_argument("--database", required=True)
    parser.add_argument("--plan", required=True, help="JSON plan file")
    args = parser.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    result = execute_plan(args.database, plan)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
