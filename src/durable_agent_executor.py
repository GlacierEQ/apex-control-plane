"""Crash-safe execution claims for GLACIEREQ agent work.

A claim is committed before a provider is invoked. An interrupted or pending
attempt is never replayed automatically; an operator or authoritative provider
readback must reconcile it first. SQLite transactions serialize competing workers.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.dynamic_execution_fabric import DynamicExecutionFabric, ExecutionResult, SubstrateObservation, Workload


@dataclass(frozen=True)
class ClaimResult:
    state: str
    workload_id: str
    execution: ExecutionResult | None = None


class DurableAgentExecutor:
    """Single-host durable at-most-once invocation boundary per workload ID.

    The caller must keep the SQLite database on persistent local storage.
    This is not a distributed lease and does not prove remote side-effect success.
    """

    def __init__(self, database: str | Path, fabric: DynamicExecutionFabric | None = None):
        self.database = str(database)
        self.fabric = fabric or DynamicExecutionFabric()
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS execution_claims (
                workload_id TEXT PRIMARY KEY,
                objective TEXT NOT NULL,
                state TEXT NOT NULL,
                result_json TEXT
            )""")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database, timeout=30, isolation_level=None)
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def status(self, workload_id: str) -> str | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT state FROM execution_claims WHERE workload_id=?", (workload_id,)
            ).fetchone()
        return row[0] if row else None

    def readback(self, workload_id: str) -> dict[str, Any] | None:
        """Read the durable claim and outcome without invoking any provider."""
        with self._connect() as db:
            row = db.execute(
                "SELECT objective, state, result_json FROM execution_claims WHERE workload_id=?",
                (workload_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "workload_id": workload_id,
            "objective": row[0],
            "state": row[1],
            "result": json.loads(row[2]) if row[2] else None,
        }

    @staticmethod
    def inspect(database: str | Path, workload_id: str) -> dict[str, Any] | None:
        """Inspect an existing claim without creating or modifying SQLite state.

        Missing databases and absent claim tables return None. Other database
        errors propagate instead of being mistaken for an empty execution.
        """
        db_path = Path(database)
        if not db_path.is_file():
            return None
        with sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='execution_claims'"
            ).fetchone()
            if not exists:
                return None
            row = db.execute(
                "SELECT objective, state, result_json FROM execution_claims WHERE workload_id=?",
                (workload_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "workload_id": workload_id,
            "objective": row[0],
            "state": row[1],
            "result": json.loads(row[2]) if row[2] else None,
        }

    def execute(
        self,
        workload: Workload,
        observations: list[SubstrateObservation],
        executor: Callable[[str, Workload], Any],
    ) -> ClaimResult:
        # Reserve before invoking any provider. A crashed worker leaves an
        # ambiguous claim, not a free retry slot.
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                existing = db.execute(
                    "SELECT objective, state FROM execution_claims WHERE workload_id=?",
                    (workload.workload_id,),
                ).fetchone()
                if existing:
                    if existing[0] != workload.objective:
                        raise ValueError("workload ID already belongs to a different objective")
                    db.execute("COMMIT")
                    return ClaimResult("already_claimed:" + existing[1], workload.workload_id)
                db.execute(
                    "INSERT INTO execution_claims(workload_id, objective, state) VALUES (?, ?, 'invoking')",
                    (workload.workload_id, workload.objective),
                )
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise

        last_provider_result: Any = None

        def capturing_executor(substrate: str, work: Workload) -> Any:
            nonlocal last_provider_result
            last_provider_result = executor(substrate, work)
            return last_provider_result

        try:
            result = self.fabric.execute(workload, observations, capturing_executor)
        except BaseException:
            # Unknown side effects: leave invoking claim for reconciliation.
            raise
        state = "succeeded" if result.ok else (
            "failed_no_route" if result.status == "no_current_route" else "needs_reconciliation"
        )
        # Never release the claim automatically: even a reported terminal
        # failure can have a provider-side effect or an inconsistent adapter.
        with self._connect() as db:
            db.execute(
                "UPDATE execution_claims SET state=?, result_json=? WHERE workload_id=?",
                (state, json.dumps({
                    "status": result.status,
                    "attempted": result.attempted,
                    "substrate": result.substrate,
                    "provider_result": (
                        result.result if result.result is not None else last_provider_result
                    ) if isinstance(
                        result.result if result.result is not None else last_provider_result,
                        (dict, list, str, int, float, bool, type(None))
                    ) else repr(last_provider_result)[:16000],
                }, default=str), workload.workload_id),
            )
        return ClaimResult(state, workload.workload_id, result)

    def reconcile(self, workload_id: str, *, authoritative_state: str, evidence: str) -> None:
        """Record an externally verified terminal outcome, without re-executing.

        To retry, submit a new explicitly authorized workload ID after verifying
        that the prior invocation has no live side effect.
        """
        if authoritative_state not in {"succeeded", "failed", "cancelled"}:
            raise ValueError("authoritative_state must be terminal")
        if not evidence.strip():
            raise ValueError("provider readback or operator evidence required")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute(
                    "SELECT state FROM execution_claims WHERE workload_id=?", (workload_id,)
                ).fetchone()
                if row is None:
                    raise KeyError(workload_id)
                if row[0] not in {"invoking", "needs_reconciliation"}:
                    raise ValueError("only uncertain claims may be reconciled; terminal outcomes are immutable")
                db.execute(
                    "UPDATE execution_claims SET state=?, result_json=? WHERE workload_id=?",
                    (authoritative_state, json.dumps({"reconciliation_evidence": evidence}),
                     workload_id),
                )
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
