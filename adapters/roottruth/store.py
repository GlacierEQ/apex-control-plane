"""
APEX ROOTTRUTH STORE
Standard: Authoritative current projection of state across all estate entities.
Answers: 'What do we currently believe to be true?'
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional


class RootTruthStore:
    """
    Sovereign state projection store.
    Persists the verified truth of entities (Git HEADs, Notion status, evidence).
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self.path = storage_path or Path("/Users/kcbflux/APEX_SYSTEM/INFRASTRUCTURE/apex-control-plane/data/root_truth.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._state: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._state, indent=2, sort_keys=True), encoding="utf-8")

    def get(self, entity_key: str) -> Optional[Any]:
        entry = self._state.get(entity_key)
        return entry.get("value") if entry else None

    def get_entry(self, entity_key: str) -> Optional[Dict[str, Any]]:
        return self._state.get(entity_key)

    def set(self, entity_key: str, value: Any, provenance_receipt_id: str, version: Optional[str] = None) -> None:
        """Sets a projected truth value, strictly anchored to a verifying ECHO receipt."""
        self._state[entity_key] = {
            "value": value,
            "version": version or str(time.time()),
            "provenance_receipt_id": provenance_receipt_id,
            "updated_at_utc": time.time(),
        }
        self._save()

    def all_truths(self) -> Dict[str, Any]:
        return dict(self._state)
