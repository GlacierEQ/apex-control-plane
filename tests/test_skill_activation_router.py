"""Skill activation router: routing truth, fail-closed validation, tier integrity."""
from __future__ import annotations

import pytest

from src.skill_activation_router import (
    SCHEMA,
    SkillActivationError,
    declare_catalog,
    declare_skill,
    route_skill_activation,
)


def _catalog() -> list[dict]:
    return [
        {
            "name": "dynamic-leverage",
            "tier": "always",
            "triggers": ["USE when any task touches code"],
            "description": "Route task to skill then connector then repo.",
            "declared_procedure": True,
        },
        {
            "name": "macos-health-check",
            "tier": "situational",
            "triggers": ["macos memory pressure", "kernel_task"],
            "description": "Check a Mac for memory pressure and load.",
            "declared_procedure": True,
        },
        {
            "name": "ios-simulator-browser",
            "tier": "conditional",
            "triggers": ["simctl", "swiftui preview"],
            "description": "Mirror an iOS simulator into a browser.",
            "declared_procedure": True,
        },
        {
            "name": "stub-skill",
            "tier": "conditional",
            "triggers": [],
            "description": "No trigger, no procedure.",
            "declared_procedure": False,
        },
    ]


def test_always_tier_is_selected_first():
    result = route_skill_activation(
        catalog=_catalog(),
        mission_brief="my macos has memory pressure and kernel_task is hot",
    )
    assert result["schema"] == SCHEMA
    first = result["skills"][0]
    assert first["name"] == "dynamic-leverage"
    assert first["tier"] == "always"
    assert first["reason"] == "always-on"


def test_matched_trigger_ranks_above_unmatched():
    result = route_skill_activation(
        catalog=_catalog(),
        mission_brief="macos memory pressure, kernel_task at 80 percent",
    )
    names = [s["name"] for s in result["skills"]]
    assert "macos-health-check" in names
    # The conditional skill must either rank below the matched one or be absent.
    if "ios-simulator-browser" in names:
        assert names.index("macos-health-check") < names.index("ios-simulator-browser")


def test_conditional_without_match_is_unrouted_not_selected():
    result = route_skill_activation(
        catalog=_catalog(),
        mission_brief="review the quarterly financial statements",
    )
    selected = [s["name"] for s in result["skills"]]
    unrouted = [s["name"] for s in result["unrouted"]]
    assert "ios-simulator-browser" not in selected
    assert "ios-simulator-browser" in unrouted


def test_stub_skill_is_skipped_and_reported():
    result = route_skill_activation(
        catalog=_catalog(),
        mission_brief="anything at all",
    )
    skipped = [s["name"] for s in result["skipped"]]
    assert "stub-skill" in skipped
    stub = [s for s in result["skipped"] if s["name"] == "stub-skill"][0]
    assert "trigger" in stub["reason"]
    assert "procedure" in stub["reason"]


def test_stub_is_never_selected_even_when_max_skills_is_large():
    result = route_skill_activation(
        catalog=_catalog(),
        mission_brief="macos memory pressure",
        max_skills=50,
    )
    selected = [s["name"] for s in result["skills"]]
    assert "stub-skill" not in selected


def test_max_skills_caps_selection():
    result = route_skill_activation(
        catalog=_catalog(),
        mission_brief="macos memory pressure kernel_task",
        max_skills=1,
    )
    assert len(result["skills"]) == 1
    assert result["skills"][0]["name"] == "dynamic-leverage"


def test_counts_are_consistent():
    catalog = _catalog()
    result = route_skill_activation(
        catalog=catalog,
        mission_brief="macos memory pressure",
    )
    assert result["declared_count"] == len(catalog)
    assert result["routed_count"] == len(result["skills"])
    assert result["declared_count"] >= result["routed_count"] + len(result["deferred"])


def test_mission_brief_must_be_non_empty():
    with pytest.raises(SkillActivationError):
        route_skill_activation(catalog=_catalog(), mission_brief="   ")


def test_max_skills_must_be_positive():
    with pytest.raises(SkillActivationError):
        route_skill_activation(catalog=_catalog(), mission_brief="x", max_skills=0)


def test_unknown_tier_is_rejected():
    bad = _catalog()
    bad[0]["tier"] = "whenever"
    with pytest.raises(SkillActivationError):
        declare_catalog(bad)


def test_duplicate_names_are_rejected():
    catalog = _catalog()
    catalog.append(dict(catalog[0]))
    with pytest.raises(SkillActivationError) as excinfo:
        declare_catalog(catalog)
    assert "duplicate" in str(excinfo.value)


def test_missing_name_is_rejected():
    with pytest.raises(SkillActivationError):
        declare_skill({"tier": "always", "triggers": [], "declared_procedure": True})


def test_declared_procedure_must_be_boolean():
    with pytest.raises(SkillActivationError):
        declare_skill(
            {
                "name": "x",
                "tier": "always",
                "triggers": [],
                "declared_procedure": "yes",
            }
        )


def test_is_real_requires_both_halves():
    real = declare_skill(
        {"name": "a", "tier": "always", "triggers": ["t"], "declared_procedure": True}
    )
    assert real.is_real is True
    assert real.missing_parts() == ()

    half = declare_skill(
        {"name": "b", "tier": "always", "triggers": ["t"], "declared_procedure": False}
    )
    assert half.is_real is False
    assert half.missing_parts() == ("procedure",)


def test_trigger_matching_respects_word_boundaries():
    catalog = [
        {
            "name": "needs-simctl",
            "tier": "situational",
            "triggers": ["simctl"],
            "description": "d",
            "declared_procedure": True,
        }
    ]
    miss = route_skill_activation(catalog=catalog, mission_brief="simctlx is not it")
    assert miss["skills"] == []
    hit = route_skill_activation(catalog=catalog, mission_brief="run xcrun simctl list")
    assert [s["name"] for s in hit["skills"]] == ["needs-simctl"]


def test_text_override_supplies_matching_haystack():
    result = route_skill_activation(
        catalog=_catalog(),
        mission_brief="short brief",
        text="long surrounding transcript mentioning macos memory pressure",
    )
    assert "macos-health-check" in [s["name"] for s in result["skills"]]


def test_empty_catalog_yields_no_skills():
    result = route_skill_activation(catalog=[], mission_brief="anything")
    assert result["skills"] == []
    assert result["declared_count"] == 0


def test_duplicate_triggers_are_collapsed():
    skill = declare_skill(
        {
            "name": "a",
            "tier": "situational",
            "triggers": ["dup", "dup", "dup"],
            "declared_procedure": True,
        }
    )
    assert skill.triggers == ("dup",)