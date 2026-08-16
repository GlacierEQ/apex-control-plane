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
        for row in policy["canonical_notion_pages"]
    ]
    return {
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
            "query": "continuity identity capabilities current state active build",
            "pages_loaded": pages,
            "identity_loaded": True,
            "expectations_loaded": True,
            "capabilities_loaded": True,
            "current_state_loaded": True,
            "canonical_conflicts": [],
        },
        "existing_work_discovery": {
            "tool": "GitHub.search",
            "status": "found" if existing else "none_found",
            "query": "current requested capability and likely existing owner",
            "systems_searched": ["Notion", "GitHub"],
            "candidates": (
                [
                    {
                        "system": "GitHub",
                        "id": "GlacierEQ/apex-control-plane",
                        "relationship": "existing_owner",
                    }
                ]
                if existing
                else []
            ),
            "canonical_owner": (
                {
                    "system": "GitHub",
                    "id": "GlacierEQ/apex-control-plane",
                    "kind": "repository",
                }
                if existing
                else None
            ),
            "canonical_conflicts": [],
            "decision": "extend" if existing else "create_if_needed",
        },
        "integration_map": {
            "status": "complete",
            "need_search_performed": True,
            "searched_relationships": ["owner", "consumer", "dependency", "overlap"],
            "owner": (
                {
                    "system": "GitHub",
                    "id": "GlacierEQ/apex-control-plane",
                    "kind": "repository",
                }
                if existing
                else None
            ),
            "consumers": (
                [{"system": "APEX", "id": "control-plane-runtime"}]
                if existing
                else []
            ),
            "dependencies": [],
            "related_nodes": [],
            "link_plan": [
                "extend the existing startup gate and preserve prior valid capability"
            ],
            "decision": "integrate" if existing else "standalone_last_resort",
            "create_new_root": not existing,
            "abandon_existing": False,
            "standalone_justification": (
                "" if existing else "No existing owner or related consumer was found."
            ),
        },
    }


def test_policy_is_valid_and_requires_five_continuity_pages() -> None:
    policy = load_notion_policy()
    assert policy["schema_version"] == "1.1.0"
    assert policy["stage_order"] == [
        "notion_boot_analysis",
        "existing_work_discovery",
        "integration_map",
    ]
    assert len(policy["canonical_notion_pages"]) == 5
    assert (
        policy["authority_semantics"]["project_direction_authority"]
        == "operator_intent"
    )
    assert (
        policy["authority_semantics"]["canonical_fields_do_not_override_operator_intent"]
        is True
    )


def test_valid_existing_work_receipt_passes() -> None:
    policy = load_notion_policy()
    assert validate_notion_continuity_receipt(policy, _valid_receipt()) == ()


def test_valid_standalone_last_resort_receipt_passes() -> None:
    policy = load_notion_policy()
    assert validate_notion_continuity_receipt(policy, _valid_receipt(existing=False)) == ()


def test_missing_continuity_page_blocks() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    missing = receipt["notion_boot_analysis"]["pages_loaded"].pop()
    errors = validate_notion_continuity_receipt(policy, receipt)
    assert f"missing continuity Notion page: {missing['id']}" in errors
    assert any("must load at least 5 continuity pages" in error for error in errors)


def test_required_page_id_and_role_must_match_same_record() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    pages = receipt["notion_boot_analysis"]["pages_loaded"]
    pages[0]["role"], pages[1]["role"] = pages[1]["role"], pages[0]["role"]
    errors = validate_notion_continuity_receipt(policy, receipt)
    assert any("continuity Notion page role mismatch" in error for error in errors)


def test_identity_expectations_capabilities_and_state_are_mandatory() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    fields = (
        "identity_loaded",
        "expectations_loaded",
        "capabilities_loaded",
        "current_state_loaded",
    )
    for field in fields:
        receipt["notion_boot_analysis"][field] = False
    errors = validate_notion_continuity_receipt(policy, receipt)
    for field in fields:
        assert f"notion_boot_analysis.{field} must be true" in errors


