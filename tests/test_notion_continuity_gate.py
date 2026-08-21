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
        for row in policy["apex_notion_pages"]
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
            "apex_conflicts": [],
        },
        "existing_work_discovery": {
            "tool": "GitHub.search",
            "status": "found" if existing else "none_found",
            "query": "current requested capability and likely existing topology",
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
            "apex_owner": (
                {
                    "system": "GitHub",
                    "id": "GlacierEQ/apex-control-plane",
                    "kind": "repository",
                }
                if existing
                else None
            ),
            "apex_conflicts": [],
            "decision": "integrate_non_destructively" if existing else "map_none_found",
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
            "link_plan": ["continue existing topology and integrate non-destructively"],
            "decision": "integrate_non_destructively",
            "create_new_root": False,
            "abandon_existing": False,
            "asset_value_ranking_performed": False,
            "asset_disposition_performed": False,
            "inspection_scope_expanded": False,
            "mission_aligned_hardening": False,
        },
    }


def test_policy_is_valid_and_requires_five_continuity_pages() -> None:
    policy = load_notion_policy()
    assert policy["schema_version"] == "1.3.0"
    assert policy["stage_order"] == [
        "notion_boot_analysis",
        "existing_work_discovery",
        "integration_map",
    ]
    assert policy["block_user_facing_text_until_complete"] is False
    assert len(policy["apex_notion_pages"]) == 5
    semantics = policy["authority_semantics"]
    assert semantics["project_direction_authority"] == "operator_intent"
    assert (
        semantics[
            "discovered_relationships_authorize_non_destructive_operator_aligned_integration"
        ]
        is True
    )
    assert (
        semantics[
            "inspection_may_expand_into_mission_aligned_hardening_without_reconfirmation"
        ]
        is True
    )
    assert semantics["topology_conflicts_do_not_block_independent_executable_lanes"] is True


def test_valid_existing_work_receipt_passes() -> None:
    policy = load_notion_policy()
    assert validate_notion_continuity_receipt(policy, _valid_receipt()) == ()


def test_valid_none_found_mapping_receipt_passes() -> None:
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


def test_topology_conflicts_are_recorded_without_nullifying_independent_work() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    receipt["existing_work_discovery"]["apex_conflicts"] = [
        "two competing topology records need reconciliation"
    ]
    assert validate_notion_continuity_receipt(policy, receipt) == ()


def test_conflict_fields_must_still_be_structured_arrays() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    receipt["notion_boot_analysis"]["apex_conflicts"] = "conflict"
    receipt["existing_work_discovery"]["apex_conflicts"] = {"conflict": True}
    errors = validate_notion_continuity_receipt(policy, receipt)
    assert "notion_boot_analysis.apex_conflicts must be an array" in errors
    assert "existing_work_discovery.apex_conflicts must be an array" in errors


def test_found_work_requires_existing_owner_metadata() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    receipt["existing_work_discovery"]["apex_owner"] = None
    receipt["existing_work_discovery"]["decision"] = "map_only"
    errors = validate_notion_continuity_receipt(policy, receipt)
    assert "found existing work requires existing owner metadata" in errors
    assert any("allowed continuation/integration decision" in error for error in errors)


def test_discovery_owner_rejects_non_mapping_values() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt(existing=False)
    receipt["existing_work_discovery"]["apex_owner"] = "GitHub/repo"
    errors = validate_notion_continuity_receipt(policy, receipt)
    assert "existing_work_discovery.apex_owner must be an object or null" in errors
    assert "none_found existing work requires apex_owner=null" in errors


def test_existing_work_discovery_must_search_notion_and_another_system() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    receipt["existing_work_discovery"]["systems_searched"] = ["GitHub"]
    errors = validate_notion_continuity_receipt(policy, receipt)
    assert "existing_work_discovery.systems_searched must include Notion" in errors
    assert any("must search at least 2 systems" in error for error in errors)


def test_relationship_map_must_search_all_relationship_types() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    receipt["integration_map"]["searched_relationships"] = ["owner"]
    errors = validate_notion_continuity_receipt(policy, receipt)
    assert any("must include consumer" in error for error in errors)
    assert any("must include dependency" in error for error in errors)
    assert any("must include overlap" in error for error in errors)


