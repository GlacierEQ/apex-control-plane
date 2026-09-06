#!/usr/bin/env python3
"""Deterministic Casey continuity auto-boot gate.

This module never pretends that a Mem search result is a loaded note or that a
connector is live merely because it is configured. It emits an exact boot
request and validates a provider-backed receipt before a case or systems
runtime proceeds.

No network client or credential is embedded here. A connected agent or bridge
must retrieve the notes and sources, then provide a receipt through
``CASEY_BOOT_RECEIPT_JSON`` or ``CASEY_BOOT_RECEIPT_PATH``.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH = REPO_ROOT / "config" / "casey_auto_boot_manifest.json"
EXIT_BOOT_BLOCKED = 78


class BootError(RuntimeError):
    """Raised when the continuity gate cannot be proven complete."""


@dataclass(frozen=True, slots=True)
class BootValidation:
    ok: bool
    status: str
    profiles: tuple[str, ...]
    required_note_ids: tuple[str, ...]
    loaded_note_ids: tuple[str, ...]
    errors: tuple[str, ...]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BootError(f"boot JSON not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BootError(f"invalid boot JSON at {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise BootError(f"boot JSON must be an object: {path}")
    return payload


def load_manifest(path: Path | None = None) -> dict[str, Any]:
    manifest_path = path or DEFAULT_MANIFEST_PATH
    manifest = _read_json(manifest_path)
    required_keys = {
        "schema_version",
        "mem_collection",
        "canonical_mem_manifest",
        "profiles",
        "required_note_versions",
        "default_profiles",
    }
    missing = sorted(required_keys.difference(manifest))
    if missing:
        raise BootError(f"manifest missing keys: {', '.join(missing)}")
    if not isinstance(manifest["profiles"], dict):
        raise BootError("manifest.profiles must be an object")
    if not isinstance(manifest["required_note_versions"], dict):
        raise BootError("manifest.required_note_versions must be an object")
    return manifest


def normalize_profiles(
    manifest: Mapping[str, Any],
    requested: Iterable[str] | None = None,
) -> tuple[str, ...]:
    raw = list(requested or manifest.get("default_profiles", ()))
    profiles: list[str] = ["always"]
    for value in raw:
        for item in str(value).split(","):
            profile = item.strip()
            if profile and profile not in profiles:
                profiles.append(profile)
    available = set(manifest.get("profiles", {}))
    unknown = [profile for profile in profiles if profile not in available]
    if unknown:
        raise BootError(f"unknown boot profile(s): {', '.join(unknown)}")
    return tuple(profiles)


def required_note_ids(
    manifest: Mapping[str, Any],
    profiles: Sequence[str],
    *,
    restricted_authorized: bool = False,
) -> tuple[str, ...]:
    if "restricted_child" in profiles and not restricted_authorized:
        raise BootError(
            "restricted_child profile requires CASEY_RESTRICTED_CONTEXT_AUTHORIZED=1"
        )
    output: list[str] = []
    profile_map = manifest.get("profiles", {})
    for profile in profiles:
        values = profile_map.get(profile, ())
        if not isinstance(values, list):
            raise BootError(f"manifest profile {profile!r} must be a list")
        for note_id in values:
            text = str(note_id).strip()
            if text and text not in output:
                output.append(text)
    return tuple(output)


def required_note_versions(
    manifest: Mapping[str, Any],
    profiles: Sequence[str],
    *,
    restricted_authorized: bool = False,
) -> dict[str, int]:
    ids = required_note_ids(
        manifest,
        profiles,
        restricted_authorized=restricted_authorized,
    )
    version_map = manifest.get("required_note_versions", {})
    output: dict[str, int] = {}
    for note_id in ids:
        raw_version = version_map.get(note_id)
        if isinstance(raw_version, bool):
            raise BootError(f"invalid required version for note {note_id}")
        try:
            version = int(raw_version)
        except (TypeError, ValueError) as exc:
            raise BootError(
                f"missing or invalid required version for note {note_id}"
            ) from exc
        if version < 1:
            raise BootError(f"required note version must be >= 1 for {note_id}")
        output[note_id] = version
    return output


def build_boot_request(
    manifest: Mapping[str, Any],
    profiles: Sequence[str],
    *,
    task: str = "resume Operator-directed unfinished material action",
    restricted_authorized: bool = False,
) -> dict[str, Any]:
    versions = required_note_versions(
        manifest,
        profiles,
        restricted_authorized=restricted_authorized,
    )
    return {
        "request_type": "casey_continuity_auto_boot",
        "requested_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "boot_manifest_id": manifest["canonical_mem_manifest"]["id"],
        "boot_manifest_version": manifest["canonical_mem_manifest"]["version"],
        "mem_collection_id": manifest["mem_collection"]["id"],
        "profiles": list(profiles),
        "required_note_ids": list(versions),
        "required_notes": [
            {"id": note_id, "version": version} for note_id, version in versions.items()
        ],
        "task": task,
        "requirements": {
            "fetch_each_note_by_exact_id_and_version": True,
            "search_result_is_not_loaded_note": True,
            "open_current_task_sources": True,
            "emit_provider_receipt": True,
            "preserve_case_boundaries": True,
            "no_external_action_without_authority": True,
            "preserve_literal_operator_operation_scope": True,
            "no_unsolicited_operator_asset_value_ranking": True,
            "no_unsolicited_operator_asset_disposition": True,
        },
        "receipt_contract": {
            "boot_manifest_id": "string",
            "boot_manifest_version": "integer",
            "mem_collection_id": "string",
            "boot_profile": "array[string]",
            "notes_loaded": "array[{id:string,version:integer}]",
            "sources_opened": "array[{system:string,object_id:string,version:string|null}]",
            "repository_receipts": "array[{repository:string,revision:string,checked_at:string}]",
            "case_lane": "string|null",
            "matter_lane": "string|null",
            "deadline_check": "{status:verified|not_relevant,source_ids:array[string],reason:string|null}",
            "restricted_context": "boolean",
            "current_task": "string",
            "next_material_action": "string",
            "boot_status": "complete|degraded|blocked",
            "blockers": "array[string]",
        },
    }


def _receipt_from_environment() -> dict[str, Any] | None:
    inline = os.getenv("CASEY_BOOT_RECEIPT_JSON", "").strip()
    path_value = os.getenv("CASEY_BOOT_RECEIPT_PATH", "").strip()
    if inline and path_value:
        raise BootError(
            "set only one of CASEY_BOOT_RECEIPT_JSON or CASEY_BOOT_RECEIPT_PATH"
        )
    if inline:
        try:
            payload = json.loads(inline)
        except json.JSONDecodeError as exc:
            raise BootError(f"CASEY_BOOT_RECEIPT_JSON is invalid: {exc}") from exc
        if not isinstance(payload, dict):
            raise BootError("CASEY_BOOT_RECEIPT_JSON must contain an object")
        return payload
    if path_value:
        return _read_json(Path(path_value).expanduser().resolve())
    return None


def _loaded_note_versions(
    receipt: Mapping[str, Any],
) -> tuple[dict[str, int], list[str]]:
    loaded: dict[str, int] = {}
    errors: list[str] = []
    rows = receipt.get("notes_loaded")
    if not isinstance(rows, list):
        return loaded, ["notes_loaded must be an array"]
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            errors.append(f"notes_loaded[{index}] must be an object")
            continue
        note_id = str(row.get("id", "")).strip()
        if not note_id:
            errors.append(f"notes_loaded[{index}].id is required")
            continue
        raw_version = row.get("version")
        if isinstance(raw_version, bool):
            errors.append(f"notes_loaded[{index}].version must be an integer")
            continue
        try:
            version = int(raw_version)
        except (TypeError, ValueError):
            errors.append(f"notes_loaded[{index}].version must be an integer")
            continue
        if version < 1:
            errors.append(f"notes_loaded[{index}].version must be >= 1")
            continue
        if note_id in loaded and loaded[note_id] != version:
            errors.append(f"conflicting loaded versions for note {note_id}")
            continue
        loaded[note_id] = version
    return loaded, errors


def _validate_sources(receipt: Mapping[str, Any]) -> tuple[int, list[str]]:
    rows = receipt.get("sources_opened")
    if not isinstance(rows, list):
        return 0, ["sources_opened must be an array"]
    valid = 0
    errors: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            errors.append(f"sources_opened[{index}] must be an object")
            continue
        system = str(row.get("system", "")).strip()
        object_id = str(row.get("object_id", "")).strip()
        if not system:
            errors.append(f"sources_opened[{index}].system is required")
        if not object_id:
            errors.append(f"sources_opened[{index}].object_id is required")
        if "version" not in row:
            errors.append(f"sources_opened[{index}].version key is required")
        if system and object_id and "version" in row:
            valid += 1
    return valid, errors


def _validate_repository_receipts(receipt: Mapping[str, Any]) -> tuple[int, list[str]]:
    rows = receipt.get("repository_receipts")
    if not isinstance(rows, list):
        return 0, ["repository_receipts must be an array"]
    valid = 0
    errors: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            errors.append(f"repository_receipts[{index}] must be an object")
            continue
        repository = str(row.get("repository", "")).strip()
        revision = str(row.get("revision", "")).strip()
        checked_at = str(row.get("checked_at", "")).strip()
        if not repository:
            errors.append(f"repository_receipts[{index}].repository is required")
        if not revision:
            errors.append(f"repository_receipts[{index}].revision is required")
        if not checked_at:
            errors.append(f"repository_receipts[{index}].checked_at is required")
        if repository and revision and checked_at:
            valid += 1
    return valid, errors


def _validate_deadline_check(
    manifest: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> list[str]:
    value = receipt.get("deadline_check")
    if not isinstance(value, Mapping):
        return ["deadline_check must be an object"]
    status = str(value.get("status", "")).strip()
    allowed = set(manifest.get("deadline_check_statuses", ()))
    errors: list[str] = []
    if status not in allowed:
        errors.append("deadline_check.status must be verified or not_relevant")
    if status == "verified":
        source_ids = value.get("source_ids")
        if not isinstance(source_ids, list) or not any(
            str(item).strip() for item in source_ids
        ):
            errors.append("verified deadline_check requires source_ids")
    if status == "not_relevant" and not str(value.get("reason", "")).strip():
        errors.append("not_relevant deadline_check requires reason")
    return errors


def validate_receipt(
    manifest: Mapping[str, Any],
    receipt: Mapping[str, Any],
    profiles: Sequence[str],
    *,
    restricted_authorized: bool = False,
) -> BootValidation:
    required_versions = required_note_versions(
        manifest,
        profiles,
        restricted_authorized=restricted_authorized,
    )
    loaded_versions, note_errors = _loaded_note_versions(receipt)
    errors: list[str] = list(note_errors)

    expected_manifest = manifest["canonical_mem_manifest"]
    if receipt.get("boot_manifest_id") != expected_manifest["id"]:
        errors.append("boot_manifest_id mismatch")
    try:
        receipt_version = int(receipt.get("boot_manifest_version", 0))
    except (TypeError, ValueError):
        receipt_version = 0
    if receipt_version != int(expected_manifest["version"]):
        errors.append("boot_manifest_version mismatch")
    if receipt.get("mem_collection_id") != manifest["mem_collection"]["id"]:
        errors.append("mem_collection_id mismatch")

    for note_id, expected_version in required_versions.items():
        actual_version = loaded_versions.get(note_id)
        if actual_version is None:
            errors.append(f"missing loaded note ID: {note_id}")
        elif actual_version != expected_version:
            errors.append(
                f"note version mismatch for {note_id}: expected {expected_version}, got {actual_version}"
            )

    receipt_profiles = receipt.get("boot_profile")
    if not isinstance(receipt_profiles, list):
        errors.append("boot_profile must be an array")
        receipt_profiles = []
    missing_profiles = [
        profile for profile in profiles if profile not in receipt_profiles
    ]
    if missing_profiles:
        errors.append("missing boot profiles: " + ", ".join(missing_profiles))

    valid_sources, source_errors = _validate_sources(receipt)
    errors.extend(source_errors)
    valid_repo_receipts, repository_errors = _validate_repository_receipts(receipt)
    errors.extend(repository_errors)

    requirements = manifest.get("profile_requirements", {})
    for profile in profiles:
        rule = requirements.get(profile, {})
        if rule.get("requires_current_sources") and valid_sources < 1:
            errors.append(f"profile {profile} requires current sources")
        if (
            rule.get("requires_case_lane")
            and not str(receipt.get("case_lane", "")).strip()
        ):
            errors.append(f"profile {profile} requires case_lane")
        if (
            rule.get("requires_matter_lane")
            and not str(receipt.get("matter_lane", "")).strip()
        ):
            errors.append(f"profile {profile} requires matter_lane")
        if rule.get("requires_repository_receipt") and valid_repo_receipts < 1:
            errors.append(f"profile {profile} requires repository receipt")
        if rule.get("requires_live_deadline_check_when_relevant"):
            errors.extend(_validate_deadline_check(manifest, receipt))

    restricted_context = receipt.get("restricted_context")
    if not isinstance(restricted_context, bool):
        errors.append("restricted_context must be a boolean")
    if "restricted_child" in profiles and restricted_context is not True:
        errors.append("restricted_child profile requires restricted_context=true")

    if not str(receipt.get("current_task", "")).strip():
        errors.append("current_task is required")
    if not str(receipt.get("next_material_action", "")).strip():
        errors.append("next_material_action is required")

    status = str(receipt.get("boot_status", "blocked"))
    if status != "complete":
        errors.append(f"boot_status is {status!r}, not 'complete'")
    blockers = receipt.get("blockers")
    if not isinstance(blockers, list):
        errors.append("blockers must be an array")
    elif blockers:
        errors.append("receipt contains blockers: " + "; ".join(map(str, blockers)))

    return BootValidation(
        ok=not errors,
        status="complete" if not errors else "blocked",
        profiles=tuple(profiles),
        required_note_ids=tuple(required_versions),
        loaded_note_ids=tuple(loaded_versions),
        errors=tuple(errors),
    )


def automatic_boot() -> BootValidation | None:
    """Run the environment-driven boot validation and surface recoverable continuations.

    Missing or invalid evidence remains non-authorizing, but now returns a durable
    continuation receipt so local diagnosis and receipt repair can proceed.
    """
    mode = os.getenv("CASEY_AUTO_BOOT_MODE", "strict").strip().lower()
    if mode == "off" or os.getenv("CASEY_AUTO_BOOT_DISABLE") == "1":
        return None
    if mode not in {"strict", "request"}:
        raise BootError(f"unsupported CASEY_AUTO_BOOT_MODE: {mode}")

    manifest = load_manifest()
    profile_value = os.getenv("CASEY_BOOT_PROFILE", "systems")
    profiles = normalize_profiles(manifest, [profile_value])
    restricted_authorized = os.getenv("CASEY_RESTRICTED_CONTEXT_AUTHORIZED", "0") == "1"
    task = os.getenv(
        "CASEY_BOOT_TASK",
        "resume Operator-directed unfinished material action",
    )
    receipt = _receipt_from_environment()

    if receipt is not None:
        result = validate_receipt(
            manifest,
            receipt,
            profiles,
            restricted_authorized=restricted_authorized,
        )
        if result.ok:
            os.environ["CASEY_BOOT_STATUS"] = "complete"
            return result
        request = build_boot_request(
            manifest,
            profiles,
            task=task,
            restricted_authorized=restricted_authorized,
        )
        request["receipt_errors"] = list(result.errors)
        loaded_ids = result.loaded_note_ids
        degraded_errors = result.errors
    else:
        request = build_boot_request(
            manifest,
            profiles,
            task=task,
            restricted_authorized=restricted_authorized,
        )
        request["receipt_errors"] = ["no boot receipt supplied"]
        loaded_ids = ()
        degraded_errors = ("no boot receipt supplied",)

    from startup_continuation import (
        emit_startup_continuation,
        record_startup_continuation,
    )

    continuation = record_startup_continuation(
        "auto_boot",
        degraded_errors,
        request=request,
        environment_key="CASEY_BOOT_STATUS",
    )
    emit_startup_continuation(continuation)
    return BootValidation(
        ok=False,
        status="continuation_required",
        profiles=tuple(profiles),
        required_note_ids=tuple(request["required_note_ids"]),
        loaded_note_ids=tuple(loaded_ids),
        errors=tuple(degraded_errors),
    )


def _profiles_from_args(values: Sequence[str]) -> tuple[str, ...]:
    output: list[str] = []
    for value in values:
        output.extend(item.strip() for item in value.split(",") if item.strip())
    return tuple(output)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help="path to the machine-readable auto-boot manifest",
    )
    parser.add_argument(
        "--profile",
        action="append",
        default=[],
        help="boot profile; repeat or use comma-separated values",
    )
    parser.add_argument(
        "--task", default="resume Operator-directed unfinished material action"
    )
    parser.add_argument("--emit-request", action="store_true")
    parser.add_argument("--verify-receipt", type=Path)
    parser.add_argument("--restricted-authorized", action="store_true")
    args = parser.parse_args(argv)

    manifest = load_manifest(args.manifest)
    requested = _profiles_from_args(args.profile)
    profiles = normalize_profiles(manifest, requested or None)

    if args.emit_request:
        print(
            json.dumps(
                build_boot_request(
                    manifest,
                    profiles,
                    task=args.task,
                    restricted_authorized=args.restricted_authorized,
                ),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.verify_receipt:
        receipt = _read_json(args.verify_receipt)
        result = validate_receipt(
            manifest,
            receipt,
            profiles,
            restricted_authorized=args.restricted_authorized,
        )
        print(
            json.dumps(
                {
                    "ok": result.ok,
                    "status": result.status,
                    "profiles": list(result.profiles),
                    "required_note_ids": list(result.required_note_ids),
                    "loaded_note_ids": list(result.loaded_note_ids),
                    "errors": list(result.errors),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if result.ok else EXIT_BOOT_BLOCKED

    parser.error("choose --emit-request or --verify-receipt")


if __name__ == "__main__":
    raise SystemExit(main())
