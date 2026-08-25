#!/usr/bin/env python3
"""Validate the APEX Buildkite Master contract against source-controlled CI.

This validator proves repository configuration invariants only. It deliberately
does not claim live Buildkite organization, agent, queue, token, secret, or
build state. Live state requires Buildkite API readback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "config" / "buildkite_master_policy.json"
DEFAULT_PIPELINE = ROOT / ".buildkite" / "pipeline.yml"

SECRET_ASSIGNMENT_RE = re.compile(
    r"(?im)^\s*(?:export\s+)?[A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PRIVATE_KEY|API_KEY)\s*=\s*['\"]?[^$\s]"
)
STEP_KEY_RE = re.compile(r"(?m)^\s{4}key:\s*[A-Za-z0-9_.:-]+\s*$")
QUEUE_RE = re.compile(r"(?m)^\s{6}queue:\s*[A-Za-z0-9_.:-]+\s*$")
TIMEOUT_RE = re.compile(r"(?m)^\s{4}timeout_in_minutes:\s*\d+\s*$")
STEP_START_RE = re.compile(r"(?m)^  - label:")
STEP_KEY_VALUE_RE = re.compile(r"(?m)^    key:\s*([A-Za-z0-9_.:-]+)\s*$")


@dataclass(frozen=True)
class ValidationResult:
    name: str
    passed: bool
    detail: str


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_policy(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Buildkite master policy must be a JSON object")
    return data


def _step_blocks(text: str) -> dict[str, str]:
    starts = [match.start() for match in STEP_START_RE.finditer(text)]
    blocks: dict[str, str] = {}
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        block = text[start:end]
        key_match = STEP_KEY_VALUE_RE.search(block)
        if key_match:
            blocks[key_match.group(1)] = block
    return blocks


def validate_policy(policy: dict[str, Any]) -> list[ValidationResult]:
    results: list[ValidationResult] = []

    required_top = {
        "schema_version",
        "name",
        "role",
        "authority_boundary",
        "execution_spine",
        "observed_lineages",
        "queue_contracts",
        "pipeline_contract",
        "receipt_contract",
        "security_target",
        "known_unverified_requirements",
        "live_readback_contract",
        "github_projection_contract",
        "terminal_state_separation",
        "current_reconciled_observations",
    }
    missing = sorted(required_top - policy.keys())
    results.append(
        ValidationResult(
            "policy.required_top_level",
            not missing,
            "complete" if not missing else f"missing={missing}",
        )
    )

    authority = policy.get("authority_boundary", {})
    results.append(
        ValidationResult(
            "policy.knowledge_use_boundary",
            authority.get("akos") == "determines_what_is_known"
            and authority.get("operator") == "determines_what_is_done_with_what_is_known"
            and authority.get("buildkite") == "executes_and_reports_operator_directed_work",
            "AKOS/OPERATOR/Buildkite roles are separated",
        )
    )

    spine = policy.get("execution_spine", [])
    expected_spine = [
        "akos_observation",
        "operator_direction",
        "execution_intent",
        "buildkite_dispatch",
        "exact_source_checkout",
        "execution",
        "test",
        "adversarial_test",
        "verification",
        "receipt",
        "persistence",
        "readback",
        "akos_observation",
    ]
    results.append(
        ValidationResult(
            "policy.execution_spine",
            spine == expected_spine,
            "exact semantic spine" if spine == expected_spine else f"actual={spine}",
        )
    )

    queues = policy.get("queue_contracts", {})
    results.append(
        ValidationResult(
            "policy.observed_queues",
            {"macos-self", "oracle-arm64"}.issubset(queues),
            f"queues={sorted(queues)}",
        )
    )

    contract = policy.get("pipeline_contract", {})
    required_parallel = contract.get("required_parallel_keys", [])
    results.append(
        ValidationResult(
            "policy.parallel_proof_mesh",
            isinstance(required_parallel, list)
            and len(required_parallel) >= 3
            and contract.get("parallel_fanout_parent") == "buildkite-master"
            and contract.get("receipt_fanin_key") == "verified-receipt"
            and contract.get("receipt_requires_all_parallel_keys") is True,
            f"parallel_keys={required_parallel}",
        )
    )

    unverified = policy.get("known_unverified_requirements", [])
    results.append(
        ValidationResult(
            "policy.unknowns_preserved",
            isinstance(unverified, list) and len(unverified) >= 4,
            f"unverified_count={len(unverified) if isinstance(unverified, list) else 0}",
        )
    )
    live = policy.get("live_readback_contract", {})
    results.append(
        ValidationResult(
            "policy.live_readback_is_observation_only",
            live.get("observation_only") is True and live.get("credential_values_forbidden") is True,
            "live inventory cannot mutate or record credential values",
        )
    )
    projection = policy.get("github_projection_contract", {})
    results.append(
        ValidationResult(
            "policy.projection_not_completion",
            projection.get("exact_commit_required") is True
            and projection.get("projection_does_not_replace_terminal_receipt") is True,
            "GitHub projection is exact-SHA evidence, not terminal completion",
        )
    )
    separation = policy.get("terminal_state_separation", {})
    results.append(
        ValidationResult(
            "policy.terminal_state_separation",
            separation.get("build_passed") == "build_terminal_success_only"
            and separation.get("domain_completion") == "requires_domain_specific_readback",
            "build success and domain completion remain separate",
        )
    )
    return results


def validate_pipeline(text: str, policy: dict[str, Any]) -> list[ValidationResult]:
    contract = policy.get("pipeline_contract", {})
    results: list[ValidationResult] = []

    step_count = len(re.findall(r"(?m)^\s{2}- label:", text))
    key_count = len(STEP_KEY_RE.findall(text))
    queue_count = len(QUEUE_RE.findall(text))
    timeout_count = len(TIMEOUT_RE.findall(text))

    results.extend(
        [
            ValidationResult(
                "pipeline.steps_have_keys",
                (not contract.get("require_step_keys")) or (step_count > 0 and key_count == step_count),
                f"steps={step_count} keys={key_count}",
            ),
            ValidationResult(
                "pipeline.steps_have_queues",
                (not contract.get("require_explicit_queue")) or (step_count > 0 and queue_count == step_count),
                f"steps={step_count} queues={queue_count}",
            ),
            ValidationResult(
                "pipeline.steps_have_timeouts",
                (not contract.get("require_timeouts")) or (step_count > 0 and timeout_count == step_count),
                f"steps={step_count} timeouts={timeout_count}",
            ),
            ValidationResult(
                "pipeline.exact_commit_check",
                (not contract.get("require_exact_commit_verification"))
                or ("git rev-parse HEAD" in text and "BUILDKITE_COMMIT" in text),
                "exact-SHA comparison present",
            ),
            ValidationResult(
                "pipeline.fail_closed_shell",
                (not contract.get("require_fail_closed_shell")) or ("set -euo pipefail" in text),
                "fail-closed shell mode present",
            ),
            ValidationResult(
                "pipeline.receipt_artifacts",
                (not contract.get("require_receipt_artifacts"))
                or ("verified-ci-receipt.json" in text and "SHA256SUMS" in text),
                "receipt + digest artifacts present",
            ),
            ValidationResult(
                "pipeline.no_inline_secrets",
                (not contract.get("reject_inline_secret_assignments"))
                or not SECRET_ASSIGNMENT_RE.search(text),
                "no literal inline credential assignment detected",
            ),
        ]
    )

    blocks = _step_blocks(text)
    fanout_parent = contract.get("parallel_fanout_parent")
    required_parallel = contract.get("required_parallel_keys", [])
    if fanout_parent and isinstance(required_parallel, list):
        missing = [key for key in required_parallel if key not in blocks]
        wrong_parent = [
            key
            for key in required_parallel
            if key in blocks
            and f"depends_on: {fanout_parent}" not in blocks[key]
        ]
        results.append(
            ValidationResult(
                "pipeline.parallel_fanout",
                not missing and not wrong_parent,
                f"missing={missing} wrong_parent={wrong_parent}",
            )
        )

    receipt_key = contract.get("receipt_fanin_key")
    if receipt_key and contract.get("receipt_requires_all_parallel_keys"):
        receipt_block = blocks.get(receipt_key, "")
        missing_dependencies = [
            key
            for key in required_parallel
            if not re.search(rf"(?m)^\s+-\s+{re.escape(key)}\s*$", receipt_block)
        ]
        results.append(
            ValidationResult(
                "pipeline.receipt_fanin",
                bool(receipt_block) and not missing_dependencies,
                f"receipt={receipt_key} missing_dependencies={missing_dependencies}",
            )
        )

    if contract.get("failure_diagnostics_required"):
        results.append(
            ValidationResult(
                "pipeline.failure_diagnostics",
                "failure-context" in text and "trap capture_failure ERR" in text,
                "parallel verification lanes emit failure-context artifacts",
            )
        )

    if "buildkite-agent pipeline upload" in text and contract.get("dynamic_upload_reject_secrets"):
        results.append(
            ValidationResult(
                "pipeline.dynamic_upload_rejects_secrets",
                "--reject-secrets" in text,
                "dynamic pipeline upload must use --reject-secrets",
            )
        )
    return results


def build_receipt(
    policy_path: Path,
    pipeline_path: Path,
    results: list[ValidationResult],
) -> dict[str, Any]:
    passed = all(item.passed for item in results)
    return {
        "schema": "glaciereq.apex.buildkite-master-validation.v1",
        "status": "PASS" if passed else "FAIL",
        "scope": "repository_contract_only",
        "live_buildkite_state_verified": False,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "policy": {
            "path": str(policy_path.relative_to(ROOT)),
            "sha256": sha256(policy_path),
        },
        "pipeline": {
            "path": str(pipeline_path.relative_to(ROOT)),
            "sha256": sha256(pipeline_path),
        },
        "checks": [
            {"name": item.name, "passed": item.passed, "detail": item.detail}
            for item in results
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--pipeline", type=Path, default=DEFAULT_PIPELINE)
    parser.add_argument("--emit-receipt", type=Path)
    args = parser.parse_args()

    policy_path = args.policy if args.policy.is_absolute() else ROOT / args.policy
    pipeline_path = args.pipeline if args.pipeline.is_absolute() else ROOT / args.pipeline
    policy = load_policy(policy_path)
    pipeline_text = pipeline_path.read_text(encoding="utf-8")

    results = validate_policy(policy) + validate_pipeline(pipeline_text, policy)
    receipt = build_receipt(policy_path, pipeline_path, results)

    if args.emit_receipt:
        receipt_path = (
            args.emit_receipt
            if args.emit_receipt.is_absolute()
            else ROOT / args.emit_receipt
        )
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for item in results:
        marker = "PASS" if item.passed else "FAIL"
        print(f"{marker} {item.name}: {item.detail}")
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
