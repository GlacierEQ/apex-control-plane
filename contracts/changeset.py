"""
APEX CONTROL PLANE CONTRACTS: CHANGESET
Standard: Formal Change Specification with Optimistic Concurrency and Idempotency.
Separates AI judgment from the authority to mutate reality.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Operation:
    system: str  # "github", "notion", "dropbox", "filesystem"
    resource: str  # e.g. "GlacierEQ/job-app", "page_id_123", "/path/to/file"
    operation: str  # "update_file", "create_file", "delete_file", "update_properties"
    expected_before: Dict[str, Any]  # e.g. {"head_sha": "abc123"} or {"content_hash": "..."}
    desired_after: Dict[str, Any]  # e.g. {"path": "src/foo.py", "content": "..."}
    idempotency_key: str = ""

    def __post_init__(self):
        if not self.idempotency_key:
            raw = f"{self.system}:{self.resource}:{self.operation}:{json.dumps(self.desired_after, sort_keys=True)}"
            self.idempotency_key = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class ChangeSet:
    changeset_id: str
    mission_id: str
    correlation_id: str
    operations: List[Operation] = field(default_factory=list)
    expected_source_versions: Dict[str, str] = field(default_factory=dict)
    status: str = "PENDING"  # "PENDING", "PREFLIGHT_PASSED", "APPLYING", "COMMITTED", "REVERTED"
    created_at_utc: float = field(default_factory=time.time)

    @classmethod
    def create(cls, mission_id: str, correlation_id: str) -> ChangeSet:
        return cls(
            changeset_id=f"chg_{uuid.uuid4().hex[:12]}",
            mission_id=mission_id,
            correlation_id=correlation_id,
        )

    def add_operation(
        self,
        system: str,
        resource: str,
        operation: str,
        expected_before: Dict[str, Any],
        desired_after: Dict[str, Any],
    ) -> Operation:
        op = Operation(
            system=system,
            resource=resource,
            operation=operation,
            expected_before=expected_before,
            desired_after=desired_after,
        )
        self.operations.append(op)
        return op

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
