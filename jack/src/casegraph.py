"""Typed case graph extension for Jack CaseBuilder.

This module preserves the v1 allegation API while making the rest of the case
architecture first-class: facts, actors, events, defenses, damages, remedies,
accountability paths, contradiction state, orphan detection, and promotion
beyond pleading-ready.

No private evidence belongs in this public runtime. Private matters bind IDs
and source locators at execution time.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from jack.src.casebuilder import (
    Allegation,
    CasePacket,
    Contradiction,
    DiscoveryTarget,
    PromotionState,
    SourceRef,
    compile_case,
    element_status,
    proof_strength,
    promote,
)

GRAPH_CONTRACT_ID = "JTR-CASEGRAPH-v1"
GRAPH_CONTRACT_VERSION = "1.0.0"


class ContradictionState(str, Enum):
    OPEN = "OPEN"
    PARTIALLY_RECONCILED = "PARTIALLY_RECONCILED"
    RESOLVED = "RESOLVED"
    IMPEACHMENT_READY = "IMPEACHMENT_READY"


class PatternState(str, Enum):
    POTENTIAL = "POTENTIAL"
    SUPPORTED = "SUPPORTED"
    ESTABLISHED = "ESTABLISHED"
    QUARANTINED = "QUARANTINED"


@dataclass(frozen=True)
class FactProposition:
    id: str
    proposition: str
    source_ids: tuple[str, ...]
    actor_ids: tuple[str, ...] = ()
    event_ids: tuple[str, ...] = ()
    disputed: bool = False


@dataclass(frozen=True)
class IncidentNode:
    id: str
    title: str
    event_ids: tuple[str, ...]
    actor_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    date_or_period: str = ""
    location_or_context: str = ""


@dataclass(frozen=True)
class InstitutionNode:
    id: str
    name: str
    authority: tuple[str, ...] = ()
    policy_source_ids: tuple[str, ...] = ()
    system_names: tuple[str, ...] = ()
    notice_fact_ids: tuple[str, ...] = ()
    supervision_actor_ids: tuple[str, ...] = ()
    pattern_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActorNode:
    id: str
    name_or_role: str
    role: str = ""
    entity_id: str | None = None
    authority: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    unknown_identity: bool = False
    identity_discovery_target_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class EventNode:
    id: str
    title: str
    date_or_period: str
    location_or_context: str
    act: str
    actor_ids: tuple[str, ...]
    fact_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    harm_ids: tuple[str, ...] = ()
    incident_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class PatternNode:
    id: str
    title: str
    mechanism: str
    event_ids: tuple[str, ...]
    actor_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    allegation_ids: tuple[str, ...] = ()
    state: PatternState = PatternState.POTENTIAL


@dataclass(frozen=True)
class DefenseTheory:
    id: str
    allegation_id: str
    theory: str
    supporting_fact_ids: tuple[str, ...] = ()
    rebuttal_fact_ids: tuple[str, ...] = ()
    unresolved_risk: str | None = None


@dataclass(frozen=True)
class DamageRecord:
    id: str
    description: str
    cause_event_ids: tuple[str, ...]
    source_ids: tuple[str, ...] = ()
    date: str | None = None
    amount: float | None = None
    category: str | None = None


@dataclass(frozen=True)
class RemedyPath:
    id: str
    kind: str
    basis: str
    allegation_ids: tuple[str, ...]
    authority_ids: tuple[str, ...] = ()
    proof_required: tuple[str, ...] = ()


@dataclass(frozen=True)
class AccountabilityPath:
    id: str
    allegation_id: str
    forum_or_entity: str
    route: str
    basis: str
    remedy_ids: tuple[str, ...] = ()
    ready: bool = False


@dataclass(frozen=True)
class AllegationLink:
    allegation_id: str
    fact_ids: tuple[str, ...]
    duty_or_prohibition: tuple[str, ...]
    entity_ids: tuple[str, ...] = ()
    knowledge_fact_ids: tuple[str, ...] = ()
    mental_state_fact_ids: tuple[str, ...] = ()
    defense_ids: tuple[str, ...] = ()
    contradiction_ids: tuple[str, ...] = ()
    pattern_ids: tuple[str, ...] = ()
    accountability_path_ids: tuple[str, ...] = ()
    limitations_timeliness: str | None = None
    do_not_overstate: str | None = None


@dataclass(frozen=True)
class ContradictionAssessment:
    contradiction_id: str
    state: ContradictionState = ContradictionState.OPEN
    impeachment_value: str | None = None
    knowledge_inference: str | None = None
    discovery_target_ids: tuple[str, ...] = ()


def _put_unique(mapping: dict[str, Any], key: str, value: Any) -> None:
    if not key or not key.strip():
        raise ValueError("case graph object id must be non-empty")
    if key in mapping:
        raise ValueError(f"duplicate case graph object id: {key}")
    mapping[key] = value


def _serialize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {key: _serialize(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize(item) for item in value]
    return value


_PROMOTION_ORDER = {
    state: index
    for index, state in enumerate(
        (
            PromotionState.RAW,
            PromotionState.STRUCTURED,
            PromotionState.SOURCED,
            PromotionState.CORROBORATED,
            PromotionState.ELEMENT_MAPPED,
            PromotionState.DEFENSE_TESTED,
            PromotionState.HARDENED,
            PromotionState.PLEADING_READY,
            PromotionState.REFERRAL_READY,
            PromotionState.TRIAL_READY,
        )
    )
}


@dataclass
class CaseGraph:
    """Full typed case architecture wrapped around the stable v1 CasePacket."""

    matter_id: str
    packet: CasePacket = field(init=False)
    facts: dict[str, FactProposition] = field(default_factory=dict)
    incidents: dict[str, IncidentNode] = field(default_factory=dict)
    institutions: dict[str, InstitutionNode] = field(default_factory=dict)
    actor_nodes: dict[str, ActorNode] = field(default_factory=dict)
    event_nodes: dict[str, EventNode] = field(default_factory=dict)
    patterns: dict[str, PatternNode] = field(default_factory=dict)
    defense_theories: dict[str, DefenseTheory] = field(default_factory=dict)
    damage_records: dict[str, DamageRecord] = field(default_factory=dict)
    remedy_paths: dict[str, RemedyPath] = field(default_factory=dict)
    accountability_paths: dict[str, AccountabilityPath] = field(default_factory=dict)
    allegation_links: dict[str, AllegationLink] = field(default_factory=dict)
    contradiction_assessments: dict[str, ContradictionAssessment] = field(
        default_factory=dict
    )
    resolved_discovery_target_ids: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if not self.matter_id or not self.matter_id.strip():
            raise ValueError("matter_id must be non-empty")
        self.packet = CasePacket(self.matter_id)

    def add_source(self, source: SourceRef) -> None:
        self.packet.add_source(source)

    def add_fact(self, fact: FactProposition) -> None:
        _put_unique(self.facts, fact.id, fact)

    def add_incident(self, incident: IncidentNode) -> None:
        _put_unique(self.incidents, incident.id, incident)

    def add_institution(self, institution: InstitutionNode) -> None:
        _put_unique(self.institutions, institution.id, institution)

    def add_actor(self, actor: ActorNode) -> None:
        _put_unique(self.actor_nodes, actor.id, actor)
        self.packet.actors[actor.id] = _serialize(actor)

    def add_event(self, event: EventNode) -> None:
        _put_unique(self.event_nodes, event.id, event)
        self.packet.events[event.id] = _serialize(event)

    def add_pattern(self, pattern: PatternNode) -> None:
        _put_unique(self.patterns, pattern.id, pattern)

    def add_allegation(
        self, allegation: Allegation, link: AllegationLink | None = None
    ) -> None:
        self.packet.add_allegation(allegation)
        if link is not None:
            self.link_allegation(link)

    def link_allegation(self, link: AllegationLink) -> None:
        _put_unique(self.allegation_links, link.allegation_id, link)

    def add_contradiction(
        self,
        contradiction: Contradiction,
        assessment: ContradictionAssessment | None = None,
    ) -> None:
        self.packet.add_contradiction(contradiction)
        if assessment is not None:
            if assessment.contradiction_id != contradiction.id:
                raise ValueError("contradiction assessment id does not match")
            _put_unique(
                self.contradiction_assessments,
                assessment.contradiction_id,
                assessment,
            )

    def add_discovery_target(
        self, target: DiscoveryTarget, *, resolved: bool = False
    ) -> None:
        self.packet.add_discovery_target(target)
        if resolved:
            self.resolved_discovery_target_ids.add(target.id)

    def resolve_discovery_target(self, target_id: str) -> None:
        if target_id not in self.packet.discovery_targets:
            raise KeyError(target_id)
        self.resolved_discovery_target_ids.add(target_id)

    def add_defense(self, defense: DefenseTheory) -> None:
        _put_unique(self.defense_theories, defense.id, defense)

    def add_damage(self, damage: DamageRecord) -> None:
        _put_unique(self.damage_records, damage.id, damage)
        self.packet.harms[damage.id] = _serialize(damage)

    def add_remedy(self, remedy: RemedyPath) -> None:
        _put_unique(self.remedy_paths, remedy.id, remedy)
        self.packet.remedies[remedy.id] = _serialize(remedy)

    def add_accountability_path(self, path: AccountabilityPath) -> None:
        _put_unique(self.accountability_paths, path.id, path)

    def validate(self) -> list[str]:
        errors = list(self.packet.validate())

        for fact in self.facts.values():
            for source_id in fact.source_ids:
                if source_id not in self.packet.sources:
                    errors.append(f"{fact.id}: missing source {source_id}")
            for actor_id in fact.actor_ids:
                if actor_id not in self.actor_nodes:
                    errors.append(f"{fact.id}: missing actor {actor_id}")
            for event_id in fact.event_ids:
                if event_id not in self.event_nodes:
                    errors.append(f"{fact.id}: missing event {event_id}")

        for incident in self.incidents.values():
            for event_id in incident.event_ids:
                if event_id not in self.event_nodes:
                    errors.append(f"{incident.id}: missing event {event_id}")
            for actor_id in incident.actor_ids:
                if actor_id not in self.actor_nodes:
                    errors.append(f"{incident.id}: missing actor {actor_id}")
            for source_id in incident.source_ids:
                if source_id not in self.packet.sources:
                    errors.append(f"{incident.id}: missing source {source_id}")

        for institution in self.institutions.values():
            for source_id in institution.policy_source_ids:
                if source_id not in self.packet.sources:
                    errors.append(f"{institution.id}: missing policy source {source_id}")
            for fact_id in institution.notice_fact_ids:
                if fact_id not in self.facts:
                    errors.append(f"{institution.id}: missing notice fact {fact_id}")
            for actor_id in institution.supervision_actor_ids:
                if actor_id not in self.actor_nodes:
                    errors.append(f"{institution.id}: missing supervisory actor {actor_id}")
            for pattern_id in institution.pattern_ids:
                if pattern_id not in self.patterns:
                    errors.append(f"{institution.id}: missing pattern {pattern_id}")

        for actor in self.actor_nodes.values():
            if actor.entity_id and actor.entity_id not in self.institutions:
                errors.append(f"{actor.id}: missing institution {actor.entity_id}")
            for source_id in actor.source_ids:
                if source_id not in self.packet.sources:
                    errors.append(f"{actor.id}: missing source {source_id}")
            if actor.unknown_identity and not actor.identity_discovery_target_ids:
                errors.append(
                    f"{actor.id}: unknown actor requires identity discovery target"
                )
            for target_id in actor.identity_discovery_target_ids:
                if target_id not in self.packet.discovery_targets:
                    errors.append(f"{actor.id}: missing discovery target {target_id}")

        for event in self.event_nodes.values():
            for actor_id in event.actor_ids:
                if actor_id not in self.actor_nodes:
                    errors.append(f"{event.id}: missing actor {actor_id}")
            for fact_id in event.fact_ids:
                if fact_id not in self.facts:
                    errors.append(f"{event.id}: missing fact {fact_id}")
            for source_id in event.source_ids:
                if source_id not in self.packet.sources:
                    errors.append(f"{event.id}: missing source {source_id}")
            for harm_id in event.harm_ids:
                if harm_id not in self.damage_records:
                    errors.append(f"{event.id}: missing damage {harm_id}")
            for incident_id in event.incident_ids:
                if incident_id not in self.incidents:
                    errors.append(f"{event.id}: missing incident {incident_id}")

        for pattern in self.patterns.values():
            for event_id in pattern.event_ids:
                if event_id not in self.event_nodes:
                    errors.append(f"{pattern.id}: missing event {event_id}")
            for actor_id in pattern.actor_ids:
                if actor_id not in self.actor_nodes:
                    errors.append(f"{pattern.id}: missing actor {actor_id}")
            for source_id in pattern.source_ids:
                if source_id not in self.packet.sources:
                    errors.append(f"{pattern.id}: missing source {source_id}")
            for allegation_id in pattern.allegation_ids:
                if allegation_id not in self.packet.allegations:
                    errors.append(f"{pattern.id}: missing allegation {allegation_id}")
            if pattern.state in {PatternState.SUPPORTED, PatternState.ESTABLISHED} and len(set(pattern.event_ids)) < 2:
                errors.append(
                    f"{pattern.id}: supported pattern requires at least two events"
                )
            if pattern.state is PatternState.ESTABLISHED and len(set(pattern.source_ids)) < 2:
                errors.append(
                    f"{pattern.id}: established pattern requires at least two sources"
                )

        for allegation_id, allegation in self.packet.allegations.items():
            link = self.allegation_links.get(allegation_id)
            if link is None:
                errors.append(f"{allegation_id}: missing full graph allegation link")
                continue
            if not link.fact_ids:
                errors.append(f"{allegation_id}: no factual propositions linked")
            if not link.duty_or_prohibition:
                errors.append(f"{allegation_id}: no duty/prohibition mapped")
            for fact_id in (
                link.fact_ids + link.knowledge_fact_ids + link.mental_state_fact_ids
            ):
                if fact_id not in self.facts:
                    errors.append(f"{allegation_id}: missing fact {fact_id}")
            for entity_id in link.entity_ids:
                if entity_id not in self.institutions:
                    errors.append(f"{allegation_id}: missing institution {entity_id}")
            for pattern_id in link.pattern_ids:
                if pattern_id not in self.patterns:
                    errors.append(f"{allegation_id}: missing pattern {pattern_id}")
            for defense_id in link.defense_ids:
                defense = self.defense_theories.get(defense_id)
                if defense is None:
                    errors.append(f"{allegation_id}: missing defense {defense_id}")
                elif defense.allegation_id != allegation_id:
                    errors.append(
                        f"{allegation_id}: defense {defense_id} belongs to "
                        f"{defense.allegation_id}"
                    )
            for contradiction_id in link.contradiction_ids:
                if contradiction_id not in self.packet.contradictions:
                    errors.append(
                        f"{allegation_id}: missing contradiction {contradiction_id}"
                    )
            for path_id in link.accountability_path_ids:
                path = self.accountability_paths.get(path_id)
                if path is None:
                    errors.append(
                        f"{allegation_id}: missing accountability path {path_id}"
                    )
                elif path.allegation_id != allegation_id:
                    errors.append(
                        f"{allegation_id}: accountability path {path_id} belongs to "
                        f"{path.allegation_id}"
                    )
            if allegation.mental_state_required and not (
                allegation.mental_state_source_ids or link.mental_state_fact_ids
            ):
                errors.append(
                    f"{allegation_id}: mental state required without evidence"
                )

        for defense in self.defense_theories.values():
            if defense.allegation_id not in self.packet.allegations:
                errors.append(
                    f"{defense.id}: missing allegation {defense.allegation_id}"
                )
            for fact_id in defense.supporting_fact_ids + defense.rebuttal_fact_ids:
                if fact_id not in self.facts:
                    errors.append(f"{defense.id}: missing fact {fact_id}")

        for damage in self.damage_records.values():
            for event_id in damage.cause_event_ids:
                if event_id not in self.event_nodes:
                    errors.append(f"{damage.id}: missing event {event_id}")
            for source_id in damage.source_ids:
                if source_id not in self.packet.sources:
                    errors.append(f"{damage.id}: missing source {source_id}")

        for remedy in self.remedy_paths.values():
            for allegation_id in remedy.allegation_ids:
                if allegation_id not in self.packet.allegations:
                    errors.append(
                        f"{remedy.id}: missing allegation {allegation_id}"
                    )

        for path in self.accountability_paths.values():
            if path.allegation_id not in self.packet.allegations:
                errors.append(f"{path.id}: missing allegation {path.allegation_id}")
            for remedy_id in path.remedy_ids:
                if remedy_id not in self.remedy_paths:
                    errors.append(f"{path.id}: missing remedy {remedy_id}")

        for contradiction_id, assessment in self.contradiction_assessments.items():
            if contradiction_id not in self.packet.contradictions:
                errors.append(
                    f"{contradiction_id}: assessment has no contradiction object"
                )
            for target_id in assessment.discovery_target_ids:
                if target_id not in self.packet.discovery_targets:
                    errors.append(
                        f"{contradiction_id}: missing discovery target {target_id}"
                    )

        return list(dict.fromkeys(errors))

    def promotion_for(self, allegation_id: str) -> PromotionState:
        allegation = self.packet.allegations[allegation_id]
        base = promote(allegation, self.packet.sources)
        if _PROMOTION_ORDER[base] < _PROMOTION_ORDER[PromotionState.PLEADING_READY]:
            return base

        link = self.allegation_links.get(allegation_id)
        if link is None or not link.fact_ids or not link.duty_or_prohibition:
            return PromotionState.HARDENED
        if link.defense_ids and not all(
            self.defense_theories.get(defense_id)
            and self.defense_theories[defense_id].rebuttal_fact_ids
            for defense_id in link.defense_ids
        ):
            return PromotionState.DEFENSE_TESTED

        ready_paths = [
            self.accountability_paths[path_id]
            for path_id in link.accountability_path_ids
            if path_id in self.accountability_paths
            and self.accountability_paths[path_id].ready
        ]
        if not ready_paths:
            return PromotionState.PLEADING_READY

        state = PromotionState.REFERRAL_READY
        if allegation.missing_evidence_ids:
            return state
        if not all(element.satisfied for element in allegation.elements):
            return state

        unresolved_targets = [
            target
            for target in self.packet.discovery_targets.values()
            if target.allegation_id == allegation_id
            and target.priority in {"P0", "P1"}
            and target.id not in self.resolved_discovery_target_ids
        ]
        if unresolved_targets:
            return state

        for contradiction_id in link.contradiction_ids:
            assessment = self.contradiction_assessments.get(contradiction_id)
            if assessment is None or assessment.state in {
                ContradictionState.OPEN,
                ContradictionState.PARTIALLY_RECONCILED,
            }:
                return state

        return PromotionState.TRIAL_READY

    def pressure_vector(self, allegation_id: str) -> dict[str, Any]:
        allegation = self.packet.allegations[allegation_id]
        primary = [
            self.packet.sources[source_id]
            for source_id in allegation.primary_source_ids
            if source_id in self.packet.sources
        ]
        source_types = {
            source.source_type
            for source in (
                self.packet.sources[source_id]
                for source_id in (
                    allegation.primary_source_ids
                    + allegation.corroborating_source_ids
                )
                if source_id in self.packet.sources
            )
        }
        element_count = len(allegation.elements)
        element_coverage = (
            sum(element.satisfied for element in allegation.elements) / element_count
            if element_count
            else 0.0
        )
        link = self.allegation_links.get(allegation_id)
        return {
            "proof_strength": max(
                (proof_strength(source.proof_state) for source in primary),
                default=0,
            ),
            "element_coverage": round(element_coverage, 4),
            "source_depth": len(
                set(
                    allegation.primary_source_ids
                    + allegation.corroborating_source_ids
                )
            ),
            "source_type_diversity": len(source_types),
            "contradiction_count": len(link.contradiction_ids) if link else 0,
            "damage_count": len(allegation.harm_ids),
            "open_discovery_count": sum(
                target.allegation_id == allegation_id
                and target.id not in self.resolved_discovery_target_ids
                for target in self.packet.discovery_targets.values()
            ),
            "defense_tested": bool(
                allegation.defenses
                and allegation.rebuttals
                and link
                and link.defense_ids
            ),
            "accountability_path_count": (
                len(link.accountability_path_ids) if link else 0
            ),
            "promotion_state": self.promotion_for(allegation_id).value,
        }

    def orphan_report(self) -> dict[str, list[str]]:
        used_sources: set[str] = set()
        used_facts: set[str] = set()
        used_actors: set[str] = set()
        used_events: set[str] = set()
        used_defenses: set[str] = set()
        used_damages: set[str] = set()
        used_discovery: set[str] = set()
        used_accountability: set[str] = set()

        for fact in self.facts.values():
            used_sources.update(fact.source_ids)
            used_actors.update(fact.actor_ids)
            used_events.update(fact.event_ids)
        for actor in self.actor_nodes.values():
            used_sources.update(actor.source_ids)
            used_discovery.update(actor.identity_discovery_target_ids)
        for event in self.event_nodes.values():
            used_sources.update(event.source_ids)
            used_facts.update(event.fact_ids)
            used_actors.update(event.actor_ids)
            used_damages.update(event.harm_ids)
        for allegation in self.packet.allegations.values():
            used_sources.update(allegation.primary_source_ids)
            used_sources.update(allegation.corroborating_source_ids)
            used_sources.update(allegation.contradictory_source_ids)
            used_sources.update(allegation.mental_state_source_ids)
            used_actors.update(allegation.actor_ids)
            used_events.update(allegation.event_ids)
            used_damages.update(allegation.harm_ids)
            used_discovery.update(allegation.discovery_target_ids)
        for link in self.allegation_links.values():
            used_facts.update(link.fact_ids)
            used_facts.update(link.knowledge_fact_ids)
            used_facts.update(link.mental_state_fact_ids)
            used_defenses.update(link.defense_ids)
            used_accountability.update(link.accountability_path_ids)
        for defense in self.defense_theories.values():
            used_facts.update(defense.supporting_fact_ids)
            used_facts.update(defense.rebuttal_fact_ids)
        for damage in self.damage_records.values():
            used_events.update(damage.cause_event_ids)
            used_sources.update(damage.source_ids)
        for assessment in self.contradiction_assessments.values():
            used_discovery.update(assessment.discovery_target_ids)

        return {
            "sources": sorted(set(self.packet.sources) - used_sources),
            "facts": sorted(set(self.facts) - used_facts),
            "actors": sorted(set(self.actor_nodes) - used_actors),
            "events": sorted(set(self.event_nodes) - used_events),
            "defenses": sorted(set(self.defense_theories) - used_defenses),
            "damages": sorted(set(self.damage_records) - used_damages),
            "discovery_targets": sorted(
                set(self.packet.discovery_targets) - used_discovery
            ),
            "accountability_paths": sorted(
                set(self.accountability_paths) - used_accountability
            ),
        }

    def ledgers(self) -> dict[str, Any]:
        return {
            "master_fact_ledger": [
                _serialize(item) for item in self.facts.values()
            ],
            "master_event_timeline": [
                _serialize(item) for item in self.event_nodes.values()
            ],
            "actor_index": [
                _serialize(item) for item in self.actor_nodes.values()
            ],
            "allegation_ledger": [
                _serialize(item) for item in self.packet.allegations.values()
            ],
            "contradiction_matrix": [
                _serialize(item) for item in self.packet.contradictions.values()
            ],
            "damages_ledger": [
                _serialize(item) for item in self.damage_records.values()
            ],
            "discovery_matrix": [
                _serialize(item) for item in self.packet.discovery_targets.values()
            ],
            "defense_matrix": [
                _serialize(item) for item in self.defense_theories.values()
            ],
            "accountability_map": [
                _serialize(item) for item in self.accountability_paths.values()
            ],
        }


def compile_case_graph(graph: CaseGraph) -> dict[str, Any]:
    """Validate the entire graph before any derived promotion state is mutated."""

    errors = graph.validate()
    if errors:
        raise ValueError("case graph invalid: " + "; ".join(errors))

    result = compile_case(graph.packet)

    promotion_report: dict[str, str] = {}
    pressure_map: dict[str, dict[str, Any]] = {}
    for allegation_id, allegation in graph.packet.allegations.items():
        allegation.promotion_state = graph.promotion_for(allegation_id)
        promotion_report[allegation_id] = allegation.promotion_state.value
        pressure_map[allegation_id] = graph.pressure_vector(allegation_id)
        result["allegations"][allegation_id][
            "promotion_state"
        ] = allegation.promotion_state.value

    result["graph_contract_id"] = GRAPH_CONTRACT_ID
    result["graph_contract_version"] = GRAPH_CONTRACT_VERSION
    result["facts"] = {key: _serialize(value) for key, value in graph.facts.items()}
    result["typed_actors"] = {
        key: _serialize(value) for key, value in graph.actor_nodes.items()
    }
    result["typed_events"] = {
        key: _serialize(value) for key, value in graph.event_nodes.items()
    }
    result["defense_theories"] = {
        key: _serialize(value) for key, value in graph.defense_theories.items()
    }
    result["damage_records"] = {
        key: _serialize(value) for key, value in graph.damage_records.items()
    }
    result["remedy_paths"] = {
        key: _serialize(value) for key, value in graph.remedy_paths.items()
    }
    result["accountability_paths"] = {
        key: _serialize(value) for key, value in graph.accountability_paths.items()
    }
    result["allegation_links"] = {
        key: _serialize(value) for key, value in graph.allegation_links.items()
    }
    result["contradiction_assessments"] = {
        key: _serialize(value)
        for key, value in graph.contradiction_assessments.items()
    }
    result["resolved_discovery_target_ids"] = sorted(
        graph.resolved_discovery_target_ids
    )
    result["promotion_report"] = promotion_report
    result["pressure_map"] = pressure_map
    result["orphans"] = graph.orphan_report()
    result["ledgers"] = graph.ledgers()
    result["metrics"].update(
        {
            "facts": len(graph.facts),
            "defenses": len(graph.defense_theories),
            "damages": len(graph.damage_records),
            "accountability_paths": len(graph.accountability_paths),
            "referral_ready": sum(
                state in {
                    PromotionState.REFERRAL_READY.value,
                    PromotionState.TRIAL_READY.value,
                }
                for state in promotion_report.values()
            ),
            "trial_ready": sum(
                state == PromotionState.TRIAL_READY.value
                for state in promotion_report.values()
            ),
        }
    )
    return result
