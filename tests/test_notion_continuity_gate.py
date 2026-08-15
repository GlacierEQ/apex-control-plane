from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from notion_continuity_gate import (
    build_notion_preflight_request,
    load_notion_policy,
    validate_notion_continuity_receipt,
)


def _valid_receipt(*, existing: bool = True) -> dict:
    policy = load_notion_policy()
    pages = [
        {
            "id": row["id"],
            "role": row["role"],
            "source": f"Notion.fetch:{row['id']}",
        }
        for row in policy["apex_boot_pages"]
    ]
    source = (
        {
            "system": "GitHub",
            "id": "GlacierEQ/apex-control-plane",
            "kind": "repository",
        }
        if existing
        else None
    )
    return {
        "mode": "APEX",
        "human_project_direction_authority": "Casey Barton",
        "execution_law": "MAXIMUM_COHERENT_ADVANCE",
        "tool_inventory": {
            "tool": "api_tool.list_resources",
            "status": "complete",
            "loaded_tools": [
                "api_tool.list_resources",
                "Notion.search",
                "Notion.fetch",
                "GitHub.search",
            ],
            "gaps": [],
        },
        "notion_boot_analysis": {
            "search_tool": "Notion.search",
            "fetch_tool": "Notion.fetch",
            "status": "complete",
            "query": "continuity identity capabilities operator intent current source state",
            "pages_loaded": pages,
            "identity_loaded": True,
            "expectations_loaded": True,
            "capabilities_loaded": True,
            "current_state_loaded": True,
            "operator_intent_loaded": True,
            "source_conflicts": [],
            "conflicts_preserved": True,
        },
        "existing_work_discovery": {
            "tool": "GitHub.search",
            "status": "found" if existing else "none_found",
            "query": "current requested capability strongest source and prior implementation",
            "systems_searched": ["Notion", "GitHub"],
            "candidates": (
                [
                    {
                        "system": "GitHub",
                        "id": "GlacierEQ/apex-control-plane",
                        "relationship": "current_source",
                    }
                ]
                if existing
                else []
            ),
            "continuation_source": source,
            "source_conflicts": [],
            "conflicts_preserved": True,
            "operator_intent_preserved": True,
            "strongest_prior_state_checked": True,
            "decision": "recover" if existing else "create_if_needed",
        },
        "integration_map": {
            "status": "complete",
            "need_search_performed": True,
            "searched_relationships": [
                "owner",
                "consumer",
                "dependency",
                "overlap",
                "complement",
            ],
            "continuation_source": source,
            "consumers": (
                [{"system": "APEX", "id": "control-plane-runtime"}]
                if existing
                else []
            ),
            "dependencies": [],
            "related_nodes": [],
            "complements": [],
            "link_plan": [
                "strengthen the existing APEX startup path and preserve prior gains"
            ],
            "decision": "integrate" if existing else "new_root",
            "create_new_root": not existing,
            "new_root_reason": (
                "" if existing else "No existing or complementary source boundary was found."
            ),
            "preserve_prior_gains": True,
            "maximum_coherent_advance": True,
        },
    }


def test_policy_is_valid_and_requires_five_apex_boot_pages() -> None:
    policy = load_notion_policy()
    assert policy["schema_version"] == "2.0.0"
    assert policy["mode"] == "APEX"
    assert policy["human_project_direction_authority"] == "Casey Barton"
    assert policy["execution_law"] == "MAXIMUM_COHERENT_ADVANCE"
    assert policy["stage_order"] == [
        "notion_boot_analysis",
        "existing_work_discovery",
        "integration_map",
    ]
    assert len(policy["apex_boot_pages"]) == 5


def test_valid_existing_work_receipt_passes() -> None:
    policy = load_notion_policy()
    assert validate_notion_continuity_receipt(policy, _valid_receipt()) == ()


def test_valid_new_root_receipt_passes_when_no_existing_or_related_source_exists() -> None:
    policy = load_notion_policy()
    assert validate_notion_continuity_receipt(policy, _valid_receipt(existing=False)) == ()


def test_missing_apex_boot_page_blocks() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    missing = receipt["notion_boot_analysis"]["pages_loaded"].pop()
    errors = validate_notion_continuity_receipt(policy, receipt)
    assert any(f"missing APEX boot page: {missing['id']}" == error for error in errors)
    assert any("must load at least 5 APEX boot pages" in error for error in errors)


