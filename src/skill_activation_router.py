"""Skill activation router: rank declared skills for a mission turn.

The router never loads a skill, never reads a skill body, and never grants
authority. It ranks what the caller *declared* is available, so the caller
decides what to load. This is routing, not permission.

Scope boundary: this module cannot know whether a skill body actually exists
on disk, whether a connector is reachable, or whether the mission is
authorized. Those are the caller's checks. Claiming otherwise would make the
router a liar.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

SCHEMA = "glaciereq.apex.skill-activation.v1"

# Tiered vocabulary. Ordered, never collapsed: a tier-3 skill is never
# silently upgraded to tier 1 because its description used the word "always".
TIERS: tuple[str, ...] = ("always", "situational", "conditional")


class SkillActivationError(ValueError):
    """Malformed catalog or mission declaration."""


@dataclass(frozen=True)
class SkillDeclaration:
    """One declared skill as the catalog reports it.

    ``declared_triggers`` and ``declared_procedure`` are claims made by the
    catalog, not facts the router verified. They are carried so the caller can
    see what it is acting on.
    """

    name: str
    tier: str
    triggers: tuple[str, ...]
    description: str
    declared_procedure: bool

    @property
    def is_real(self) -> bool:
        """A skill is real when it states both when to use it and how."""
        return bool(self.triggers) and self.declared_procedure

    def missing_parts(self) -> tuple[str, ...]:
        """Which half of the skill contract is absent."""
        absent: list[str] = []
        if not self.triggers:
            absent.append("trigger")
        if not self.declared_procedure:
            absent.append("procedure")
        return tuple(absent)


@dataclass(frozen=True)
class SkillDecision:
    """One routing decision, with the reason it was made."""

    name: str
    tier: str
    matched_triggers: tuple[str, ...]
    reason: str
    declared_procedure: bool

    @property
    def load_first(self) -> bool:
        return self.tier == "always"


def _normalize(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _as_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SkillActivationError(f"{field} must be a non-empty string")
    return value.strip()


def _as_tier(value: object) -> str:
    tier = _as_text(value, "tier").lower()
    if tier not in TIERS:
        raise SkillActivationError(f"unknown tier: {tier}")
    return tier


def _as_triggers(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raw: Sequence[object] = [value]
    elif isinstance(value, (list, tuple)):
        raw = value
    else:
        raise SkillActivationError("triggers must be a string or sequence")
    out: list[str] = []
    for item in raw:
        text = _as_text(item, "trigger")
        if text not in out:
            out.append(text)
    return tuple(out)


def declare_skill(raw: Mapping[str, object]) -> SkillDeclaration:
    """Validate one catalog record into a declaration.

    Fails closed: a record missing a name or tier is an error, not a default.
    """
    if not isinstance(raw, Mapping):
        raise SkillActivationError("skill declaration must be a mapping")
    name = _as_text(raw.get("name"), "name")
    tier = _as_tier(raw.get("tier"))
    triggers = _as_triggers(raw.get("triggers"))
    description = raw.get("description", "")
    if description is None:
        description = ""
    if not isinstance(description, str):
        raise SkillActivationError("description must be a string")
    procedure = raw.get("declared_procedure", False)
    if not isinstance(procedure, bool):
        raise SkillActivationError("declared_procedure must be boolean")
    return SkillDeclaration(
        name=name,
        tier=tier,
        triggers=triggers,
        description=description.strip(),
        declared_procedure=procedure,
    )


def declare_catalog(records: Iterable[Mapping[str, object]]) -> tuple[SkillDeclaration, ...]:
    """Validate a whole catalog. Duplicate names are rejected, not merged."""
    declared: list[SkillDeclaration] = []
    seen: set[str] = set()
    for record in records:
        skill = declare_skill(record)
        if skill.name in seen:
            raise SkillActivationError(f"duplicate skill: {skill.name}")
        seen.add(skill.name)
        declared.append(skill)
    return tuple(declared)


def _match_triggers(
    skill: SkillDeclaration, text: str, *, whole_word: bool = True
) -> tuple[str, ...]:
    """Return the skill's triggers that appear in the mission text.

    A trigger that is only a generic prose word (for example ``api`` or
    ``code``) matches as a substring; a short or underscore-bearing trigger is
    matched on word boundaries so ``adaptyv`` does not fire inside an unrelated
    token.
    """
    hits: list[str] = []
    for trigger in skill.triggers:
        needle = trigger.lower()
        if not needle:
            continue
        if not whole_word and len(needle) >= 4 and " " not in needle:
            if needle in text:
                hits.append(trigger)
            continue
        pattern = r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])"
        if re.search(pattern, text):
            hits.append(trigger)
    return tuple(hits)


def route_skill_activation(
    *,
    catalog: Iterable[Mapping[str, object]],
    mission_brief: str,
    max_skills: int = 5,
    text: str | None = None,
) -> dict[str, object]:
    """Rank declared skills for one mission turn.

    ``catalog`` is the caller's declaration of what exists. ``mission_brief``
    is the turn's task text. The result is a routing receipt: what matched,
    why, and what was left out. It is not proof that any skill was loaded.
    """
    brief = _as_text(mission_brief, "mission_brief")
    if not isinstance(max_skills, int) or isinstance(max_skills, bool):
        raise SkillActivationError("max_skills must be an integer")
    if max_skills < 1:
        raise SkillActivationError("max_skills must be at least 1")

    declared = declare_catalog(catalog)
    haystack = _normalize(text if text is not None else brief)

    decisions: list[SkillDecision] = []
    unrouted: list[SkillDecision] = []
    for skill in declared:
        hits = _match_triggers(skill, haystack)
        if skill.tier == "always":
            decisions.append(
                SkillDecision(
                    name=skill.name,
                    tier=skill.tier,
                    matched_triggers=hits,
                    reason="always-on",
                    declared_procedure=skill.declared_procedure,
                )
            )
        elif hits:
            decisions.append(
                SkillDecision(
                    name=skill.name,
                    tier=skill.tier,
                    matched_triggers=hits,
                    reason="matched:" + ",".join(hits),
                    declared_procedure=skill.declared_procedure,
                )
            )
        elif skill.tier == "conditional":
            unrouted.append(
                SkillDecision(
                    name=skill.name,
                    tier=skill.tier,
                    matched_triggers=(),
                    reason="conditional: no trigger matched",
                    declared_procedure=skill.declared_procedure,
                )
            )

    def sort_key(decision: SkillDecision) -> tuple[int, int, str]:
        tier_rank = TIERS.index(decision.tier)
        return (tier_rank, -len(decision.matched_triggers), decision.name)

    decisions.sort(key=sort_key)
    selected = decisions[:max_skills]
    deferred = decisions[max_skills:]

    skipped = [
        SkillDecision(
            name=skill.name,
            tier=skill.tier,
            matched_triggers=(),
            reason="stub:" + "+".join(skill.missing_parts()),
            declared_procedure=skill.declared_procedure,
        )
        for skill in declared
        if not skill.is_real
    ]

    return {
        "schema": SCHEMA,
        "mission_brief": brief,
        "skills": [decision.__dict__ for decision in selected],
        "deferred": [decision.__dict__ for decision in deferred],
        "unrouted": [decision.__dict__ for decision in unrouted],
        "skipped": [decision.__dict__ for decision in skipped],
        "declared_count": len(declared),
        "routed_count": len(selected),
    }