def test_unresolved_topology_conflicts_block() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    receipt["existing_work_discovery"]["canonical_conflicts"] = [
        "two competing control-plane roots"
    ]
    errors = validate_notion_continuity_receipt(policy, receipt)
    assert "existing_work_discovery.canonical_conflicts must be empty" in errors


def test_found_work_requires_existing_owner_metadata() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    receipt["existing_work_discovery"]["canonical_owner"] = None
    receipt["existing_work_discovery"]["decision"] = "create_if_needed"
    errors = validate_notion_continuity_receipt(policy, receipt)
    assert "found existing work requires existing owner metadata" in errors
    assert "found existing work requires decision=extend or operator_override" in errors


def test_discovery_owner_rejects_non_mapping_values() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt(existing=False)
    receipt["existing_work_discovery"]["canonical_owner"] = "GitHub/repo"
    errors = validate_notion_continuity_receipt(policy, receipt)
    assert (
        "existing_work_discovery.canonical_owner must be an object or null" in errors
    )
    assert "none_found existing work requires canonical_owner=null" in errors


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


def test_existing_work_new_root_requires_explicit_operator_override() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    receipt["existing_work_discovery"]["decision"] = "operator_override"
    receipt["integration_map"]["decision"] = "operator_override"
    receipt["integration_map"]["create_new_root"] = True
    errors = validate_notion_continuity_receipt(policy, receipt)
    assert (
        "integration_map.create_new_root requires explicit Operator override when work exists"
        in errors
    )

    receipt["integration_map"]["operator_override"] = {
        "authorized": True,
        "reason": "Operator explicitly directed a separate root while preserving existing capability.",
    }
    assert validate_notion_continuity_receipt(policy, receipt) == ()


def test_operator_override_requires_nonblank_string_reason() -> None:
    policy = load_notion_policy()
    for invalid in (None, {}, [], "   "):
        receipt = _valid_receipt()
        receipt["existing_work_discovery"]["decision"] = "operator_override"
        receipt["integration_map"]["decision"] = "operator_override"
        receipt["integration_map"]["create_new_root"] = True
        receipt["integration_map"]["operator_override"] = {
            "authorized": True,
            "reason": invalid,
        }
        errors = validate_notion_continuity_receipt(policy, receipt)
        assert any("requires explicit Operator override" in error for error in errors)


def test_integration_owner_rejects_non_mapping_values() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt(existing=False)
    receipt["integration_map"]["owner"] = "GitHub/repo"
    errors = validate_notion_continuity_receipt(policy, receipt)
    assert "integration_map.owner must be an object or null" in errors


def test_existing_work_cannot_be_abandoned() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    receipt["integration_map"]["abandon_existing"] = True
    errors = validate_notion_continuity_receipt(policy, receipt)
    assert "integration_map.abandon_existing must be false" in errors


def test_standalone_requires_none_found_and_justification() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt(existing=False)
    receipt["integration_map"]["standalone_justification"] = ""
    errors = validate_notion_continuity_receipt(policy, receipt)
    assert "standalone work requires integration_map.standalone_justification" in errors


def test_request_declares_apex_continuity_laws() -> None:
    policy = load_notion_policy()
    request = build_notion_preflight_request(policy, task="continue current build")
    assert request["request_type"] == "glaciereq_notion_continuity_preflight"
    assert request["requirements"]["notion_before_user_facing_text"] is True
    assert (
        request["requirements"]["determine_whether_work_already_exists_before_starting"]
        is True
    )
    assert (
        request["requirements"]["discover_owner_consumers_dependencies_and_overlap_before_making"]
        is True
    )
    assert request["requirements"]["continue_and_link_before_restarting"] is True
    assert request["requirements"]["operator_override_may_authorize_new_root"] is True


def test_policy_file_is_valid_json() -> None:
    policy_path = ROOT / "config" / "notion_continuity_policy.json"
    parsed = json.loads(policy_path.read_text(encoding="utf-8"))
    assert parsed["schema_version"] == "1.1.0"
