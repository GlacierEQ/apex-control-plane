"""Durable dependency-aware work-unit orchestration.

Consumes a JSON plan of explicitly authorized argv commands. Each node is
persistently claimed by the existing work runner. On restart, completed nodes
are read back; uncertain or failed nodes block dependents instead of replaying.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
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
        if not isinstance(identifier, str) or not identifier.strip() or identifier in ids or identifier == "__plan_manifest__" or ":" in identifier:
            raise ValueError("job ids must be unique nonempty strings")
        argv = job.get("command")
        if (not isinstance(argv, list) or not argv or not argv[0]
                or any(not isinstance(x, str) or "\\x00" in x for x in argv)):
            raise ValueError("command must be a nonempty argv string list")
        if not isinstance(job.get("objective"), str) or not job["objective"].strip():
            raise ValueError("job objective is required")
        timeout = job.get("timeout_seconds", 300)
        if type(timeout) is not int or timeout <= 0:
            raise ValueError("timeout_seconds must be a positive integer")
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
    if not isinstance(namespace, str) or not namespace.strip() or ":" in namespace:
        raise ValueError("plan.id is required")
    durable = DurableAgentExecutor(database)
    # Bind the whole graph to its namespace before any side effect. Otherwise
    # a resumed plan could silently change dependencies or skip prior jobs.
    manifest = [
        {
            "id": job["id"], "objective": job["objective"],
            "command": job["command"], "depends_on": sorted(job.get("depends_on", [])),
            "timeout_seconds": job.get("timeout_seconds", 300),
        }
        for job in sorted(ordered, key=lambda item: item["id"])
    ]
    fingerprint = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    manifest_id = namespace + ":__plan_manifest__"
    # Claim a manifest using the same transactional durable identity mechanism.
    # This never invokes a provider: the manifest is a persistent identity record.
    import sqlite3
    with sqlite3.connect(str(database), timeout=30, isolation_level=None) as db:
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("BEGIN IMMEDIATE")
        try:
            existing = db.execute(
                "SELECT objective FROM execution_claims WHERE workload_id=?", (manifest_id,)
            ).fetchone()
            if existing and existing[0] != fingerprint:
                raise ValueError("plan id already belongs to a different graph")
            if not existing:
                db.execute(
                    "INSERT INTO execution_claims(workload_id, objective, state) VALUES (?, ?, 'succeeded')",
                    (manifest_id, fingerprint),
                )
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
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



def inspect_plan(database: str | Path, plan: dict[str, Any]) -> dict[str, Any]:
    """Read DAG progress without claiming, dispatching, or executing any job."""
    ordered = validate_plan(plan)
    namespace = plan.get("id")
    if not isinstance(namespace, str) or not namespace.strip() or ":" in namespace:
        raise ValueError("plan.id must be a nonempty unambiguous identifier")
    manifest = [
        {
            "id": job["id"], "objective": job["objective"],
            "command": job["command"], "depends_on": sorted(job.get("depends_on", [])),
            "timeout_seconds": job.get("timeout_seconds", 300),
        }
        for job in sorted(ordered, key=lambda item: item["id"])
    ]
    fingerprint = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    # Inspect without creating a database, schema, or execution claim.
    records: dict[str, dict[str, Any]] = {}
    db_path = Path(database)
    if db_path.exists():
        connection = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            # Pin one SQLite snapshot across manifest and job reads. Without
            # BEGIN, concurrent reconciliation can produce a mixed-time DAG.
            connection.execute("BEGIN")
            table = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='execution_claims'"
            ).fetchone()
            if table:
                ids = [namespace + ":__plan_manifest__"] + [
                    namespace + ":" + job["id"] for job in ordered
                ]
                for workload_id in ids:
                    row = connection.execute(
                        "SELECT objective, state, result_json FROM execution_claims WHERE workload_id=?",
                        (workload_id,),
                    ).fetchone()
                    if row:
                        records[workload_id] = {
                            "workload_id": workload_id,
                            "objective": row[0],
                            "state": row[1],
                            "result": json.loads(row[2]) if row[2] else None,
                        }
            connection.execute("COMMIT")
        finally:
            connection.close()
    stored = records.get(namespace + ":__plan_manifest__")
    if stored and stored["objective"] != fingerprint:
        raise ValueError("plan id already belongs to a different graph")
    outcomes: dict[str, dict[str, Any]] = {}
    for job in ordered:
        identifier = job["id"]
        deps = job.get("depends_on", [])
        record = records.get(namespace + ":" + identifier)
        if record is not None:
            state = record["state"]
        elif any(outcomes[dep]["state"] != "succeeded" for dep in deps):
            state = "blocked_dependency"
        else:
            state = "not_started"
        outcomes[identifier] = {"state": state, "record": record}
    return {
        "plan_id": namespace,
        "manifest_recorded": stored is not None,
        "ok": bool(stored) and all(item["state"] == "succeeded" for item in outcomes.values()),
        "jobs": outcomes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Execute a durable dependency DAG")
    parser.add_argument("--database", required=True)
    parser.add_argument("--plan", required=True, help="JSON plan file")
    parser.add_argument("--readback", action="store_true", help="Inspect persisted DAG without executing")
    args = parser.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    result = inspect_plan(args.database, plan) if args.readback else execute_plan(args.database, plan)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
