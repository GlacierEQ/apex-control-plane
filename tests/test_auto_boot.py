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
    required_note_requirements,
    required_note_versions,
    validate_receipt,
)


CORE_OPERATOR_NOTE_ID = "fc259258-55b6-5008-a8d1-d8db22a2d8c6"
WORKER_CONTRACT_NOTE_ID = "ffd1101e-d209-5bf7-8009-0d190bd3263c"
EXECUTION_KERNEL_NOTE_ID = "54b47921-92c3-56b7-a4fa-de115e12d273"
HIDDEN_HARM_NOTE_ID = "e98732a2-0564-5b64-b5ad-9360a8cdcc3d"
TOWER_NOTE_ID = "39447e48-0aeb-5c7a-91bc-7ab0bd40313f"
FEDERATION_NOTE_ID = "63f1d7cd-9202-577a-8d0d-211c40a07606"
REPO_REGISTER_NOTE_ID = "035886f7-e0fd-5fcd-aeb6-55b282e09904"


def _valid_receipt(manifest: dict, profiles: tuple[str, ...]) -> dict:
    requirements = required_note_requirements(
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
            {"id": note_id, "version": rule["version"]}
            for note_id, rule in requirements.items()
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
        "operator_operation_class": "CONTINUE",
        "standing_authorizations_preserved": True,
        "target_state_progress_semantics_loaded": True,
        "boot_status": "complete",
        "blockers": [],
    }


def test_manifest_loads_and_always_profile_is_first() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["legal_case"])
    assert profiles == ("always", "legal_case")
    assert manifest["schema_version"] == "1.4.0"
    assert manifest["mem_collection"]["id"] == "e9990f2e-affe-55b2-a402-1de35aeb1b73"
    assert manifest["project_direction_authority"] == "operator_intent"
    assert manifest["apex_genesis"]["required"] is True
    assert manifest["core_operator_model"]["required"] is True
    assert manifest["core_operator_model"]["mem_note"]["id"] == CORE_OPERATOR_NOTE_ID
    assert manifest["core_operator_model"]["mem_note"]["version"] == 2
    assert manifest["core_operator_model"]["mem_note"]["version_mode"] == "at_least"
    assert manifest["worker_execution_contract"]["required"] is True
    assert manifest["worker_execution_contract"]["mem_note"]["id"] == WORKER_CONTRACT_NOTE_ID
    assert manifest["canonical_mem_manifest"]["version"] == 6
    assert manifest["canonical_mem_manifest"]["version_mode"] == "at_least"
    prime = manifest["prime_directive"]
    assert prime["policy_schema_version"] == "1.5.0"
    assert prime["requires_memory_state"] is True
    assert prime["requires_memory_search"] is False
    assert prime["known_state_reuse_before_rediscovery"] is True
    assert prime["memory_search_requires_material_justification"] is True
    assert prime["rediscovery_is_not_progress"] is True
    assert prime["worker_activity_is_not_progress"] is True
    assert prime["standing_authority_persists_across_mechanical_state_changes"] is True
    assert "resume_chain" not in manifest


def test_boot_request_contains_polycentric_note_version_policies() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["systems"])
    request = build_boot_request(manifest, profiles, task="continue")

    assert request["boot_manifest_id"] == "6925915b-33d6-5fc9-b499-4fbe78790413"
    assert request["boot_manifest_version"] == 6
    assert request["boot_manifest_version_mode"] == "at_least"
    assert request["mem_collection_id"] == "e9990f2e-affe-55b2-a402-1de35aeb1b73"
    for note_id in (
        CORE_OPERATOR_NOTE_ID,
        WORKER_CONTRACT_NOTE_ID,
        EXECUTION_KERNEL_NOTE_ID,
        HIDDEN_HARM_NOTE_ID,
        TOWER_NOTE_ID,
        FEDERATION_NOTE_ID,
        REPO_REGISTER_NOTE_ID,
    ):
        assert note_id in request["required_note_ids"]

    required = {row["id"]: row for row in request["required_notes"]}
    assert required[CORE_OPERATOR_NOTE_ID] == {
        "id": CORE_OPERATOR_NOTE_ID,
        "version": 2,
        "version_mode": "at_least",
    }
    assert required[WORKER_CONTRACT_NOTE_ID]["version_mode"] == "at_least"
    assert required[EXECUTION_KERNEL_NOTE_ID]["version_mode"] == "exact"
    assert required[HIDDEN_HARM_NOTE_ID]["version_mode"] == "exact"
    assert required[TOWER_NOTE_ID]["version"] == 2
    assert required[FEDERATION_NOTE_ID]["version"] == 7
    assert required[REPO_REGISTER_NOTE_ID]["version"] == 5
    assert request["requirements"]["fetch_each_note_by_exact_id_and_version_policy"] is True
    assert request["requirements"]["living_notes_accept_newer_provider_version"] is True
    assert request["requirements"]["immutable_notes_require_exact_version"] is True
    assert request["requirements"]["preserve_standing_operator_authority"] is True
    assert request["requirements"]["progress_requires_material_target_state_change"] is True


