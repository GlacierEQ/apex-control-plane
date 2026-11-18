"""Source-native cross-cloud file pointers for the existing GLACIEREQ graph.

Input is metadata already returned by an authorized Drive, Dropbox or OneDrive
connector. This module never downloads, copies, summarizes or transcribes source
files. Native file IDs and account scopes are the deduplication authority.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from urllib.parse import urlsplit
from uuid import UUID

GRAPH = "GLACIEREQ-MEMGRAPH-V1"
SOURCE = "glaciereq_cloud_file_catalog_v1"
PARENTS = {
    "google_drive": "DRIVE-CATALOG",
    "dropbox": "CLOUD-DROPBOX",
    "onedrive": "CLOUD-ONEDRIVE",
}
CLASSIFICATIONS = {"internal_metadata_no_case_payload", "restricted_pointer_only"}
RAW_FIELDS = {"content", "contents", "body", "transcript", "text", "base64",
              "b64_string", "raw", "bytes", "data", "extracted_text"}


def _stamp(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid timestamp")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if dt.tzinfo is None:
        raise ValueError("timestamp lacks timezone")
    return value


def _identity(value, what):
    if (not isinstance(value, str) or not value.strip() or len(value) > 512
            or any(ord(c) < 32 for c in value)):
        raise ValueError("invalid " + what)
    return value


def _url(value, provider):
    if value is None and provider == "dropbox":
        return None
    if not isinstance(value, str):
        raise ValueError("invalid provider URL")
    u = urlsplit(value)
    host = (u.hostname or "").lower()
    allowed = {
        "google_drive": host in ("drive.google.com", "docs.google.com"),
        "onedrive": host in ("onedrive.live.com",) or host.endswith(".sharepoint.com"),
        "dropbox": host in ("dropbox.com", "www.dropbox.com"),
    }
    if (u.scheme != "https" or not allowed[provider] or u.username or u.password
            or u.port not in (None, 443) or u.fragment):
        raise ValueError("invalid provider URL")
    return value


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _uuid(label):
    return str(UUID(bytes=hashlib.sha256(label.encode("utf-8")).digest()[:16]))


def _parent(provider):
    return PARENTS[provider]


def prepare_catalog(entries, *, observed_at):
    """Generate deterministic apex_memories rows without asserting file contents.

    Repeated identical connector metadata collapses. Two different revisions
    of one native file in the same batch are rejected, not silently overwritten.
    """
    _stamp(observed_at)
    if not isinstance(entries, list) or len(entries) > 1000:
        raise ValueError("invalid bounded catalog batch")
    dedup = {}
    for source in entries:
        if not isinstance(source, dict) or RAW_FIELDS.intersection(source):
            raise ValueError("raw content in catalog entry")
        provider = source.get("provider")
        if provider not in PARENTS:
            raise ValueError("unknown cloud provider")
        account = _identity(source.get("account_id"), "provider account")
        native = _identity(source.get("item_id"), "native file ID")
        name = _identity(source.get("name"), "file name")
        if len(name) > 256:
            raise ValueError("file name too long")
        classification = source.get("classification", "restricted_pointer_only")
        if classification not in CLASSIFICATIONS:
            raise ValueError("invalid classification")
        related = source.get("related_projects", [])
        if (not isinstance(related, list) or len(related) > 24
                or any(not isinstance(p, str) or not re.fullmatch(r"[A-Z][A-Z0-9-]{0,63}", p) for p in related)):
            raise ValueError("invalid related projects")
        if len(set(related)) != len(related):
            raise ValueError("duplicate related projects")
        modified = source.get("modified_at")
        if modified is not None:
            _stamp(modified)
        uri = _url(source.get("url"), provider)
        path = source.get("namespace_path")
        if provider == "dropbox":
            if not isinstance(path, str) or not re.fullmatch(r"ns:[0-9]+//.+", path) or any(c in path for c in ("\r", "\n")):
                raise ValueError("invalid Dropbox namespace path")
        elif path is not None:
            raise ValueError("unexpected namespace path")
        size = source.get("size")
        if size is not None and (type(size) is not int or size < 0):
            raise ValueError("invalid file size")
        mime = source.get("mime_type")
        if mime is not None:
            _identity(mime, "MIME type")
        snap = {
            "provider": provider, "account_id": account, "item_id": native,
            "name": name, "url": uri, "modified_at": modified,
            "mime_type": mime, "size": size, "classification": classification,
            "related_projects": related, "namespace_path": path,
        }
        encoded = json.dumps(snap, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        h = _digest(f"{provider}|{account}|{native}")
        key = "CLOUD-" + h[:24].upper()
        row = {
            "id": _uuid("glaciereq-cloud.v1|" + provider + "|" + account + "|" + native),
            "user_id": "casey_barton",
            "case_id": None,
            "source": SOURCE,
            "source_id": "GLACIEREQ-CLOUD-V1-" + h,
            "source_uri": uri,
            "source_hash": None,
            "source_type": "cloud_file_provider_metadata",
            "verification_method": "provider_native_file_metadata",
            "observed_at": observed_at,
            "court_facing": False,
            "authority_status": "unresolved",
            "memory_type": "structured_memory_graph_node",
            "content": "Provider-native cloud file pointer only; original content not copied or verified.",
            "metadata": {
                "schema": "glaciereq.cloud_file.v1",
                "graph_id": GRAPH,
                "node_key": key,
                "node_kind": "cloud_file",
                "parent_key": _parent(provider),
                "provider": provider,
                "provider_account": account,
                "provider_item_id": native,
                "provider_url": uri,
                "provider_path": path,
                "name": name,
                "mime_type": mime,
                "size": size,
                "source_modified_at": modified,
                "classification": classification,
                "related_projects": related,
                "metadata_snapshot_sha256": _digest(encoded),
                "original_file_hash_verified": False,
                "source_content_ingested": False,
            },
        }
        existing = dedup.get(row["id"])
        if existing is not None and existing != row:
            raise ValueError("conflicting revisions for native file ID")
        dedup[row["id"]] = row
    return sorted(dedup.values(), key=lambda x: x["source_id"])


def provider_parent_rows(*, observed_at):
    _stamp(observed_at)
    rows = []
    for provider in ("dropbox", "onedrive"):
        key = _parent(provider)
        rows.append({
            "id": _uuid("glaciereq-cloud-parent.v1|" + provider),
            "user_id": "casey_barton", "case_id": None,
            "source": SOURCE, "source_id": "GLACIEREQ-MEMGRAPH-V1-" + key,
            "source_uri": None, "source_hash": None,
            "source_type": "cloud_provider_catalog",
            "verification_method": "provider_native_folder_listing",
            "observed_at": observed_at, "court_facing": False,
            "authority_status": "unresolved",
            "memory_type": "structured_memory_graph_node",
            "content": "Provider-owned cloud catalog; file contents stay in source.",
            "metadata": {
                "schema": "glaciereq.cloud_file.v1", "graph_id": GRAPH,
                "node_key": key, "node_kind": "project", "parent_key": "ROOT",
                "provider": provider, "classification": "internal_metadata_no_case_payload",
            },
        })
    return rows


def select_project_sources(rows, project, *, include_restricted=False, limit=8):
    """Read-only source navigation; cannot promote cloud metadata to actions."""
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("invalid source limit")
    found = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        meta = row.get("metadata")
        if not isinstance(meta, dict):
            continue
        if (meta.get("schema") != "glaciereq.cloud_file.v1"
                or meta.get("graph_id") != GRAPH or meta.get("node_kind") != "cloud_file"
                or row.get("memory_type") != "structured_memory_graph_node"):
            continue
        related = meta.get("related_projects")
        if not isinstance(related, list) or project not in related:
            continue
        classification = meta.get("classification")
        if classification == "restricted_pointer_only" and not include_restricted:
            continue
        if classification != "internal_metadata_no_case_payload" and not include_restricted:
            continue
        sid = row.get("source_id")
        if not isinstance(sid, str) or not sid.startswith("GLACIEREQ-CLOUD-V1-"):
            raise ValueError("invalid indexed cloud source")
        if sid in found:
            raise ValueError("duplicate cloud source identity")
        found[sid] = {
            "source_id": sid,
            "provider": meta["provider"],
            "source_uri": row.get("source_uri") or meta.get("provider_url"),
            "provider_item_id": meta["provider_item_id"],
            "provider_account": meta["provider_account"],
            "classification": classification,
            "source_modified_at": meta.get("source_modified_at"),
            "authority": row.get("authority_status", "unresolved"),
        }
    return [found[k] for k in sorted(found)[:limit]]