def test_relationship_discovery_defaults_to_non_destructive_integration() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    receipt["integration_map"]["decision"] = "map_only"
    errors = validate_notion_continuity_receipt(policy, receipt)
    assert any("default non-destructive integration decision" in error for error in errors)


def test_related_node_cannot_create_new_root_without_operator_direction() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt(existing=False)
    receipt["integration_map"]["related_nodes"] = [
        {"system": "GitHub", "id": "GlacierEQ/related"}
    ]
    receipt["integration_map"]["create_new_root"] = True
    errors = validate_notion_continuity_receipt(policy, receipt)
    assert "integration_map.create_new_root requires explicit Operator direction" in errors


def test_explicit_operator_override_can_authorize_new_root() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    receipt["existing_work_discovery"]["decision"] = "operator_override"
    receipt["integration_map"]["decision"] = "operator_override"
    receipt["integration_map"]["create_new_root"] = True
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
        assert any("non-destructive integration decision" in error for error in errors)
        assert any("requires explicit Operator direction" in error for error in errors)


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


def test_unsolicited_asset_value_ranking_is_rejected() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    receipt["integration_map"]["asset_value_ranking_performed"] = True
    errors = validate_notion_continuity_receipt(policy, receipt)
    assert any("asset_value_ranking_performed" in error for error in errors)


def test_unsolicited_asset_disposition_is_rejected() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    receipt["integration_map"]["asset_disposition_performed"] = True
    errors = validate_notion_continuity_receipt(policy, receipt)
    assert any("asset_disposition_performed" in error for error in errors)


def test_explicit_operator_override_can_authorize_asset_disposition() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    receipt["existing_work_discovery"]["decision"] = "operator_override"
    receipt["integration_map"]["decision"] = "operator_override"
    receipt["integration_map"]["asset_value_ranking_performed"] = True
    receipt["integration_map"]["asset_disposition_performed"] = True
    receipt["integration_map"]["operator_override"] = {
        "authorized": True,
        "reason": "Operator explicitly directed asset ranking and disposition for this operation.",
    }
    assert validate_notion_continuity_receipt(policy, receipt) == ()


def test_inspection_scope_expansion_requires_mission_aligned_hardening() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    receipt["integration_map"]["inspection_scope_expanded"] = True
    errors = validate_notion_continuity_receipt(policy, receipt)
    assert (
        "inspection scope expansion requires mission_aligned_hardening=true" in errors
    )


def test_mission_aligned_hardening_allows_inspection_scope_expansion() -> None:
    policy = load_notion_policy()
    receipt = _valid_receipt()
    receipt["integration_map"]["inspection_scope_expanded"] = True
    receipt["integration_map"]["mission_aligned_hardening"] = True
    assert validate_notion_continuity_receipt(policy, receipt) == ()


def test_request_declares_apex_continuity_and_asset_sovereignty_laws() -> None:
    policy = load_notion_policy()
    request = build_notion_preflight_request(policy, task="look at legal repos")
    assert request["request_type"] == "glaciereq_notion_continuity_preflight"
    assert request["requirements"]["notion_before_material_mutation"] is True
    assert request["requirements"]["determine_whether_work_already_exists_before_starting"] is True
    assert request["requirements"]["discover_owner_consumers_dependencies_and_overlap_before_making"] is True
    assert request["requirements"]["relationship_discovery_may_drive_non_destructive_integration"] is True
    assert request["requirements"]["inspection_may_expand_into_mission_aligned_hardening"] is True
    assert request["requirements"]["continue_nonconflicting_executable_lanes_during_reconciliation"] is True
    assert request["requirements"]["preserve_literal_operator_operation_scope"] is True
    assert request["requirements"]["no_unsolicited_operator_asset_value_ranking"] is True
    assert request["requirements"]["no_unsolicited_operator_asset_disposition"] is True
    assert request["requirements"]["operator_override_may_authorize_new_root"] is True


def test_policy_file_is_valid_json() -> None:
    policy_path = ROOT / "config" / "notion_continuity_policy.json"
    parsed = json.loads(policy_path.read_text(encoding="utf-8"))
    assert parsed["schema_version"] == "1.3.0"
