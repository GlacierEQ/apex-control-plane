"""Jack CaseBuilder / Allegation Forge.

Transforms raw case material into traceable case objects and hardened allegation
cards. Dependency-free. Facts, legal theories, and mental-state inferences remain
separate proof layers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping

CONTRACT_ID = "JTR-CASEBUILDER-v1"
CONTRACT_VERSION = "1.0.0"


class ProofState(str, Enum):
    VERIFIED_PRIMARY = "VERIFIED_PRIMARY"
    CORROBORATED = "CORROBORATED"
    FIRSTHAND_CONTEMPORANEOUS = "FIRSTHAND_CONTEMPORANEOUS"
    ATTRIBUTED = "ATTRIBUTED"
    STRONG_INFERENCE = "STRONG_INFERENCE"
    ALLEGED = "ALLEGED"
    UNRESOLVED = "UNRESOLVED"
    CONTRADICTED = "CONTRADICTED"
    QUARANTINED = "QUARANTINED"
    DISPROVED = "DISPROVED"


class PromotionState(str, Enum):
    RAW = "RAW"
    STRUCTURED = "STRUCTURED"
    SOURCED = "SOURCED"
    CORROBORATED = "CORROBORATED"
    ELEMENT_MAPPED = "ELEMENT_MAPPED"
    DEFENSE_TESTED = "DEFENSE_TESTED"
    HARDENED = "HARDENED"
    PLEADING_READY = "PLEADING_READY"
    REFERRAL_READY = "REFERRAL_READY"
    TRIAL_READY = "TRIAL_READY"


class Lane(str, Enum):
    FACTUAL = "FACTUAL"
    PROCEDURAL = "PROCEDURAL"
    ETHICAL = "ETHICAL"
    CIVIL = "CIVIL"
    ADMINISTRATIVE = "ADMINISTRATIVE"
    EVIDENTIARY = "EVIDENTIARY"
    POTENTIAL_CRIMINAL = "POTENTIAL_CRIMINAL"


@dataclass(frozen=True)
class SourceRef:
    id: str
    source_type: str
    locator: str
    proof_state: ProofState
    excerpt: str = ""
    timestamp: str | None = None
    hash: str | None = None


@dataclass(frozen=True)
class ElementSupport:
    name: str
    supporting_source_ids: tuple[str, ...] = ()
    contrary_source_ids: tuple[str, ...] = ()
    gap_ids: tuple[str, ...] = ()
    satisfied: bool = False


@dataclass
class Allegation:
    id: str
    title: str
    lane: Lane
    actor_ids: list[str]
    event_ids: list[str]
    act: str
    factual_theory: str
    legal_theory: str
    elements: list[ElementSupport]
    primary_source_ids: list[str]
    corroborating_source_ids: list[str] = field(default_factory=list)
    contradictory_source_ids: list[str] = field(default_factory=list)
    mental_state_required: str | None = None
    mental_state_source_ids: list[str] = field(default_factory=list)
    causation: str = ""
    harm_ids: list[str] = field(default_factory=list)
    defenses: list[str] = field(default_factory=list)
    rebuttals: list[str] = field(default_factory=list)
    missing_evidence_ids: list[str] = field(default_factory=list)
    discovery_target_ids: list[str] = field(default_factory=list)
    remedy_ids: list[str] = field(default_factory=list)
    proof_state: ProofState = ProofState.ALLEGED
    promotion_state: PromotionState = PromotionState.RAW
    confidence: float = 0.0
    impact_score: float = 0.0
    pleading_paragraph: str = ""


@dataclass(frozen=True)
class Contradiction:
    id: str
    allegation_id: str
    proposition: str
    left_source_id: str
    right_source_id: str
    materiality: str
    resolution_target_id: str | None = None


@dataclass(frozen=True)
class DiscoveryTarget:
    id: str
    allegation_id: str
    missing_fact: str
    record_or_witness: str
    custodian: str
    route: str
    priority: str = "P1"
    gap_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.priority not in {"P0", "P1", "P2", "P3"}:
            raise ValueError(f"invalid discovery priority: {self.priority}")
        if any(not gap_id or not gap_id.strip() for gap_id in self.gap_ids):
            raise ValueError("discovery gap_ids must be non-empty")


@dataclass
class CasePacket:
    matter_id: str
    sources: dict[str, SourceRef] = field(default_factory=dict)
    actors: dict[str, dict[str, Any]] = field(default_factory=dict)
    events: dict[str, dict[str, Any]] = field(default_factory=dict)
    allegations: dict[str, Allegation] = field(default_factory=dict)
    contradictions: dict[str, Contradiction] = field(default_factory=dict)
    harms: dict[str, dict[str, Any]] = field(default_factory=dict)
    remedies: dict[str, dict[str, Any]] = field(default_factory=dict)
    discovery_targets: dict[str, DiscoveryTarget] = field(default_factory=dict)

    def add_source(self, source: SourceRef) -> None:
        _insert_unique(self.sources, source.id, source)

    def add_allegation(self, allegation: Allegation) -> None:
        _insert_unique(self.allegations, allegation.id, allegation)

    def add_contradiction(self, contradiction: Contradiction) -> None:
        _insert_unique(self.contradictions, contradiction.id, contradiction)

    def add_discovery_target(self, target: DiscoveryTarget) -> None:
        _insert_unique(self.discovery_targets, target.id, target)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.matter_id or not self.matter_id.strip():
            errors.append("matter_id must be non-empty")
        for source_id, source in self.sources.items():
            if source_id != source.id:
                errors.append(
                    f"source map key {source_id} does not match source id {source.id}"
                )
        for allegation in self.allegations.values():
            source_lists = (
                ("primary", allegation.primary_source_ids),
                ("corroborating", allegation.corroborating_source_ids),
                ("contradictory", allegation.contradictory_source_ids),
                ("mental-state", allegation.mental_state_source_ids),
            )
            for label, source_ids in source_lists:
                duplicates = _duplicate_ids(source_ids)
                if duplicates:
                    errors.append(
                        f"{allegation.id}: duplicate {label} source ids: "
                        + ", ".join(duplicates)
                    )
            for element in allegation.elements:
                if element.satisfied and not element.supporting_source_ids:
                    errors.append(
                        f"{allegation.id}: satisfied element {element.name} "
                        "has no supporting source"
                    )
            for actor_id in allegation.actor_ids:
                if actor_id not in self.actors:
                    errors.append(f"{allegation.id}: missing actor {actor_id}")
            for event_id in allegation.event_ids:
                if event_id not in self.events:
                    errors.append(f"{allegation.id}: missing event {event_id}")
            for source_id in _all_source_refs(allegation):
                if source_id not in self.sources:
                    errors.append(f"{allegation.id}: missing source {source_id}")
            linked_gap_ids: set[str] = set()
            for target_id in allegation.discovery_target_ids:
                target = self.discovery_targets.get(target_id)
                if target is None:
                    errors.append(f"{allegation.id}: missing discovery target {target_id}")
                elif target.allegation_id != allegation.id:
                    errors.append(
                        f"{allegation.id}: discovery target {target_id} belongs to "
                        f"{target.allegation_id}"
                    )
                else:
                    linked_gap_ids.update(target.gap_ids)
            for gap_id in allegation.missing_evidence_ids:
                if gap_id not in linked_gap_ids:
                    errors.append(
                        f"{allegation.id}: unresolved gap {gap_id} has no discovery target"
                    )
            for remedy_id in allegation.remedy_ids:
                if remedy_id not in self.remedies:
                    errors.append(f"{allegation.id}: missing remedy {remedy_id}")
            for harm_id in allegation.harm_ids:
                if harm_id not in self.harms:
                    errors.append(f"{allegation.id}: missing harm {harm_id}")
        for target in self.discovery_targets.values():
            if target.allegation_id not in self.allegations:
                errors.append(f"{target.id}: missing allegation {target.allegation_id}")
            elif target.id not in self.allegations[target.allegation_id].discovery_target_ids:
                errors.append(
                    f"{target.id}: not attached to allegation {target.allegation_id}"
                )
        for contradiction in self.contradictions.values():
            if contradiction.allegation_id not in self.allegations:
                errors.append(f"{contradiction.id}: missing allegation {contradiction.allegation_id}")
            for source_id in (contradiction.left_source_id, contradiction.right_source_id):
                if source_id not in self.sources:
                    errors.append(f"{contradiction.id}: missing source {source_id}")
            if contradiction.resolution_target_id and contradiction.resolution_target_id not in self.discovery_targets:
                errors.append(f"{contradiction.id}: missing target {contradiction.resolution_target_id}")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": CONTRACT_ID,
            "contract_version": CONTRACT_VERSION,
            "matter_id": self.matter_id,
            "sources": {k: _serialize(v) for k, v in self.sources.items()},
            "actors": _serialize(self.actors),
            "events": _serialize(self.events),
            "allegations": {k: _serialize(v) for k, v in self.allegations.items()},
            "contradictions": {k: _serialize(v) for k, v in self.contradictions.items()},
            "harms": _serialize(self.harms),
            "remedies": _serialize(self.remedies),
            "discovery_targets": {k: _serialize(v) for k, v in self.discovery_targets.items()},
        }


def _insert_unique(mapping: dict[str, Any], key: str, value: Any) -> None:
    if not key or not key.strip():
        raise ValueError("case object id must be non-empty")
    if key in mapping:
        raise ValueError(f"duplicate case object id: {key}")
    mapping[key] = value


def _duplicate_ids(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def _serialize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {k: _serialize(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    return value


def _all_source_refs(a: Allegation) -> set[str]:
    refs = set(a.primary_source_ids) | set(a.corroborating_source_ids) | set(a.contradictory_source_ids) | set(a.mental_state_source_ids)
    for element in a.elements:
        refs.update(element.supporting_source_ids)
        refs.update(element.contrary_source_ids)
    return refs


def _source_is_usable(source: SourceRef) -> bool:
    return proof_strength(source.proof_state) > 0


def proof_strength(state: ProofState) -> int:
    return {
        ProofState.VERIFIED_PRIMARY: 5,
        ProofState.CORROBORATED: 4,
        ProofState.FIRSTHAND_CONTEMPORANEOUS: 3,
        ProofState.ATTRIBUTED: 2,
        ProofState.STRONG_INFERENCE: 2,
        ProofState.ALLEGED: 1,
        ProofState.UNRESOLVED: 0,
        ProofState.CONTRADICTED: 0,
        ProofState.QUARANTINED: -2,
        ProofState.DISPROVED: -5,
    }[state]


def attack(allegation: Allegation, sources: Mapping[str, SourceRef]) -> list[str]:
    defects: list[str] = []
    if not allegation.actor_ids:
        defects.append("actor attribution absent; use UNKNOWN/DOE actor object or identify actor")
    if not allegation.act.strip():
        defects.append("concrete act/omission absent")
    if not allegation.primary_source_ids:
        defects.append("no primary source linked")
    if not allegation.elements:
        defects.append("no elements mapped")
    elif any(not e.satisfied for e in allegation.elements):
        defects.append("one or more required elements unsatisfied")
    for element in allegation.elements:
        if element.satisfied and not element.supporting_source_ids:
            defects.append(
                f"satisfied element {element.name} has no supporting source"
            )
        elif element.satisfied and not any(
            source_id in sources and _source_is_usable(sources[source_id])
            for source_id in element.supporting_source_ids
        ):
            defects.append(
                f"satisfied element {element.name} has no usable supporting source"
            )
    missing_refs = [sid for sid in _all_source_refs(allegation) if sid not in sources]
    if allegation.primary_source_ids and not any(
        source_id in sources and _source_is_usable(sources[source_id])
        for source_id in set(allegation.primary_source_ids)
    ):
        defects.append("no usable primary source")
    if missing_refs:
        defects.append("broken source references: " + ", ".join(sorted(missing_refs)))
    if allegation.mental_state_required and not allegation.mental_state_source_ids:
        defects.append("mental state required but no mental-state evidence linked")
    if not allegation.defenses:
        defects.append("best defense not yet built")
    if allegation.defenses and not allegation.rebuttals:
        defects.append("defense exists but rebuttal not yet built")
    if not allegation.causation.strip():
        defects.append("causation chain absent")
    if allegation.proof_state in {ProofState.QUARANTINED, ProofState.DISPROVED}:
        defects.append(f"proof state blocks promotion: {allegation.proof_state.value}")
    return defects


def score(allegation: Allegation, sources: Mapping[str, SourceRef]) -> float:
    """Deterministic impact score; consequence never substitutes for proof."""
    source_values = [
        proof_strength(sources[source_id].proof_state)
        for source_id in set(allegation.primary_source_ids)
        if source_id in sources
    ]
    proof = max(source_values, default=0)
    element_coverage = 5 * (sum(e.satisfied for e in allegation.elements) / len(allegation.elements)) if allegation.elements else 0
    corroboration = min(5, len(set(allegation.corroborating_source_ids)))
    contradiction_power = min(5, len(set(allegation.contradictory_source_ids)))
    actor = 5 if allegation.actor_ids else 0
    mental = 5 if not allegation.mental_state_required else min(5, len(set(allegation.mental_state_source_ids)) * 2.5)
    defense = 5 if allegation.defenses and allegation.rebuttals else 2 if allegation.defenses else 0
    harm = min(5, len(set(allegation.harm_ids)) * 2.5)
    remedy = min(5, len(set(allegation.remedy_ids)) * 2.5)
    gap_penalty = min(15, len(allegation.missing_evidence_ids) * 3)
    return round(
        proof * 5 + element_coverage * 5 + corroboration * 3
        + contradiction_power * 2 + actor * 2 + mental * 2
        + defense * 2 + harm * 2 + remedy * 2 - gap_penalty,
        2,
    )


def promote(allegation: Allegation, sources: Mapping[str, SourceRef]) -> PromotionState:
    """Fail closed: promotion follows proof, elements, defense testing, and traceability."""
    defects = attack(allegation, sources)
    if allegation.proof_state in {ProofState.QUARANTINED, ProofState.DISPROVED}:
        return PromotionState.RAW
    if not allegation.actor_ids or not allegation.act.strip():
        return PromotionState.STRUCTURED
    if not allegation.primary_source_ids:
        return PromotionState.STRUCTURED
    if any("broken source" in defect for defect in defects):
        return PromotionState.STRUCTURED
    if any("no usable primary source" in defect for defect in defects):
        return PromotionState.STRUCTURED
    if not allegation.elements:
        return PromotionState.SOURCED
    if any(not element.satisfied for element in allegation.elements):
        return PromotionState.ELEMENT_MAPPED
    if any(
        element.satisfied
        and (
            not element.supporting_source_ids
            or not any(
                source_id in sources and _source_is_usable(sources[source_id])
                for source_id in element.supporting_source_ids
            )
        )
        for element in allegation.elements
    ):
        return PromotionState.ELEMENT_MAPPED
    if not allegation.defenses:
        return PromotionState.ELEMENT_MAPPED
    if not allegation.rebuttals:
        return PromotionState.DEFENSE_TESTED
    if allegation.mental_state_required and not allegation.mental_state_source_ids:
        return PromotionState.DEFENSE_TESTED
    if not allegation.causation.strip():
        return PromotionState.DEFENSE_TESTED
    if allegation.missing_evidence_ids:
        return PromotionState.HARDENED
    return PromotionState.PLEADING_READY


def harden(allegation: Allegation, sources: Mapping[str, SourceRef]) -> Allegation:
    allegation.impact_score = score(allegation, sources)
    allegation.promotion_state = promote(allegation, sources)
    return allegation


def gap_to_discovery_target(
    *,
    allegation_id: str,
    gap_id: str,
    missing_fact: str,
    record_or_witness: str,
    custodian: str,
    route: str,
    priority: str = "P1",
) -> DiscoveryTarget:
    """Prime directive: unresolved gaps become executable acquisition targets."""
    if not gap_id or not gap_id.strip():
        raise ValueError("gap_id must be non-empty")
    return DiscoveryTarget(
        id=f"DISC-{gap_id}",
        allegation_id=allegation_id,
        missing_fact=missing_fact,
        record_or_witness=record_or_witness,
        custodian=custodian,
        route=route,
        priority=priority,
        gap_ids=(gap_id,),
    )


def render_allegation_card(a: Allegation) -> str:
    lines = [
        f"# {a.id} — {a.title}",
        "",
        f"**Lane:** {a.lane.value}",
        f"**Proof:** {a.proof_state.value}",
        f"**Promotion:** {a.promotion_state.value}",
        f"**Impact score:** {a.impact_score}",
        f"**Actors:** {', '.join(a.actor_ids) or 'UNMAPPED'}",
        f"**Events:** {', '.join(a.event_ids) or 'UNMAPPED'}",
        "",
        "## Act", a.act,
        "", "## Factual theory", a.factual_theory,
        "", "## Legal theory", a.legal_theory,
        "", "## Elements",
    ]
    for e in a.elements:
        lines.append(f"- [{'x' if e.satisfied else ' '}] {e.name} | support={list(e.supporting_source_ids)} | contrary={list(e.contrary_source_ids)} | gaps={list(e.gap_ids)}")
    lines += [
        "", "## Contradictions", ", ".join(a.contradictory_source_ids) or "None linked",
        "", "## Mental state", f"required={a.mental_state_required or 'none'} evidence={a.mental_state_source_ids}",
        "", "## Causation", a.causation or "UNMAPPED",
        "", "## Defenses / rebuttals", f"defenses={a.defenses}", f"rebuttals={a.rebuttals}",
        "", "## Missing evidence / discovery", f"missing={a.missing_evidence_ids}", f"targets={a.discovery_target_ids}",
        "", "## Remedies / harms", f"harms={a.harm_ids}", f"remedies={a.remedy_ids}",
        "", "## Pleading-ready paragraph", a.pleading_paragraph or "NOT YET GENERATED",
    ]
    return "\n".join(lines) + "\n"


def compile_case(packet: CasePacket) -> dict[str, Any]:
    """Validate first, then harden allegations and emit the machine packet."""
    errors = packet.validate()
    if errors:
        raise ValueError("case packet invalid: " + "; ".join(errors))
    for allegation in packet.allegations.values():
        harden(allegation, packet.sources)
    result = packet.to_dict()
    result["metrics"] = {
        "sources": len(packet.sources),
        "actors": len(packet.actors),
        "events": len(packet.events),
        "allegations": len(packet.allegations),
        "contradictions": len(packet.contradictions),
        "discovery_targets": len(packet.discovery_targets),
        "pleading_ready": sum(a.promotion_state == PromotionState.PLEADING_READY for a in packet.allegations.values()),
    }
    return result
