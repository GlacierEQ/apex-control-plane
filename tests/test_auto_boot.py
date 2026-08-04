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
    validate_receipt,
)


def _valid_receipt(manifest: dict, profiles: tuple[str, ...]) -> dict:
    required = required_note_ids(manifest, profiles)
    return {
        "boot_manifest_id": manifest["canonical_mem_manifest"]["id"],
        "boot_manifest_version": manifest["canonical_mem_manifest"]["version"],
        "mem_collection_id": manifest["mem_collection"]["id"],
        "boot_profile": list(profiles),
        "notes_loaded": [
            {"id": note_id, "version": 1}
            for note_id in required
        ],
        "sources_opened": [
            {
                "system": "test-provider",
                "object_id": "source-1",
                "version": "1",
            }
        ],
        "case_lane": "1FDV-23-0001009",
        "restricted_context": False,
        "current_task": "test the auto-boot contract",
        "next_material_action": "run control-plane tests",
        "boot_status": "complete",
        "blockers": [],
    }


def test_manifest_loads_and_always_profile_is_first() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["legal_case"])
    assert profiles == ("always", "legal_case")
    assert manifest["mem_collection"]["id"] == "e9990f2e-affe-55b2-a402-1de35aeb1b73"


def test_boot_request_contains_exact_manifest_and_note_ids() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["systems"])
    request = build_boot_request(manifest, profiles, task="continue")

    assert request["boot_manifest_id"] == "6925915b-33d6-5fc9-b499-4fbe78790413"
    assert request["mem_collection_id"] == "e9990f2e-affe-55b2-a402-1de35aeb1b73"
    assert "618140c7-bb34-404b-926c-8daffd28f162" in request["required_note_ids"]
    assert "035886f7-e0fd-5fcd-aeb6-55b282e09904" in request["required_note_ids"]
    assert request["requirements"]["fetch_each_note_by_exact_id"] is True


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
    receipt["notes_loaded"].pop()

    result = validate_receipt(manifest, receipt, profiles)

    assert result.ok is False
    assert result.status == "blocked"
    assert any("missing loaded note IDs" in error for error in result.errors)


def test_legal_profile_without_opened_source_blocks_boot() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["legal_case"])
    receipt = _valid_receipt(manifest, profiles)
    receipt["sources_opened"] = []

    result = validate_receipt(manifest, receipt, profiles)

    assert result.ok is False
    assert any("requires current sources" in error for error in result.errors)


def test_restricted_child_profile_requires_authorization() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["restricted_child"])

    with pytest.raises(BootError, match="restricted_child profile requires"):
        required_note_ids(manifest, profiles, restricted_authorized=False)

    notes = required_note_ids(manifest, profiles, restricted_authorized=True)
    assert "a4cf7086-b558-52e1-8398-b699ce6d309a" in notes


def test_manifest_is_valid_json() -> None:
    manifest_path = ROOT / "config" / "casey_auto_boot_manifest.json"
    parsed = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert parsed["schema_version"] == "1.0.0"
