"""Durable SQLite callbacks for the existing source-bound APEX session gateway.

This adapter is part of the APEX execution boundary, not a replacement memory
system. It stores model-authored output and source-only, non-authoritative
memory candidates with explicit speaker and correction lineage. The host must
still authenticate Spiral and original source bytes independently.

SQLite proves durability only for hosts sharing the same owner-private file;
distributed/remote workers require a shared transactional provider backend.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
import json
import os
from pathlib import Path
import sqlite3
import stat
from typing import Any

from .apex_session_gateway import (
    ContinuationEnvelope, GatewayDenied, MemoryProposal, SourceAssertion,
    _envelope_digest, _snapshot,
)


class GatewayStoreDenied(GatewayDenied):
    """Storage integrity, ownership, mission isolation or proof failed."""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class GatewayCheckpointStore:
    """Atomic reservation, checkpoint and independent process readback.

    Callable interfaces: `reserve`, `persist`, and `readback` can be bound
    directly into run_admitted_session. An unknown or failed model effect stays
    reserved; no automatic retry converts uncertainty into duplicate effects.
    """

    def __init__(self, path: str | Path, *, mission_id: str):
        if (not isinstance(mission_id, str) or not mission_id.strip()
                or ":" in mission_id):
            raise GatewayStoreDenied("explicit unambiguous mission identity required")
        if not isinstance(path, (str, Path)) or not str(path).strip():
            raise GatewayStoreDenied("owner-private SQLite path required")
        self.path = Path(path).expanduser()
        self.mission_id = mission_id
        self._check_private_path(create=True)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""
                CREATE TABLE IF NOT EXISTS apex_session_gateway_continuations (
                    operation_key TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'RESERVED'
                        CHECK (state IN ('RESERVED','CHECKPOINTED')),
                    envelope_json TEXT,
                    envelope_digest TEXT,
                    reserved_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)

    def _check_private_path(self, *, create: bool = False) -> None:
        parent = self.path.parent
        try:
            directory = os.lstat(parent)
        except OSError as exc:
            raise GatewayStoreDenied("owner-private store directory unavailable") from exc
        if (not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.getuid()
                or directory.st_mode & 0o077):
            raise GatewayStoreDenied("store directory must be owner-private")
        try:
            f = os.lstat(self.path)
        except FileNotFoundError:
            if not create:
                raise GatewayStoreDenied("checkpoint database missing; no implicit recreation")
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            try:
                fd = os.open(self.path, flags, 0o600)
            except FileExistsError:
                pass  # Another authorized process won creation; validate below.
            except OSError as exc:
                raise GatewayStoreDenied("cannot initialize private checkpoint store") from exc
            else:
                os.close(fd)
            f = os.lstat(self.path)
        if (not stat.S_ISREG(f.st_mode) or f.st_uid != os.getuid()
                or f.st_mode & 0o077):
            raise GatewayStoreDenied("checkpoint database must be owner-private regular file; symlink refused")

    @contextmanager
    def _connect(self):
        self._check_private_path()
        db = sqlite3.connect(str(self.path), timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout = 30000")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _validate_operation_key(self, key: str) -> None:
        if not isinstance(key, str):
            raise GatewayStoreDenied("operation key must be text")
        parts = key.split(":")
        if (len(parts) != 4 or any(not part.strip() for part in parts)
                or parts[0] != self.mission_id):
            raise GatewayStoreDenied("operation mission mismatch or ambiguous key")
        if parts[1] != "model":
            raise GatewayStoreDenied("only a model invocation can be reserved by this store")

    def reserve(self, operation_key: str) -> bool:
        """Atomically insert-if-absent BEFORE the model callback."""
        self._validate_operation_key(operation_key)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            result = db.execute(
                "INSERT OR IGNORE INTO apex_session_gateway_continuations "
                "(operation_key,mission_id) VALUES (?,?)",
                (operation_key, self.mission_id),
            )
            return result.rowcount == 1

    def persist(self, envelope: ContinuationEnvelope) -> str:
        """Write only a validated, already-reserved envelope; never auto-promote memory."""
        if not isinstance(envelope, ContinuationEnvelope):
            raise GatewayStoreDenied("typed continuation envelope required")
        self._validate_operation_key(envelope.operation_key)
        if envelope.mission_id != self.mission_id:
            raise GatewayStoreDenied("checkpoint mission mismatch")
        if envelope.response_author != "assistant":
            raise GatewayStoreDenied("model response cannot impersonate user authorship")
        if envelope.memory_authority != "SOURCE_CANDIDATE_ONLY":
            raise GatewayStoreDenied("proposals cannot be promoted to governing memory")
        if envelope.digest != _envelope_digest(envelope):
            raise GatewayStoreDenied("checkpoint digest missing or invalid")
        # A first-session admission has no historical source reference. A
        # cursor-only recovery can also have no source_ref, but must have passed
        # the gateway's source-matched application callback. Do not make the
        # durable store silently reject these valid gateway admissions.
        if not envelope.chat_session_id:
            raise GatewayStoreDenied("chat session identity required")
        data = _snapshot(envelope)
        data["digest"] = envelope.digest
        encoded = _canonical(data)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT state,mission_id FROM apex_session_gateway_continuations "
                "WHERE operation_key=?",
                (envelope.operation_key,),
            ).fetchone()
            if current is None or current["mission_id"] != self.mission_id:
                raise GatewayStoreDenied("no matching durable reservation for checkpoint")
            if current["state"] != "RESERVED":
                raise GatewayStoreDenied("checkpoint already stored; replay denied")
            result = db.execute(
                "UPDATE apex_session_gateway_continuations "
                "SET state='CHECKPOINTED',envelope_json=?,envelope_digest=? "
                "WHERE operation_key=? AND mission_id=? AND state='RESERVED'",
                (encoded, envelope.digest, envelope.operation_key, self.mission_id),
            )
            if result.rowcount != 1:
                raise GatewayStoreDenied("checkpoint state changed during persistence")
        return envelope.operation_key

    def readback(self, operation_key: str) -> ContinuationEnvelope:
        """Reopen and authenticate stored checksum + typed source/role metadata."""
        self._validate_operation_key(operation_key)
        with self._connect() as db:
            row = db.execute(
                "SELECT state,mission_id,envelope_json,envelope_digest "
                "FROM apex_session_gateway_continuations WHERE operation_key=?",
                (operation_key,),
            ).fetchone()
        if row is None or row["mission_id"] != self.mission_id:
            raise GatewayStoreDenied("checkpoint not found for selected mission")
        if row["state"] != "CHECKPOINTED" or not row["envelope_json"]:
            raise GatewayStoreDenied("checkpoint not committed; reservation remains uncertain")
        try:
            payload = json.loads(row["envelope_json"])
            attributions = tuple(SourceAssertion(**s) for s in payload["attributions"])
            proposals = tuple(
                MemoryProposal(kind=p["kind"], source=SourceAssertion(**p["source"]))
                for p in payload["memory_proposals"]
            )
            envelope = ContinuationEnvelope(
                operation_key=payload["operation_key"],
                chat_session_id=payload["chat_session_id"],
                mission_id=payload["mission_id"],
                source_ref=payload["source_ref"],
                cursor=payload["cursor"],
                corrections=tuple(payload["corrections"]),
                response_text=payload["response_text"],
                attributions=attributions,
                memory_proposals=proposals,
                digest=payload["digest"],
                response_author=payload["response_author"],
                memory_authority=payload["memory_authority"],
                # Old checkpoint JSON lacks these fields. Preserve its original
                # digest while round-tripping new source-bound fingerprints.
                recovered_facts_sha256=payload.get("recovered_facts_sha256", ""),
                application_ref_sha256=payload.get("application_ref_sha256", ""),
            )
            if (_snapshot(envelope) != {k: v for k, v in payload.items() if k != "digest"}
                    or envelope.response_author != "assistant"
                    or envelope.memory_authority != "SOURCE_CANDIDATE_ONLY"
                    or envelope.digest != row["envelope_digest"]
                    or envelope.digest != _envelope_digest(envelope)
                    or envelope.operation_key != operation_key
                    or envelope.mission_id != self.mission_id):
                raise GatewayStoreDenied("checkpoint readback digest or authority mismatch")
            return envelope
        except GatewayStoreDenied:
            raise
        except (KeyError, TypeError, ValueError, AttributeError, json.JSONDecodeError) as exc:
            raise GatewayStoreDenied("checkpoint readback invalid or corrupted") from exc
