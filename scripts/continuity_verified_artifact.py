"""Replay-safe owner-local handoff consumer for verified startup evidence."""
import hashlib
import json
import os
from pathlib import Path
import stat

def apply_verified_handoff(receipt, *, output_dir):
    if (receipt.get("status") != "STARTUP_DECISION_VERIFIED"
        or receipt.get("registered_action") != "VERIFY_REQUIRED_RETRIEVED_SOURCES"
        or receipt.get("action_result") != "REQUIRED_RETRIEVED_SOURCES_VERIFIED"
        or not isinstance(receipt.get("action_source_ids"), list)
        or not receipt["action_source_ids"]):
        raise ValueError("verified source-bound startup receipt required")
    directory = Path(output_dir)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("owner-private handoff directory required")
    digest = receipt["startup_receipt_digest"]
    if not isinstance(digest, str) or len(digest) != 71 or not digest.startswith("sha256:") or any(c not in "0123456789abcdef" for c in digest[7:]):
        raise ValueError("invalid receipt digest")
    target = directory / (digest[7:] + ".json")
    payload = {key: receipt[key] for key in ("key", "startup_receipt_digest", "retrieval_digest", "action_source_ids", "recovered_cursor", "checkpoint_digest", "journal_source_ref")}
    payload["schema"] = "glaciereq.verified-continuity-handoff/1"
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError:
        if target.is_symlink() or target.stat().st_uid != os.getuid() or target.stat().st_mode & 0o077 or target.read_bytes() != encoded:
            raise ValueError("handoff replay conflict or incomplete write")
        status = "HANDOFF_REPLAY_VERIFIED"
    else:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        status = "HANDOFF_CREATED"
    return {"status": status, "path": str(target), "digest": "sha256:" + hashlib.sha256(encoded).hexdigest()}
