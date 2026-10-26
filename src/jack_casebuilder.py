from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Mapping


class ProofState(str, Enum):
    VERIFIED = "verified"
    CORROBORATED = "corroborated"
    SUPPORTED = "supported"
    REPORTED = "reported"
    INFERRED = "inferred"
    HYPOTHESIS = "hypothesis"
    CONTRADICTED = "contradicted"
    DISPROVEN = "disproven"
    QUARANTINED = "quarantined"


class ElementState(str, Enum):
    PROVEN = "proven"
    SUPPORTED = "supported"
    DISPUTED = "disputed"
    MISSING = "missing"


class PromotionState(str, Enum):
    RAW = "raw"
    STRUCTURED = "structured"
    SOURCED = "sourced"
    CORROBORATED = "corroborated"
    ELEMENT_MAPPED = "element_mapped"
    DEFENSE_TESTED = "defense_tested"
    HARDENED = "hardened"
    PLEADING_READY = "pleading_ready"
    REFERRAL_READY = "referral_ready"
    TRIAL_READY = "trial_ready"


@dataclass(frozen=True, slots=True)
class SourceRef:
    source_id: str
    uri: str
    source_grade: int
    locator: str | None = None
    digest: str | None = None

    def validate(self) -> None:
        if not self.source_id.strip() or not self.uri.strip():
            raise ValueError("source_id and uri are required")
        if not 1 <= self.source_grade <= 10:
            raise ValueError("source_grade must be 1..10")
        if self.digest is not None:
            if len(self.digest) != 64 or any(c not in "0123456789abcdef" for c in self.digest):
                raise ValueError("digest must be lowercase SHA-256")


@dataclass(frozen=True, slots=True)
class FactNode:
    fact_id: str
    proposition: str
    proof_state: ProofState
    source_ids: tuple[str, ...]
    event_ids: tuple[str, ...] = ()
    actor_ids: tuple[str, ...] = ()
    contradiction_ids: tuple[str, ...] = ()
    harm_ids: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.fact_id.strip() or not self.proposition.strip():
            raise ValueError("fact_id and proposition are required")
        if not self.source_ids:
            raise ValueError("fact requires at least one source")


@dataclass(frozen=True, slots=True)
class ActorNode:
    actor_id: str
    canonical_name: str
    actor_class: str
    organization: str | None = None
    identity_status: str = "identified"
    aliases: tuple[str, ...] = ()
    discovery_targets: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.actor_id.strip() or not self.canonical_name.strip():
            raise ValueError("actor_id and canonical_name are required")
        if self.identity_status not in {"identified", "partial", "doe"}:
            raise ValueError("identity_status must be identified, partial, or doe")


@dataclass(frozen=True, slots=True)
class ElementMap:
    element_id: str
    requirement: str
    state: ElementState
    fact_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    gap: str | None = None

    def validate(self) -> None:
        if not self.element_id.strip() or not self.requirement.strip():
            raise ValueError("element_id and requirement are required")
        if self.state is ElementState.MISSING and not self.gap:
            raise ValueError("missing element must name the proof gap")


@dataclass(frozen=True, slots=True)
class DefenseNode:
    defense_id: str
    title: str
    supporting_fact_ids: tuple[str, ...] = ()
    rebuttal_fact_ids: tuple[str, ...] = ()
    unresolved_risk: str | None = None


