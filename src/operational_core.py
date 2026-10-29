"""Direct durable execution; independent of legacy APEX startup gates.

The host supplies an authenticated provider adapter with execute(payload, id)
and verify(payload). Verification is an independent target read; True means the
effect exists, False means absent, None means inconclusive. Only idempotent
operations can be replayed after a confirmed missing effect.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Mapping, Protocol


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return sha256(_json(value).encode("utf-8")).hexdigest()


class OperationConflict(ValueError):
    """An idempotency key cannot represent two different requested effects."""


class Adapter(Protocol):
    idempotent: bool

    def execute(self, payload: Mapping[str, Any], operation_id: str) -> Any: ...
    def verify(self, payload: Mapping[str, Any]) -> bool | None: ...


@dataclass(frozen=True)
class Status:
    operation_id: str
    adapter: str
    state: str
    attempts: int
    verified: bool
    result_sha256: str | None
    error_type: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class OperationalCore:
    """SQLite-backed dispatcher with crash recovery, direct work and readback."""

    def __init__(self, state_path: str | Path, adapters: Mapping[str, Adapter], *,
                 lease_seconds: int = 60):
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        self.path = Path(state_path)
        self.adapters = dict(adapters)
        self.lease_seconds = lease_seconds
        self.path.parent.mkdir(parents=True, exist_ok=True)
        first = not self.path.exists()
        self.db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        if first and os.name == "posix":
            os.chmod(self.path, 0o600)
        self.db.execute("PRAGMA busy_timeout=15000")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS operations (
            id TEXT PRIMARY KEY, adapter TEXT NOT NULL,
            request TEXT NOT NULL, request_digest TEXT NOT NULL,
            state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
            lease_until TEXT, result_sha256 TEXT, error_type TEXT,
            updated_at TEXT NOT NULL
        )""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_id TEXT NOT NULL, state TEXT NOT NULL,
            observed_at TEXT NOT NULL, detail TEXT NOT NULL
        )""")

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "OperationalCore":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _event(self, op_id: str, state: str, detail: str) -> None:
        self.db.execute("INSERT INTO events(operation_id,state,observed_at,detail) VALUES(?,?,?,?)",
                        (op_id, state, _now().isoformat(), detail))

    def submit(self, operation_id: str, adapter: str, payload: Mapping[str, Any]) -> Status:
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ValueError("operation_id must be a nonempty string")
        if adapter not in self.adapters:
            raise ValueError(f"adapter not registered: {adapter}")
        if not isinstance(payload, Mapping):
            raise ValueError("payload must be a mapping")
        serialized = _json(dict(payload))
        digest = _digest({"adapter": adapter, "payload": dict(payload)})
        self.db.execute("BEGIN IMMEDIATE")
        try:
            old = self.db.execute("SELECT request_digest FROM operations WHERE id=?", (operation_id,)).fetchone()
            if old:
                if old["request_digest"] != digest:
                    raise OperationConflict("same idempotency key, different operation")
            else:
                self.db.execute("""INSERT INTO operations
                    (id,adapter,request,request_digest,state,updated_at)
                    VALUES(?,?,?,?,?,?)""",
                    (operation_id, adapter, serialized, digest, "queued", _now().isoformat()))
                self._event(operation_id, "queued", "accepted")
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return self.status(operation_id)

    def status(self, operation_id: str) -> Status:
        r = self.db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
        if not r:
            raise KeyError(operation_id)
        return Status(operation_id, r["adapter"], r["state"], r["attempts"],
                      r["state"] == "verified", r["result_sha256"], r["error_type"])

    def _transition(self, operation_id: str, state: str, *,
                    result_sha256: str | None = None, error_type: str | None = None) -> Status:
        self.db.execute("""UPDATE operations SET state=?, lease_until=NULL,
            result_sha256=COALESCE(?,result_sha256), error_type=?, updated_at=? WHERE id=?""",
            (state, result_sha256, error_type, _now().isoformat(), operation_id))
        self._event(operation_id, state, error_type or "provider_readback")
        return self.status(operation_id)

    def _verify(self, adapter: Adapter, payload: Mapping[str, Any]) -> bool | None:
        try:
            verdict = adapter.verify(payload)
        except Exception:
            return None
        if verdict is not None and type(verdict) is not bool:
            return None
        return verdict

    def run(self, operation_id: str) -> Status:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            r = self.db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            if not r:
                raise KeyError(operation_id)
            adapter = self.adapters[r["adapter"]]
            if r["state"] == "verified":
                self.db.execute("COMMIT")
                return self.status(operation_id)
            if r["state"] == "running" and r["lease_until"] and datetime.fromisoformat(r["lease_until"]) > _now():
                self.db.execute("COMMIT")
                return self.status(operation_id)
            payload = json.loads(r["request"])
            if r["attempts"] > 0:
                # An earlier provider effect can exist even if its response was lost.
                self.db.execute("COMMIT")
                verdict = self._verify(adapter, payload)
                if verdict is True:
                    return self._finish(operation_id, "verified")
                if verdict is None:
                    return self._finish(operation_id, "uncertain", error_type="readback_unavailable")
                if not adapter.idempotent:
                    return self._finish(operation_id, "needs_reconciliation", error_type="non_idempotent_replay")
                self.db.execute("BEGIN IMMEDIATE")
                r = self.db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
                if r["state"] == "verified":
                    self.db.execute("COMMIT")
                    return self.status(operation_id)
                if r["state"] == "running" and r["lease_until"] and datetime.fromisoformat(r["lease_until"]) > _now():
                    self.db.execute("COMMIT")
                    return self.status(operation_id)
            lease = (_now() + timedelta(seconds=self.lease_seconds)).isoformat()
            self.db.execute("""UPDATE operations SET attempts=attempts+1,
                state='running', lease_until=?, error_type=NULL, updated_at=? WHERE id=?""",
                (lease, _now().isoformat(), operation_id))
            self._event(operation_id, "running", "dispatch")
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

        try:
            result = adapter.execute(payload, operation_id)
            result_hash = _digest(result) if result is not None else None
            failure = None
        except Exception as exc:
            result_hash = None
            failure = type(exc).__name__

        verdict = self._verify(adapter, payload)
        if verdict is True:
            return self._finish(operation_id, "verified", result_sha256=result_hash)
        if verdict is None:
            return self._finish(operation_id, "uncertain", result_sha256=result_hash,
                                error_type=failure or "readback_unavailable")
        if adapter.idempotent:
            return self._finish(operation_id, "retryable", result_sha256=result_hash,
                                error_type=failure or "desired_effect_missing")
        return self._finish(operation_id, "needs_reconciliation", result_sha256=result_hash,
                            error_type=failure or "desired_effect_missing")

    def _finish(self, operation_id: str, state: str, *,
                result_sha256: str | None = None, error_type: str | None = None) -> Status:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            current = self.db.execute("SELECT state FROM operations WHERE id=?", (operation_id,)).fetchone()
            if current is None:
                raise KeyError(operation_id)
            if current["state"] == "verified":
                self.db.execute("COMMIT")
                return self.status(operation_id)
            status = self._transition(operation_id, state, result_sha256=result_sha256, error_type=error_type)
            self.db.execute("COMMIT")
            return status
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def events(self, operation_id: str) -> list[dict[str, str]]:
        return [dict(row) for row in self.db.execute(
            "SELECT state,observed_at,detail FROM events WHERE operation_id=? ORDER BY sequence",
            (operation_id,))]


class FileWriteAdapter:
    """Explicit, idempotent local file action, verified by independent read."""

    idempotent = True

    def execute(self, payload: Mapping[str, Any], operation_id: str) -> dict[str, str]:
        destination = Path(str(payload["path"]))
        content = payload["content"]
        if not isinstance(content, str):
            raise ValueError("file content must be text")
        if destination.is_symlink():
            raise ValueError("refusing to overwrite a symbolic link")
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent,
                                             prefix=".operational-", delete=False) as stream:
                tmp_path = stream.name
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp_path, destination)
        finally:
            if tmp_path is not None and os.path.exists(tmp_path):
                os.unlink(tmp_path)
        return {"path": str(destination), "sha256": sha256(content.encode()).hexdigest()}

    def verify(self, payload: Mapping[str, Any]) -> bool | None:
        destination = Path(str(payload["path"]))
        if destination.is_symlink():
            return None
        try:
            actual = destination.read_bytes()
        except FileNotFoundError:
            return False
        except OSError:
            return None
        return actual == str(payload["content"]).encode("utf-8")
