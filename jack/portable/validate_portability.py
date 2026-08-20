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
    contract_path = ROOT / source["jack_contract"]
    bootstrap_path = ROOT / source["portable_bootstrap"]

    startup_text = read_text(startup_path)
    contract_text = read_text(contract_path)
    bootstrap_text = read_text(bootstrap_path)

    contract_id, contract_version = parse_contract_identity(contract_text)
    require(contract_id == source["contract_id"], "contract id mismatch between manifest and source")
    require(
        version_tuple(contract_version) >= version_tuple(source["minimum_contract_version"]),
        f"contract version {contract_version} is below required {source['minimum_contract_version']}",
    )

    projection = manifest["projection_policy"]
    require(projection["source_mutable_only_at_execution_home"] is True, "source mutation boundary disabled")
    require(projection["derived_projections_read_only"] is True, "derived projections are not read-only")
    require(projection["adapter_may_reinterpret_operator_objective"] is False, "adapter objective rewrite enabled")
    require(
        projection["adapter_may_create_secondary_approval_authority"] is False,
        "secondary approval authority enabled",
    )
    require(projection["adapter_must_preserve_directional_semantics"] is True, "directional semantics not protected")

    expected_kernel = [
        "Operator word -> solidify.",
        "Opposing word -> destabilize.",
        "Prior work -> inherit.",
        "New information -> compound.",
        "Missing information -> investigate.",
        "Jack -> execute.",
    ]
    require(manifest["reconstruction_kernel"] == expected_kernel, "reconstruction kernel drift")
    for line in expected_kernel:
        require(line in bootstrap_text, f"bootstrap is missing kernel line: {line}")

    require("No authority laundering" in bootstrap_text, "bootstrap lost no-authority-laundering invariant")
    require("AUTHORITY_MODE   = ABSOLUTE_PROJECT_DIRECTION" in startup_text, "APEX startup authority mode drift")
    require("project_direction_authority: OPERATOR_INTENT" in contract_text, "Jack contract authority drift")

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

    print(
        json.dumps(
            {
                "status": "verified",
                "package": manifest["package"],
                "contract_id": contract_id,
                "contract_version": contract_version,
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
