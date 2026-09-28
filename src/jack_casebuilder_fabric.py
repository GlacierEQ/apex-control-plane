"""Federated JACK CaseBuilder projection fabric.

JACK consumes case-scoped peer projections without creating a new global source
of truth. Provider/source identity is preserved; peer disagreement is surfaced as
an explicit conflict; stale peers remain visible; action selection delegates to
the current APEX continuous-impact selector.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

try:
    from .continuous_impact_selection import ContinuousImpactSelector, ImpactCandidate, ImpactDecision
except ImportError:
    from continuous_impact_selection import ContinuousImpactSelector, ImpactCandidate, ImpactDecision

FABRIC_VERSION = "glaciereq.jack-fabric/2.1"
PROJECTION_ROLES = {
    "NATIVE_EVIDENCE",
    "MATTER_GRAPH",
    "STRUCTURED_DB",
    "EVIDENCE_VAULT",
    "HUMAN_REVIEW",
    "ORCHESTRATION",
    "MEMORY_ROUTING",
    "COMPATIBILITY_AGGREGATE",
}


class JackFabricViolation(ValueError):
    """Raised when a peer projection violates fabric invariants."""


@dataclass(frozen=True, slots=True)
class ProjectionEnvelope:
    projection_id: str
    case_id: str
    provider: str
    locator: str
    role: str
    revision: str
    observed_at: str
    payload: Mapping[str, Any]
    provenance_refs: tuple[str, ...] = ()
    coverage: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def payload_sha256(self) -> str:
        return _digest(self.payload)


@dataclass(frozen=True, slots=True)
class ProjectionConflict:
    conflict_id: str
    case_id: str
    object_type: str
    object_id: str
    field: str
    values: Mapping[str, Any]
    projection_ids: tuple[str, ...]
    status: str = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class ProjectionHealth:
    projection_id: str
    role: str
    revision: str
    observed_at: str
    age_seconds: int
    stale: bool
    payload_sha256: str


@dataclass(frozen=True, slots=True)
class FabricView:
    case_id: str
    projection_ids: tuple[str, ...]
    projection_health: tuple[ProjectionHealth, ...]
    allegation_ids: tuple[str, ...]
    discovery_target_ids: tuple[str, ...]
    remedy_ids: tuple[str, ...]
    conflicts: tuple[ProjectionConflict, ...]
    stale_projection_ids: tuple[str, ...]
    fabric_sha256: str
    fabric_version: str = FABRIC_VERSION


def validate_envelope(envelope: ProjectionEnvelope) -> None:
    for name, value in {
        "projection_id": envelope.projection_id,
        "case_id": envelope.case_id,
        "provider": envelope.provider,
        "locator": envelope.locator,
        "revision": envelope.revision,
        "observed_at": envelope.observed_at,
    }.items():
        _required_text(value, name)
    if envelope.role not in PROJECTION_ROLES:
        raise JackFabricViolation(f"unsupported projection role: {envelope.role}")
    if not isinstance(envelope.payload, Mapping):
        raise JackFabricViolation("projection payload must be an object")
    _parse_time(envelope.observed_at)
    if envelope.metadata.get("global_authority") is True:
        raise JackFabricViolation("peer projection may not claim global authority")
    if envelope.metadata.get("globally_canonical") is True:
        raise JackFabricViolation("peer projection may not claim global canonicality")


def build_fabric(
    projections: Sequence[ProjectionEnvelope],
    *,
    now: datetime | None = None,
    stale_after_seconds: int = 7 * 24 * 60 * 60,
) -> FabricView:
    if not projections:
        raise JackFabricViolation("at least one peer projection is required")
    if stale_after_seconds <= 0:
        raise JackFabricViolation("stale_after_seconds must be positive")

    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise JackFabricViolation("now must be timezone-aware")

    case_ids: set[str] = set()
    projection_ids: set[str] = set()
    health: list[ProjectionHealth] = []
    for projection in projections:
        validate_envelope(projection)
        if projection.projection_id in projection_ids:
            raise JackFabricViolation(f"duplicate projection_id: {projection.projection_id}")
        projection_ids.add(projection.projection_id)
        case_ids.add(projection.case_id)
        observed = _parse_time(projection.observed_at)
        age_seconds = max(0, int((current - observed).total_seconds()))
        health.append(
            ProjectionHealth(
                projection_id=projection.projection_id,
                role=projection.role,
                revision=projection.revision,
                observed_at=projection.observed_at,
                age_seconds=age_seconds,
                stale=age_seconds > stale_after_seconds,
                payload_sha256=projection.payload_sha256,
            )
        )

    if len(case_ids) != 1:
        raise JackFabricViolation("one fabric view may contain only one case_id")

    case_id = next(iter(case_ids))
    conflicts = tuple(_find_conflicts(projections, case_id=case_id))
    allegations = tuple(sorted(_union_ids(projections, "allegations", "allegation_id")))
    discovery = tuple(sorted(_union_ids(projections, "discovery_targets", "discovery_target_id")))
    remedies = tuple(sorted(_union_ids(projections, "remedies", "remedy_id")))
    stale_ids = tuple(sorted(row.projection_id for row in health if row.stale))
    payload = {
        "fabric_version": FABRIC_VERSION,
        "case_id": case_id,
        "projections": [
            {
                "projection_id": p.projection_id,
                "provider": p.provider,
                "locator": p.locator,
                "role": p.role,
                "revision": p.revision,
                "payload_sha256": p.payload_sha256,
            }
            for p in sorted(projections, key=lambda item: item.projection_id)
        ],
        "allegation_ids": allegations,
        "discovery_target_ids": discovery,
        "remedy_ids": remedies,
        "conflict_ids": [row.conflict_id for row in conflicts],
        "stale_projection_ids": stale_ids,
    }
    return FabricView(
        case_id=case_id,
        projection_ids=tuple(sorted(projection_ids)),
        projection_health=tuple(sorted(health, key=lambda row: row.projection_id)),
        allegation_ids=allegations,
        discovery_target_ids=discovery,
        remedy_ids=remedies,
        conflicts=conflicts,
        stale_projection_ids=stale_ids,
        fabric_sha256=_digest(payload),
    )


def select_case_action(
    *,
    fabric: FabricView,
    mission: str,
    state_version: str,
    candidates: Sequence[ImpactCandidate],
    operation_class: str = "CASE_EXECUTION",
    selector: ContinuousImpactSelector | None = None,
) -> ImpactDecision:
    """Route case candidates through the current APEX impact selector."""
    engine = selector or ContinuousImpactSelector()
    return engine.select(
        task_id=f"jack:{fabric.case_id}",
        mission=mission,
        operation_class=operation_class,
        state_version=state_version,
        candidates=candidates,
    )


def _find_conflicts(
    projections: Sequence[ProjectionEnvelope], *, case_id: str
) -> list[ProjectionConflict]:
    conflicts: list[ProjectionConflict] = []
    specifications = (
        ("allegation", "allegations", "allegation_id", ("promotion_state", "proof_status", "status", "tier")),
        ("fact", "facts", "fact_id", ("fact_state", "proof_state", "statement")),
        ("event", "events", "event_id", ("date_or_range", "date_period", "title")),
    )
    for object_type, collection, id_key, fields in specifications:
        bucket: dict[str, list[tuple[str, Mapping[str, Any]]]] = {}
        for projection in projections:
            for row in _rows(projection.payload, collection):
                object_id = str(row.get(id_key, "")).strip()
                if object_id:
                    bucket.setdefault(object_id, []).append((projection.projection_id, row))
        for object_id, rows in bucket.items():
            if len(rows) < 2:
                continue
            for field_name in fields:
                values = {
                    projection_id: row[field_name]
                    for projection_id, row in rows
                    if field_name in row and row[field_name] is not None
                }
                normalized = {_canonical_json({"value": value}) for value in values.values()}
                if len(values) >= 2 and len(normalized) > 1:
                    ordered = dict(sorted(values.items()))
                    conflicts.append(
                        ProjectionConflict(
                            conflict_id=_digest(
                                {
                                    "case_id": case_id,
                                    "object_type": object_type,
                                    "object_id": object_id,
                                    "field": field_name,
                                    "values": ordered,
                                }
                            ),
                            case_id=case_id,
                            object_type=object_type,
                            object_id=object_id,
                            field=field_name,
                            values=ordered,
                            projection_ids=tuple(ordered),
                        )
                    )
    return sorted(conflicts, key=lambda row: (row.object_type, row.object_id, row.field))


def _union_ids(projections: Sequence[ProjectionEnvelope], collection: str, key: str) -> set[str]:
    values: set[str] = set()
    for projection in projections:
        for row in _rows(projection.payload, collection):
            value = str(row.get(key, "")).strip()
            if value:
                values.add(value)
    return values


def _rows(payload: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = payload.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(row, Mapping) for row in value):
        raise JackFabricViolation(f"{key} must be a list of objects when present")
    return list(value)


def _parse_time(value: str) -> datetime:
    text = _required_text(value, "observed_at")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise JackFabricViolation("observed_at must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise JackFabricViolation("observed_at must be timezone-aware")
    return parsed.astimezone(UTC)


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise JackFabricViolation(f"{field_name} must be non-empty")
    return value.strip()


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Mapping[str, Any]) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()
