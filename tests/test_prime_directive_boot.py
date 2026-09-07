from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from auto_boot import load_manifest, normalize_profiles
from prime_directive_boot import (
    build_prime_directive_boot_request,
    validate_prime_directive_receipt,
)
from prime_directive_enforcer import load_policy


def _base_receipt() -> dict:
    policy = load_policy()
    return {
        "memory_state": {
            "mode": "reused",
            "status": "complete",
            "source": "conversation-context:current-worker",
            "item_count": 3,
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
            "loaded_tools": [
                "GitHub.fetch_file",
                "api_tool.list_resources",
            ],
            "gaps": [],
        },
    }


def _searched_receipt(*, empty: bool = False, known_state_available: bool = False) -> dict:
    receipt = _base_receipt()
    receipt["memory_state"] = {
        "mode": "searched",
        "status": "empty" if empty else "complete",
        "source": "personal_context.search:task-topic",
        "item_count": 0 if empty else 3,
        "known_state_available": known_state_available,
        "material_rediscovery_justification": (
            "state_may_have_changed" if known_state_available else "state_not_available_in_usable_form"
        ),
        "tool": "personal_context.search",
        "query": "task topic and user project context",
    }
    receipt["tool_inventory"]["loaded_tools"].append("personal_context.search")
    return receipt


def test_reused_memory_state_passes_without_memory_search_tool() -> None:
    policy = load_policy()
    receipt = _base_receipt()

    assert "personal_context.search" not in receipt["tool_inventory"]["loaded_tools"]
    assert validate_prime_directive_receipt(policy, receipt) == ()


def test_searched_memory_state_passes_when_materially_justified() -> None:
    policy = load_policy()
    assert validate_prime_directive_receipt(policy, _searched_receipt()) == ()


def test_searched_memory_state_can_refresh_known_state_with_material_reason() -> None:
    policy = load_policy()
    receipt = _searched_receipt(known_state_available=True)

    assert validate_prime_directive_receipt(policy, receipt) == ()


def test_search_without_material_rediscovery_justification_blocks() -> None:
    policy = load_policy()
    receipt = _searched_receipt(known_state_available=True)
    receipt["memory_state"]["material_rediscovery_justification"] = ""

    errors = validate_prime_directive_receipt(policy, receipt)

    assert "searched memory_state requires material_rediscovery_justification" in errors


def test_search_with_unknown_rediscovery_reason_blocks() -> None:
    policy = load_policy()
    receipt = _searched_receipt()
    receipt["memory_state"]["material_rediscovery_justification"] = "because_search_is_easy"

    errors = validate_prime_directive_receipt(policy, receipt)

    assert any("material_rediscovery_justification must be one of" in error for error in errors)


def test_empty_searched_memory_result_is_valid() -> None:
    policy = load_policy()
    assert validate_prime_directive_receipt(policy, _searched_receipt(empty=True)) == ()


def test_empty_searched_memory_result_rejects_nonzero_count() -> None:
    policy = load_policy()
    receipt = _searched_receipt(empty=True)
    receipt["memory_state"]["item_count"] = 3

    errors = validate_prime_directive_receipt(policy, receipt)

    assert "empty searched memory_state requires item_count=0" in errors


def test_reused_memory_state_requires_nonempty_state() -> None:
    policy = load_policy()
    receipt = _base_receipt()
    receipt["memory_state"]["item_count"] = 0

    errors = validate_prime_directive_receipt(policy, receipt)

    assert "reused memory_state requires item_count>=1" in errors


def test_reused_memory_state_requires_provenance_source() -> None:
    policy = load_policy()
    receipt = _base_receipt()
    receipt["memory_state"]["source"] = ""

    errors = validate_prime_directive_receipt(policy, receipt)

    assert "memory_state.source is required" in errors


def test_missing_memory_state_blocks() -> None:
    policy = load_policy()
    receipt = _base_receipt()
    del receipt["memory_state"]

    errors = validate_prime_directive_receipt(policy, receipt)

    assert "memory_state must be an object" in errors


def test_unknown_search_tool_alias_blocks() -> None:
    policy = load_policy()
    receipt = _searched_receipt()
    receipt["memory_state"]["tool"] = "invented.memory"
    receipt["tool_inventory"]["loaded_tools"].append("invented.memory")

    errors = validate_prime_directive_receipt(policy, receipt)

    assert "searched memory_state.tool is not an allowed tool alias" in errors


def test_search_tool_must_appear_in_loaded_inventory() -> None:
    policy = load_policy()
    receipt = _searched_receipt()
    receipt["tool_inventory"]["loaded_tools"].remove("personal_context.search")

    errors = validate_prime_directive_receipt(policy, receipt)

    assert "searched memory_state.tool must appear in loaded_tools" in errors


def test_legacy_memory_search_receipt_remains_compatible() -> None:
    policy = load_policy()
    receipt = _base_receipt()
    del receipt["memory_state"]
    receipt["memory_search"] = {
        "tool": "personal_context.search",
        "query": "task topic and user project context",
        "status": "searched",
        "hit_count": 3,
    }
    receipt["tool_inventory"]["loaded_tools"].append("personal_context.search")

    assert validate_prime_directive_receipt(policy, receipt) == ()


