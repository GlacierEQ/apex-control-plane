"""Owner-local durable cursor application with independent SQLite readback.

The authenticated handoff remains the authority. This provider persists only
the selected cursor and its provenance, never executes recovered text.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

from scripts.continuity_verified_artifact import (
    consume_once_verified_handoff, reconcile_once_verified_handoff,
)


def _connect(path):
    path = Path(path)
    parent = path.parent
    info = parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("private owner database directory required")
    if path.is_symlink():
        raise ValueError("database symlink forbidden")
    if path.exists():
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("untrusted database")
    db = sqlite3.connect(str(path), timeout=10)
    os.chmod(path, 0o600)
    db.execute("PRAGMA synchronous=FULL")
    db.execute("CREATE TABLE IF NOT EXISTS applied_cursor (identity TEXT PRIMARY KEY, cursor TEXT NOT NULL, provenance TEXT NOT NULL)")
    db.commit()
    return db


def apply_cursor_once(receipt, *, handoff_dir, database):
    """Apply a verified recovered cursor as a real durable owner-local effect."""
    def handler(payload, identity):
        provenance = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with _connect(database) as db:
            db.execute("INSERT OR IGNORE INTO applied_cursor VALUES (?, ?, ?)",
                       (identity, payload["recovered_cursor"], provenance))
            row = db.execute("SELECT cursor, provenance FROM applied_cursor WHERE identity=?", (identity,)).fetchone()
            if row != (payload["recovered_cursor"], provenance):
                raise ValueError("conflicting provider effect")
        return {"operation_identity": identity, "cursor": payload["recovered_cursor"]}
    return consume_once_verified_handoff(receipt, output_dir=handoff_dir,
                                          handler=handler, operation_name="apply_recovered_cursor")


def readback_cursor_once(receipt, *, handoff_dir, database):
    """Independently read durable provider effect; never replay the write."""
    def readback(identity, payload):
        provenance = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with _connect(database) as db:
            row = db.execute("SELECT cursor, provenance FROM applied_cursor WHERE identity=?", (identity,)).fetchone()
        if row is None:
            return None
        if row != (payload["recovered_cursor"], provenance):
            raise ValueError("provider effect conflicts with authenticated handoff")
        return {"operation_identity": identity, "effect_verified": True,
                "provider_reference": "sqlite:applied_cursor:" + identity}
    return reconcile_once_verified_handoff(receipt, output_dir=handoff_dir,
             operation_name="apply_recovered_cursor", provider_readback=readback)
