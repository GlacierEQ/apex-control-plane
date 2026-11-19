"""Executable, owner-controlled Spiral/APEX -> cloud-index continuity host.

This intentionally invokes a deterministic registered LOCAL consumer, not a
ChatGPT-native boot hook or a general LLM. The verified extracted text is an
indexable derivative, never proof of the original cloud binary's SHA-256.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
from typing import Any, Mapping, Sequence

from .apex_session_gateway import ContextApplication, GatewayDenied, GatewayModelOutput
from .apex_session_gateway_store import GatewayCheckpointStore
from .cloud_continuity_corpus import recover_cloud_context
from .mission_startup import run_authenticated_mission


def _private_database(path: Path, *, create: bool) -> Path:
    path = Path(path).expanduser()
    parent = os.lstat(path.parent)
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid()
            or parent.st_mode & 0o077):
        raise GatewayDenied("cloud index parent must be owner-private")
    try:
        current = os.lstat(path)
    except FileNotFoundError:
        if not create:
            raise GatewayDenied("cloud index not found")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        current = os.lstat(path)
    if (not stat.S_ISREG(current.st_mode) or current.st_uid != os.getuid()
            or current.st_mode & 0o077):
        raise GatewayDenied("cloud index must be owner-private; symlink denied")
    return path


def _open_index(path: Path, *, create: bool):
    path = _private_database(path, create=create)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout = 30000")
    db.execute("PRAGMA synchronous = FULL")
    return db


def index_cloud_documents(path: Path, context: dict[str, Any]) -> int:
    """Durably index previously SHA-verified extracted text, by source revision."""
    docs = context["sources"]
    namespace = context["namespace"]
    if not docs or not namespace:
        raise GatewayDenied("verified cloud sources and namespace required")
    with _open_index(path, create=True) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("""
            CREATE TABLE IF NOT EXISTS documents (
              namespace TEXT NOT NULL, source_id TEXT NOT NULL,
              revision TEXT NOT NULL, text_sha256 TEXT NOT NULL,
              title TEXT NOT NULL, url TEXT NOT NULL, extracted_text TEXT NOT NULL,
              UNIQUE(namespace, source_id, revision)
            )
        """)
        db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
              extracted_text, namespace UNINDEXED, source_id UNINDEXED,
              revision UNINDEXED)
        """)
        for record in docs:
            body = record.get("text")
            digest = record.get("text_sha256")
            if (record["namespace"] != namespace or not isinstance(body, str)
                    or record.get("text_truncated") is not False
                    or hashlib.sha256(body.encode("utf-8")).hexdigest() != digest):
                raise GatewayDenied("cloud text not completely verified")
            key = (namespace, record["source_id"], record["revision"])
            old = db.execute(
                "SELECT rowid,text_sha256 FROM documents "
                "WHERE namespace=? AND source_id=? AND revision=?", key
            ).fetchone()
            if old is not None:
                if old["text_sha256"] != digest:
                    raise GatewayDenied("index provider revision collision")
                continue
            added = db.execute(
                "INSERT INTO documents "
                "(namespace,source_id,revision,text_sha256,title,url,extracted_text) "
                "VALUES (?,?,?,?,?,?,?)",
                (*key, digest, record["title"], record["url"], body),
            )
            db.execute(
                "INSERT INTO documents_fts "
                "(rowid,extracted_text,namespace,source_id,revision) VALUES (?,?,?,?,?)",
                (added.lastrowid, body, *key),
            )
    # Independent connection ensures durable readback, not uncommitted memory.
    with _open_index(path, create=False) as db:
        for record in docs:
            row = db.execute(
                "SELECT text_sha256,extracted_text FROM documents "
                "WHERE namespace=? AND source_id=? AND revision=?",
                (namespace, record["source_id"], record["revision"]),
            ).fetchone()
            if (row is None or row["text_sha256"] != record["text_sha256"]
                    or hashlib.sha256(row["extracted_text"].encode()).hexdigest()
                    != row["text_sha256"]):
                raise GatewayDenied("index readback differs from authenticated text")
    return len(docs)


def search_cloud_index(
    path: Path, *, namespace: str, query: str, limit: int = 10,
) -> list[dict[str, Any]]:
    """Scoped full-text search; verify stored text on every returned hit."""
    if (not isinstance(namespace, str) or not namespace.strip()
            or not isinstance(query, str) or not query.strip()
            or not isinstance(limit, int) or not 1 <= limit <= 100):
        raise GatewayDenied("explicit cloud search scope/query and bounded limit required")
    phrase = '"' + query.replace('"', '""') + '"'
    with _open_index(Path(path), create=False) as db:
        hits = db.execute(
            "SELECT d.source_id,d.revision,d.title,d.url,d.text_sha256,"
            "d.extracted_text FROM documents_fts "
            "JOIN documents d ON d.rowid=documents_fts.rowid "
            "WHERE documents_fts MATCH ? AND d.namespace=? "
            "ORDER BY d.source_id,d.revision LIMIT ?",
            (phrase, namespace, limit),
        ).fetchall()
        result = []
        for row in hits:
            if hashlib.sha256(row["extracted_text"].encode()).hexdigest() != row["text_sha256"]:
                raise GatewayDenied("indexed text corrupted")
            result.append({
                "source_id": row["source_id"], "revision": row["revision"],
                "title": row["title"], "url": row["url"],
                "text_sha256": row["text_sha256"],
                "excerpt": row["extracted_text"][:240],
                "extracted_text_not_original_binary": True,
            })
        return result


