"""Replay-safe owner-local handoff consumer for verified startup evidence."""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

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
    # Publish only fully fsynced bytes. A crash during staging cannot leave a
    # partial final artifact; hard-link publication never overwrites a winner.
    fd, staging = tempfile.mkstemp(prefix=".handoff-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(staging, target, follow_symlinks=False)
        except FileExistsError:
            if (target.is_symlink() or target.stat().st_uid != os.getuid()
                    or target.stat().st_mode & 0o077
                    or target.read_bytes() != encoded):
                raise ValueError("handoff replay conflict or incomplete write")
            status = "HANDOFF_REPLAY_VERIFIED"
        else:
            status = "HANDOFF_CREATED"
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        os.unlink(staging)
    return {"status": status, "path": str(target), "digest": "sha256:" + hashlib.sha256(encoded).hexdigest()}


def consume_verified_handoff(receipt, *, output_dir, handler):
    """Read back the durable handoff before an explicit owner-local consumer runs.

    The original authenticated startup receipt is the authority; a file alone
    cannot authorize a downstream action. No recovered text selects code.
    """
    if not callable(handler):
        raise ValueError("explicit owner consumer required")
    published = apply_verified_handoff(receipt, output_dir=output_dir)
    target = Path(published["path"])
    info = target.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink < 1 or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("untrusted handoff artifact")
    raw = target.read_bytes()
    if "sha256:" + hashlib.sha256(raw).hexdigest() != published["digest"]:
        raise ValueError("handoff readback digest mismatch")
    def unique(pairs):
        obj = {}
        for k, v in pairs:
            if k in obj:
                raise ValueError("duplicate handoff field")
            obj[k] = v
        return obj
    payload = json.loads(raw, object_pairs_hook=unique,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite handoff value")))
    expected = {k: receipt[k] for k in ("key", "startup_receipt_digest", "retrieval_digest", "action_source_ids", "recovered_cursor", "checkpoint_digest", "journal_source_ref")}
    expected["schema"] = "glaciereq.verified-continuity-handoff/1"
    if payload != expected:
        raise ValueError("handoff provenance mismatch")
    return handler(payload)
