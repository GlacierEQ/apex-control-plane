"""Durable process-to-process mission continuation adapter for APEX.

Compounds existing lifecycle/receipt abstractions; it neither replaces source truth
nor supplies permission to execute. A new worker recovers the durable graph and
performs provider readback before attempting a reserved transition.

SQLite is a single shared-filesystem proof backend. Remote workers need a shared
transactional provider backend (e.g. an existing APEX database), not private copies.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Callable, Mapping, Any


class ResumeError(ValueError):
    """Invalid or unreconcilable mission recovery state."""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _check_plan(tasks: list[Mapping[str, Any]]) -> None:
    ids = [t["id"] for t in tasks]
    if len(ids) != len(set(ids)) or not ids:
        raise ResumeError("task ids must be present and unique")
    keys = [t["key"] for t in tasks]
    if len(keys) != len(set(keys)) or any(not v for v in keys):
        raise ResumeError("idempotency keys must be present and unique")
    all_ids = set(ids)
    graph = {t["id"]: t["deps"] for t in tasks}
    if any(set(deps) - all_ids for deps in graph.values()):
        raise ResumeError("dependency points to unknown task")
    visiting, done = set(), set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise ResumeError("dependency cycle")
        if task_id in done:
            return
        visiting.add(task_id)
        for predecessor in graph[task_id]:
            visit(predecessor)
        visiting.remove(task_id)
        done.add(task_id)

    for task_id in ids:
        visit(task_id)


class MissionCheckpointStore:
    """Atomic task claim/receipt store for agents sharing the same SQLite path.

    No automatic retry after an ambiguous provider side effect. The external
    provider remains the truth; a local claims table is not a native receipt.
    """

    def __init__(self, path: str | Path, *, mission_id: str | None = None):
        self.path = str(path)
        if mission_id is not None and not mission_id.strip():
            raise ResumeError("mission_id must be nonblank when specified")
        self.mission_id = mission_id
        with self._connect() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS missions (
                    mission_id TEXT PRIMARY KEY, objective TEXT NOT NULL,
                    outcome TEXT NOT NULL, plan_sha256 TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'ACTIVE');
                CREATE TABLE IF NOT EXISTS tasks (
                    mission_id TEXT NOT NULL, task_id TEXT NOT NULL,
                    ordering INTEGER NOT NULL, deps_json TEXT NOT NULL,
                    key TEXT NOT NULL UNIQUE, provider TEXT NOT NULL,
                    expected TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'READY',
                    claimed_by TEXT, receipt TEXT,
                    PRIMARY KEY(mission_id,task_id));
                CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mission_id TEXT NOT NULL, task_id TEXT,
                    event TEXT NOT NULL, details_json TEXT NOT NULL,
                    observed_at TEXT NOT NULL);
            """)

    @contextmanager
    def _connect(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA busy_timeout=30000")
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    @staticmethod
    def _event(c, mission_id: str, task_id: str | None, event: str, details: Mapping[str, Any]):
        c.execute("INSERT INTO events(mission_id,task_id,event,details_json,observed_at) VALUES (?,?,?,?,?)",
                  (mission_id, task_id, event, _canonical(details), datetime.now(timezone.utc).isoformat()))

    def initialize(self, *, mission_id: str, operator_objective: str,
                   desired_outcome: str, tasks: list[Mapping[str, Any]]) -> None:
        _check_plan(tasks)
        if self.mission_id is not None and self.mission_id != mission_id:
            raise ResumeError("mission selection and initialization mission_id mismatch")
        if not mission_id or not operator_objective or not desired_outcome:
            raise ResumeError("mission id, original objective and outcome required")
        material = dict(mission_id=mission_id, objective=operator_objective,
                        outcome=desired_outcome, tasks=tasks)
        digest = hashlib.sha256(_canonical(material).encode()).hexdigest()
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            existing = c.execute("SELECT plan_sha256 FROM missions WHERE mission_id=?",(mission_id,)).fetchone()
            if existing:
                if existing['plan_sha256'] != digest:
                    raise ResumeError("existing mission plan mismatch: use source reconciliation, not overwrite")
                return
            c.execute("INSERT INTO missions(mission_id,objective,outcome,plan_sha256) VALUES (?,?,?,?)",
                      (mission_id,operator_objective,desired_outcome,digest))
            for t in tasks:
                c.execute("INSERT INTO tasks(mission_id,task_id,ordering,deps_json,key,provider,expected) VALUES (?,?,?,?,?,?,?)",
                          (mission_id,t['id'],t['order'],_canonical(t['deps']),t['key'],t['provider'],t['expected']))
            self._event(c,mission_id,None,"mission_recovered",{"plan_sha256":digest})

    def _get_mission(self, c):
        if self.mission_id is not None:
            row = c.execute("SELECT mission_id FROM missions WHERE mission_id=?",
                            (self.mission_id,)).fetchone()
            if row is None:
                raise ResumeError("selected mission not present in checkpoint store")
            return row["mission_id"]
        rows=c.execute("SELECT mission_id FROM missions ORDER BY mission_id").fetchall()
        if len(rows) != 1:
            raise ResumeError("explicit mission selection required for multi-mission stores")
        return rows[0]['mission_id']

    def reconcile(self, readback: Callable[[str,str], str | None]) -> set[str]:
        """Never use a mutation response as proof: only this separate readback."""
        with self._connect() as c:
            mission=self._get_mission(c)
            snapshots=c.execute("SELECT * FROM tasks WHERE mission_id=? AND state!='VERIFIED_STEP'",(mission,)).fetchall()
        unreadable: set[str] = set()
        for row in snapshots:
            try:
                native_receipt = readback(row['key'], row['expected'])
            except Exception:
                # Failure is local to this provider/task. Never dispatch a READY task
                # when its live provider state cannot be checked; other lanes continue.
                unreadable.add(row['task_id'])
                with self._connect() as c:
                    c.execute("BEGIN IMMEDIATE")
                    if row['state'] == 'IN_FLIGHT':
                        c.execute("UPDATE tasks SET state='NEEDS_PROOF' WHERE mission_id=? AND task_id=? AND state='IN_FLIGHT'",
                                  (mission, row['task_id']))
                    self._event(c, mission, row['task_id'], 'provider_unavailable_route_local',
                                {'key': row['key'], 'retry_mutation': False})
                continue
            with self._connect() as c:
                c.execute("BEGIN IMMEDIATE")
                current=c.execute("SELECT state,claimed_by FROM tasks WHERE mission_id=? AND task_id=?",
                                  (mission,row['task_id'])).fetchone()
                if current is None:
                    raise ResumeError("task disappeared during provider reconciliation")
                # The provider read ran outside the DB transaction. Only apply it
                # to the exact state/claim it observed; another worker may have
                # reserved the action while this readback was still in flight.
                if (current['state'] != row['state'] or
                        current['claimed_by'] != row['claimed_by']):
                    self._event(c, mission, row['task_id'], "stale_readback_ignored",
                                {"observed_state": row['state'],
                                 "current_state": current['state'],
                                 "key": row['key']})
                    continue
                if current['state']=='VERIFIED_STEP':
                    continue
                if native_receipt:
                    c.execute("UPDATE tasks SET state='VERIFIED_STEP',receipt=?,claimed_by=NULL WHERE mission_id=? AND task_id=?",
                              (str(native_receipt),mission,row['task_id']))
                    self._event(c,mission,row['task_id'],"native_readback_verified",
                                {"receipt":str(native_receipt),"provider":row['provider'],"key":row['key']})
                elif current['state']=='IN_FLIGHT':
                    c.execute("UPDATE tasks SET state='NEEDS_PROOF' WHERE mission_id=? AND task_id=?",(mission,row['task_id']))
                    self._event(c,mission,row['task_id'],"unknown_external_effect_no_retry",{"key":row['key']})
        return unreadable

    def resume(self, agent: str, readback: Callable[[str,str],str | None]) -> dict | None:
        if not agent or not agent.strip():
            raise ResumeError("agent identity required")
        unreadable = self.reconcile(readback)
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            mission=self._get_mission(c)
            tasks=c.execute("SELECT * FROM tasks WHERE mission_id=? ORDER BY ordering,task_id",(mission,)).fetchall()
            verified={t['task_id'] for t in tasks if t['state']=='VERIFIED_STEP'}
            for row in tasks:
                if row['state']=='READY' and row['task_id'] not in unreadable and set(json.loads(row['deps_json'])) <= verified:
                    c.execute("UPDATE tasks SET state='IN_FLIGHT',claimed_by=? WHERE mission_id=? AND task_id=? AND state='READY'",
                              (agent,mission,row['task_id']))
                    self._event(c,mission,row['task_id'],"task_reserved",{"agent":agent,"key":row['key']})
                    return dict(mission_id=mission,task_id=row['task_id'],provider=row['provider'],
                                expected=row['expected'],idempotency_key=row['key'])
        return None

    def rearm_after_provider_guarantee(
        self, task_id: str, *, provider_idempotency_ref: str,
        readback: Callable[[str, str], str | None],
        idempotency_verifier: Callable[[str, str, str], Mapping[str, Any]] | None = None,
    ) -> str:
        """Rearm an uncertain claim only under an externally verified replay guarantee.

        The caller must establish that the native provider actually enforces the
        same idempotency key on repeated requests. This method validates the
        presence of an attributable provider reference; it cannot independently
        prove the guarantee or authorize an external mutation. It re-reads native
        state immediately before any durable cursor change.
        """
        if not isinstance(provider_idempotency_ref, str) or not (
            provider_idempotency_ref.startswith("provider-native:") and
            provider_idempotency_ref.strip() != "provider-native:"
        ):
            raise ResumeError("provider-native idempotency guarantee reference required")
        with self._connect() as c:
            mission = self._get_mission(c)
            row = c.execute(
                "SELECT state,key,expected,provider FROM tasks WHERE mission_id=? AND task_id=?",
                (mission, task_id),
            ).fetchone()
            if row is None:
                raise ResumeError("unknown task")
            if row["state"] != "NEEDS_PROOF":
                raise ResumeError("only an ambiguous NEEDS_PROOF claim can be rearmed")
        if idempotency_verifier is None:
            raise ResumeError("independent provider idempotency verifier required")
        # The provider-specific adapter (NOT the agent's prose or reference
        # string) must attest that this exact operation key is replay-safe.
        try:
            evidence = idempotency_verifier(
                row["provider"], row["key"], provider_idempotency_ref
            )
        except Exception as exc:
            raise ResumeError("provider idempotency attestation unavailable") from exc
        if not isinstance(evidence, Mapping) or not (
            evidence.get("provider") == row["provider"] and
            evidence.get("idempotency_key") == row["key"] and
            evidence.get("reference") == provider_idempotency_ref and
            evidence.get("native_enforced") is True and
            isinstance(evidence.get("evidence"), str) and
            bool(evidence["evidence"].strip())
        ):
            raise ResumeError("provider guarantee mismatch or missing native evidence")
        try:
            native_receipt = readback(row["key"], row["expected"])
        except Exception as exc:
            raise ResumeError("provider readback unavailable: ambiguous claim unchanged") from exc
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            current = c.execute(
                "SELECT state,key FROM tasks WHERE mission_id=? AND task_id=?",
                (mission, task_id),
            ).fetchone()
            if (current is None or current["state"] != "NEEDS_PROOF" or
                    current["key"] != row["key"]):
                raise ResumeError("claim changed during readback; recover again")
            if native_receipt:
                c.execute(
                    "UPDATE tasks SET state='VERIFIED_STEP',receipt=?,claimed_by=NULL "
                    "WHERE mission_id=? AND task_id=? AND state='NEEDS_PROOF'",
                    (str(native_receipt), mission, task_id),
                )
                self._event(c, mission, task_id, "late_native_receipt_verified",
                            {"key": row["key"], "receipt": str(native_receipt)})
                return "VERIFIED_STEP"
            c.execute(
                "UPDATE tasks SET state='READY',claimed_by=NULL "
                "WHERE mission_id=? AND task_id=? AND state='NEEDS_PROOF'",
                (mission, task_id),
            )
            self._event(c, mission, task_id, "rearmed_after_provider_idempotency_guarantee",
                        {"key": row["key"],
                         "provider": row["provider"],
                         "provider_idempotency_ref": provider_idempotency_ref,
                         "provider_guarantee_evidence": evidence["evidence"],
                         "native_readback": "no_receipt",
                         "warning": "absence alone is not proof of nonexecution"})
            return "READY"

    def task_state(self, task_id: str) -> str:
        with self._connect() as c:
            mission = self._get_mission(c)
            row=c.execute("SELECT state FROM tasks WHERE mission_id=? AND task_id=?",
                          (mission, task_id)).fetchone()
        if row is None:
            raise ResumeError("unknown task")
        return row['state']

    def task_receipt(self, task_id: str) -> str | None:
        with self._connect() as c:
            mission = self._get_mission(c)
            row=c.execute("SELECT receipt FROM tasks WHERE mission_id=? AND task_id=?",
                          (mission, task_id)).fetchone()
        if row is None:
            raise ResumeError("unknown task")
        return row['receipt']

    def mission_state(self) -> str:
        with self._connect() as c:
            mission=self._get_mission(c)
            return c.execute("SELECT state FROM missions WHERE mission_id=?",(mission,)).fetchone()['state']
