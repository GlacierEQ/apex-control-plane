#!/usr/bin/env python3
"""Fail when active APEX control surfaces regress into promoted authority or minimization."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ACTIVE_TEXT = [
    "AGENT_SYSTEM_PROMPT.md",
    "STATE.md",
    "README.md",
    "src/control_plane.py",
    "src/auto_boot.py",
    "src/notion_continuity_gate.py",
    "src/prime_directive_boot.py",
    "src/prime_directive_enforcer.py",
    "src/sitecustomize.py",
    "jack/README.md",
    "jack/config/jack_relentless_contract.yaml",
    "jack/config/jack_relentless_contract.compiled.json",
    "jack/src/jack_relentless_gate.py",
    "jack/odin/jack_relentless_gate.odin",
    "glaciereq/jack/v1/jack_relentless_contract.proto",
]

# These are positive control commands from the contaminated path, not mere
# mentions of concepts that APEX explicitly prohibits.
FORBIDDEN_ACTIVE_SEMANTICS = [
    "execute the smallest compatible extension",
    "resolve one controlling canonical owner",
    "one controlling canonical owner",
    "resume and extend the canonical owner before creating",
    "unresolved canonical conflicts block creation",
    "unresolved canonical conflicts block progress",
    "resolve_one_canonical_owner_before_continuing",
    "canonical_conflicts_block_progress",
    "canonical_owner",
    "canonical_notion_pages",
    "canonical_mem_manifest",
]

REQUIRED_PROMPT = [
    "Human project-direction authority:",
    "Casey Barton",
    "MAXIMUM_COHERENT_ADVANCE",
    "operator_pressure_up -> evidence_depth_up + execution_depth_up + integration_depth_up",
    "Smallness itself is never the objective.",
    "MVP as product ceiling",
    "smallest vertical slice",
    "minimal diff as scope objective",
]

REQUIRED_STATE = [
    "Human project-direction authority:",
    "Casey Barton",
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

    directive = _json("config/prime_directive_policy.json")
    if directive.get("mode") != "APEX":
        errors.append("config/prime_directive_policy.json: mode must be APEX")
    if directive.get("human_project_direction_authority") != "Casey Barton":
        errors.append("config/prime_directive_policy.json: Casey authority missing")
    if directive.get("execution_law") != "MAXIMUM_COHERENT_ADVANCE":
        errors.append("config/prime_directive_policy.json: execution law drift")
    if directive.get("pin_semantics") != "DRIFT_DETECTION_ONLY_NOT_PROJECT_DIRECTION_AUTHORITY":
        errors.append("config/prime_directive_policy.json: integrity pins promoted beyond drift detection")
    semantic_gate = directive.get("semantic_gate") or {}
    if semantic_gate.get("command") != "python scripts/validate_apex_authority.py":
        errors.append("config/prime_directive_policy.json: semantic APEX gate missing")
    pin_paths = {
        row.get("path")
        for row in directive.get("ground_truth_files", [])
        if isinstance(row, dict)
    }
    if pin_paths != {
        "APEX_AUTHORITY.md",
        "config/apex_authority.json",
        "STATE.md",
        "AGENT_SYSTEM_PROMPT.md",
    }:
        errors.append("config/prime_directive_policy.json: APEX control-file pin set drift")

    jack = _json("jack/config/jack_relentless_contract.compiled.json")
    if jack.get("mode") != "APEX":
        errors.append("jack compiled contract: mode must be APEX")
    if jack.get("human_project_direction_authority") != "Casey Barton":
        errors.append("jack compiled contract: Casey authority missing")
    if jack.get("execution_law") != "MAXIMUM_COHERENT_ADVANCE":
        errors.append("jack compiled contract: execution law drift")
    if "operator_authority_loaded" not in jack.get("preflight_gates", []):
        errors.append("jack compiled contract: operator authority gate missing")
    if "maximum_coherent_advance_selected" not in jack.get("completion_gates", []):
        errors.append("jack compiled contract: maximum coherent advance gate missing")

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
        "is not an authority class in APEX",
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