def test_ground_truth_receipt_hash_mismatch_blocks() -> None:
    policy = load_policy()
    receipt = _base_receipt()
    receipt["ground_truth_files_loaded"][0]["sha256"] = "0" * 64

    errors = validate_prime_directive_receipt(policy, receipt)

    assert any("ground-truth receipt hash mismatch" in error for error in errors)


def test_ground_truth_source_alias_and_locator_are_validated() -> None:
    policy = load_policy()
    receipt = _base_receipt()
    receipt["ground_truth_files_loaded"][0]["source"] = "unknown.read:OTHER.md"
    receipt["tool_inventory"]["loaded_tools"].append("unknown.read")

    errors = validate_prime_directive_receipt(policy, receipt)

    assert any("source uses an unknown tool alias" in error for error in errors)
    assert any("source locator does not match" in error for error in errors)


def test_active_ground_truth_bytes_are_verified(tmp_path: Path) -> None:
    policy = load_policy()
    receipt = _base_receipt()
    for row in policy["ground_truth_files"]:
        source = ROOT / row["path"]
        target = tmp_path / row["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    (tmp_path / "STATE.md").write_text("changed active state", encoding="utf-8")

    errors = validate_prime_directive_receipt(
        policy,
        receipt,
        repo_root=tmp_path,
    )

    assert any("active ground-truth hash mismatch for STATE.md" in error for error in errors)
    assert any("receipt is not bound to active bytes for STATE.md" in error for error in errors)


def test_missing_tool_inventory_blocks() -> None:
    policy = load_policy()
    receipt = _base_receipt()
    receipt["tool_inventory"] = {
        "tool": "api_tool.list_resources",
        "status": "complete",
        "loaded_tools": [],
        "gaps": [],
    }

    errors = validate_prime_directive_receipt(policy, receipt)

    assert "tool_inventory.loaded_tools must contain at least one tool" in errors


def test_unknown_inventory_tool_alias_blocks() -> None:
    policy = load_policy()
    receipt = _base_receipt()
    receipt["tool_inventory"]["tool"] = "invented.list"
    receipt["tool_inventory"]["loaded_tools"].append("invented.list")

    errors = validate_prime_directive_receipt(policy, receipt)

    assert "tool_inventory.tool is not an allowed tool alias" in errors


def test_combined_boot_request_declares_reuse_first_contract() -> None:
    manifest = load_manifest()
    policy = load_policy()
    profiles = normalize_profiles(manifest, ["systems"])

    request = build_prime_directive_boot_request(
        manifest,
        policy,
        profiles,
        task="continue",
        restricted_authorized=False,
    )

    assert request["request_type"] == "glaciereq_prime_directive_auto_boot"
    assert request["prime_directive_policy"]["schema_version"] == "1.5.0"
    assert request["requirements"]["consult_relevant_memory_state_before_text"] is True
    assert request["requirements"]["reuse_known_state_before_rediscovery"] is True
    assert request["requirements"]["memory_search_only_when_materially_justified"] is True
    assert "run_memory_search_before_text" not in request["requirements"]
    assert request["requirements"]["read_and_hash_verify_ground_truth_files"] is True
    assert request["requirements"]["enumerate_loaded_tools"] is True
    assert request["requirements"]["open_current_task_sources"] is True
    assert request["requirements"]["validate_combined_receipt"] is True
    assert "memory_state" in request["receipt_contract"]
    assert "ground_truth_files_loaded" in request["receipt_contract"]
    assert "tool_inventory" in request["receipt_contract"]


def test_policy_requires_memory_state_not_mandatory_search() -> None:
    policy = load_policy()
    assert policy["required_stages"] == [
        "memory_state",
        "ground_truth_read",
        "tool_inventory",
        "current_source_open",
        "receipt_validation",
    ]
    assert policy["apex_binding"]["project_direction_authority"] == "operator_intent"
    assert policy["apex_binding"]["known_state_reused_before_rediscovery"] is True
    assert policy["apex_binding"]["rediscovery_is_not_progress"] is True
    assert policy["apex_binding"]["memory_state_consultation_required"] is True
    assert policy["apex_binding"]["memory_search_requires_material_justification_when_known_state_is_usable"] is True
    assert policy["apex_binding"]["unearned_state_promotion_prohibited"] is True
    assert policy["apex_binding"]["operator_fidelity_required"] is True
    assert policy["apex_binding"]["instruction_displacement_is_execution_failure"] is True
    assert policy["apex_binding"]["uncertainty_routes_to_investigation"] is True
    assert policy["apex_binding"]["governance_is_subordinate_to_function"] is True


def test_all_authority_bearing_startup_files_are_pinned() -> None:
    policy = load_policy()
    paths = {row["path"] for row in policy["ground_truth_files"]}
    assert paths == {
        "STATE.md",
        "AGENT_SYSTEM_PROMPT.md",
        "APEX_ENFORCED_STARTUP.md",
        "OPERATOR_EXECUTION_LAW.md",
    }


def test_policy_hashes_match_repository_ground_truth_files() -> None:
    import hashlib

    policy = load_policy()
    expected = {row["path"]: row["sha256"] for row in policy["ground_truth_files"]}

    for path, digest in expected.items():
        actual = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        assert actual == digest
