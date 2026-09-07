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
    required_note_policies,
    required_note_versions,
    validate_receipt,
)


CORE_OPERATOR_NOTE_ID = "fc259258-55b6-5008-a8d1-d8db22a2d8c6"
SIMPLE_CONTINUITY_NOTE_ID = "54b47921-92c3-56b7-a4fa-de115e12d273"
HIDDEN_HARM_NOTE_ID = "e98732a2-0564-5b64-b5ad-9360a8cdcc3d"
TOWER_ROUTING_NOTE_ID = "39447e48-0aeb-5c7a-91bc-7ab0bd40313f"
FEDERATION_NOTE_ID = "63f1d7cd-9202-577a-8d0d-211c40a07606"
RESPONSIBILITY_NOTE_ID = "035886f7-e0fd-5fcd-aeb6-55b282e09904"


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
                "checked_at": "2026-09-07T00:00:00Z",
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


def _loaded_row(receipt: dict, note_id: str) -> dict:
    return next(row for row in receipt["notes_loaded"] if row["id"] == note_id)


def test_manifest_loads_with_small_polycentric_core() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["legal_case"])

    assert profiles == ("always", "legal_case")
    assert manifest["schema_version"] == "1.4.0"
    assert manifest["mem_collection"]["id"] == "e9990f2e-affe-55b2-a402-1de35aeb1b73"
    assert manifest["mem_collection"]["expected_core_note_count"] == 7
    assert manifest["mem_collection"]["semantics"] == "cross_cutting_routing_core_not_global_truth"
    assert manifest["project_direction_authority"] == "operator_intent"
    assert manifest["apex_genesis"]["required"] is True
    assert manifest["core_operator_model"]["required"] is True
    assert manifest["core_operator_model"]["mem_note"]["id"] == CORE_OPERATOR_NOTE_ID
    assert manifest["core_operator_model"]["mem_note"]["version"] == 2
    assert manifest["core_operator_model"]["mem_note"]["version_mode"] == "at_least"
    assert manifest["canonical_mem_manifest"]["version"] == 5
    assert manifest["canonical_mem_manifest"]["version_mode"] == "at_least"

    prime = manifest["prime_directive"]
    assert prime["policy_schema_version"] == "1.5.0"
    assert prime["requires_memory_state"] is True
    assert prime["requires_memory_search"] is False
    assert prime["known_state_reuse_before_rediscovery"] is True
    assert prime["memory_search_requires_material_justification"] is True
    assert prime["rediscovery_is_not_progress"] is True


def test_default_systems_boot_contains_only_cross_cutting_core_and_system_routes() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["systems"])
    request = build_boot_request(manifest, profiles, task="continue")

    assert request["boot_manifest_id"] == "6925915b-33d6-5fc9-b499-4fbe78790413"
    assert request["boot_manifest_version"] == 5
    assert request["boot_manifest_version_mode"] == "at_least"
    assert request["mem_collection_id"] == "e9990f2e-affe-55b2-a402-1de35aeb1b73"

    assert set(request["required_note_ids"]) == {
        CORE_OPERATOR_NOTE_ID,
        SIMPLE_CONTINUITY_NOTE_ID,
        HIDDEN_HARM_NOTE_ID,
        TOWER_ROUTING_NOTE_ID,
        FEDERATION_NOTE_ID,
        RESPONSIBILITY_NOTE_ID,
    }

    for stale_global_note in (
        "618140c7-bb34-404b-926c-8daffd28f162",
        "774ac390-77d9-57be-adcf-3d830816b8bd",
        "714910a8-14ae-50f5-9e2e-16566369edac",
        "b51f5cf3-9fbe-511c-a400-915f0f5dd8a0",
        "1c5f821b-af89-5898-97fe-2789095e1163",
        "0ff8b9aa-490c-5187-a495-61759a8bbe82",
        "cf749759-468a-5903-807a-078b20fca0e3",
        "47502b91-2af6-5cce-b2ed-bd244d9a82d8",
    ):
        assert stale_global_note not in request["required_note_ids"]

    policies = {
        row["id"]: (row["version_mode"], row["required_version"])
        for row in request["required_notes"]
    }
    assert policies[CORE_OPERATOR_NOTE_ID] == ("at_least", 2)
    assert policies[SIMPLE_CONTINUITY_NOTE_ID] == ("exact", 2)
    assert policies[HIDDEN_HARM_NOTE_ID] == ("exact", 1)
    assert policies[TOWER_ROUTING_NOTE_ID] == ("at_least", 2)
    assert policies[FEDERATION_NOTE_ID] == ("at_least", 7)
    assert policies[RESPONSIBILITY_NOTE_ID] == ("at_least", 5)
    assert request["requirements"]["fetch_each_note_by_stable_id_and_version_policy"] is True
    assert request["requirements"]["fetch_each_note_by_exact_id_and_version"] is False
    assert request["requirements"]["forbid_global_provider_authority_rank"] is True


def test_required_note_policies_preserve_exact_and_at_least_modes() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["systems"])
    policies = required_note_policies(manifest, profiles)

    assert policies[CORE_OPERATOR_NOTE_ID] == ("at_least", 2)
    assert policies[SIMPLE_CONTINUITY_NOTE_ID] == ("exact", 2)
    assert policies[HIDDEN_HARM_NOTE_ID] == ("exact", 1)
    assert policies[FEDERATION_NOTE_ID] == ("at_least", 7)


