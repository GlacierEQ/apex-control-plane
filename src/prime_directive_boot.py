"""Prime Directive augmentation for the Casey continuity auto-boot gate.

The base continuity validator proves exact continuity notes, current sources,
lanes, deadlines, and repository receipts. This module adds startup behavior
proof without forcing redundant rediscovery: relevant memory/continuity state
must be consulted, and may be satisfied either by provenance-bearing reuse of
already-available state or by a materially justified search. Pinned ground-truth
files are still read and verified against active bytes, and the worker still
proves its loaded-tool inventory.
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
    memory_state_mode: str
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
    memory_state_mode: str = "",
) -> PrimeDirectiveBootValidation:
    return PrimeDirectiveBootValidation(
        ok=ok,
        status=status,
        profiles=tuple(profiles),
        errors=tuple(errors),
        memory_search_empty=memory_search_empty,
        memory_state_mode=str(memory_state_mode or "").strip().lower(),
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
    return any(
        tool_name.endswith(f".{alias}")
        for alias in aliases
        if "." not in alias
    )


def _source_tool_prefix(value: str) -> str:
    return _normalize_tool_name(value.split(":", 1)[0])


def _source_locator(value: str) -> str:
    return value.split(":", 1)[1].strip() if ":" in value else ""


def _nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _structured_provenance(value: Any) -> tuple[str, str] | None:
    """Return normalized (source class, locator) for explicit class:locator proof."""
    if not _nonempty_text(value):
        return None
    raw = value.strip()
    if ":" not in raw:
        return None
    source_class, locator = raw.split(":", 1)
    source_class = source_class.strip()
    locator = locator.strip()
    if not source_class or not locator:
        return None
    return source_class, locator


def _json_nonnegative_integer(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def _legacy_memory_state(receipt: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Project legacy memory_search receipts into searched-mode compatibility state.

    Legacy receipts remain accepted so existing provider bridges do not break, but
    invalid legacy statuses remain invalid after projection instead of being
    laundered into ``complete``. New requests emit only memory_state.
    """
    legacy = receipt.get("memory_search")
    if not isinstance(legacy, Mapping):
        return None

    raw_status = legacy.get("status")
    status = raw_status.strip().lower() if isinstance(raw_status, str) else ""
    if status == "empty":
        projected_status = "empty"
    elif status in {"complete", "searched"}:
        projected_status = "complete"
    else:
        projected_status = status

    raw_tool = legacy.get("tool")
    tool = raw_tool.strip() if isinstance(raw_tool, str) else ""
    hit_count = legacy.get("hit_count")
    return {
        "mode": "searched",
        "status": projected_status,
        "source": f"{tool}:legacy-memory-search" if tool else "",
        "item_count": hit_count,
        "known_state_available": False,
        "material_rediscovery_justification": "state_not_available_in_usable_form",
        "tool": raw_tool,
        "query": legacy.get("query"),
    }


def _memory_state(receipt: Mapping[str, Any]) -> Mapping[str, Any] | None:
    row = receipt.get("memory_state")
    if isinstance(row, Mapping):
        return row
    return _legacy_memory_state(receipt)


