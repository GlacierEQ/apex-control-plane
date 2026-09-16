"""Durable startup uplift records for recoverable APEX observations.

Startup evidence remains strict about truth. Missing or incomplete evidence is
recorded as repair work while all unaffected executable frontiers continue.
This module never manufactures global permission authority: genuine provider,
credential, destructive-action, hardware, or legal constraints remain scoped to
the concrete route that actually carries them.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA = "glaciereq.apex.startup-continuation.v2"


def _safe_gate(value: str) -> str:
    normalized = "".join(
        ch if ch.isalnum() or ch in {"_", "-"} else "_"
        for ch in value.strip().lower()
    )
    return normalized.strip("_") or "startup"


def _json_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(value),
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _continuation_root() -> Path:
    configured = os.getenv("GLACIEREQ_STARTUP_CONTINUATION_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".apex-control-plane" / "continuations"


def _route_authority(request: Mapping[str, Any] | None) -> str:
    if request is None:
        return "route_local_only"
    value = request.get("external_action_authorized", "route_local_only")
    if value is True:
        return "active_mission_authority"
    if value is False:
        return "route_local_only"
    normalized = str(value).strip()
    return normalized or "route_local_only"


def record_startup_continuation(
    gate: str,
    errors: Sequence[str],
    *,
    request: Mapping[str, Any] | None = None,
    environment_key: str | None = None,
) -> Mapping[str, Any]:
    """Record startup repair state without changing unrelated execution authority."""
    normalized_errors = tuple(
        str(error) for error in errors if str(error).strip()
    ) or ("startup observation incomplete",)
    gate_id = _safe_gate(gate)
    authority = _route_authority(request)
    body: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "uplift_required",
        "gate": gate_id,
        "errors": list(normalized_errors),
        "next_actions": [
            "inspect_startup_observation",
            "assemble_or_repair_evidence",
            "revalidate_startup_observation",
            "resume_known_executable_frontiers",
            "repair_only_the_affected_route",
        ],
        "mission_execution": "continue_known_executable_frontiers",
        "local_recovery_authorized": True,
        "external_action_authorized": authority,
        "authority_semantics": (
            "startup findings do not create or revoke global execution authority; "
            "each consequential route resolves its own provider/operator constraint"
        ),
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
        temporary.write_text(
            json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
        body["record_path"] = str(target)
        persistence = "durable_local_record"
    except OSError as exc:
        body["persistence_error"] = exc.__class__.__name__
    body["persistence"] = persistence

    os.environ["GLACIEREQ_STARTUP_CONTINUATION_STATUS"] = "uplift_required"
    # Deliberately do NOT set GLACIEREQ_EXTERNAL_ACTION_AUTHORIZED here. Startup
    # observation state is not an authority source and must not silently revoke
    # mission or provider-scoped authority already established elsewhere.
    if environment_key:
        os.environ[environment_key] = "uplift_required"
    return body


def emit_startup_continuation(record: Mapping[str, Any]) -> None:
    """Emit structured uplift data without converting it into a permission gate."""
    print(
        json.dumps(dict(record), ensure_ascii=False, sort_keys=True),
        file=sys.stderr,
    )
    sys.stderr.flush()
