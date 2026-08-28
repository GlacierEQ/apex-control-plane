"""Prime Directive augmentation for the Casey continuity auto-boot gate.

The base continuity validator proves exact Mem notes, current sources, lanes,
deadlines, and repository receipts. This module adds startup behavior proof: a
memory search was executed, pinned ground-truth files were read and verified
against active bytes, and the worker enumerated its loaded tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
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


_VALIDATION_SEAL = object()


@dataclass(frozen=True, slots=True)
class PrimeDirectiveBootValidation:
    ok: bool
    status: str
    profiles: tuple[str, ...]
    errors: tuple[str, ...]
    memory_search_empty: bool
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _VALIDATION_SEAL:
            raise TypeError(
                "PrimeDirectiveBootValidation must be issued by the combined validator"
            )


_IN_PROCESS_VALIDATION: PrimeDirectiveBootValidation | None = None


def _issue_validation(
    *,
    ok: bool,
    status: str,
    profiles: Sequence[str],
    errors: Sequence[str],
    memory_search_empty: bool = False,
) -> PrimeDirectiveBootValidation:
    return PrimeDirectiveBootValidation(
        ok=ok,
        status=status,
        profiles=tuple(profiles),
        errors=tuple(errors),
        memory_search_empty=memory_search_empty,
        _seal=_VALIDATION_SEAL,
    )


def is_authentic_validation(value: Any) -> bool:
    """Return whether value was issued by this module in the current process."""
    return (
        isinstance(value, PrimeDirectiveBootValidation)
        and value._seal is _VALIDATION_SEAL
    )


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


def _normalize_tool_name(value: Any) -> str:
    return str(value or "").strip().lower().replace("::", ".")


def _stage_aliases(policy: Mapping[str, Any], stage: str) -> set[str]:
    aliases = policy.get("tool_aliases", {})
    if not isinstance(aliases, Mapping):
        return set()
    values = aliases.get(stage, ())
    if not isinstance(values, (list, tuple, set, frozenset)):
        return set()
    return {_normalize_tool_name(value) for value in values if str(value).strip()}


def _matches_alias(tool_name: str, aliases: set[str]) -> bool:
    if tool_name in aliases:
        return True
    return any(tool_name.endswith(f".{alias}") for alias in aliases if "." not in alias)


def _source_tool_prefix(value: str) -> str:
    return _normalize_tool_name(value.split(":", 1)[0])


def _source_locator(value: str) -> str:
    return value.split(":", 1)[1].strip() if ":" in value else ""


def validate_prime_directive_receipt(
    policy: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    repo_root: Path | None = None,
) -> tuple[str, ...]:
    errors: list[str] = []
    requirements = policy.get("receipt_requirements", {})
    root = (repo_root or Path(__file__).resolve().parents[1]).resolve()

    inventory = receipt.get("tool_inventory")
    loaded_tool_names: set[str] = set()
    inventory_tool = ""
    if not isinstance(inventory, Mapping):
        errors.append("tool_inventory must be an object")
    else:
        inventory_tool = _normalize_tool_name(inventory.get("tool"))
        status = str(inventory.get("status", "")).strip().lower()
        loaded_tools = inventory.get("loaded_tools")
        if not inventory_tool:
            errors.append("tool_inventory.tool is required")
        inventory_aliases = _stage_aliases(policy, "tool_inventory")
        if not _matches_alias(inventory_tool, inventory_aliases):
            errors.append("tool_inventory.tool is not an allowed tool alias")
        expected_status = str(
            requirements.get("tool_inventory_status", "complete")
        ).lower()
        if status != expected_status:
            errors.append(f"tool_inventory.status must be {expected_status}")
        if not isinstance(loaded_tools, list):
            errors.append("tool_inventory.loaded_tools must be an array")
        else:
            loaded_tool_names = {
                _normalize_tool_name(value)
                for value in loaded_tools
                if str(value).strip()
            }
            if not loaded_tool_names:
                errors.append(
                    "tool_inventory.loaded_tools must contain at least one tool"
                )
        if inventory_tool and inventory_tool not in loaded_tool_names:
            errors.append("tool_inventory.tool must appear in loaded_tools")

    memory = receipt.get("memory_search")
    if not isinstance(memory, Mapping):
        errors.append("memory_search must be an object")
    else:
        memory_tool = _normalize_tool_name(memory.get("tool"))
        query = str(memory.get("query", "")).strip()
        status = str(memory.get("status", "")).strip().lower()
        allowed = set(requirements.get("memory_search_statuses", ()))
        if not memory_tool:
            errors.append("memory_search.tool is required")
        if not _matches_alias(memory_tool, _stage_aliases(policy, "memory_search")):
            errors.append("memory_search.tool is not an allowed tool alias")
        if memory_tool and memory_tool not in loaded_tool_names:
            errors.append("memory_search.tool must appear in loaded_tools")
        if not query:
            errors.append("memory_search.query is required")
        if status not in allowed:
            errors.append(
                "memory_search.status must be one of: " + ", ".join(sorted(allowed))
            )
        hit_count = memory.get("hit_count")
        if isinstance(hit_count, bool) or not isinstance(hit_count, int):
            errors.append("memory_search.hit_count must be a non-negative integer")
        else:
            if hit_count < 0:
                errors.append("memory_search.hit_count must be a non-negative integer")
            if status == "empty" and hit_count != 0:
                errors.append("empty memory_search requires hit_count=0")

    expected_files = {
        str(row["path"]): str(row["sha256"]).lower()
        for row in policy.get("ground_truth_files", ())
        if isinstance(row, Mapping) and row.get("path") and row.get("sha256")
    }
    loaded_rows = receipt.get("ground_truth_files_loaded")
    loaded: dict[str, tuple[str, str]] = {}
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
            source_tool = _source_tool_prefix(source)
            source_locator = _source_locator(source)
            if source and not _matches_alias(
                source_tool,
                _stage_aliases(policy, "ground_truth_read"),
            ):
                errors.append(
                    f"ground_truth_files_loaded[{index}].source uses an unknown tool alias"
                )
            if source_tool and source_tool not in loaded_tool_names:
                errors.append(
                    f"ground_truth_files_loaded[{index}].source tool must appear in loaded_tools"
                )
            if (
                path
                and source_locator
                and not source_locator.lower().endswith(path.lower())
            ):
                errors.append(
                    f"ground_truth_files_loaded[{index}].source locator does not match {path}"
                )
            if path and digest and source:
                loaded[path] = (digest, source)

    for path, expected_hash in expected_files.items():
        active_path = (root / path).resolve()
        try:
            active_path.relative_to(root)
        except ValueError:
            errors.append(f"ground-truth path escapes repository root: {path}")
            continue
        try:
            active_bytes = active_path.read_bytes()
        except FileNotFoundError:
            errors.append(f"active ground-truth file not found: {path}")
            continue
        active_hash = hashlib.sha256(active_bytes).hexdigest()
        if active_hash != expected_hash:
            errors.append(
                f"active ground-truth hash mismatch for {path}: "
                f"expected {expected_hash}, got {active_hash}"
            )
        receipt_row = loaded.get(path)
        if receipt_row is None:
            errors.append(f"missing ground-truth file receipt: {path}")
            continue
        receipt_hash, _ = receipt_row
        if receipt_hash != expected_hash:
            errors.append(
                f"ground-truth receipt hash mismatch for {path}: "
                f"expected {expected_hash}, got {receipt_hash}"
            )
        if receipt_hash != active_hash:
            errors.append(
                f"ground-truth receipt is not bound to active bytes for {path}"
            )

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
            "open_current_task_sources": True,
            "validate_combined_receipt": True,
            "tool_call_without_success_does_not_complete_stage": True,
            "block_user_facing_text_until_gate_complete": True,
            "preserve_literal_operator_operation_scope": True,
            "no_unsolicited_operator_asset_value_ranking": True,
            "no_unsolicited_operator_asset_disposition": True,
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


def validate_combined_receipt(
    manifest: Mapping[str, Any],
    policy: Mapping[str, Any],
    receipt: Mapping[str, Any],
    profiles: Sequence[str],
    *,
    restricted_authorized: bool,
    repo_root: Path | None = None,
) -> PrimeDirectiveBootValidation:
    """Validate continuity and Prime Directive proof and issue sealed result."""
    base = validate_receipt(
        manifest,
        receipt,
        profiles,
        restricted_authorized=restricted_authorized,
    )
    errors = list(base.errors)
    errors.extend(
        validate_prime_directive_receipt(
            policy,
            receipt,
            repo_root=repo_root,
        )
    )
    memory = receipt.get("memory_search")
    memory_search_empty = (
        isinstance(memory, Mapping)
        and str(memory.get("status", "")).strip().lower() == "empty"
        and memory.get("hit_count") == 0
    )
    return _issue_validation(
        ok=not errors,
        status="complete" if not errors else "blocked",
        profiles=profiles,
        errors=errors,
        memory_search_empty=memory_search_empty,
    )


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
        str(manifest.get("prime_directive", {}).get("policy_path", DEFAULT_POLICY_PATH))
    )
    if not policy_path.is_absolute():
        policy_path = Path(__file__).resolve().parents[1] / policy_path
    policy = load_policy(policy_path)

    profiles = normalize_profiles(
        manifest,
        [os.getenv("CASEY_BOOT_PROFILE", "systems")],
    )
    restricted_authorized = os.getenv("CASEY_RESTRICTED_CONTEXT_AUTHORIZED", "0") == "1"
    task = os.getenv(
        "CASEY_BOOT_TASK",
        "resume Operator-directed unfinished material action",
    )
    receipt = receipt_from_environment()

    if receipt is None:
        validation = _issue_validation(
            ok=False,
            status="blocked",
            profiles=profiles,
            errors=("no boot receipt supplied",),
        )
    else:
        validation = validate_combined_receipt(
            manifest,
            policy,
            receipt,
            profiles,
            restricted_authorized=restricted_authorized,
        )

    if validation.ok:
        _IN_PROCESS_VALIDATION = validation
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
    request["receipt_errors"] = list(validation.errors)
    print(json.dumps(request, ensure_ascii=False, sort_keys=True), file=sys.stderr)
    sys.stderr.flush()

    if mode == "request":
        _IN_PROCESS_VALIDATION = _issue_validation(
            ok=False,
            status="degraded",
            profiles=profiles,
            errors=validation.errors,
            memory_search_empty=validation.memory_search_empty,
        )
        os.environ["CASEY_BOOT_STATUS"] = "degraded"
        os.environ["GLACIEREQ_PRIME_DIRECTIVE_GATE_STATUS"] = "degraded"
        return _IN_PROCESS_VALIDATION

    os.environ["CASEY_BOOT_STATUS"] = "blocked"
    os.environ["GLACIEREQ_PRIME_DIRECTIVE_GATE_STATUS"] = "blocked"
    raise SystemExit(EXIT_BOOT_BLOCKED)
