"""APEX continuity and integration preflight.

Notion is a continuity source, not a superior project-direction authority. The
preflight recovers source state, prior implementation, relationships, and
conflicts while preserving Casey's authority and MAXIMUM_COHERENT_ADVANCE.
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

DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[1] / "config" / "notion_continuity_policy.json"
_SEAL = object()


@dataclass(frozen=True, slots=True)
class NotionContinuityValidation:
    ok: bool
    status: str
    errors: tuple[str, ...]
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _SEAL:
            raise TypeError("validation must be issued by the APEX continuity gate")


_IN_PROCESS: NotionContinuityValidation | None = None


def _issue(ok: bool, status: str, errors: Sequence[str] = ()) -> NotionContinuityValidation:
    return NotionContinuityValidation(ok, status, tuple(errors), _SEAL)


def get_in_process_notion_validation() -> NotionContinuityValidation | None:
    return _IN_PROCESS


def load_notion_policy(path: str | Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BootError(f"APEX continuity policy not found: {target}") from exc
    except json.JSONDecodeError as exc:
        raise BootError(f"invalid APEX continuity policy: {exc}") from exc
    if not isinstance(value, dict):
        raise BootError("APEX continuity policy must be a JSON object")
    if value.get("mode") != "APEX":
        raise BootError("APEX continuity policy must declare mode=APEX")
    if value.get("execution_law") != "MAXIMUM_COHERENT_ADVANCE":
        raise BootError("APEX continuity policy execution law mismatch")
    if value.get("human_project_direction_authority") != "Casey Barton":
        raise BootError("APEX continuity policy human authority mismatch")
    return value


def _norm(value: Any) -> str:
    return str(value or "").strip().lower().replace("::", ".")


def _matches(tool: Any, aliases: Sequence[str]) -> bool:
    name = _norm(tool)
    allowed = {_norm(alias) for alias in aliases if str(alias).strip()}
    return name in allowed or any(name.endswith(f".{alias}") for alias in allowed)


def _inventory(receipt: Mapping[str, Any], errors: list[str]) -> set[str]:
    row = receipt.get("tool_inventory")
    if not isinstance(row, Mapping) or not isinstance(row.get("loaded_tools"), list):
        errors.append("tool_inventory.loaded_tools must exist before continuity preflight")
        return set()
    return {_norm(value) for value in row["loaded_tools"] if str(value).strip()}


def _tool(stage: str, value: Any, aliases: Sequence[str], loaded: set[str], errors: list[str]) -> None:
    name = _norm(value)
    if not name:
        errors.append(f"{stage}.tool is required")
    elif not _matches(name, aliases):
        errors.append(f"{stage}.tool is not an allowed tool alias")
    elif name not in loaded:
        errors.append(f"{stage}.tool must appear in tool_inventory.loaded_tools")


def _source_identity(value: Any) -> tuple[str, str] | None:
    if not isinstance(value, Mapping):
        return None
    system = _norm(value.get("system"))
    object_id = str(value.get("id", "")).strip()
    if not system or not object_id:
        return None
    return system, object_id


def validate_notion_continuity_receipt(
    policy: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> tuple[str, ...]:
    errors: list[str] = []
    loaded = _inventory(receipt, errors)
    aliases = policy.get("tool_aliases", {})
    req = policy.get("receipt_requirements", {})

    if receipt.get("mode") not in (None, "APEX"):
        errors.append("continuity receipt mode must be APEX")
    if receipt.get("human_project_direction_authority") not in (None, "Casey Barton"):
        errors.append("continuity receipt human authority mismatch")
    if receipt.get("execution_law") not in (None, "MAXIMUM_COHERENT_ADVANCE"):
        errors.append("continuity receipt execution law mismatch")

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
        if not str(boot.get("query", "")).strip():
            errors.append("notion_boot_analysis.query is required")
        for key in (
            "identity_loaded",
            "expectations_loaded",
            "capabilities_loaded",
            "current_state_loaded",
            "operator_intent_loaded",
        ):
            if boot.get(key) is not True:
                errors.append(f"notion_boot_analysis.{key} must be true")

        conflicts = boot.get("source_conflicts")
        if not isinstance(conflicts, list):
            errors.append("notion_boot_analysis.source_conflicts must be an array")
        elif conflicts and boot.get("conflicts_preserved") is not True:
            errors.append("notion_boot_analysis conflicts must be preserved, not collapsed")

        pages = boot.get("pages_loaded")
        ids: set[str] = set()
        roles: set[str] = set()
        if not isinstance(pages, list):
            errors.append("notion_boot_analysis.pages_loaded must be an array")
        else:
            for index, row in enumerate(pages):
                if not isinstance(row, Mapping):
                    errors.append(f"notion_boot_analysis.pages_loaded[{index}] must be an object")
                    continue
                page_id = str(row.get("id", "")).strip().lower()
                role = _norm(row.get("role"))
                source = str(row.get("source", "")).strip()
                if not page_id:
                    errors.append(f"notion_boot_analysis.pages_loaded[{index}].id is required")
                if not role:
                    errors.append(f"notion_boot_analysis.pages_loaded[{index}].role is required")
                if not source:
                    errors.append(f"notion_boot_analysis.pages_loaded[{index}].source is required")
                elif not _matches(source.split(":", 1)[0], aliases.get("notion_fetch", ())):
                    errors.append(f"notion_boot_analysis.pages_loaded[{index}].source must use Notion.fetch")
                ids.add(page_id)
                roles.add(role)
            minimum = int(req.get("minimum_pages_loaded", 1))
            if len(ids - {""}) < minimum:
                errors.append(f"notion_boot_analysis must load at least {minimum} APEX boot pages")
        for row in policy.get("apex_boot_pages", ()):
            if not isinstance(row, Mapping):
                continue
            page_id = str(row.get("id", "")).strip().lower()
            role = _norm(row.get("role"))
            if page_id and page_id not in ids:
                errors.append(f"missing APEX boot page: {page_id}")
            if role and role not in roles:
                errors.append(f"missing APEX boot role: {role}")

    discovery = receipt.get("existing_work_discovery")
    found_status = ""
    continuation_source: Mapping[str, Any] | None = None
    if not isinstance(discovery, Mapping):
        errors.append("existing_work_discovery must be an object")
    else:
        _tool(
            "existing_work_discovery",
            discovery.get("tool"),
            aliases.get("work_search", ()),
            loaded,
            errors,
        )
        if not str(discovery.get("query", "")).strip():
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
            {_norm(value) for value in systems if str(value).strip()}
            if isinstance(systems, list)
            else set()
        )
        if not isinstance(systems, list):
            errors.append("existing_work_discovery.systems_searched must be an array")
        if "notion" not in system_set:
            errors.append("existing_work_discovery.systems_searched must include Notion")
        minimum = int(req.get("minimum_existing_work_systems_searched", 2))
        if len(system_set) < minimum:
            errors.append(f"existing_work_discovery must search at least {minimum} systems")

        conflicts = discovery.get("source_conflicts")
        if not isinstance(conflicts, list):
            errors.append("existing_work_discovery.source_conflicts must be an array")
        elif conflicts and discovery.get("conflicts_preserved") is not True:
            errors.append("existing_work_discovery conflicts must be preserved, not collapsed")

        candidates = discovery.get("candidates")
        candidates = candidates if isinstance(candidates, list) else []
        if not isinstance(discovery.get("candidates"), list):
            errors.append("existing_work_discovery.candidates must be an array")

        value = discovery.get("continuation_source")
        continuation_source = value if isinstance(value, Mapping) else None
        decision = _norm(discovery.get("decision"))
        if found_status == "found":
            if not candidates:
                errors.append("found existing work requires at least one candidate")
            if continuation_source is None:
                errors.append("found existing work requires continuation_source")
            if decision not in {"extend", "integrate", "compose", "recover"}:
                errors.append("found existing work requires a strengthening continuation decision")
            if discovery.get("operator_intent_preserved") is not True:
                errors.append("found existing work must preserve operator intent")
            if discovery.get("strongest_prior_state_checked") is not True:
                errors.append("found existing work must check strongest legitimate prior state")
        elif found_status == "none_found":
            if candidates:
                errors.append("none_found existing work requires zero candidates")
            if continuation_source is not None:
                errors.append("none_found existing work requires continuation_source=null")
            if decision != "create_if_needed":
                errors.append("none_found existing work requires decision=create_if_needed")

    integration = receipt.get("integration_map")
    if not isinstance(integration, Mapping):
        errors.append("integration_map must be an object")
    else:
        if _norm(integration.get("status")) != _norm(req.get("integration_status", "complete")):
            errors.append("integration_map.status must be complete")
        if integration.get("need_search_performed") is not True:
            errors.append("integration_map.need_search_performed must be true")
        if integration.get("preserve_prior_gains") is not True:
            errors.append("integration_map.preserve_prior_gains must be true")
        if integration.get("maximum_coherent_advance") is not True:
            errors.append("integration_map.maximum_coherent_advance must be true")

        searched = integration.get("searched_relationships")
        relation_set = (
            {_norm(value) for value in searched if str(value).strip()}
            if isinstance(searched, list)
            else set()
        )
        if not isinstance(searched, list):
            errors.append("integration_map.searched_relationships must be an array")
        for relation in ("owner", "consumer", "dependency", "overlap", "complement"):
            if relation not in relation_set:
                errors.append(f"integration_map.searched_relationships must include {relation}")

        link_plan = integration.get("link_plan")
        if not isinstance(link_plan, list) or not any(str(value).strip() for value in link_plan):
            errors.append("integration_map.link_plan must contain at least one link")

        relationships: list[Any] = []
        for key in ("consumers", "dependencies", "related_nodes", "complements"):
            value = integration.get(key)
            if not isinstance(value, list):
                errors.append(f"integration_map.{key} must be an array")
            else:
                relationships.extend(value)

        source = integration.get("continuation_source")
        decision = _norm(integration.get("decision"))
        create_new_root = integration.get("create_new_root")

        if found_status == "found":
            if not isinstance(source, Mapping):
                errors.append("integration_map.continuation_source is required when work exists")
            elif continuation_source is not None:
                a = _source_identity(continuation_source)
                b = _source_identity(source)
                if a != b:
                    errors.append("integration_map.continuation_source must match discovery source")
            if decision not in {"integrate", "extend", "compose", "recover", "new_root_with_preservation"}:
                errors.append("integration_map.decision must be a strengthening action")
            if create_new_root is True:
                if not str(integration.get("new_root_reason", "")).strip():
                    errors.append("new root requires an explicit engineering reason")
                if decision != "new_root_with_preservation":
                    errors.append("new root with existing work requires decision=new_root_with_preservation")
        elif found_status == "none_found":
            if relationships or isinstance(source, Mapping):
                if decision not in {"integrate", "compose"}:
                    errors.append("integration_map.decision must integrate or compose when related systems exist")
                if create_new_root is True and not str(integration.get("new_root_reason", "")).strip():
                    errors.append("related-system new root requires an explicit engineering reason")
            else:
                if not str(integration.get("new_root_reason", "")).strip():
                    errors.append("standalone work requires integration_map.new_root_reason")
                if decision != "new_root":
                    errors.append("standalone work requires decision=new_root")
                if create_new_root is not True:
                    errors.append("standalone new root requires create_new_root=true")

    return tuple(errors)


def build_notion_preflight_request(policy: Mapping[str, Any], *, task: str) -> dict[str, Any]:
    return {
        "request_type": "glaciereq_apex_continuity_preflight",
        "schema_version": policy.get("schema_version"),
        "mode": "APEX",
        "human_project_direction_authority": "Casey Barton",
        "execution_law": "MAXIMUM_COHERENT_ADVANCE",
        "task": task,
        "stage_order": list(policy.get("stage_order", ())),
        "apex_boot_pages": list(policy.get("apex_boot_pages", ())),
        "requirements": {
            "retrieve_before_user_facing_continuity_claims": True,
            "recover_operator_intent": True,
            "determine_whether_work_already_exists_before_starting": True,
            "recover_current_source_and_strongest_prior_state": True,
            "preserve_source_conflicts_instead_of_collapsing_them": True,
            "discover_owner_consumers_dependencies_overlap_and_complements": True,
            "preserve_prior_gains": True,
            "maximum_coherent_advance": True,
            "new_root_requires_engineering_reason_not_smallness_rule": True,
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
    task = os.getenv("CASEY_BOOT_TASK", "resume highest-value unfinished material action")
    receipt = receipt_from_environment()
    if receipt is None:
        print(
            json.dumps(build_notion_preflight_request(policy, task=task), ensure_ascii=False, sort_keys=True),
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
