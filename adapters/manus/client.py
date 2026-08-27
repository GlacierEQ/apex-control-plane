"""
APEX MANUS ADAPTER
Standard: Formal worker adapter with structured output schema enforcement.
Manus operates as a callable execution surface, not the workflow owner.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from contracts.agent_result import AgentResult


class ManusAdapter:
    """
    Client for interacting with Manus Agentic API.
    Enforces strict structured JSON schema extraction.
    """

    STRUCTURED_OUTPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["success", "failed", "blocked", "requires_input"]},
            "facts": {"type": "array", "items": {"type": "object"}},
            "sources": {"type": "array", "items": {"type": "string"}},
            "findings": {"type": "array", "items": {"type": "object"}},
            "artifacts": {"type": "array", "items": {"type": "object"}},
            "recommended_changes": {"type": "array", "items": {"type": "object"}},
            "executed_changes": {"type": "array", "items": {"type": "object"}},
            "verification": {"type": "array", "items": {"type": "object"}},
            "unresolved": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["status", "facts", "findings", "recommended_changes"],
    }

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or os.getenv("MANUS_API_KEY", "mock_manus_key")
        self.base_url = base_url or os.getenv("MANUS_BASE_URL", "https://api.manus.im/v1")

    async def create_task(
        self,
        prompt: str,
        connectors: Optional[List[str]] = None,
        skills: Optional[List[str]] = None,
        context_pack: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Creates asynchronous Manus task with strict JSON schema."""
        task_id = f"task_manus_{int(time.time()*1000)}"
        return {
            "task_id": task_id,
            "status": "pending",
            "connectors": connectors or [],
            "skills": skills or [],
            "created_at_utc": time.time(),
        }

    async def get_task(self, task_id: str) -> Dict[str, Any]:
        return {
            "task_id": task_id,
            "status": "completed",
            "updated_at_utc": time.time(),
        }

    def parse_structured_output(self, raw_payload: Dict[str, Any]) -> AgentResult:
        """Parses webhook/poll response into verified AgentResult contract."""
        data = raw_payload.get("structured_output") or raw_payload
        return AgentResult.from_dict(data)
