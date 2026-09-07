from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from prime_directive_boot import validate_prime_directive_receipt
from prime_directive_enforcer import load_policy


def _base_receipt() -> dict:
    policy = load_policy()
    return {
        "memory_state": {
            "mode": "reused",
            "status": "complete",
            "source": "conversation-context:current-worker",
            "item_count": 2,
            "known_state_available": True,
            "material_rediscovery_justification": "",
        },
        "ground_truth_files_loaded": [
            {
                "path": row["path"],
                "sha256": row["sha256"],
                "source": f"GitHub.fetch_file:{row['path']}",
            }
            for row in policy["ground_truth_files"]
        ],
        "tool_inventory": {
            "tool": "api_tool.list_resources",
            "status": "complete",
            "loaded_tools": ["GitHub.fetch_file", "api_tool.list_resources"],
            "gaps": [],
        },
    }


def _searched_receipt() -> dict:
    receipt = _base_receipt()
    receipt["memory_state"] = {
        "mode": "searched",
        "status": "complete",
        "source": "personal_context.search:current-task",
        "item_count": 2,
        "known_state_available": False,
        "material_rediscovery_justification": "state_not_available_in_usable_form",
        "tool": "personal_context.search",
        "query": "current task and project context",
    }
    receipt["tool_inventory"]["loaded_tools"].append("personal_context.search")
    return receipt


def test_reused_empty_status_is_rejected() -> None:
    policy = load_policy()
    receipt = _base_receipt()
    receipt["memory_state"]["status"] = "empty"

    errors = validate_prime_directive_receipt(policy, receipt)

    assert "reused memory_state requires status=complete" in errors


def test_reused_known_state_false_is_rejected() -> None:
    policy = load_policy()
    receipt = _base_receipt()
    receipt["memory_state"]["known_state_available"] = False

    errors = validate_prime_directive_receipt(policy, receipt)

    assert "reused memory_state requires known_state_available=true" in errors


def test_reused_rediscovery_justification_is_rejected() -> None:
    policy = load_policy()
    receipt = _base_receipt()
    receipt["memory_state"]["material_rediscovery_justification"] = "state_may_have_changed"

    errors = validate_prime_directive_receipt(policy, receipt)

    assert "reused memory_state must not claim a rediscovery justification" in errors


def test_searched_complete_zero_count_is_rejected() -> None:
    policy = load_policy()
    receipt = _searched_receipt()
    receipt["memory_state"]["item_count"] = 0

    errors = validate_prime_directive_receipt(policy, receipt)

    assert "searched memory_state with item_count=0 requires status=empty" in errors


def test_null_source_is_rejected_instead_of_becoming_string_none() -> None:
    policy = load_policy()
    receipt = _base_receipt()
    receipt["memory_state"]["source"] = None

    errors = validate_prime_directive_receipt(policy, receipt)

    assert "memory_state.source must be a non-empty string" in errors


def test_null_search_query_is_rejected_instead_of_becoming_string_none() -> None:
    policy = load_policy()
    receipt = _searched_receipt()
    receipt["memory_state"]["query"] = None

    errors = validate_prime_directive_receipt(policy, receipt)

    assert "searched memory_state.query must be a non-empty string" in errors


def test_reused_unstructured_provenance_is_rejected() -> None:
    policy = load_policy()
    receipt = _base_receipt()
    receipt["memory_state"]["source"] = "invented-projection"

    errors = validate_prime_directive_receipt(policy, receipt)

    assert "memory_state.source must use structured class:locator provenance" in errors


def test_searched_source_must_match_search_tool() -> None:
    policy = load_policy()
    receipt = _searched_receipt()
    receipt["memory_state"]["source"] = "some.other.tool:current-task"

    errors = validate_prime_directive_receipt(policy, receipt)

    assert "searched memory_state.source class must match searched memory_state.tool" in errors


def test_invalid_legacy_status_survives_projection_and_is_rejected() -> None:
    policy = load_policy()
    receipt = _base_receipt()
    del receipt["memory_state"]
    receipt["memory_search"] = {
        "tool": "personal_context.search",
        "query": "current task and project context",
        "status": "invalid",
        "hit_count": 2,
    }
    receipt["tool_inventory"]["loaded_tools"].append("personal_context.search")

    errors = validate_prime_directive_receipt(policy, receipt)

    assert any("memory_state.status must be one of" in error for error in errors)