def test_required_note_versions_remains_compatibility_view() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["systems"])
    versions = required_note_versions(manifest, profiles)
    assert versions[CORE_OPERATOR_NOTE_ID] == 2
    assert versions[WORKER_CONTRACT_NOTE_ID] == 1
    assert versions[EXECUTION_KERNEL_NOTE_ID] == 2


def test_hidden_harm_contract_is_machine_bound_to_always_boot() -> None:
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


def test_missing_worker_or_hidden_harm_memory_blocks_boot() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["systems"])
    for missing_id in (WORKER_CONTRACT_NOTE_ID, HIDDEN_HARM_NOTE_ID):
        receipt = _valid_receipt(manifest, profiles)
        receipt["notes_loaded"] = [
            row for row in receipt["notes_loaded"] if row["id"] != missing_id
        ]
        result = validate_receipt(manifest, receipt, profiles)
        assert result.ok is False
        assert f"missing loaded note ID: {missing_id}" in result.errors


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
    assert f"missing loaded note ID: {missing_id}" in result.errors


def test_living_note_accepts_newer_provider_version_but_not_stale_version() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["systems"])
    receipt = _valid_receipt(manifest, profiles)
    core = next(row for row in receipt["notes_loaded"] if row["id"] == CORE_OPERATOR_NOTE_ID)
    core["version"] = 3
    assert validate_receipt(manifest, receipt, profiles).ok is True

    core["version"] = 1
    result = validate_receipt(manifest, receipt, profiles)
    assert result.ok is False
    assert any(
        f"version below minimum for note {CORE_OPERATOR_NOTE_ID}" in error
        for error in result.errors
    )


def test_exact_contract_rejects_future_or_stale_version() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["systems"])
    for bad_version in (1, 3):
        receipt = _valid_receipt(manifest, profiles)
        kernel = next(
            row for row in receipt["notes_loaded"] if row["id"] == EXECUTION_KERNEL_NOTE_ID
        )
        kernel["version"] = bad_version
        result = validate_receipt(manifest, receipt, profiles)
        assert result.ok is False
        assert any(
            f"version mismatch for note {EXECUTION_KERNEL_NOTE_ID}" in error
            for error in result.errors
        )


def test_living_manifest_accepts_newer_version_but_not_older() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["systems"])
    receipt = _valid_receipt(manifest, profiles)
    receipt["boot_manifest_version"] = 7
    assert validate_receipt(manifest, receipt, profiles).ok is True

    receipt["boot_manifest_version"] = 5
    result = validate_receipt(manifest, receipt, profiles)
    assert result.ok is False
    assert any("version below minimum for boot manifest" in error for error in result.errors)


def test_standing_authority_progress_semantics_and_operation_class_are_required() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["systems"])
    receipt = _valid_receipt(manifest, profiles)
    receipt["standing_authorizations_preserved"] = False
    receipt["target_state_progress_semantics_loaded"] = False
    receipt["operator_operation_class"] = ""
    result = validate_receipt(manifest, receipt, profiles)
    assert result.ok is False
    assert "standing_authorizations_preserved must be true" in result.errors
    assert "target_state_progress_semantics_loaded must be true" in result.errors
    assert "operator_operation_class is required" in result.errors


def test_legal_profile_without_valid_opened_source_blocks_boot() -> None:
    manifest = load_manifest()
    profiles = normalize_profiles(manifest, ["legal_case"])
    receipt = _valid_receipt(manifest, profiles)
    receipt["sources_opened"] = [{}]
    result = validate_receipt(manifest, receipt, profiles)
    assert result.ok is False
    assert "sources_opened[0].system is required" in result.errors
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


def test_manifest_is_valid_json_and_has_no_default_legal_resume_chain() -> None:
    manifest_path = ROOT / "config" / "casey_auto_boot_manifest.json"
    parsed = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert parsed["schema_version"] == "1.4.0"
    assert parsed["compatibility"]["canonical_labels_do_not_confer_project_authority"] is True
    assert parsed["compatibility"]["living_note_versions_use_at_least_semantics"] is True
    assert parsed["core_operator_model"]["required"] is True
    assert parsed["worker_execution_contract"]["required"] is True
    assert parsed["model_attractor_defense"]["durable_mem_note"]["id"] == HIDDEN_HARM_NOTE_ID
    assert "resume_chain" not in parsed