def _validate_memory_state(
    policy: Mapping[str, Any],
    receipt: Mapping[str, Any],
    loaded_tool_names: set[str],
    errors: list[str],
) -> tuple[str, bool]:
    """Validate reuse-first memory acquisition and return (mode, searched_empty)."""
    requirements = policy.get("receipt_requirements", {})
    row = _memory_state(receipt)
    if not isinstance(row, Mapping):
        errors.append("memory_state must be an object")
        return "", False

    raw_mode = row.get("mode")
    raw_status = row.get("status")
    raw_source = row.get("source")
    raw_justification = row.get("material_rediscovery_justification")

    mode = raw_mode.strip().lower() if isinstance(raw_mode, str) else ""
    status = raw_status.strip().lower() if isinstance(raw_status, str) else ""
    source = raw_source.strip() if isinstance(raw_source, str) else ""
    provenance = _structured_provenance(raw_source)
    item_count = row.get("item_count")
    known_state_available = row.get("known_state_available")
    justification = (
        raw_justification.strip()
        if isinstance(raw_justification, str)
        else ""
    )

    allowed_modes = {
        str(value).strip().lower()
        for value in requirements.get("memory_state_modes", ("reused", "searched"))
    }
    allowed_statuses = {
        str(value).strip().lower()
        for value in requirements.get("memory_state_statuses", ("complete", "empty"))
    }
    allowed_justifications = {
        str(value).strip()
        for value in requirements.get("rediscovery_material_justifications", ())
        if str(value).strip()
    }

    if mode not in allowed_modes:
        errors.append(
            "memory_state.mode must be one of: " + ", ".join(sorted(allowed_modes))
        )
    if status not in allowed_statuses:
        errors.append(
            "memory_state.status must be one of: " + ", ".join(sorted(allowed_statuses))
        )
    if not _nonempty_text(raw_source):
        errors.append("memory_state.source is required")
    elif provenance is None:
        errors.append("memory_state.source must use non-empty class:locator provenance")
    if not _json_nonnegative_integer(item_count):
        errors.append("memory_state.item_count must be a non-negative integer")
    if not isinstance(known_state_available, bool):
        errors.append("memory_state.known_state_available must be boolean")
    if not isinstance(raw_justification, str):
        errors.append("memory_state.material_rediscovery_justification must be a string")

    if mode == "reused":
        if status != "complete":
            errors.append("reused memory_state requires status=complete")
        if _json_nonnegative_integer(item_count) and item_count < 1:
            errors.append("reused memory_state requires item_count>=1")
        if known_state_available is not True:
            errors.append("reused memory_state requires known_state_available=true")
        if justification:
            errors.append(
                "reused memory_state must not claim a rediscovery justification"
            )
        return mode, False

    if mode == "searched":
        raw_tool = row.get("tool")
        raw_query = row.get("query")
        tool_name = _normalize_tool_name(raw_tool) if isinstance(raw_tool, str) else ""
        query = raw_query.strip() if isinstance(raw_query, str) else ""

        if not isinstance(raw_tool, str):
            errors.append("searched memory_state.tool must be a string")
        if not tool_name:
            errors.append("searched memory_state.tool is required")
        if tool_name and not _matches_alias(
            tool_name, _stage_aliases(policy, "memory_search")
        ):
            errors.append("searched memory_state.tool is not an allowed tool alias")
        if tool_name and tool_name not in loaded_tool_names:
            errors.append("searched memory_state.tool must appear in loaded_tools")
        if not isinstance(raw_query, str):
            errors.append("searched memory_state.query must be a string")
        if not query:
            errors.append("searched memory_state.query is required")
        if provenance is not None and tool_name:
            source_class, _ = provenance
            if _normalize_tool_name(source_class) != tool_name:
                errors.append("searched memory_state.source class must match memory_state.tool")
        if not justification:
            errors.append(
                "searched memory_state requires material_rediscovery_justification"
            )
        elif allowed_justifications and justification not in allowed_justifications:
            errors.append(
                "memory_state.material_rediscovery_justification must be one of: "
                + ", ".join(sorted(allowed_justifications))
            )
        if status == "empty" and _json_nonnegative_integer(item_count) and item_count != 0:
            errors.append("empty searched memory_state requires item_count=0")
        if status == "complete" and _json_nonnegative_integer(item_count) and item_count == 0:
            errors.append("searched memory_state with item_count=0 requires status=empty")
        return mode, status == "empty" and item_count == 0

    return mode, False


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
                errors.append("tool_inventory.loaded_tools must contain at least one tool")
        if inventory_tool and inventory_tool not in loaded_tool_names:
            errors.append("tool_inventory.tool must appear in loaded_tools")

    _validate_memory_state(policy, receipt, loaded_tool_names, errors)

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
            if path and source_locator and not source_locator.lower().endswith(path.lower()):
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
            "consult_relevant_memory_state_before_text": True,
            "reuse_known_state_before_rediscovery": True,
            "memory_search_only_when_materially_justified": True,
            "rediscovery_is_not_progress": True,
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
            "memory_state": (
                "{mode:reused|searched,status:complete|empty,source:class:locator,"
                "item_count:integer,known_state_available:boolean,"
                "material_rediscovery_justification:string,"
                "tool?:string,query?:string}"
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
    memory = _memory_state(receipt)
    memory_mode = (
        str(memory.get("mode", "")).strip().lower()
        if isinstance(memory, Mapping)
        else ""
    )
    memory_search_empty = (
        isinstance(memory, Mapping)
        and memory_mode == "searched"
        and str(memory.get("status", "")).strip().lower() == "empty"
        and memory.get("item_count") == 0
    )
    return _issue_validation(
        ok=not errors,
        status="complete" if not errors else "blocked",
        profiles=profiles,
        errors=errors,
        memory_search_empty=memory_search_empty,
        memory_state_mode=memory_mode,
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
            memory_state_mode=validation.memory_state_mode,
        )
        os.environ["CASEY_BOOT_STATUS"] = "degraded"
        os.environ["GLACIEREQ_PRIME_DIRECTIVE_GATE_STATUS"] = "degraded"
        return _IN_PROCESS_VALIDATION

    os.environ["CASEY_BOOT_STATUS"] = "blocked"
    os.environ["GLACIEREQ_PRIME_DIRECTIVE_GATE_STATUS"] = "blocked"
    raise SystemExit(EXIT_BOOT_BLOCKED)
