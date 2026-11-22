"""Read-only inspection of durable APEX execution receipts.

Process identity is diagnostic only. No inspection result authorizes replay.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import stat
import subprocess
import sys


def _unique_receipt_pairs(pairs: list[tuple[str, object]]) -> dict:
    """Reject ambiguous JSON members rather than trusting last-key-wins parsing."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate receipt member: {key}")
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def inspect(path: Path) -> dict:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 1024 * 1024:
                raise ValueError("receipt must be a regular file <= 1 MiB")
            # fstat is only a snapshot: a concurrent writer may extend the file.
            # Bound the actual read as well, before invoking the JSON parser.
            payload = handle.read(1024 * 1024 + 1)
            if len(payload) > 1024 * 1024:
                raise ValueError("receipt exceeds 1 MiB during inspection")
            # A concurrent in-place writer can change the bytes after fstat.
            # Never interpret a torn or modified receipt as stable evidence.
            after = os.fstat(handle.fileno())
            identity = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
            if identity(after) != identity(info) or len(payload) != after.st_size:
                raise ValueError("receipt changed during inspection")
            record = json.loads(payload, object_pairs_hook=_unique_receipt_pairs,
                                parse_constant=_reject_nonfinite_constant)
        if not isinstance(record, dict):
            raise ValueError("receipt must be an object")
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        return {"status": "inspection_failed", "reason": str(exc), "retry_authorized": False}

    # Receipt fields are untrusted: reject non-string status before membership
    # tests, which otherwise raise TypeError for arrays and objects.
    if not isinstance(record.get("status"), str):
        return {"status": "inspection_failed", "reason": "receipt status must be a string",
                "retry_authorized": False, "outcome_verified": False}

    result = {
        "status": "inspected_unverified",
        "receipt_status": record.get("status"),
        "invocation_id": record.get("invocation_id"),
        "retry_authorized": False,
        "outcome_verified": False,
        "process_identity": "unavailable",
    }
    if record.get("status") not in {"launched_unverified", "pending_unverified"}:
        result["process_identity"] = "not_applicable"
        # Inspection is the read-only consumer of durable execution receipts.
        # Unknown or incomplete cleanup must never be promoted to verified.
        required = ("cleanup_unresolved", "output_drains_unresolved", "direct_child_reaped")
        if not all(type(record.get(key)) is bool for key in required):
            result["cleanup_status"] = "unknown"
        elif (record["cleanup_unresolved"] or record["output_drains_unresolved"]
              or not record["direct_child_reaped"]):
            result["cleanup_status"] = "unresolved"
        else:
            result["cleanup_status"] = "resolved_direct_child_only"
        # A descendant found after direct-child exit is a failed execution
        # even when subsequent cleanup succeeds. Preserve that distinction.
        if record.get("descendant_detected_after_exit") is True:
            result["descendant_detected_after_exit"] = True
            if result["cleanup_status"] == "resolved_direct_child_only":
                result["cleanup_status"] = "descendant_detected_cleanup_completed"
        # Durable receipts are diagnostic, not attested outcome proofs. The
        # executor emits outcome_verified=False even on zero subprocess exit;
        # a modified receipt must not manufacture an authorization to succeed.
        result["outcome_verified"] = False
        result["outcome_evidence"] = "unattested_receipt"
        return result
    pid = record.get("pid")
    launched = record.get("launched_at_utc")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0 or not isinstance(launched, str):
        result["process_identity"] = "insufficient_evidence"
        return result
    try:
        start = dt.datetime.fromisoformat(launched)
        if start.tzinfo is None:
            raise ValueError("missing timezone")
        # macOS/BSD ps reports process birth time at second precision.
        # Compare birth time, not just PID, to reject recycled identities.
        observed = subprocess.run(
            ["ps", "-p", str(pid), "-o", "lstart="],
            capture_output=True, text=True, timeout=3, check=False,
        )
        if observed.returncode != 0 or not observed.stdout.strip():
            result["process_identity"] = "not_observed"
            return result
        birth = dt.datetime.strptime(observed.stdout.strip(), "%a %b %d %H:%M:%S %Y")
        birth = birth.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
        delta = (birth.astimezone(dt.timezone.utc) - start.astimezone(dt.timezone.utc)).total_seconds()
        # A child cannot predate its recorded launch by more than a short
        # scheduling interval. Birth-time resolution is one second.
        result["process_identity"] = "birth_time_consistent" if -5 <= delta <= 1 else "birth_time_mismatch"
    except (OSError, ValueError, subprocess.TimeoutExpired):
        result["process_identity"] = "inspection_unavailable"
    return result


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: --inspect-receipt PATH", file=sys.stderr)
        return 2
    result = inspect(Path(argv[0]))
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] != "inspection_failed" else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
