#!/usr/bin/env python3
"""Fail when active APEX control surfaces regress into promoted authority or minimization."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

ACTIVE_TEXT = [
    "AGENT_SYSTEM_PROMPT.md",
    "STATE.md",
    "README.md",
    "src/control_plane.py",
    "src/auto_boot.py",
    "src/notion_continuity_gate.py",
]

FORBIDDEN_ACTIVE_SEMANTICS = [
    "canonical owner",
    "canonical_owner",
    "canonical notion",
    "canonical_notion_pages",
    "canonical_mem_manifest",
    "smallest compatible extension",
    "smallest vertical slice",
    "smallest possible version",
    "mvp as product ceiling",
    "minimal diff as scope objective",
    "unresolved canonical conflicts block",
    "one controlling canonical",
]

REQUIRED_PROMPT = [
    "Human project-direction authority: Casey Barton",
    "MAXIMUM_COHERENT_ADVANCE",
    "operator_pressure_up -> evidence_depth_up + execution_depth_up + integration_depth_up",
    "Smallness itself is never the objective.",
]

REQUIRED_STATE = [
    "Human project-direction authority: Casey Barton",
    "MAXIMUM_COHERENT_ADVANCE",
    "TARGET_CAPABILITY",
    "IMPLEMENTED_CAPABILITY",
    "VERIFIED_CAPABILITY",
    "PROJECTION",
]


def _read(path: str) -> str:
    target = ROOT / path
    if not target.is_file():
        raise RuntimeError(f"missing APEX control surface: {path}")
    return target.read_text(encoding="utf-8")


def _json(path: str) -> dict:
    value = json.loads(_read(path))
    if not isinstance(value, dict):
        raise RuntimeError(f"APEX machine surface must be an object: {path}")
    return value


def validate() -> list[str]:
    errors: list[str] = []

    authority = _json("config/apex_authority.json")
    human = authority.get("human_project_direction_authority") or {}
    if authority.get("mode") != "APEX":
        errors.append("config/apex_authority.json: mode must be APEX")
    if authority.get("execution_law") != "MAXIMUM_COHERENT_ADVANCE":
        errors.append("config/apex_authority.json: execution law drift")
    if human.get("name") != "Casey Barton":
        errors.append("config/apex_authority.json: Casey authority missing")
    if human.get("role") != "SOLE_HUMAN_PROJECT_DIRECTION_AUTHORITY":
        errors.append("config/apex_authority.json: human authority role drift")
    rules = authority.get("authority_rules") or {}
    if rules.get("projection_may_never_overwrite_source") is not True:
        errors.append("config/apex_authority.json: projection/source invariant missing")
    if rules.get("assistant_generated_constraints_are_not_operator_intent_by_default") is not True:
        errors.append("config/apex_authority.json: intent-provenance invariant missing")
    if rules.get("canonical_authority_semantics_forbidden") is not True:
        errors.append("config/apex_authority.json: promoted-authority prohibition missing")

    manifest = _json("config/casey_auto_boot_manifest.json")
    if manifest.get("mode") != "APEX":
        errors.append("config/casey_auto_boot_manifest.json: mode must be APEX")
    if manifest.get("human_project_direction_authority") != "Casey Barton":
        errors.append("config/casey_auto_boot_manifest.json: Casey authority missing")
    if manifest.get("execution_law") != "MAXIMUM_COHERENT_ADVANCE":
        errors.append("config/casey_auto_boot_manifest.json: execution law drift")
    if "canonical_mem_manifest" in manifest:
        errors.append("config/casey_auto_boot_manifest.json: promoted manifest key reintroduced")
    prime = manifest.get("prime_directive") or {}
    if prime.get("forbids_scope_minimization_as_default") is not True:
        errors.append("config/casey_auto_boot_manifest.json: anti-minimization boot invariant missing")
    if prime.get("requires_operator_intent_preservation") is not True:
        errors.append("config/casey_auto_boot_manifest.json: operator-intent boot invariant missing")

    continuity = _json("config/notion_continuity_policy.json")
    if continuity.get("mode") != "APEX":
        errors.append("config/notion_continuity_policy.json: mode must be APEX")
    if continuity.get("human_project_direction_authority") != "Casey Barton":
        errors.append("config/notion_continuity_policy.json: Casey authority missing")
    if continuity.get("execution_law") != "MAXIMUM_COHERENT_ADVANCE":
        errors.append("config/notion_continuity_policy.json: execution law drift")
    if "canonical_notion_pages" in continuity:
        errors.append("config/notion_continuity_policy.json: promoted Notion page key reintroduced")
    laws = continuity.get("laws") or []
    for law in (
        "CASEY AUTHORITY PRECEDES STORED PROJECTIONS",
        "MAXIMUM COHERENT ADVANCE",
    ):
        if law not in laws:
            errors.append(f"config/notion_continuity_policy.json: missing law {law}")

    for path in ACTIVE_TEXT:
        lower = _read(path).lower()
        for phrase in FORBIDDEN_ACTIVE_SEMANTICS:
            if phrase in lower:
                errors.append(f"{path}: forbidden active semantic reintroduced: {phrase}")

    prompt = _read("AGENT_SYSTEM_PROMPT.md")
    for phrase in REQUIRED_PROMPT:
        if phrase not in prompt:
            errors.append(f"AGENT_SYSTEM_PROMPT.md: missing strengthening semantic: {phrase}")

    state = _read("STATE.md")
    for phrase in REQUIRED_STATE:
        if phrase not in state:
            errors.append(f"STATE.md: missing APEX state semantic: {phrase}")

    authority_doc = _read("APEX_AUTHORITY.md")
    for phrase in (
        "Casey Barton is the sole human authority for GlacierEQ/APEX project direction",
        "canonical is not an authority class in APEX",
        "maximum coherent advance",
        "Smallness itself is never the objective.",
    ):
        if phrase.lower() not in authority_doc.lower():
            errors.append(f"APEX_AUTHORITY.md: missing operator-control semantic: {phrase}")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("APEX AUTHORITY GATE: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("APEX AUTHORITY GATE: PASS")
    print("mode=APEX")
    print("human_project_direction_authority=Casey Barton")
    print("execution_law=MAXIMUM_COHERENT_ADVANCE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
