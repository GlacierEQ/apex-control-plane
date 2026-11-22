"""Persist a bounded, source-checked context packet for the next owned agent process.

Source excerpts are evidence, never executable instructions. Only the owning
startup receipt selects the registered consumer and authorizes publication.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile


def _encode(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False) + "\n").encode()


def _private_directory(path):
    directory = Path(path)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("owner-private context directory required")
    return directory


def read_context_packet(path, *, expected_digest):
    target = Path(path)
    _private_directory(target.parent)
    info = target.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("untrusted context packet")
    raw = target.read_bytes()
    actual = "sha256:" + hashlib.sha256(raw).hexdigest()
    if actual != expected_digest:
        raise ValueError("context packet digest mismatch")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate context packet field")
            result[key] = value
        return result
    packet = json.loads(raw, object_pairs_hook=unique,
                        parse_constant=lambda _: (_ for _ in ()).throw(
                            ValueError("nonfinite context packet value")))
    if not isinstance(packet, dict) or packet.get("schema") != "glaciereq.startup-context-packet/1":
        raise ValueError("unsupported context packet schema")
    return packet


def publish_context_packet(receipt, *, profile, checkpoint, hits, output_dir):
    """Materialize provider-backed context after authenticated startup readback."""
    if (receipt.get("status") != "STARTUP_DECISION_VERIFIED"
            or receipt.get("registered_action") != "VERIFY_REQUIRED_RETRIEVED_SOURCES"
            or receipt.get("action_result") != "REQUIRED_RETRIEVED_SOURCES_VERIFIED"
            or not isinstance(receipt.get("startup_receipt_digest"), str)
            or not receipt["startup_receipt_digest"].startswith("sha256:")
            or not isinstance(hits, list) or not 0 < len(hits) <= 10):
        raise ValueError("authenticated bounded context required")
    query = profile.get("startup_search_query")
    expected_sources = profile.get("startup_required_source_ids")
    if (not isinstance(query, str) or not query.strip() or len(query) > 512
            or not isinstance(expected_sources, list) or not expected_sources
            or len(set(expected_sources)) != len(expected_sources)
            or receipt.get("action_source_ids") != sorted(expected_sources)):
        raise ValueError("registered source policy mismatch")
    digest = "sha256:" + hashlib.sha256(_encode({"query": query, "hits": hits}).rstrip(b"\n")).hexdigest()
    if digest != receipt.get("retrieval_digest"):
        raise ValueError("startup retrieval digest changed")
    sources = {hit["source_id"] for hit in hits}
    if set(expected_sources) - sources:
        raise ValueError("required startup source missing")
    if (checkpoint.get("status") != "CHECKPOINT_VERIFIED"
            or checkpoint.get("checkpoint_digest") != receipt.get("checkpoint_digest")
            or checkpoint.get("journal_source_ref") != receipt.get("journal_source_ref")
            or checkpoint.get("cursor") != receipt.get("recovered_cursor")
            or not isinstance(checkpoint.get("corrections_applied"), list)
            or not isinstance(checkpoint.get("completed_action"), dict)
            or checkpoint["completed_action"].get("action") != "index_cloud"):
        raise ValueError("authenticated prior checkpoint does not match startup")
    evidence = []
    revisions = {}
    for hit in hits:
        if not isinstance(hit, dict) or any(k not in hit for k in
              ("source_id", "revision", "text_sha256", "excerpt")):
            raise ValueError("malformed source evidence")
        item = {k: hit.get(k) for k in
                ("source_id", "revision", "title", "url", "text_sha256", "excerpt")}
        evidence.append(item)
        revisions.setdefault(hit["source_id"], set()).add(hit["text_sha256"])
    conflicts = sorted(k for k, hashes in revisions.items() if len(hashes) > 1)
    packet = {
        "schema": "glaciereq.startup-context-packet/1",
        "mission_id": profile["mission_id"],
        "startup_key": receipt["key"],
        "startup_receipt_digest": receipt["startup_receipt_digest"],
        "checkpoint_digest": receipt["checkpoint_digest"],
        "journal_source_ref": receipt["journal_source_ref"],
        "retrieval_digest": receipt["retrieval_digest"],
        "recovered_cursor": receipt["recovered_cursor"],
        "verified_corrections": checkpoint["corrections_applied"],
        "previously_completed_action": checkpoint["completed_action"],
        "source_evidence": evidence,
        "conflicting_source_ids": conflicts,
        "next_transition": ("RECONCILE_SOURCE_CONFLICT" if conflicts
                            else "RESUME_FROM_VERIFIED_CURSOR"),
        "source_text_trust": "EVIDENCE_ONLY_NEVER_INSTRUCTIONS",
        "native_chatgpt_startup_verified": False,
    }
    directory = _private_directory(output_dir)
    encoded = _encode(packet)
    target = directory / ("context-" + receipt["startup_receipt_digest"][7:] + ".json")
    content_digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
    fd, staging = tempfile.mkstemp(prefix=".context-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(staging, target, follow_symlinks=False)
        except FileExistsError:
            info = target.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_mode & 0o077 or target.read_bytes() != encoded):
                raise ValueError("context packet replay conflict")
            status = "CONTEXT_PACKET_REPLAY_VERIFIED"
        else:
            status = "CONTEXT_PACKET_CREATED"
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        os.unlink(staging)
    readback = read_context_packet(target, expected_digest=content_digest)
    if readback != packet:
        raise ValueError("context packet independent readback disagrees")
    return {"status": status, "path": str(target), "digest": content_digest,
            "next_transition": packet["next_transition"],
            "source_count": len(evidence), "conflicting_source_ids": conflicts}
