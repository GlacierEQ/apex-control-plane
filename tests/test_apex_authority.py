from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_apex_authority.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_apex_authority", VALIDATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_apex_authority_gate_passes_active_tree() -> None:
    module = _load_validator()
    assert module.validate() == []


def test_machine_authority_contract_is_operator_first() -> None:
    data = json.loads((ROOT / "config" / "apex_authority.json").read_text(encoding="utf-8"))
    assert data["mode"] == "APEX"
    assert data["execution_law"] == "MAXIMUM_COHERENT_ADVANCE"
    assert data["human_project_direction_authority"] == {
        "name": "Casey Barton",
        "role": "SOLE_HUMAN_PROJECT_DIRECTION_AUTHORITY",
    }
    assert data["authority_rules"]["projection_may_never_overwrite_source"] is True
    assert data["authority_rules"]["canonical_authority_semantics_forbidden"] is True


def test_active_boot_files_do_not_reintroduce_promoted_owner_or_minimization_defaults() -> None:
    module = _load_validator()
    for path in module.ACTIVE_TEXT:
        text = (ROOT / path).read_text(encoding="utf-8").lower()
        for phrase in module.FORBIDDEN_ACTIVE_SEMANTICS:
            assert phrase not in text, f"{path} reintroduced {phrase!r}"


def test_apex_prompt_amplifies_under_operator_pressure() -> None:
    prompt = (ROOT / "AGENT_SYSTEM_PROMPT.md").read_text(encoding="utf-8")
    assert (
        "operator_pressure_up -> evidence_depth_up + execution_depth_up + "
        "integration_depth_up + adversarial_scrutiny_up + verification_depth_up"
    ) in prompt
    assert "operator_pressure_up -> scope_down" in prompt
    assert "Never respond with:" in prompt


def test_state_dimensions_cannot_be_collapsed_into_one_promoted_truth_bucket() -> None:
    state = (ROOT / "STATE.md").read_text(encoding="utf-8")
    for token in (
        "SOURCE_STATE",
        "CURRENT_STATE",
        "TARGET_CAPABILITY",
        "IMPLEMENTED_CAPABILITY",
        "VERIFIED_CAPABILITY",
        "AUTHORIZED_CAPABILITY",
        "DEPLOYED_CAPABILITY",
        "OBSERVED_RESULT",
        "HISTORICAL_STATE",
        "PROJECTION",
    ):
        assert token in state


def test_continuity_conflicts_are_preserved_instead_of_forced_into_one_owner() -> None:
    policy = json.loads(
        (ROOT / "config" / "notion_continuity_policy.json").read_text(encoding="utf-8")
    )
    assert "canonical_notion_pages" not in policy
    assert policy["receipt_requirements"]["source_conflicts_must_be_recorded"] is True
    assert "PRESERVE CONFLICTS INSTEAD OF LAUNDERING THEM INTO ONE PROMOTED TRUTH" in policy["laws"]
