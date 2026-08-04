"""Prime Directive augmentation for the Casey continuity auto-boot gate.

The base continuity validator proves exact Mem notes, current sources, lanes,
deadlines, and repository receipts. This module adds the startup behavior proof:
a memory search was actually executed, both pinned ground-truth files were read
and hash-verified, and the worker enumerated its loaded tools.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

from auto_boot import (
    EXIT_BOOT_BLOCKED,
    BootError,
    build_boot_request,
    load_manifest,
    normalize_profiles,
    validate_receipt,
)
from prime_directive_enforcer import DEFAULT_POLICY_PATH, load_policy


@dataclass(frozen=True, slots=True)
class PrimeDirectiveBootValidation:
    ok: bool
    status: str
    profiles: tuple[str, ...]
    errors: tuple[str, ...]


_IN_PROCESS_VALIDATION: PrimeDirectiveBootValidation | None = None


def get_in_process_boot_validation() -> PrimeDirectiveBootValidation | None:
    """Return only proof produced inside the current Python process."""
    return _IN_PROCESS_VALIDATION


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BootError(f"boot receipt not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BootError(f"invalid boot receipt JSON at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BootError("boot receipt must be a JSON object")
    return value


def receipt_from_environment() -> dict[str, Any] | None:
    inline = os.getenv("CASEY_BOOT_RECEIPT_JSON", "").strip()
    path_value = os.getenv("CASEY_BOOT_RECEIPT_PATH", "").strip()
    if inline and path_value:
        raise BootError(
            "set only one of CASEY_BOOT_RECEIPT_JSON or CASEY_BOOT_RECEIPT_PATH"
        )
    if inline:
        try:
            value = json.loads(inline)
        except json.JSONDecodeError as exc:
            raise BootError(f"CASEY_BOOT_RECEIPT_JSON is invalid: {exc}") from exc
        if not isinstance(value, dict):
            raise BootError("CASEY_BOOT_RECEIPT_JSON must contain an object")
        return value
    if path_value:
        return _read_json(Path(path_value).expanduser().resolve())
    return None


def validate_prime_directive_receipt(
    policy: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> tuple[str, ...]:
    errors: list[str] = []
    requirements = policy.get("receipt_requirements", {})

    memory = receipt.get("memory_search")
    if not isinstance(memory, Mapping):
        errors.append("memory_search must be an object")
    else:
        tool = str(memory.get("tool", "")).strip()
        query = str(memory.get("query", "")).strip()
        status = str(memory.get("status", "")).strip().lower()
        allowed = set(requirements.get("memory_search_statuses", ()))
        if not tool:
            errors.append("memory_search.tool is required")
        if not query:
            errors.append("memory_search.query is required")
        if status not in allowed:
            errors.append(
                "memory_search.status must be one of: " + ", ".join(sorted(allowed))
            )
        hit_count = memory.get("hit_count")
        if isinstance(hit_count, bool):
            errors.append("memory_search.hit_count must be a non-negative integer")
        else:
            try:
                parsed_hit_count = int(hit_count)
            except (TypeError, ValueError):
                errors.append("memory_search.hit_count must be a non-negative integer")
            else:
                if parsed_hit_count < 0:
                    errors.append("memory_search.hit_count must be a non-negative integer")

    expected_files = {
        str(row["path"]): str(row["sha256"]).lower()
        for row in policy.get("ground_truth_files", ())
        if isinstance(row, Mapping) and row.get("path") and row.get("sha256")
    }
    loaded_rows = receipt.get("ground_truth_files_loaded")
    loaded: dict[str, str] = {}
    if not isinstance(loaded_rows, list):
        errors.append("ground_truth_files_loaded must be an array")
    else:
        for index, row in enumerate(loaded_rows):
            if not isinstance(row, Mapping):
                errors.append(f"ground_truth_files_loaded[{index}] must be an object")
                continue
            path = str(row.get("path", "")).strip()
            digest = str(row.get("sha256", "")).strip().lower()
            source = str(row.get("source", "")).strip()
            if not path:
                errors.append(f"ground_truth_files_loaded[{index}].path is required")
            if not digest:
                errors.append(f"ground_truth_files_loaded[{index}].sha256 is required")
            if not source:
                errors.append(f"ground_truth_files_loaded[{index}].source is required")
            if path and digest:
                loaded[path] = digest
    for path, expected_hash in expected_files.items():
        actual_hash = loaded.get(path)
        if actual_hash is None:
            errors.append(f"missing ground-truth file receipt: {path}")
        elif actual_hash != expected_hash:
            errors.append(
                f"ground-truth hash mismatch for {path}: "
                f"expected {expected_hash}, got {actual_hash}"
            )

    inventory = receipt.get("tool_inventory")
    if not isinstance(inventory, Mapping):
        errors.append("tool_inventory must be an object")
    else:
        tool = str(inventory.get("tool", "")).strip()
        status = str(inventory.get("status", "")).strip().lower()
        loaded_tools = inventory.get("loaded_tools")
        if not tool:
            errors.append("tool_inventory.tool is required")
        expected_status = str(
            requirements.get("tool_inventory_status", "complete")
        ).lower()
        if status != expected_status:
            errors.append(f"tool_inventory.status must be {expected_status}")
        if not isinstance(loaded_tools, list):
            errors.append("tool_inventory.loaded_tools must be an array")
        elif not any(str(value).strip() for value in loaded_tools):
            errors.append("tool_inventory.loaded_tools must contain at least one tool")

    return tuple(errors)


def build_prime_directive_boot_request(
    manifest: Mapping[str, Any],
    policy: Mapping[str, Any],
    profiles: Sequence[str],
    *,
    task: str,
    restricted_authorized: bool,
) -> dict[str, Any]:
    request = build_boot_request(
        manifest,
        profiles,
        task=task,
        restricted_authorized=restricted_authorized,
    )
    request["request_type"] = "glaciereq_prime_directive_auto_boot"
    request["prime_directive_policy"] = {
        "schema_version": policy.get("schema_version"),
        "path": str(
            manifest.get("prime_directive", {}).get(
                "policy_path", "config/prime_directive_policy.json"
            )
        ),
        "required_stages": list(policy.get("required_stages", ())),
        "ground_truth_files": list(policy.get("ground_truth_files", ())),
    }
    request["requirements"].update(
        {
            "run_memory_search_before_text": True,
            "read_and_hash_verify_ground_truth_files": True,
            "enumerate_loaded_tools": True,
            "tool_call_without_success_does_not_complete_stage": True,
            "block_user_facing_text_until_gate_complete": True,
        }
    )
    request["receipt_contract"].update(
        {
            "memory_search": (
                "{tool:string,query:string,status:complete|searched|empty,"
                "hit_count:integer}"
            ),
            "ground_truth_files_loaded": (
                "array[{path:string,sha256:string,source:string}]"
            ),
            "tool_inventory": (
                "{tool:string,status:complete,loaded_tools:array[string],"
                "gaps:array[string]}"
            ),
        }
    )
    return request


def automatic_prime_directive_boot() -> PrimeDirectiveBootValidation | None:
    """Validate the combined continuity and Prime Directive receipt."""
    global _IN_PROCESS_VALIDATION

    if _IN_PROCESS_VALIDATION is not None:
        return _IN_PROCESS_VALIDATION

    mode = os.getenv("CASEY_AUTO_BOOT_MODE", "strict").strip().lower()
    if mode == "off" or os.getenv("CASEY_AUTO_BOOT_DISABLE") == "1":
        os.environ["GLACIEREQ_PRIME_DIRECTIVE_GATE_STATUS"] = "off"
        return None
    if mode not in {"strict", "request"}:
        raise BootError(f"unsupported CASEY_AUTO_BOOT_MODE: {mode}")

    manifest = load_manifest()
    policy_path = Path(
        str(
            manifest.get("prime_directive", {}).get(
                "policy_path", DEFAULT_POLICY_PATH
            )
        )
    )
    if not policy_path.is_absolute():
        policy_path = Path(__file__).resolve().parents[1] / policy_path
    policy = load_policy(policy_path)

    profiles = normalize_profiles(
        manifest,
        [os.getenv("CASEY_BOOT_PROFILE", "systems")],
    )
    restricted_authorized = (
        os.getenv("CASEY_RESTRICTED_CONTEXT_AUTHORIZED", "0") == "1"
    )
    task = os.getenv(
        "CASEY_BOOT_TASK",
        "resume highest-value unfinished material action",
    )
    receipt = receipt_from_environment()
    errors: list[str] = []

    if receipt is not None:
        base = validate_receipt(
            manifest,
            receipt,
            profiles,
            restricted_authorized=restricted_authorized,
        )
        errors.extend(base.errors)
        errors.extend(validate_prime_directive_receipt(policy, receipt))
    else:
        errors.append("no boot receipt supplied")

    if not errors:
        _IN_PROCESS_VALIDATION = PrimeDirectiveBootValidation(
            ok=True,
            status="complete",
            profiles=tuple(profiles),
            errors=(),
        )
        os.environ["CASEY_BOOT_STATUS"] = "complete"
        os.environ["GLACIEREQ_PRIME_DIRECTIVE_GATE_STATUS"] = "complete"
        os.environ["GLACIEREQ_BOOT_RECEIPT_VERIFIED"] = "1"
        return _IN_PROCESS_VALIDATION

    request = build_prime_directive_boot_request(
        manifest,
        policy,
        profiles,
        task=task,
        restricted_authorized=restricted_authorized,
    )
    request["requested_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    request["receipt_errors"] = errors
    print(json.dumps(request, ensure_ascii=False, sort_keys=True), file=sys.stderr)
    sys.stderr.flush()

    if mode == "request":
        _IN_PROCESS_VALIDATION = PrimeDirectiveBootValidation(
            ok=False,
            status="degraded",
            profiles=tuple(profiles),
            errors=tuple(errors),
        )
        os.environ["CASEY_BOOT_STATUS"] = "degraded"
        os.environ["GLACIEREQ_PRIME_DIRECTIVE_GATE_STATUS"] = "degraded"
        return _IN_PROCESS_VALIDATION

    os.environ["CASEY_BOOT_STATUS"] = "blocked"
    os.environ["GLACIEREQ_PRIME_DIRECTIVE_GATE_STATUS"] = "blocked"
    raise SystemExit(EXIT_BOOT_BLOCKED)
