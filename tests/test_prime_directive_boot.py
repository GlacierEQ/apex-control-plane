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


def _valid_prime_receipt() -> dict:
    policy = load_policy()
    return {
        "memory_search": {
            "tool": "personal_context.search",
            "query": "task topic and user project context",
            "status": "searched",
            "hit_count": 3,
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
                "personal_context.search",
                "GitHub.fetch_file",
                "api_tool.list_resources",
            ],
            "gaps": [],
        },
    }


def test_valid_prime_directive_receipt_passes() -> None:
    policy = load_policy()
    assert validate_prime_directive_receipt(policy, _valid_prime_receipt()) == ()


def test_empty_memory_result_is_valid_when_search_was_executed() -> None:
    policy = load_policy()
    receipt = _valid_prime_receipt()
    receipt["memory_search"]["status"] = "empty"
    receipt["memory_search"]["hit_count"] = 0

    assert validate_prime_directive_receipt(policy, receipt) == ()


def test_empty_memory_result_rejects_nonzero_count() -> None:
    policy = load_policy()
    receipt = _valid_prime_receipt()
    receipt["memory_search"]["status"] = "empty"
    receipt["memory_search"]["hit_count"] = 3

    errors = validate_prime_directive_receipt(policy, receipt)

    assert "empty memory_search requires hit_count=0" in errors


def test_memory_hit_count_requires_json_integer() -> None:
    policy = load_policy()
    for invalid in ("3", 3.0, True, None):
        receipt = _valid_prime_receipt()
        receipt["memory_search"]["hit_count"] = invalid

        errors = validate_prime_directive_receipt(policy, receipt)

        assert "memory_search.hit_count must be a non-negative integer" in errors


def test_missing_memory_search_blocks() -> None:
    policy = load_policy()
    receipt = _valid_prime_receipt()
    del receipt["memory_search"]

    errors = validate_prime_directive_receipt(policy, receipt)

    assert "memory_search must be an object" in errors


def test_unknown_memory_tool_alias_blocks() -> None:
    policy = load_policy()
    receipt = _valid_prime_receipt()
    receipt["memory_search"]["tool"] = "invented.memory"
    receipt["tool_inventory"]["loaded_tools"].append("invented.memory")

    errors = validate_prime_directive_receipt(policy, receipt)

    assert "memory_search.tool is not an allowed tool alias" in errors


def test_stage_tools_must_appear_in_loaded_inventory() -> None:
    policy = load_policy()
    receipt = _valid_prime_receipt()
    receipt["tool_inventory"]["loaded_tools"].remove("personal_context.search")

    errors = validate_prime_directive_receipt(policy, receipt)

    assert "memory_search.tool must appear in loaded_tools" in errors


def test_ground_truth_receipt_hash_mismatch_blocks() -> None:
    policy = load_policy()
    receipt = _valid_prime_receipt()
    receipt["ground_truth_files_loaded"][0]["sha256"] = "0" * 64

    errors = validate_prime_directive_receipt(policy, receipt)

    assert any("ground-truth receipt hash mismatch" in error for error in errors)


def test_ground_truth_source_alias_and_locator_are_validated() -> None:
    policy = load_policy()
    receipt = _valid_prime_receipt()
    receipt["ground_truth_files_loaded"][0]["source"] = "unknown.read:OTHER.md"
    receipt["tool_inventory"]["loaded_tools"].append("unknown.read")

    errors = validate_prime_directive_receipt(policy, receipt)

    assert any("source uses an unknown tool alias" in error for error in errors)
    assert any("source locator does not match" in error for error in errors)


def test_active_ground_truth_bytes_are_verified(tmp_path: Path) -> None:
    policy = load_policy()
    receipt = _valid_prime_receipt()
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
    receipt = _valid_prime_receipt()
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
    receipt = _valid_prime_receipt()
    receipt["tool_inventory"]["tool"] = "invented.list"
    receipt["tool_inventory"]["loaded_tools"].append("invented.list")

    errors = validate_prime_directive_receipt(policy, receipt)

    assert "tool_inventory.tool is not an allowed tool alias" in errors


def test_combined_boot_request_declares_prime_directive_contract() -> None:
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
    assert request["prime_directive_policy"]["schema_version"] == "1.0.1"
    assert request["requirements"]["run_memory_search_before_text"] is True
    assert request["requirements"]["read_and_hash_verify_ground_truth_files"] is True
    assert request["requirements"]["enumerate_loaded_tools"] is True
    assert request["requirements"]["open_current_task_sources"] is True
    assert request["requirements"]["validate_combined_receipt"] is True
    assert "memory_search" in request["receipt_contract"]
    assert "ground_truth_files_loaded" in request["receipt_contract"]
    assert "tool_inventory" in request["receipt_contract"]


def test_policy_requires_all_five_startup_stages() -> None:
    policy = load_policy()
    assert policy["required_stages"] == [
        "memory_search",
        "ground_truth_read",
        "tool_inventory",
        "current_source_open",
        "receipt_validation",
    ]


def test_policy_hashes_match_repository_ground_truth_files() -> None:
    import hashlib

    policy = load_policy()
    expected = {row["path"]: row["sha256"] for row in policy["ground_truth_files"]}

    for path, digest in expected.items():
        actual = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        assert actual == digest