@dataclass(frozen=True, slots=True)
class AllegationNode:
    allegation_id: str
    title: str
    actor_ids: tuple[str, ...]
    event_ids: tuple[str, ...]
    factual_predicate: str
    legal_theory: str
    elements: tuple[ElementMap, ...]
    source_ids: tuple[str, ...]
    harm_ids: tuple[str, ...] = ()
    contradiction_ids: tuple[str, ...] = ()
    mental_state_fact_ids: tuple[str, ...] = ()
    defenses: tuple[DefenseNode, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    discovery_targets: tuple[str, ...] = ()
    remedies: tuple[str, ...] = ()
    promotion_state: PromotionState = PromotionState.STRUCTURED
    proof_score: int = 0
    legal_score: int = 0
    causation_score: int = 0
    harm_score: int = 0
    defense_risk: int = 0
    immunity_risk: int = 0
    jurisdiction_risk: int = 0

    def validate(self) -> None:
        if not self.allegation_id.strip() or not self.title.strip():
            raise ValueError("allegation_id and title are required")
        if not self.actor_ids:
            raise ValueError("allegation requires an actor or Doe actor")
        if not self.event_ids:
            raise ValueError("allegation requires an event")
        if not self.elements:
            raise ValueError("allegation requires element mapping")
        for element in self.elements:
            element.validate()
        for value in (
            self.proof_score,
            self.legal_score,
            self.causation_score,
            self.harm_score,
            self.defense_risk,
            self.immunity_risk,
            self.jurisdiction_risk,
        ):
            if not 0 <= value <= 5:
                raise ValueError("scores must be 0..5")

    @property
    def impact_score(self) -> int:
        return (
            self.proof_score * 4
            + self.legal_score * 3
            + self.causation_score * 3
            + self.harm_score * 3
            - self.defense_risk * 3
            - self.immunity_risk * 4
            - self.jurisdiction_risk * 4
        )

    def blockers(self) -> tuple[str, ...]:
        out: list[str] = []
        if not self.source_ids:
            out.append("no_sources")
        if any(e.state in {ElementState.MISSING, ElementState.DISPUTED} for e in self.elements):
            out.append("elements_missing_or_disputed")
        if self.promotion_state in {
            PromotionState.DEFENSE_TESTED,
            PromotionState.HARDENED,
            PromotionState.PLEADING_READY,
            PromotionState.REFERRAL_READY,
            PromotionState.TRIAL_READY,
        } and not self.defenses:
            out.append("defense_test_missing")
        if self.promotion_state in {
            PromotionState.PLEADING_READY,
            PromotionState.REFERRAL_READY,
            PromotionState.TRIAL_READY,
        } and (self.immunity_risk >= 4 or self.jurisdiction_risk >= 4):
            out.append("high_immunity_or_jurisdiction_risk")
        return tuple(out)


@dataclass(slots=True)
class JackCaseGraph:
    case_id: str
    sources: dict[str, SourceRef] = field(default_factory=dict)
    facts: dict[str, FactNode] = field(default_factory=dict)
    actors: dict[str, ActorNode] = field(default_factory=dict)
    events: dict[str, Mapping[str, Any]] = field(default_factory=dict)
    harms: dict[str, Mapping[str, Any]] = field(default_factory=dict)
    contradictions: dict[str, Mapping[str, Any]] = field(default_factory=dict)
    discovery_targets: dict[str, Mapping[str, Any]] = field(default_factory=dict)
    allegations: dict[str, AllegationNode] = field(default_factory=dict)

    def _put(self, store: dict[str, Any], key: str, value: Any) -> None:
        if not key.strip():
            raise ValueError("stable id is required")
        old = store.get(key)
        if old is not None and old != value:
            raise ValueError(f"stable id collision: {key}")
        store[key] = value

    def add_source(self, source: SourceRef) -> None:
        source.validate()
        self._put(self.sources, source.source_id, source)

    def add_fact(self, fact: FactNode) -> None:
        fact.validate()
        missing = sorted(set(fact.source_ids) - self.sources.keys())
        if missing:
            raise ValueError(f"fact has unresolved sources: {missing}")
        self._put(self.facts, fact.fact_id, fact)

    def add_actor(self, actor: ActorNode) -> None:
        actor.validate()
        self._put(self.actors, actor.actor_id, actor)

    def add_event(self, event_id: str, event: Mapping[str, Any]) -> None:
        self._put(self.events, event_id, dict(event))

    def add_harm(self, harm_id: str, harm: Mapping[str, Any]) -> None:
        self._put(self.harms, harm_id, dict(harm))

    def add_contradiction(self, contradiction_id: str, item: Mapping[str, Any]) -> None:
        self._put(self.contradictions, contradiction_id, dict(item))

    def add_discovery_target(self, target_id: str, item: Mapping[str, Any]) -> None:
        if not item.get("record") or not item.get("controlled_by"):
            raise ValueError("discovery target requires record and controlled_by")
        self._put(self.discovery_targets, target_id, dict(item))

    def add_allegation(self, allegation: AllegationNode) -> None:
        allegation.validate()
        unresolved = {
            "actors": sorted(set(allegation.actor_ids) - self.actors.keys()),
            "events": sorted(set(allegation.event_ids) - self.events.keys()),
            "sources": sorted(set(allegation.source_ids) - self.sources.keys()),
            "harms": sorted(set(allegation.harm_ids) - self.harms.keys()),
        }
        if any(unresolved.values()):
            raise ValueError("unresolved allegation references: " + json.dumps(unresolved, sort_keys=True))
        self._put(self.allegations, allegation.allegation_id, allegation)

    def pressure_map(self) -> list[dict[str, Any]]:
        ranked = sorted(
            self.allegations.values(),
            key=lambda item: (item.impact_score, item.proof_score, item.allegation_id),
            reverse=True,
        )
        return [
            {
                "allegation_id": item.allegation_id,
                "title": item.title,
                "impact_score": item.impact_score,
                "promotion_state": item.promotion_state.value,
                "blockers": list(item.blockers()),
                "missing_evidence": list(item.missing_evidence),
                "discovery_targets": list(item.discovery_targets),
            }
            for item in ranked
        ]

    def validate_promotions(self) -> None:
        for allegation in self.allegations.values():
            blockers = allegation.blockers()
            if blockers:
                raise ValueError(f"{allegation.allegation_id} promotion blocked: {','.join(blockers)}")

    def payload(self) -> dict[str, Any]:
        def encode(value: Any) -> Any:
            if isinstance(value, Enum):
                return value.value
            if hasattr(value, "__dataclass_fields__"):
                return {key: encode(val) for key, val in asdict(value).items()}
            if isinstance(value, Mapping):
                return {str(key): encode(val) for key, val in value.items()}
            if isinstance(value, (tuple, list)):
                return [encode(val) for val in value]
            return value

        return {
            "case_id": self.case_id,
            "sources": encode(self.sources),
            "facts": encode(self.facts),
            "actors": encode(self.actors),
            "events": encode(self.events),
            "harms": encode(self.harms),
            "contradictions": encode(self.contradictions),
            "discovery_targets": encode(self.discovery_targets),
            "allegations": encode(self.allegations),
            "pressure_map": self.pressure_map(),
        }

    def receipt(self) -> dict[str, Any]:
        payload = self.payload()
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return {
            "case_id": self.case_id,
            "sha256": sha256(canonical.encode("utf-8")).hexdigest(),
            "counts": {
                "sources": len(self.sources),
                "facts": len(self.facts),
                "actors": len(self.actors),
                "events": len(self.events),
                "harms": len(self.harms),
                "contradictions": len(self.contradictions),
                "discovery_targets": len(self.discovery_targets),
                "allegations": len(self.allegations),
            },
        }
