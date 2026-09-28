"""Fail-closed Notion-first continuity preflight for the APEX control-plane boot.

Compatibility fields that contain the word ``canonical`` remain supported for
existing receipts, but they are topology/source labels only. They never confer
project-direction authority over explicit Operator intent.

Relationship discovery is observational. It may map owner, consumer,
dependency, and overlap relationships, but it may not convert those observations
into integration, hierarchy, value ranking, disposition, or a new root without
explicit Operator direction.
"""
from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from auto_boot import EXIT_BOOT_BLOCKED, BootError
from prime_directive_boot import receipt_from_environment

DEFAULT_POLICY_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "notion_continuity_policy.json"
)
_SEAL = object()


@dataclass(frozen=True, slots=True)
class NotionContinuityValidation:
    ok: bool
    status: str
    errors: tuple[str, ...]
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _SEAL:
            raise TypeError("validation must be issued by the Notion continuity gate")


_IN_PROCESS: NotionContinuityValidation | None = None


def _issue(
    ok: bool, status: str, errors: Sequence[str] = ()
) -> NotionContinuityValidation:
    return NotionContinuityValidation(ok, status, tuple(errors), _SEAL)


def get_in_process_notion_validation() -> NotionContinuityValidation | None:
    return _IN_PROCESS


def load_notion_policy(path: str | Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BootError(f"Notion continuity policy not found: {target}") from exc
    except json.JSONDecodeError as exc:
        raise BootError(f"invalid Notion continuity policy: {exc}") from exc
    if not isinstance(value, dict):
        raise BootError("Notion continuity policy must be a JSON object")
    authority = value.get("authority_semantics")
    if not isinstance(authority, Mapping):
        raise BootError("Notion continuity authority_semantics must be an object")
    required = {
        "discovered_relationships_do_not_authorize_integration": True,
        "inspection_and_mapping_are_observation_only": True,
        "operator_owned_asset_value_ranking_requires_explicit_operator_request": True,
        "operator_owned_asset_disposition_requires_explicit_operator_request": True,
    }
    for name, expected in required.items():
        if authority.get(name) is not expected:
            raise BootError(f"Notion continuity authority_semantics.{name} must be {expected!r}")
    return value


def _norm(value: Any) -> str:
    return str(value or "").strip().lower().replace("::", ".")


def _nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _matches(tool: Any, aliases: Sequence[str]) -> bool:
    name = _norm(tool)
    allowed = {_norm(alias) for alias in aliases if _nonempty_text(alias)}
    return name in allowed or any(name.endswith(f".{alias}") for alias in allowed)


def _inventory(receipt: Mapping[str, Any], errors: list[str]) -> set[str]:
    row = receipt.get("tool_inventory")
    if not isinstance(row, Mapping) or not isinstance(row.get("loaded_tools"), list):
        errors.append("tool_inventory.loaded_tools must exist before continuity preflight")
        return set()
    return {
        _norm(value)
        for value in row["loaded_tools"]
        if isinstance(value, str) and value.strip()
    }


def _tool(
    stage: str,
    value: Any,
    aliases: Sequence[str],
    loaded: set[str],
    errors: list[str],
) -> None:
    name = _norm(value)
    if not name:
        errors.append(f"{stage}.tool is required")
    elif not _matches(name, aliases):
        errors.append(f"{stage}.tool is not an allowed tool alias")
    elif name not in loaded:
        errors.append(f"{stage}.tool must appear in tool_inventory.loaded_tools")


def _operator_override_authorized(
    discovery: Mapping[str, Any], integration: Mapping[str, Any]
) -> bool:
    candidates = (discovery.get("operator_override"), integration.get("operator_override"))
    for row in candidates:
        reason = row.get("reason") if isinstance(row, Mapping) else None
        if (
            isinstance(row, Mapping)
            and row.get("authorized") is True
            and _nonempty_text(reason)
        ):
            return True
    return False


def validate_notion_continuity_receipt(
    policy: Mapping[str, Any], receipt: Mapping[str, Any]
) -> tuple[str, ...]:
    errors: list[str] = []
    loaded = _inventory(receipt, errors)
    aliases = policy.get("tool_aliases", {})
    req = policy.get("receipt_requirements", {})

    boot = receipt.get("notion_boot_analysis")
    if not isinstance(boot, Mapping):
        errors.append("notion_boot_analysis must be an object")
    else:
        _tool(
            "notion_boot_analysis.search",
            boot.get("search_tool"),
            aliases.get("notion_search", ()),
            loaded,
            errors,
        )
        _tool(
            "notion_boot_analysis.fetch",
            boot.get("fetch_tool"),
            aliases.get("notion_fetch", ()),
            loaded,
            errors,
        )
        if _norm(boot.get("status")) != _norm(req.get("notion_status", "complete")):
            errors.append("notion_boot_analysis.status must be complete")
        if not _nonempty_text(boot.get("query")):
            errors.append("notion_boot_analysis.query is required")
        for key in (
            "identity_loaded",
            "expectations_loaded",
            "capabilities_loaded",
            "current_state_loaded",
        ):
            if boot.get(key) is not True:
                errors.append(f"notion_boot_analysis.{key} must be true")
        conflicts = boot.get("canonical_conflicts")
        if not isinstance(conflicts, list):
            errors.append("notion_boot_analysis.canonical_conflicts must be an array")
        elif req.get("canonical_conflicts_must_be_empty", True) and conflicts:
            errors.append("notion_boot_analysis.canonical_conflicts must be empty")

        pages = boot.get("pages_loaded")
        ids: set[str] = set()
        page_roles: set[tuple[str, str]] = set()
        if not isinstance(pages, list):
            errors.append("notion_boot_analysis.pages_loaded must be an array")
        else:
            for index, page in enumerate(pages):
                if not isinstance(page, Mapping):
                    errors.append(
                        f"notion_boot_analysis.pages_loaded[{index}] must be an object"
                    )
                    continue
                page_id = (
                    page.get("id", "").strip().lower()
                    if isinstance(page.get("id"), str)
                    else ""
                )
                role = _norm(page.get("role"))
                source = page.get("source")
                if not page_id:
                    errors.append(
                        f"notion_boot_analysis.pages_loaded[{index}].id is required"
                    )
                if not role:
                    errors.append(
                        f"notion_boot_analysis.pages_loaded[{index}].role is required"
                    )
                if not _nonempty_text(source):
                    errors.append(
                        f"notion_boot_analysis.pages_loaded[{index}].source is required"
                    )
                elif not _matches(
                    source.split(":", 1)[0], aliases.get("notion_fetch", ())
                ):
                    errors.append(
                        f"notion_boot_analysis.pages_loaded[{index}].source must use Notion.fetch"
                    )
                if page_id:
                    ids.add(page_id)
                    page_roles.add((page_id, role))
            minimum = int(req.get("minimum_pages_loaded", 1))
            if len(ids) < minimum:
                errors.append(
                    f"notion_boot_analysis must load at least {minimum} continuity pages"
                )
        for required_page in policy.get("canonical_notion_pages", ()):
            if not isinstance(required_page, Mapping):
                continue
            page_id = str(required_page.get("id", "")).strip().lower()
            role = _norm(required_page.get("role"))
            if page_id and page_id not in ids:
                errors.append(f"missing continuity Notion page: {page_id}")
            elif page_id and role and (page_id, role) not in page_roles:
                errors.append(
                    f"continuity Notion page role mismatch: {page_id} expected {role}"
                )

    discovery = receipt.get("existing_work_discovery")
    found_status = ""
    existing_owner: Mapping[str, Any] | None = None
    if not isinstance(discovery, Mapping):
        errors.append("existing_work_discovery must be an object")
        discovery = {}
    else:
        _tool(
            "existing_work_discovery",
            discovery.get("tool"),
            aliases.get("work_search", ()),
            loaded,
            errors,
        )
        if not _nonempty_text(discovery.get("query")):
            errors.append("existing_work_discovery.query is required")
        found_status = _norm(discovery.get("status"))
        allowed = {
            _norm(value)
            for value in req.get("existing_work_statuses", ("found", "none_found"))
        }
        if found_status not in allowed:
            errors.append("existing_work_discovery.status must be found or none_found")
        systems = discovery.get("systems_searched")
        system_set = (
            {_norm(value) for value in systems if _nonempty_text(value)}
            if isinstance(systems, list)
            else set()
        )
        if not isinstance(systems, list):
            errors.append("existing_work_discovery.systems_searched must be an array")
        if "notion" not in system_set:
            errors.append("existing_work_discovery.systems_searched must include Notion")
        minimum = int(req.get("minimum_existing_work_systems_searched", 2))
        if len(system_set) < minimum:
            errors.append(
                f"existing_work_discovery must search at least {minimum} systems"
            )
        conflicts = discovery.get("canonical_conflicts")
        if not isinstance(conflicts, list):
            errors.append("existing_work_discovery.canonical_conflicts must be an array")
        elif req.get("canonical_conflicts_must_be_empty", True) and conflicts:
            errors.append("existing_work_discovery.canonical_conflicts must be empty")
        candidates = discovery.get("candidates")
        candidates = candidates if isinstance(candidates, list) else []
        if not isinstance(discovery.get("candidates"), list):
            errors.append("existing_work_discovery.candidates must be an array")
        owner = discovery.get("canonical_owner")
        if owner is not None and not isinstance(owner, Mapping):
            errors.append("existing_work_discovery.canonical_owner must be an object or null")
        existing_owner = owner if isinstance(owner, Mapping) else None
        decision = _norm(discovery.get("decision"))
        allowed_found_decisions = {
            _norm(value)
            for value in req.get("found_work_decisions", ("map_existing",))
        }
        if found_status == "found":
            if not candidates:
                errors.append("found existing work requires at least one candidate")
            if existing_owner is None:
                errors.append("found existing work requires existing owner metadata")
            if decision not in allowed_found_decisions:
                errors.append(
                    "found existing work requires decision=map_existing or operator_override"
                )
        elif found_status == "none_found":
            if candidates:
                errors.append("none_found existing work requires zero candidates")
            if owner is not None:
                errors.append("none_found existing work requires canonical_owner=null")
            if decision != "map_none_found":
                errors.append(
                    "none_found existing work requires decision=map_none_found"
                )

    integration = receipt.get("integration_map")
    if not isinstance(integration, Mapping):
        errors.append("integration_map must be an object")
        integration = {}
    else:
        if _norm(integration.get("status")) != _norm(
            req.get("integration_status", "complete")
        ):
            errors.append("integration_map.status must be complete")
        if integration.get("need_search_performed") is not True:
            errors.append("integration_map.need_search_performed must be true")
        searched = integration.get("searched_relationships")
        relation_set = (
            {_norm(value) for value in searched if _nonempty_text(value)}
            if isinstance(searched, list)
            else set()
        )
        if not isinstance(searched, list):
            errors.append("integration_map.searched_relationships must be an array")
        for relation in ("owner", "consumer", "dependency", "overlap"):
            if relation not in relation_set:
                errors.append(
                    f"integration_map.searched_relationships must include {relation}"
                )
        link_plan = integration.get("link_plan")
        if not isinstance(link_plan, list) or not any(
            _nonempty_text(value) for value in link_plan
        ):
            errors.append("integration_map.link_plan must contain at least one observational link")
        if integration.get("abandon_existing") is not False:
            errors.append("integration_map.abandon_existing must be false")

        relationships: list[Any] = []
        for key in ("consumers", "dependencies", "related_nodes"):
            value = integration.get(key)
            if not isinstance(value, list):
                errors.append(f"integration_map.{key} must be an array")
            else:
                relationships.extend(value)

        owner = integration.get("owner")
        if owner is not None and not isinstance(owner, Mapping):
            errors.append("integration_map.owner must be an object or null")
        decision = _norm(integration.get("decision"))
        override = _operator_override_authorized(discovery, integration)
        create_new_root = integration.get("create_new_root") is True

        if found_status == "found" and isinstance(owner, Mapping) and existing_owner is not None:
            a = (
                _norm(existing_owner.get("system")),
                str(existing_owner.get("id", "")).strip(),
            )
            b = (
                _norm(owner.get("system")),
                str(owner.get("id", "")).strip(),
            )
            if a != b:
                errors.append(
                    "integration_map.owner must match discovered existing owner metadata"
                )

        if override:
            if decision != "operator_override":
                errors.append("explicit Operator override requires decision=operator_override")
        else:
            if decision != _norm(req.get("default_relationship_decision", "map_only")):
                errors.append(
                    "relationship discovery without Operator override requires decision=map_only"
                )
            if create_new_root:
                errors.append(
                    "integration_map.create_new_root requires explicit Operator direction"
                )

        if integration.get("asset_value_ranking_performed") is not False:
            errors.append("integration_map.asset_value_ranking_performed must be false unless explicitly Operator-directed")
        if integration.get("asset_disposition_performed") is not False:
            errors.append("integration_map.asset_disposition_performed must be false unless explicitly Operator-directed")
        if integration.get("inspection_scope_expanded") is not False:
            errors.append("integration_map.inspection_scope_expanded must be false")

    return tuple(errors)


def build_notion_preflight_request(
    policy: Mapping[str, Any], *, task: str
) -> dict[str, Any]:
    return {
        "request_type": "glaciereq_notion_continuity_preflight",
        "schema_version": policy.get("schema_version"),
        "task": task,
        "stage_order": list(policy.get("stage_order", ())),
        "canonical_notion_pages": list(policy.get("canonical_notion_pages", ())),
        "authority_semantics": dict(policy.get("authority_semantics", {})),
        "requirements": {
            "notion_before_user_facing_text": True,
            "recover_identity_expectations_capabilities_and_current_state": True,
            "determine_whether_work_already_exists_before_starting": True,
            "resolve_existing_owner_as_topology_not_project_authority": True,
            "discover_owner_consumers_dependencies_and_overlap_before_making": True,
            "relationship_discovery_produces_map_not_integration_order": True,
            "preserve_literal_operator_operation_scope": True,
            "no_unsolicited_operator_asset_value_ranking": True,
            "no_unsolicited_operator_asset_disposition": True,
            "operator_override_may_authorize_new_root": True,
            "topology_conflicts_require_resolution": True,
        },
    }


def automatic_notion_continuity_preflight() -> NotionContinuityValidation | None:
    global _IN_PROCESS
    if _IN_PROCESS is not None:
        return _IN_PROCESS
    mode = os.getenv("CASEY_AUTO_BOOT_MODE", "strict").strip().lower()
    if mode == "off" or os.getenv("CASEY_AUTO_BOOT_DISABLE") == "1":
        os.environ["GLACIEREQ_NOTION_CONTINUITY_GATE_STATUS"] = "off"
        return None
    if mode not in {"strict", "request"}:
        raise BootError(f"unsupported CASEY_AUTO_BOOT_MODE: {mode}")

    policy = load_notion_policy()
    task = os.getenv("CASEY_BOOT_TASK", "resume Operator-directed unfinished material action")
    receipt = receipt_from_environment()
    if receipt is None:
        print(
            json.dumps(
                build_notion_preflight_request(policy, task=task),
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        sys.stderr.flush()
        status = "blocked" if mode == "strict" else "degraded"
        os.environ["GLACIEREQ_NOTION_CONTINUITY_GATE_STATUS"] = status
        return _issue(False, status, ("no boot receipt supplied",))

    errors = validate_notion_continuity_receipt(policy, receipt)
    validation = _issue(not errors, "complete" if not errors else "blocked", errors)
    if validation.ok:
        _IN_PROCESS = validation
        os.environ["GLACIEREQ_NOTION_CONTINUITY_GATE_STATUS"] = "complete"
        return validation

    os.environ["GLACIEREQ_NOTION_CONTINUITY_GATE_STATUS"] = "blocked"
    print(
        json.dumps(
            {
                "boot_status": "blocked",
                "notion_continuity_status": "blocked",
                "errors": list(validation.errors),
                "external_action_authorized": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        file=sys.stderr,
    )
    sys.stderr.flush()
    if mode == "strict":
        raise SystemExit(EXIT_BOOT_BLOCKED)
    os.environ["GLACIEREQ_NOTION_CONTINUITY_GATE_STATUS"] = "degraded"
    return validation
