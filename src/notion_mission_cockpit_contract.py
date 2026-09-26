"""Non-authorizing Notion mission-cockpit projection contract.

This selectively preserves the field model from the disconnected
``feat/durable-workflow-machine/adapters/notion/adapter.py`` donor while
explicitly rejecting its in-memory ``SYNCED`` simulation. This module builds a
provider-operation plan only; it does not call Notion or claim provider state.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


class CockpitContractError(RuntimeError):
    pass


_REQUIRED_FIELDS = {
    "Mission": "objective",
    "Status": "status",
    "Run": "correlation_id",
    "Priority": "priority",
    "Worker": "worker",
    "GitHub": "repositories",
    "Started": "created_at",
    "Current Step": "current_step",
    "Verified Mutations": "verified_mutations",
    "Failed Mutations": "failed_mutations",
    "Open Blocker": "open_blocker",
    "Receipt": "receipt_id",
}


def load_contract(path: str | Path) -> Mapping[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CockpitContractError(f"contract not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CockpitContractError(f"invalid contract JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise CockpitContractError("contract must be an object")
    return value


def validate_contract(contract: Mapping[str, Any]) -> None:
    if contract.get("schema_version") != 1:
        raise CockpitContractError("schema_version must be 1")
    donor = contract.get("donor")
    if not isinstance(donor, Mapping):
        raise CockpitContractError("donor metadata required")
    if donor.get("branch") != "feat/durable-workflow-machine":
        raise CockpitContractError("unexpected donor branch")
    if donor.get("path") != "adapters/notion/adapter.py":
        raise CockpitContractError("unexpected donor path")

    semantics = contract.get("semantics")
    if not isinstance(semantics, Mapping):
        raise CockpitContractError("semantics required")
    required = {
        "authority": "projection_only",
        "provider": "notion",
        "provider_write_enabled": False,
        "provider_receipt_required": True,
        "terminal_readback_required": True,
        "mock_success_allowed": False,
        "in_memory_readback_allowed": False,
    }
    for key, expected in required.items():
        if semantics.get(key) != expected:
            raise CockpitContractError(f"unsafe semantics: {key}")

    if contract.get("fields") != _REQUIRED_FIELDS:
        raise CockpitContractError("cockpit field mapping drift")


def _text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise CockpitContractError(f"{name} is required")
    return text


def build_projection_plan(
    mission: Mapping[str, Any],
    *,
    current_step: str,
    verified_mutations: int = 0,
    failed_mutations: int = 0,
    open_blocker: str | None = None,
    receipt_id: str | None = None,
    worker: str = "continuity-repair-peer",
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a reviewable Notion projection plan without claiming provider state."""
    validate_contract(contract)
    mission_id = _text(mission.get("mission_id"), "mission_id")
    objective = _text(mission.get("objective"), "objective")
    status = _text(mission.get("status"), "status")
    correlation_id = _text(mission.get("correlation_id"), "correlation_id")
    priority = _text(mission.get("priority"), "priority")
    created_at = _text(mission.get("created_at"), "created_at")
    step = _text(current_step, "current_step")
    if not isinstance(verified_mutations, int) or verified_mutations < 0:
        raise CockpitContractError(
            "verified_mutations must be a non-negative integer"
        )
    if not isinstance(failed_mutations, int) or failed_mutations < 0:
        raise CockpitContractError(
            "failed_mutations must be a non-negative integer"
        )
    repositories = mission.get("repositories", ())
    if isinstance(repositories, (str, bytes)) or not isinstance(
        repositories,
        (list, tuple),
    ):
        raise CockpitContractError("repositories must be a list or tuple")
    repo_text = ", ".join(
        _text(value, "repository") for value in repositories
    ) or "none"

    properties = {
        "Mission": objective,
        "Status": status,
        "Run": correlation_id,
        "Priority": priority,
        "Worker": _text(worker, "worker"),
        "GitHub": repo_text,
        "Started": created_at,
        "Current Step": step,
        "Verified Mutations": verified_mutations,
        "Failed Mutations": failed_mutations,
        "Open Blocker": (open_blocker or "none").strip() or "none",
        "Receipt": (receipt_id or "none").strip() or "none",
    }
    return {
        "schema": "glaciereq.notion-mission-cockpit-projection-plan.v1",
        "status": "PLANNED",
        "provider": "notion",
        "mission_id": mission_id,
        "properties": properties,
        "external_action_authorized": False,
        "provider_write_enabled": False,
        "provider_receipt_required": True,
        "terminal_readback_required": True,
        "donor_provenance": {
            "branch": contract["donor"]["branch"],
            "path": contract["donor"]["path"],
            "blob_sha": contract["donor"]["blob_sha"],
        },
    }
