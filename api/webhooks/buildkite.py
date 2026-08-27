"""
APEX BUILDKITE WEBHOOK RECEIVER
Standard: Asynchronous CI/CD build callback processor.
Signals Temporal workflow on build completion (pass -> promote, fail -> repair loop).
"""

from __future__ import annotations

import hmac
import json
import os
import time
from typing import Any, Dict, Optional


def verify_buildkite_token(received_token: str, expected_token: Optional[str] = None) -> bool:
    sec = expected_token or os.getenv("BUILDKITE_WEBHOOK_TOKEN", "mock_buildkite_webhook_token")
    return hmac.compare_digest(sec, received_token)


def process_buildkite_event(event_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parses build.finished webhook payloads.
    Returns correlation routing info for Temporal workflow resumption.
    """
    event = event_payload.get("event", "build.finished")
    build_data = event_payload.get("build", {})
    pipeline_data = event_payload.get("pipeline", {})

    pipeline_slug = pipeline_data.get("slug", "")
    build_number = build_data.get("number", 0)
    commit_sha = build_data.get("commit", "")
    branch = build_data.get("branch", "main")
    state = build_data.get("state", "passed")  # "passed", "failed", "canceled"

    # Extract correlation metadata if passed via build environment
    meta = build_data.get("meta_data", {})
    mission_id = meta.get("mission_id", "")
    correlation_id = meta.get("correlation_id", "")

    return {
        "event": event,
        "pipeline": pipeline_slug,
        "build_number": build_number,
        "commit_sha": commit_sha,
        "branch": branch,
        "state": state,
        "passed": state == "passed",
        "mission_id": mission_id,
        "correlation_id": correlation_id,
        "processed_at_utc": time.time(),
    }