def test_newer_living_mem_note_version_does_not_deadlock_boot() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["systems"])
    receipt = _valid_receipt(manifest, profiles)
    _loaded_row(receipt, FEDERATION_NOTE_ID)["version"] = 11
    _loaded_row(receipt, CORE_OPERATOR_NOTE_ID)["version"] = 5

    result = validate_receipt(manifest, receipt, profiles)

    assert result.ok is True
    assert result.errors == ()


def test_living_mem_note_below_compatibility_floor_blocks_boot() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["systems"])
    receipt = _valid_receipt(manifest, profiles)
    _loaded_row(receipt, FEDERATION_NOTE_ID)["version"] = 6

    result = validate_receipt(manifest, receipt, profiles)

    assert result.ok is False
    assert any(
        f"note {FEDERATION_NOTE_ID} version below minimum" in error
        for error in result.errors
    )


def test_exact_semantic_lock_rejects_version_drift() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["systems"])
    receipt = _valid_receipt(manifest, profiles)
    _loaded_row(receipt, SIMPLE_CONTINUITY_NOTE_ID)["version"] = 3

    result = validate_receipt(manifest, receipt, profiles)

    assert result.ok is False
    assert any(
        f"note {SIMPLE_CONTINUITY_NOTE_ID} version mismatch" in error
        for error in result.errors
    )


def test_newer_mem_manifest_version_is_accepted_but_older_is_not() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["systems"])

    newer = _valid_receipt(manifest, profiles)
    newer["boot_manifest_version"] = 7
    assert validate_receipt(manifest, newer, profiles).ok is True

    older = _valid_receipt(manifest, profiles)
    older["boot_manifest_version"] = 4
    result = validate_receipt(manifest, older, profiles)
    assert result.ok is False
    assert "boot_manifest version below minimum" in result.errors


def test_hidden_harm_contract_is_always_loaded_and_machine_bound() -> None:
    manifest = load_manifest()
    defense = manifest["model_attractor_defense"]

    assert defense["status"] == "required-foundation"
    assert defense["failure_class"] == "MODEL_ATTRACTOR_DRIFT"
    assert defense["durable_mem_note"]["id"] == HIDDEN_HARM_NOTE_ID
    assert defense["durable_mem_note"]["version"] == 1
    assert defense["durable_mem_note"]["version_mode"] == "exact"
    assert defense["chatgpt_product_memory_is_correctness_dependency"] is False
    assert defense["summaries_are_routing_hints_only"] is True
    assert defense["source_bearing_hydration_required_for_continuity_work"] is True
    assert defense["fail_closed"] is True
    assert HIDDEN_HARM_NOTE_ID in manifest["profiles"]["always"]


def test_missing_hidden_harm_memory_blocks_systems_boot() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["systems"])
    receipt = _valid_receipt(manifest, profiles)
    receipt["notes_loaded"] = [
        row for row in receipt["notes_loaded"] if row["id"] != HIDDEN_HARM_NOTE_ID
    ]

    result = validate_receipt(manifest, receipt, profiles)

    assert result.ok is False
    assert f"missing loaded note ID: {HIDDEN_HARM_NOTE_ID}" in result.errors


def test_complete_legal_receipt_passes() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["legal_case"])
    receipt = _valid_receipt(manifest, profiles)
    result = validate_receipt(manifest, receipt, profiles)

    assert result.ok is True
    assert result.status == "complete"
    assert result.errors == ()


def test_legal_payload_is_not_in_always_profile() -> None:
    manifest = load_manifest()
    always = set(manifest["profiles"]["always"])

    assert "774ac390-77d9-57be-adcf-3d830816b8bd" not in always
    assert "714910a8-14ae-50f5-9e2e-16566369edac" not in always
    assert "43a23b64-46eb-530c-9521-9787b038c53a" not in always
    assert "a4cf7086-b558-52e1-8398-b699ce6d309a" not in always


def test_missing_note_blocks_boot() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["legal_case"])
    receipt = _valid_receipt(manifest, profiles)
    missing_id = receipt["notes_loaded"].pop()["id"]

    result = validate_receipt(manifest, receipt, profiles)

    assert result.ok is False
    assert any(f"missing loaded note ID: {missing_id}" == error for error in result.errors)


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

    assert parsed["schema_version"] == "1.4.0"
    assert parsed["compatibility"]["canonical_labels_do_not_confer_project_authority"] is True
    assert parsed["compatibility"]["mem_collection_membership_does_not_confer_authority"] is True
    assert parsed["compatibility"]["mutable_mem_notes_use_stable_id_plus_version_policy"] is True
    assert parsed["core_operator_model"]["required"] is True
    assert parsed["model_attractor_defense"]["durable_mem_note"]["id"] == HIDDEN_HARM_NOTE_ID
    assert parsed["resume_policy"]["global_default_case_chain"] is False

    prime = parsed["prime_directive"]
    assert prime["policy_schema_version"] == "1.5.0"
    assert prime["requires_memory_state"] is True
    assert prime["requires_memory_search"] is False
    assert prime["known_state_reuse_before_rediscovery"] is True
    assert prime["memory_search_requires_material_justification"] is True
    assert prime["rediscovery_is_not_progress"] is True