def test_identity_expectations_capabilities_state_and_operator_intent_are_mandatory() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    fields = (
        "identity_loaded",
        "expectations_loaded",
        "capabilities_loaded",
        "current_state_loaded",
        "operator_intent_loaded",
    )
    for field in fields:
        receipt["notion_boot_analysis"][field] = False
    errors = validate_notion_continuity_receipt(policy, receipt)
    for field in fields:
        assert f"notion_boot_analysis.{field} must be true" in errors


def test_source_conflicts_are_preserved_not_forced_empty() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    receipt["existing_work_discovery"]["source_conflicts"] = [
        "two competing historical control-plane roots"
    ]
    receipt["existing_work_discovery"]["conflicts_preserved"] = True
    assert validate_notion_continuity_receipt(policy, receipt) == ()

    receipt["existing_work_discovery"]["conflicts_preserved"] = False
    errors = validate_notion_continuity_receipt(policy, receipt)
    assert "existing_work_discovery conflicts must be preserved, not collapsed" in errors


def test_found_work_requires_continuation_source_operator_intent_and_prior_state_check() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    receipt["existing_work_discovery"]["continuation_source"] = None
    receipt["existing_work_discovery"]["operator_intent_preserved"] = False
    receipt["existing_work_discovery"]["strongest_prior_state_checked"] = False
    errors = validate_notion_continuity_receipt(policy, receipt)
    assert "found existing work requires continuation_source" in errors
    assert "found existing work must preserve operator intent" in errors
    assert "found existing work must check strongest legitimate prior state" in errors


def test_existing_work_discovery_must_search_notion_and_another_system() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    receipt["existing_work_discovery"]["systems_searched"] = ["GitHub"]
    errors = validate_notion_continuity_receipt(policy, receipt)
    assert "existing_work_discovery.systems_searched must include Notion" in errors
    assert any("must search at least 2 systems" in error for error in errors)


def test_integration_map_must_search_all_relationship_types() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    receipt["integration_map"]["searched_relationships"] = ["owner"]
    errors = validate_notion_continuity_receipt(policy, receipt)
    assert any("must include consumer" in error for error in errors)
    assert any("must include dependency" in error for error in errors)
    assert any("must include overlap" in error for error in errors)
    assert any("must include complement" in error for error in errors)


def test_existing_work_may_create_new_root_only_with_preservation_and_engineering_reason() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    receipt["integration_map"]["create_new_root"] = True
    receipt["integration_map"]["decision"] = "new_root_with_preservation"
    receipt["integration_map"]["new_root_reason"] = "Independent runtime boundary improves replaceability."
    assert validate_notion_continuity_receipt(policy, receipt) == ()

    receipt["integration_map"]["new_root_reason"] = ""
    errors = validate_notion_continuity_receipt(policy, receipt)
    assert "new root requires an explicit engineering reason" in errors


def test_maximum_coherent_advance_and_prior_gain_preservation_are_mandatory() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    receipt["integration_map"]["maximum_coherent_advance"] = False
    receipt["integration_map"]["preserve_prior_gains"] = False
    errors = validate_notion_continuity_receipt(policy, receipt)
    assert "integration_map.maximum_coherent_advance must be true" in errors
    assert "integration_map.preserve_prior_gains must be true" in errors


def test_request_declares_apex_authority_and_continuity_laws() -> None:
    policy = load_notion_policy()
    request = build_notion_preflight_request(policy, task="continue current build")
    assert request["request_type"] == "glaciereq_apex_continuity_preflight"
    assert request["mode"] == "APEX"
    assert request["human_project_direction_authority"] == "Casey Barton"
    assert request["execution_law"] == "MAXIMUM_COHERENT_ADVANCE"
    assert request["requirements"]["recover_operator_intent"] is True
    assert request["requirements"]["recover_current_source_and_strongest_prior_state"] is True
    assert request["requirements"]["preserve_source_conflicts_instead_of_collapsing_them"] is True
    assert request["requirements"]["maximum_coherent_advance"] is True


def test_policy_file_is_valid_json_and_has_no_promoted_page_authority_key() -> None:
    policy_path = ROOT / "config" / "notion_continuity_policy.json"
    parsed = json.loads(policy_path.read_text(encoding="utf-8"))
    assert parsed["schema_version"] == "2.0.0"
    assert "canonical_notion_pages" not in parsed
    assert "apex_boot_pages" in parsed
