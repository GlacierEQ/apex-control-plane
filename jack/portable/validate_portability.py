#!/usr/bin/env python3
"""Validate the APEX Juggernaut Jack portability package.

The validator deliberately uses only the Python standard library so it can run in
GitHub Actions, local checkouts, and lightweight agent environments.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "jack" / "portable" / "portability_manifest.json"


class ValidationError(RuntimeError):
    """Raised when a portability invariant is violated."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def read_text(path: Path) -> str:
    require(path.is_file(), f"required file missing: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def parse_contract_identity(contract_text: str) -> tuple[str, str]:
    contract_id = re.search(r"(?m)^\s*id:\s*([^\n#]+)", contract_text)
    version = re.search(r"(?m)^\s*version:\s*([^\n#]+)", contract_text)
    require(contract_id is not None, "Jack contract id is missing")
    require(version is not None, "Jack contract version is missing")
    return contract_id.group(1).strip(), version.group(1).strip()


def version_tuple(value: str) -> tuple[int, ...]:
    require(bool(re.fullmatch(r"\d+(?:\.\d+)*", value)), f"invalid numeric version: {value}")
    return tuple(int(part) for part in value.split("."))


def main() -> int:
    manifest = json.loads(read_text(MANIFEST))

    require(manifest["package"] == "APEX_JUGGERNAUT_JACK_PORTABILITY", "unexpected package id")
    require(manifest["execution_home"] == "GlacierEQ/apex-control-plane", "execution home drift")
    require(manifest["project_direction_authority"] == "OPERATOR_INTENT", "project authority drift")

    source = manifest["source"]
    startup_path = ROOT / source["startup_contract"]
    sovereignty_path = ROOT / source["operator_asset_sovereignty_contract"]
    contract_path = ROOT / source["jack_contract"]
    bootstrap_path = ROOT / source["portable_bootstrap"]

    startup_text = read_text(startup_path)
    sovereignty_text = read_text(sovereignty_path)
    contract_text = read_text(contract_path)
    bootstrap_text = read_text(bootstrap_path)

    contract_id, contract_version = parse_contract_identity(contract_text)
    require(contract_id == source["contract_id"], "contract id mismatch between manifest and source")
    require(
        version_tuple(contract_version) >= version_tuple("1.3.0"),
        f"contract version {contract_version} is below mandatory 1.3.0",
    )
    require(
        version_tuple(source["minimum_contract_version"]) >= version_tuple("1.3.0"),
        "portability manifest permits a pre-reuse-first Jack contract",
    )

    projection = manifest["projection_policy"]
    require(projection["source_mutable_only_at_execution_home"] is True, "source mutation boundary disabled")
    require(projection["derived_projections_read_only"] is True, "derived projections are not read-only")
    require(projection["adapter_may_reinterpret_operator_objective"] is False, "adapter objective rewrite enabled")
    require(projection["adapter_may_expand_operator_operation_scope"] is False, "adapter scope expansion enabled")
    require(projection["adapter_may_rank_operator_assets_without_request"] is False, "adapter asset ranking authority enabled")
    require(projection["adapter_may_dispose_operator_assets_without_direction"] is False, "adapter asset disposition authority enabled")
    require(
        projection["adapter_may_create_secondary_approval_authority"] is False,
        "secondary approval authority enabled",
    )
    require(
        projection["adapter_may_force_rediscovery_of_usable_known_state"] is False,
        "adapter can force rediscovery over usable known state",
    )
    require(
        projection["adapter_may_replace_continuation_with_reconstruction"] is False,
        "adapter can replace continuation with reconstruction",
    )
    require(projection["adapter_must_preserve_directional_semantics"] is True, "directional semantics not protected")
    require(projection["adapter_must_preserve_operation_class"] is True, "operation class not protected")
    require(projection["adapter_must_reuse_known_state_where_usable"] is True, "known-state reuse not protected")
    require(projection["adapter_must_hydrate_only_material_delta"] is True, "material-delta hydration not protected")

    continuation = manifest["continuation_model"]
    require(continuation["known_state_before_rediscovery"] is True, "known state does not precede rediscovery")
    require(continuation["reuse_known_state_where_usable"] is True, "known-state reuse disabled")
    require(continuation["material_delta_hydration_only"] is True, "material-delta hydration disabled")
    require(continuation["redundant_rediscovery_is_not_progress"] is True, "rediscovery can impersonate progress")
    require(continuation["reconstruction_over_usable_state_forbidden"] is True, "reconstruction over usable state allowed")
    require(continuation["search_or_reopen_requires_material_reason"] is True, "search can be forced without material reason")

    asset = manifest["operator_asset_sovereignty"]
    require(asset["look_inspect_open_list_inventory_map_trace_are_observation_only"] is True, "observational verbs can expand scope")
    require(asset["tool_access_is_capability_not_authority"] is True, "tool access can become authority")
    require(asset["observation_is_knowledge_not_authority"] is True, "observation can become authority")
    require(asset["unsolicited_operator_asset_value_ranking"] is False, "unsolicited asset ranking enabled")
    require(asset["unsolicited_operator_asset_disposition"] is False, "unsolicited asset disposition enabled")
    require(asset["inspection_scope_expansion"] is False, "inspection scope expansion enabled")
    require(asset["similar_names_do_not_imply_duplication"] is True, "similar-name duplication inference enabled")
    require(asset["overlap_does_not_imply_subordination"] is True, "overlap subordination inference enabled")

    expected_kernel = [
        "Operator word -> solidify.",
        "Known valid state -> reuse.",
        "Prior work -> inherit.",
        "Material delta -> hydrate.",
        "Opposing word -> destabilize.",
        "New information -> compound.",
        "Missing material information -> investigate.",
        "Jack -> execute.",
    ]
    require(manifest["continuity_kernel"] == expected_kernel, "continuity kernel drift")
    require("reconstruction_kernel" not in manifest, "legacy reconstruction kernel survived in active manifest")
    for line in expected_kernel:
        require(line in bootstrap_text, f"bootstrap is missing kernel line: {line}")

    require("No authority laundering" in bootstrap_text, "bootstrap lost no-authority-laundering invariant")
    require("Operator Asset Sovereignty" in bootstrap_text, "bootstrap lost Operator Asset Sovereignty")
    require("Rediscovery of already-known relevant Operator/project state is not progress." in bootstrap_text, "bootstrap lost rediscovery-is-not-progress invariant")
    require("Tool access is capability. Observation is knowledge. Neither is authority." in bootstrap_text, "bootstrap lost capability/knowledge/authority distinction")
    require("UNSOLICITED_ASSET_RANKING=FORBIDDEN" in startup_text, "APEX startup lost unsolicited asset-ranking prohibition")
    require("UNSOLICITED_ASSET_DISPOSITION=FORBIDDEN" in startup_text, "APEX startup lost unsolicited asset-disposition prohibition")
    require("INSPECTION_SCOPE_EXPANSION=FORBIDDEN" in startup_text, "APEX startup lost inspection-scope prohibition")
    require("The phrase `winners vs dead weight`" in sovereignty_text, "asset-sovereignty correction receipt missing")
    require("project_direction_authority: OPERATOR_INTENT" in contract_text, "Jack contract authority drift")
    require("known_state_before_rediscovery: true" in contract_text, "Jack contract lost known-state-first invariant")
    require("reuse_known_state_where_usable: true" in contract_text, "Jack contract lost reuse invariant")
    require("material_delta_hydration_only: true" in contract_text, "Jack contract lost material-delta invariant")
    require("- CONSULT_RELEVANT_KNOWN_STATE" in contract_text, "Jack loop does not begin from known state")
    require("- REUSE_KNOWN_STATE_WHERE_USABLE" in contract_text, "Jack loop does not reuse known state")
    require("- HYDRATE_MATERIAL_DELTA_IF_REQUIRED" in contract_text, "Jack loop does not hydrate material delta")
    require("RECONSTRUCT_CONTEXT" not in contract_text, "legacy reconstruction-first Jack loop survived")
    require("search_existing_work_before_creation" not in contract_text, "legacy forced-search invariant survived")
    require("operator_asset_sovereignty_preserved" in contract_text, "Jack contract sovereignty gate missing")
    require("operator_aligned_delta_selected" in contract_text, "Jack contract still lacks Operator-aligned delta gate")
    require("highest_value_delta_selected" not in contract_text, "legacy highest-value delta authority survived in active Jack contract")

    targets = manifest["targets"]
    expected_targets = {
        "memoryplugin",
        "notion",
        "github_repositories",
        "chatgpt",
        "claude",
        "gemini",
        "local_models",
        "api_and_mcp_agents",
    }
    require(expected_targets.issubset(targets), "one or more required propagation targets are missing")
    for adapter in ("chatgpt", "claude", "gemini"):
        require(targets[adapter]["known_state_first"] is True, f"{adapter} adapter is not known-state-first")
        require(targets[adapter]["material_delta_retrieval_only"] is True, f"{adapter} adapter can force broad rediscovery")

    print(
        json.dumps(
            {
                "status": "verified",
                "package": manifest["package"],
                "contract_id": contract_id,
                "contract_version": contract_version,
                "continuation_semantics": "reuse-first-material-delta",
                "operator_asset_sovereignty": "verified",
                "targets": sorted(expected_targets),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValidationError, KeyError, json.JSONDecodeError) as exc:
        print(f"PORTABILITY_VALIDATION_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
