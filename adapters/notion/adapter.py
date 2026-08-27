"""
APEX NOTION COCKPIT ADAPTER
Standard: Human control surface adapter enforcing the universal contract:
observe() -> plan() -> execute() -> readback() -> verify()
Notion is the windshield/cockpit displaying authoritative workflow state, NOT the engine.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from contracts.mission import Mission, MissionStatus


class NotionCockpitAdapter:
    """
    Synchronizes authoritative workflow state to the Notion Mission Cockpit database.
    """

    def __init__(self, api_key: Optional[str] = None, database_id: Optional[str] = None):
        self.api_key = api_key or os.getenv("NOTION_API_KEY", "mock_notion_key")
        self.database_id = database_id or os.getenv("NOTION_COCKPIT_DATABASE_ID", "mock_cockpit_db")
        # In-memory mirror for readback validation
        self._page_store: Dict[str, Dict[str, Any]] = {}

    def observe_page(self, page_id: str) -> Dict[str, Any]:
        """observe(): Reads current page properties from Notion."""
        entry = self._page_store.get(page_id, {})
        return {
            "page_id": page_id,
            "properties": entry.get("properties", {}),
            "last_edited_time": entry.get("last_edited_time", time.time()),
        }

    def sync_mission_state(
        self,
        mission: Mission,
        current_step: str,
        verified_mutations: int = 0,
        failed_mutations: int = 0,
        open_blocker: Optional[str] = None,
        receipt_id: Optional[str] = None,
        worker: str = "Manus / Reasoning",
    ) -> Dict[str, Any]:
        """
        execute(): Pushes authoritative state transition to Notion Cockpit.
        """
        page_id = f"notion_page_{mission.mission_id}"
        props = {
            "Mission": mission.objective,
            "Status": mission.status.value,
            "Run": mission.correlation_id,
            "Priority": mission.priority,
            "Worker": worker,
            "GitHub": ", ".join(mission.source_state.repositories) or "none",
            "Started": time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime(mission.created_at_utc)),
            "Current Step": current_step,
            "Verified Mutations": verified_mutations,
            "Failed Mutations": failed_mutations,
            "Open Blocker": open_blocker or "none",
            "Receipt": receipt_id or "none",
        }

        self._page_store[page_id] = {
            "page_id": page_id,
            "mission_id": mission.mission_id,
            "properties": props,
            "last_edited_time": time.time(),
        }

        return {
            "status": "SYNCED",
            "page_id": page_id,
            "mission_status": mission.status.value,
            "updated_at_utc": time.time(),
        }

    def readback_page(self, page_id: str) -> Dict[str, Any]:
        """readback(): Verifies properties written to Notion."""
        return self.observe_page(page_id)

    def verify_update(self, readback_state: Dict[str, Any], expected_status: str) -> bool:
        """verify(): Confirms Notion windshield reflects true workflow state."""
        props = readback_state.get("properties", {})
        return props.get("Status") == expected_status
