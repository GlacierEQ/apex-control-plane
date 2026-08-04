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


def test_missing_memory_search_blocks() -> None:
    policy = load_policy()
    receipt = _valid_prime_receipt()
    del receipt["memory_search"]

    errors = validate_prime_directive_receipt(policy, receipt)

    assert "memory_search must be an object" in errors


def test_ground_truth_hash_mismatch_blocks() -> None:
    policy = load_policy()
    receipt = _valid_prime_receipt()
    receipt["ground_truth_files_loaded"][0]["sha256"] = "0" * 64

    errors = validate_prime_directive_receipt(policy, receipt)

    assert any("ground-truth hash mismatch" in error for error in errors)


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
    assert request["prime_directive_policy"]["schema_version"] == "1.0.0"
    assert request["requirements"]["run_memory_search_before_text"] is True
    assert request["requirements"]["read_and_hash_verify_ground_truth_files"] is True
    assert request["requirements"]["enumerate_loaded_tools"] is True
    assert "memory_search" in request["receipt_contract"]
    assert "ground_truth_files_loaded" in request["receipt_contract"]
    assert "tool_inventory" in request["receipt_contract"]


def test_policy_hashes_match_repository_ground_truth_files() -> None:
    import hashlib

    policy = load_policy()
    expected = {row["path"]: row["sha256"] for row in policy["ground_truth_files"]}

    for path, digest in expected.items():
        actual = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        assert actual == digest
