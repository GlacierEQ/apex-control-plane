"""
APEX MANUS WEBHOOK RECEIVER
Standard: Signature-verified asynchronous task callback processor.
Resumes sleeping Temporal workflows on task completion or input requests.
"""

from __future__ import annotations

import hmac
import hashlib
import json
import os
import time
from typing import Any, Dict, Optional, Tuple


def verify_manus_signature(payload_bytes: bytes, signature_header: str, secret: Optional[str] = None) -> bool:
    sec = secret or os.getenv("MANUS_WEBHOOK_SECRET", "mock_webhook_secret")
    expected = hmac.new(sec.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def process_manus_event(event_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Processes task_created or task_stopped webhook events.
    Returns correlation routing info for Temporal workflow resumption.
    """
    event_type = event_payload.get("event_type", "task_stopped")
    task_id = event_payload.get("task_id", "")
    mission_id = event_payload.get("mission_id", "")

    structured_output = event_payload.get("structured_output", {})
    status = event_payload.get("status", "completed")

    return {
        "event_type": event_type,
        "task_id": task_id,
        "mission_id": mission_id,
        "status": status,
        "structured_output": structured_output,
        "processed_at_utc": time.time(),
    }
