"""Source-bound local cloud-file continuity corpus.

Cloud providers remain authoritative. Input is explicit connector observations,
not borrowed ChatGPT OAuth, not original evidence bytes, and never instructions
to execute untrusted cloud-file content.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping, Sequence

SCHEMA = "glaciereq.cloud-continuity/1"
PROVIDERS = frozenset({"drive", "dropbox", "box", "onedrive", "notion", "github"})
MAX_EXTRACTED_BYTES = 2_000_000


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(data: Any) -> bytes:
    return (json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _prepare_store(root: Path) -> None:
    if root.is_symlink():
        raise ValueError("symlink corpus root is not trusted")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    obj = root / "objects"
    if obj.is_symlink():
        raise ValueError("symlink objects directory is not trusted")
    obj.mkdir(mode=0o700, exist_ok=True)


def _atomic(path: Path, data: bytes) -> None:
    if path.is_symlink():
        raise ValueError("symlink target refused")
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".staging-")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _manifest(root: Path) -> dict[str, Any]:
    path = root / "manifest.json"
    if path.is_symlink():
        raise ValueError("symlink manifest refused")
    if not path.exists():
        return {"schema": SCHEMA, "revisions": []}
    data = json.loads(path.read_bytes())
    if data.get("schema") != SCHEMA or not isinstance(data.get("revisions"), list):
        raise ValueError("unrecognized cloud corpus manifest")
    return data


def _normalize(item: Mapping[str, Any]) -> tuple[dict[str, Any], bytes | None]:
    provider = item.get("provider")
    if provider not in PROVIDERS:
        raise ValueError("provider is not explicitly supported")
    for k in ("account", "native_id", "namespace", "title", "url"):
        if not isinstance(item.get(k), str) or not item[k].strip():
            raise ValueError(f"missing provider-native {k}")
    text = item.get("extracted_text")
    if text is not None and not isinstance(text, str):
        raise ValueError("extracted_text must be a string or null")
    raw = text.encode("utf-8") if text is not None else None
    if raw is not None and len(raw) > MAX_EXTRACTED_BYTES:
        raise ValueError("extracted text exceeds bounded ingestion limit")
    text_sha = _sha(raw) if raw is not None else None
    revision = item.get("revision")
    if not isinstance(revision, str) or not revision:
        if raw is None:
            raise ValueError("metadata-only observations need a provider revision")
        revision = "text-sha256:" + text_sha
    source_id = f"{provider}:{item['account']}:{item['native_id']}"
    return ({
        "source_id": source_id, "provider": provider, "account": item["account"],
        "native_id": item["native_id"], "revision": revision,
        "namespace": item["namespace"], "title": item["title"],
        "url": item["url"], "modified_at": item.get("modified_at"),
        "provider_hash": item.get("provider_hash"),
        "content_state": "EXTRACTED_TEXT" if raw is not None else "METADATA_ONLY",
        "text_sha256": text_sha, "extracted_text_bytes": len(raw) if raw is not None else None,
        "raw_bytes_acquired": False,
    }, raw)


def ingest_cloud_snapshot(root: Path, items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Merge provider observations without overwriting a prior provider revision."""
    root = Path(root)
    _prepare_store(root)
    state = _manifest(root)
    existing = {(r["source_id"], r["revision"]): r for r in state["revisions"]}
    fresh: list[tuple[dict[str, Any], bytes | None]] = []
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        record, raw = _normalize(item)
        key = (record["source_id"], record["revision"])
        if key in existing and existing[key] != record:
            raise ValueError("same provider revision changed: refuse revision collision")
        if key in seen and seen[key] != record:
            raise ValueError("conflicting observations in one provider snapshot")
        seen[key] = record
        if key not in existing and all(key != (x["source_id"], x["revision"]) for x, _ in fresh):
            fresh.append((record, raw))
    for record, raw in fresh:
        if raw is not None:
            target = root / "objects" / (record["text_sha256"] + ".txt")
            if target.is_symlink():
                raise ValueError("symlink cloud content object refused")
            if target.exists():
                if _sha(target.read_bytes()) != record["text_sha256"]:
                    raise ValueError("content-addressed object tampered")
            else:
                _atomic(target, raw)
        state["revisions"].append(record)
    if fresh:
        _atomic(root / "manifest.json", _json(state))
    return {"new_revisions": len(fresh), "total_revisions": len(state["revisions"])}


def recover_cloud_context(
    root: Path, *, namespace: str, required_source_ids: Sequence[str],
    require_text: bool = True, max_chars: int = 12000,
) -> dict[str, Any]:
    """Read explicitly required sources and verify extracted content on readback."""
    if not namespace or not required_source_ids or max_chars < 1:
        raise ValueError("explicit namespace, source selection and positive bound required")
    root = Path(root)
    state = _manifest(root)
    matched = []
    for source_id in dict.fromkeys(required_source_ids):
        entries = [e for e in state["revisions"] if e["source_id"] == source_id and e["namespace"] == namespace]
        if not entries:
            raise ValueError("required source missing from requested namespace")
        # Native provider modification time, not ingestion order, controls recency.
        record = max(enumerate(entries), key=lambda indexed: (indexed[1].get("modified_at") or "", indexed[0]))[1]
        if require_text and record["content_state"] != "EXTRACTED_TEXT":
            raise ValueError("required cloud source has metadata only")
        current = dict(record)
        if record["text_sha256"]:
            target = root / "objects" / (record["text_sha256"] + ".txt")
            if target.is_symlink() or not target.is_file():
                raise ValueError("cloud content object missing or symlinked")
            raw = target.read_bytes()
            if _sha(raw) != record["text_sha256"]:
                raise ValueError("extracted content failed SHA-256 readback")
            current["text"] = raw.decode("utf-8")[:max_chars]
            current["text_truncated"] = len(raw.decode("utf-8")) > max_chars
        matched.append(current)
    digest = _sha(_json([{k: x[k] for k in ("source_id", "revision", "text_sha256")} for x in matched]))
    return {"schema": SCHEMA, "namespace": namespace, "sources": matched, "evidence_digest": digest}


def dispatch_cloud_action(
    root: Path, *, namespace: str, action: str,
    handlers: Mapping[str, Callable[[Mapping[str, Any]], Any]],
    required_source_ids: Sequence[str],
) -> Any:
    """Run only an explicitly registered callback after source verification."""
    handler = handlers.get(action)
    if not callable(handler):
        raise ValueError("unregistered cloud context action")
    context = recover_cloud_context(root, namespace=namespace, required_source_ids=required_source_ids)
    return handler(context)