def run_owned_cloud_mission(
    *, bridge: Path, store: Path, spiral_root: Path, mission_id: str,
    session_id: str, invocation_id: str, cloud_store: Path,
    cloud_index_db: Path, checkpoint_db: Path, namespace: str,
    source_ids: Sequence[str], expected_cursor: str,
    required_corrections: Sequence[str], required_fact_keys: Sequence[str] = (),
    required_fact_values: Mapping[str, Any] | None = None,
    required_fact_sources: Mapping[str, str] | None = None,
    runner=subprocess.run,
) -> dict[str, Any]:
    """Real controlled-host action: authenticated recovery -> index -> checkpoint.

    The existing Spiral anchor must already exist. An exact recovered cursor and
    corrections are preconditions, not executable commands. No external writes.
    """
    if (not isinstance(expected_cursor, str) or not expected_cursor.strip()
            or isinstance(source_ids, (str, bytes)) or not source_ids
            or not all(isinstance(s, str) and s for s in source_ids)
            or isinstance(required_corrections, (str, bytes))
            or not required_corrections
            or not all(isinstance(c, str) and c.strip() for c in required_corrections)):
        raise GatewayDenied("explicit cursor, source IDs and correction policy required")
    checkpoint = GatewayCheckpointStore(checkpoint_db, mission_id=mission_id)
    applied: dict[str, Any] = {}

    def apply_context(recovery):
        if recovery.cursor != expected_cursor:
            raise GatewayDenied("persisted cursor differs from approved action policy")
        if any(c not in recovery.corrections for c in required_corrections):
            raise GatewayDenied("required original correction absent")
        fact_map = {}
        for encoded in recovery.facts:
            entry = json.loads(encoded)
            if entry["key"] in fact_map:
                raise GatewayDenied("duplicate recovered fact")
            fact_map[entry["key"]] = entry["record"]
        for key, expected in (required_fact_values or {}).items():
            fact = fact_map.get(key)
            if (not isinstance(fact, dict) or "value" not in fact
                    or type(fact["value"]) is not type(expected)
                    or fact["value"] != expected):
                raise GatewayDenied("recovered fact value conflicts with owner policy")
        for key, expected in (required_fact_sources or {}).items():
            fact = fact_map.get(key)
            if (not isinstance(expected, str) or not expected.strip()
                    or not isinstance(fact, dict)
                    or fact.get("source") != expected):
                raise GatewayDenied("recovered fact source conflicts with owner policy")
        context = recover_cloud_context(
            cloud_store, namespace=namespace,
            required_source_ids=source_ids, max_chars=2_000_000,
        )
        if any(record.get("text_truncated") for record in context["sources"]):
            raise GatewayDenied("incomplete cloud evidence not actionable")
        applied["cloud"] = context
        return ContextApplication(
            recovery.mission_id, recovery.source_ref, recovery.cursor,
            recovery.corrections, recovery.facts,
            "cloud-index:" + context["evidence_digest"],
        )

    def invoke_index(receipt):
        context = applied.get("cloud")
        if context is None or not receipt.application_ref.startswith("cloud-index:"):
            raise GatewayDenied("source-verified cloud context not applied")
        count = index_cloud_documents(cloud_index_db, context)
        return GatewayModelOutput(
            text=json.dumps({
                "action": "index_cloud", "documents": count,
                "namespace": namespace, "evidence_digest": context["evidence_digest"],
                "source_ids": [r["source_id"] for r in context["sources"]],
            }, sort_keys=True),
            attributions=(), memory_proposals=(),
            corrections_applied=receipt.recovery.corrections,
        )

    output = run_authenticated_mission(
        bridge=bridge, store=store, spiral_root=spiral_root, mission_id=mission_id,
        session_id=session_id, invocation_id=invocation_id,
        apply_context=apply_context, invoke_model=invoke_index,
        resolve_source=lambda _: (_ for _ in ()).throw(
            GatewayDenied("original source assertion not available for cloud derivatives")),
        reserve=checkpoint.reserve, persist=checkpoint.persist,
        readback=checkpoint.readback, required_fact_keys=tuple(required_fact_keys),
        runner=runner,
    )
    key = ":".join((mission_id, "model", session_id, invocation_id))
    saved = GatewayCheckpointStore(checkpoint_db, mission_id=mission_id).readback(key)
    action = json.loads(output.text)
    return {
        "status": "CHECKPOINTED", "checkpoint_key": key,
        "checkpoint_digest": saved.digest,
        "journal_source_ref": saved.source_ref, "cursor": saved.cursor,
        "source_count": action["documents"], "evidence_digest": action["evidence_digest"],
        "source_ids": action["source_ids"], "action": "index_cloud",
        "native_chatgpt_startup_verified": False,
    }
