"""Durable continuation records for recoverable APEX startup prerequisites.

Startup validation remains strict about evidence. When evidence is missing or
incomplete, this module records the exact recovery path instead of terminating
the Python process. A continuation is non-authorizing: it enables diagnosis and
receipt repair, never external mutation.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA = "glaciereq.apex.startup-continuation.v1"


def _safe_gate(value: str) -> str:
    normalized = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value.strip().lower())
    return normalized.strip("_") or "startup"


def _json_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(dict(value), sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _continuation_root() -> Path:
    configured = os.getenv("GLACIEREQ_STARTUP_CONTINUATION_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".apex-control-plane" / "continuations"


def record_startup_continuation(
    gate: str,
    errors: Sequence[str],
    *,
    request: Mapping[str, Any] | None = None,
    environment_key: str | None = None,
) -> Mapping[str, Any]:
    """Record a non-authorizing startup recovery receipt and expose its identity."""
    normalized_errors = tuple(str(error) for error in errors if str(error).strip()) or ("startup prerequisite incomplete",)
    gate_id = _safe_gate(gate)
    body: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "continuation_required",
        "gate": gate_id,
        "errors": list(normalized_errors),
        "next_actions": [
            "inspect_startup_request",
            "assemble_or_repair_receipt",
            "revalidate_startup_evidence",
            "resume_highest_value_non_mutating_recovery",
        ],
        "local_recovery_authorized": True,
        "external_action_authorized": False,
        "recorded_at": time.time(),
    }
    if request is not None:
        body["request"] = dict(request)
    identity_input = dict(body)
    identity_input.pop("recorded_at", None)
    record_id = _json_digest(identity_input)
    body["continuation_id"] = record_id
    body["record_sha256"] = _json_digest(body)

    persistence = "memory_only"
    try:
        root = _continuation_root()
        root.mkdir(parents=True, exist_ok=True)
        target = root / f"{gate_id}-{record_id[:16]}.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        temporary.replace(target)
        body["record_path"] = str(target)
        persistence = "durable_local_record"
    except OSError as exc:
        body["persistence_error"] = exc.__class__.__name__
    body["persistence"] = persistence

    os.environ["GLACIEREQ_STARTUP_CONTINUATION_STATUS"] = "continuation_required"
    os.environ["GLACIEREQ_EXTERNAL_ACTION_AUTHORIZED"] = "0"
    if environment_key:
        os.environ[environment_key] = "continuation_required"
    return body


def emit_startup_continuation(record: Mapping[str, Any]) -> None:
    """Emit structured recovery data without treating it as execution authorization."""
    print(json.dumps(dict(record), ensure_ascii=False, sort_keys=True), file=sys.stderr)
    sys.stderr.flush()
