"""Jack CaseBuilder adapter for the APEX control plane.

Consumes a CaseBuilder JSON projection without promoting allegations to fact.
Validates structural lineage and exposes case pressure to the legal_case profile.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

CASEBUILDER_SCHEMA_VERSION = "1.0"
CASEBUILDER_ADAPTER_VERSION = "1.0.0"

class CaseBuilderAdapterError(ValueError):
    pass

@dataclass(frozen=True, slots=True)
class CaseBuilderRuntimeProjection:
    case_id: str
    title: str
    objective: str
    casebuilder_sha256: str
    counts: Mapping[str, int]
    anchor_allegation_ids: tuple[str, ...]
    development_allegation_ids: tuple[str, ...]
    pleading_ready_ids: tuple[str, ...]
    critical_discovery_target_ids: tuple[str, ...]
    high_discovery_target_ids: tuple[str, ...]
    open_gap_count: int
    unresolved_gap_refs: tuple[str, ...]

    def as_payload(self) -> dict[str, Any]:
        return {
            "adapter_version": CASEBUILDER_ADAPTER_VERSION,
            "case_id": self.case_id,
            "title": self.title,
            "objective": self.objective,
            "casebuilder_sha256": self.casebuilder_sha256,
            "counts": dict(self.counts),
            "anchor_allegation_ids": list(self.anchor_allegation_ids),
            "development_allegation_ids": list(self.development_allegation_ids),
            "pleading_ready_ids": list(self.pleading_ready_ids),
            "critical_discovery_target_ids": list(self.critical_discovery_target_ids),
            "high_discovery_target_ids": list(self.high_discovery_target_ids),
            "open_gap_count": self.open_gap_count,
            "unresolved_gap_refs": list(self.unresolved_gap_refs),
        }

def _rows(data: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = data.get(key)
    if not isinstance(value, list):
        raise CaseBuilderAdapterError(f"{key} must be a list")
    if any(not isinstance(row, Mapping) for row in value):
        raise CaseBuilderAdapterError(f"{key} entries must be objects")
    return value

def _unique(rows: list[Mapping[str, Any]], key: str) -> set[str]:
    values: set[str] = set()
    for row in rows:
        value = str(row.get(key, "")).strip()
        if not value:
            raise CaseBuilderAdapterError(f"missing {key}")
        if value in values:
            raise CaseBuilderAdapterError(f"duplicate {key}: {value}")
        values.add(value)
    return values

def _require_refs(values: Any, valid: set[str], owner: str, label: str) -> None:
    if values is None:
        return
    if not isinstance(values, list):
        raise CaseBuilderAdapterError(f"{owner}: {label} must be a list")
    for ref in values:
        if ref not in valid:
            raise CaseBuilderAdapterError(f"{owner}: unknown {label} {ref}")

def validate_casebuilder(data: Mapping[str, Any]) -> None:
    if data.get("schema_version") != CASEBUILDER_SCHEMA_VERSION:
        raise CaseBuilderAdapterError("unsupported CaseBuilder schema_version")
    case = data.get("case")
    if not isinstance(case, Mapping):
        raise CaseBuilderAdapterError("case must be an object")
    for field in ("case_id", "title", "jurisdiction", "posture", "objective"):
        if not str(case.get(field, "")).strip():
            raise CaseBuilderAdapterError(f"case.{field} is required")

    sources = _rows(data, "sources")
    actors = _rows(data, "actors")
    events = _rows(data, "events")
    facts = _rows(data, "facts")
    allegations = _rows(data, "allegations")
    contradictions = _rows(data, "contradictions")
    damages = _rows(data, "damages")
    discovery = _rows(data, "discovery_targets")
    remedies = _rows(data, "remedies")
    accountability = _rows(data, "accountability_paths")

    source_ids = _unique(sources, "source_id")
    actor_ids = _unique(actors, "actor_id")
    event_ids = _unique(events, "event_id")
    fact_ids = _unique(facts, "fact_id")
    allegation_ids = _unique(allegations, "allegation_id")
    damage_ids = _unique(damages, "damage_id")
    discovery_ids = _unique(discovery, "discovery_target_id")
    remedy_ids = _unique(remedies, "remedy_id")
    accountability_ids = _unique(accountability, "accountability_path_id")

    for event in events:
        eid = event["event_id"]
        for field in ("actor_ids", "source_ids", "fact_ids"):
            if not event.get(field):
                raise CaseBuilderAdapterError(f"{eid}: {field} cannot be empty")
        _require_refs(event["actor_ids"], actor_ids, eid, "actor")
        _require_refs(event["source_ids"], source_ids, eid, "source")
        _require_refs(event["fact_ids"], fact_ids, eid, "fact")
        _require_refs(event.get("allegation_ids", []), allegation_ids, eid, "allegation")

    for fact in facts:
        fid = fact["fact_id"]
        if not fact.get("source_ids"):
            raise CaseBuilderAdapterError(f"{fid}: source lineage required")
        _require_refs(fact["source_ids"], source_ids, fid, "source")
        _require_refs(fact.get("event_ids", []), event_ids, fid, "event")
        _require_refs(fact.get("actor_ids", []), actor_ids, fid, "actor")

    for allegation in allegations:
        aid = allegation["allegation_id"]
        for field in (
            "actor_ids","event_ids","elements","supporting_fact_ids","primary_source_ids",
            "defenses","harm_ids","remedy_ids","next_use",
        ):
            if not allegation.get(field):
                raise CaseBuilderAdapterError(f"{aid}: {field} cannot be empty")
        _require_refs(allegation["actor_ids"], actor_ids, aid, "actor")
        _require_refs(allegation["event_ids"], event_ids, aid, "event")
        _require_refs(allegation["supporting_fact_ids"], fact_ids, aid, "fact")
        _require_refs(allegation["primary_source_ids"], source_ids, aid, "source")
        _require_refs(allegation.get("corroborating_source_ids", []), source_ids, aid, "source")
        _require_refs(allegation.get("contradictory_source_ids", []), source_ids, aid, "source")
        _require_refs(allegation["harm_ids"], damage_ids, aid, "damage")
        _require_refs(allegation.get("discovery_target_ids", []), discovery_ids, aid, "discovery")
        _require_refs(allegation["remedy_ids"], remedy_ids, aid, "remedy")
        _require_refs(allegation.get("accountability_path_ids", []), accountability_ids, aid, "accountability")
        for element in allegation["elements"]:
            if not isinstance(element, Mapping):
                raise CaseBuilderAdapterError(f"{aid}: element must be object")
            if not all(str(element.get(k, "")).strip() for k in ("element_id","description","status")):
                raise CaseBuilderAdapterError(f"{aid}: malformed element")
            _require_refs(element.get("supporting_fact_ids", []), fact_ids, aid, "fact")
            _require_refs(element.get("adverse_fact_ids", []), fact_ids, aid, "fact")
            _require_refs(element.get("source_ids", []), source_ids, aid, "source")
            _require_refs(element.get("discovery_target_ids", []), discovery_ids, aid, "discovery")

    for contradiction in contradictions:
        cid = str(contradiction.get("contradiction_id",""))
        _require_refs([contradiction.get("source_a"), contradiction.get("source_b")], source_ids, cid, "source")
        _require_refs(contradiction.get("affected_allegation_ids", []), allegation_ids, cid, "allegation")
        _require_refs(contradiction.get("discriminating_target_ids", []), discovery_ids, cid, "discovery")

def build_projection(data: Mapping[str, Any]) -> CaseBuilderRuntimeProjection:
    validate_casebuilder(data)
    case = data["case"]
    allegations = _rows(data, "allegations")
    discovery = _rows(data, "discovery_targets")
    anchors: list[str] = []
    development: list[str] = []
    pleading_ready: list[str] = []
    gaps: list[str] = []

    for allegation in allegations:
        aid = str(allegation["allegation_id"])
        states = {str(e.get("status")) for e in allegation["elements"]}
        promotion = str(allegation.get("promotion_state",""))
        tier = int(allegation.get("tier", 5))
        if promotion in {"PLEADING_READY","TRIAL_READY","FILED","ADJUDICATED"}:
            pleading_ready.append(aid)
        if tier <= 2 and promotion in {"HARDENED","PLEADING_READY","REFERRAL_READY","TRIAL_READY","FILED","ADJUDICATED"} and "MISSING" not in states:
            anchors.append(aid)
        else:
            development.append(aid)
        for idx, gap in enumerate(allegation.get("missing_evidence", []), 1):
            gaps.append(f"{aid}:gap:{idx}:{gap}")

    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",",":")).encode("utf-8")
    counts = {
        "sources":len(_rows(data,"sources")),
        "actors":len(_rows(data,"actors")),
        "events":len(_rows(data,"events")),
        "facts":len(_rows(data,"facts")),
        "allegations":len(allegations),
        "contradictions":len(_rows(data,"contradictions")),
        "damages":len(_rows(data,"damages")),
        "discovery_targets":len(discovery),
        "remedies":len(_rows(data,"remedies")),
        "accountability_paths":len(_rows(data,"accountability_paths")),
    }
    return CaseBuilderRuntimeProjection(
        case_id=str(case["case_id"]),
        title=str(case["title"]),
        objective=str(case["objective"]),
        casebuilder_sha256=sha256(canonical).hexdigest(),
        counts=counts,
        anchor_allegation_ids=tuple(anchors),
        development_allegation_ids=tuple(development),
        pleading_ready_ids=tuple(pleading_ready),
        critical_discovery_target_ids=tuple(str(t["discovery_target_id"]) for t in discovery if t.get("priority")=="CRITICAL" and t.get("status")!="CLOSED"),
        high_discovery_target_ids=tuple(str(t["discovery_target_id"]) for t in discovery if t.get("priority")=="HIGH" and t.get("status")!="CLOSED"),
        open_gap_count=len(gaps),
        unresolved_gap_refs=tuple(gaps),
    )

def load_projection(path: str | Path) -> CaseBuilderRuntimeProjection:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise CaseBuilderAdapterError("casebuilder root must be object")
    return build_projection(data)
