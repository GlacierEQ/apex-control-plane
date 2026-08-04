from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from auto_boot import (  # noqa: E402
    BootError,
    build_boot_request,
    load_manifest,
    normalize_profiles,
    required_note_ids,
    required_note_versions,
    validate_receipt,
)


def _valid_receipt(manifest: dict, profiles: tuple[str, ...]) -> dict:
    versions = required_note_versions(
        manifest,
        profiles,
        restricted_authorized="restricted_child" in profiles,
    )
    return {
        "boot_manifest_id": manifest["canonical_mem_manifest"]["id"],
        "boot_manifest_version": manifest["canonical_mem_manifest"]["version"],
        "mem_collection_id": manifest["mem_collection"]["id"],
        "boot_profile": list(profiles),
        "notes_loaded": [
            {"id": note_id, "version": version}
            for note_id, version in versions.items()
        ],
        "sources_opened": [
            {
                "system": "test-provider",
                "object_id": "source-1",
                "version": "1",
            }
        ],
        "repository_receipts": [
            {
                "repository": "GlacierEQ/apex-control-plane",
                "revision": "0" * 40,
                "checked_at": "2026-08-04T00:00:00Z",
            }
        ],
        "case_lane": "1FDV-23-0001009",
        "matter_lane": "TEST-MATTER",
        "deadline_check": {
            "status": "verified",
            "source_ids": ["source-1"],
            "reason": None,
        },
        "restricted_context": "restricted_child" in profiles,
        "current_task": "test the auto-boot contract",
        "next_material_action": "run control-plane tests",
        "boot_status": "complete",
        "blockers": [],
    }


def test_manifest_loads_and_always_profile_is_first() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["legal_case"])
    assert profiles == ("always", "legal_case")
    assert manifest["schema_version"] == "1.1.1"
    assert manifest["mem_collection"]["id"] == "e9990f2e-affe-55b2-a402-1de35aeb1b73"


def test_boot_request_contains_exact_manifest_note_ids_and_versions() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["systems"])
    request = build_boot_request(manifest, profiles, task="continue")

    assert request["boot_manifest_id"] == "6925915b-33d6-5fc9-b499-4fbe78790413"
    assert request["mem_collection_id"] == "e9990f2e-affe-55b2-a402-1de35aeb1b73"
    assert "618140c7-bb34-404b-926c-8daffd28f162" in request["required_note_ids"]
    assert "035886f7-e0fd-5fcd-aeb6-55b282e09904" in request["required_note_ids"]
    assert "cf749759-468a-5903-807a-078b20fca0e3" in request["required_note_ids"]
    required = {row["id"]: row["version"] for row in request["required_notes"]}
    assert required["618140c7-bb34-404b-926c-8daffd28f162"] == 7
    assert required["1c5f821b-af89-5898-97fe-2789095e1163"] == 4
    assert required["cf749759-468a-5903-807a-078b20fca0e3"] == 1
    assert request["requirements"]["fetch_each_note_by_exact_id_and_version"] is True


def test_complete_legal_receipt_passes() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["legal_case"])
    receipt = _valid_receipt(manifest, profiles)
    result = validate_receipt(manifest, receipt, profiles)

    assert result.ok is True
    assert result.status == "complete"
    assert result.errors == ()


def test_missing_note_blocks_boot() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["legal_case"])
    receipt = _valid_receipt(manifest, profiles)
    missing_id = receipt["notes_loaded"].pop()["id"]

    result = validate_receipt(manifest, receipt, profiles)

    assert result.ok is False
    assert any(f"missing loaded note ID: {missing_id}" == error for error in result.errors)


def test_stale_or_future_note_version_blocks_boot() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["systems"])
    receipt = _valid_receipt(manifest, profiles)
    receipt["notes_loaded"][0]["version"] += 1

    result = validate_receipt(manifest, receipt, profiles)

    assert result.ok is False
    assert any("note version mismatch" in error for error in result.errors)


def test_manifest_version_must_match_exactly() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["systems"])
    receipt = _valid_receipt(manifest, profiles)
    receipt["boot_manifest_version"] += 1

    result = validate_receipt(manifest, receipt, profiles)

    assert result.ok is False
    assert "boot_manifest_version mismatch" in result.errors


def test_legal_profile_without_valid_opened_source_blocks_boot() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["legal_case"])
    receipt = _valid_receipt(manifest, profiles)
    receipt["sources_opened"] = [{}]

    result = validate_receipt(manifest, receipt, profiles)

    assert result.ok is False
    assert any("sources_opened[0].system is required" == error for error in result.errors)
    assert any("requires current sources" in error for error in result.errors)


def test_systems_profile_requires_repository_receipt() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["systems"])
    receipt = _valid_receipt(manifest, profiles)
    receipt["repository_receipts"] = []

    result = validate_receipt(manifest, receipt, profiles)

    assert result.ok is False
    assert "profile systems requires repository receipt" in result.errors


def test_legal_profile_requires_deadline_check_contract() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["legal_case"])
    receipt = _valid_receipt(manifest, profiles)
    receipt["deadline_check"] = {"status": "not_relevant", "source_ids": []}

    result = validate_receipt(manifest, receipt, profiles)

    assert result.ok is False
    assert "not_relevant deadline_check requires reason" in result.errors


def test_separate_matter_uses_matter_lane_not_case_lane() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["separate_matter"])
    receipt = _valid_receipt(manifest, profiles)
    receipt["matter_lane"] = ""
    receipt["case_lane"] = "1FDV-23-0001009"

    result = validate_receipt(manifest, receipt, profiles)

    assert result.ok is False
    assert "profile separate_matter requires matter_lane" in result.errors


def test_core_continuity_fields_and_blocker_type_are_enforced() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["systems"])
    receipt = _valid_receipt(manifest, profiles)
    receipt["restricted_context"] = "false"
    receipt["current_task"] = ""
    receipt["next_material_action"] = ""
    receipt["blockers"] = "docket unavailable"

    result = validate_receipt(manifest, receipt, profiles)

    assert result.ok is False
    assert "restricted_context must be a boolean" in result.errors
    assert "current_task is required" in result.errors
    assert "next_material_action is required" in result.errors
    assert "blockers must be an array" in result.errors


def test_restricted_child_profile_requires_authorization() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["restricted_child"])

    with pytest.raises(BootError, match="restricted_child profile requires"):
        required_note_ids(manifest, profiles, restricted_authorized=False)

    notes = required_note_ids(manifest, profiles, restricted_authorized=True)
    assert "a4cf7086-b558-52e1-8398-b699ce6d309a" in notes


def test_combined_legal_and_restricted_profiles_authorize_and_deduplicate() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["legal_case", "restricted_child"])

    with pytest.raises(BootError, match="restricted_child profile requires"):
        required_note_ids(manifest, profiles, restricted_authorized=False)

    notes = required_note_ids(manifest, profiles, restricted_authorized=True)
    legal = required_note_ids(
        manifest,
        normalize_profiles(manifest, ["legal_case"]),
        restricted_authorized=True,
    )
    assert set(legal).issubset(set(notes))
    assert "a4cf7086-b558-52e1-8398-b699ce6d309a" in notes
    assert len(notes) == len(set(notes))


def test_manifest_is_valid_json() -> None:
    manifest_path = ROOT / "config" / "casey_auto_boot_manifest.json"
    parsed = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert parsed["schema_version"] == "1.1.1"
