"""
APEX CONTROL PLANE CONTRACTS: CONTEXT PACK
Standard: Pre-execution hydration payload ensuring zero model amnesia.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ContextPack:
    context_pack_id: str
    mission_id: str
    correlation_id: str
    facts: List[Dict[str, Any]] = field(default_factory=list)
    verified_state: List[Dict[str, Any]] = field(default_factory=list)
    unverified_claims: List[Dict[str, Any]] = field(default_factory=list)
    existing_artifacts: List[Dict[str, Any]] = field(default_factory=list)
    source_versions: Dict[str, str] = field(default_factory=dict)  # e.g. {"github:repo": "sha", "file:path": "hash"}
    open_work: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    created_at_utc: float = field(default_factory=time.time)
    locked_at_utc: Optional[float] = None

    @classmethod
    def create(cls, mission_id: str, correlation_id: str) -> ContextPack:
        cp_id = f"ctx_{uuid.uuid4().hex[:12]}"
        return cls(
            context_pack_id=cp_id,
            mission_id=mission_id,
            correlation_id=correlation_id,
        )

    def lock(self) -> None:
        """Locks context pack to prevent mid-execution drift."""
        self.locked_at_utc = time.time()

    @property
    def is_locked(self) -> bool:
        return self.locked_at_utc is not None

    def add_fact(self, statement: str, source: str, verified: bool = True) -> None:
        if self.is_locked:
            raise ValueError("Cannot modify locked ContextPack")
        entry = {
            "statement": statement,
            "source": source,
            "timestamp_utc": time.time(),
            "verified": verified,
        }
        if verified:
            self.facts.append(entry)
            self.verified_state.append(entry)
        else:
            self.unverified_claims.append(entry)

    def record_source_version(self, resource_uri: str, version_hash: str) -> None:
        if self.is_locked:
            raise ValueError("Cannot modify locked ContextPack")
        self.source_versions[resource_uri] = version_hash

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
