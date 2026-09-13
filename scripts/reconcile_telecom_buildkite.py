#!/usr/bin/env python3
"""Bootstrap and terminally verify Telecom on the existing APEX Buildkite fabric."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "reconcile_genius_buildkite.py"
RECEIPT_PATH = ROOT / "artifacts" / "buildkite" / "telecom-reconciliation.json"
TARGET_REF = os.getenv(
    "TELECOM_BUILDKITE_REF", "feat/telecom-foundation-boot-v1"
).strip()

TARGET = {
    "name": "Telecom-valley-atlas-cabin-solar",
    "slug": "telecom-valley-atlas-cabin-solar",
    "repository": "git@github.com:GlacierEQ/Telecom-valley-atlas-cabin-solar.git",
    "github_repository": "GlacierEQ/Telecom-valley-atlas-cabin-solar",
    "status_context": "buildkite/telecom-valley-atlas-cabin-solar",
    "pipeline_file": ".buildkite/pipeline.yml",
    "role": "telecom-domain",
}


def load_reconciler():
    spec = importlib.util.spec_from_file_location(
        "reconcile_genius_buildkite_for_telecom", MODULE_PATH
    )
    if not spec or not spec.loader:
        raise RuntimeError("unable to load APEX Buildkite reconciler")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    if not TARGET_REF:
        raise RuntimeError("TELECOM_BUILDKITE_REF must not be empty")

    mod = load_reconciler()
    mod.DEFAULT_BRANCH = TARGET_REF
    mod.PIPELINES = (TARGET,)
    mod.RECEIPT_PATH = RECEIPT_PATH

    result = mod.main()
    if result != 0:
        return int(result)

    payload = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    pipelines = payload.get("pipelines") or []
    if len(pipelines) != 1:
        raise RuntimeError(f"expected one Telecom reconciliation result, got {len(pipelines)}")
    row = pipelines[0]
    if row.get("repository") != TARGET["github_repository"]:
        raise RuntimeError(f"unexpected reconciliation repository: {row.get('repository')!r}")
    if row.get("verification_status") != "VERIFIED_TERMINAL_SUCCESS":
        raise RuntimeError(
            f"Telecom Buildkite verification incomplete: {row.get('verification_status')!r}"
        )

    payload["schema"] = "glaciereq.apex.telecom-buildkite-reconciliation.v1"
    payload["target_ref"] = TARGET_REF
    payload["credentials_recorded"] = False
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    RECEIPT_PATH.write_bytes(encoded)
    digest = hashlib.sha256(encoded).hexdigest()
    RECEIPT_PATH.with_suffix(RECEIPT_PATH.suffix + ".sha256").write_text(
        f"{digest}  {RECEIPT_PATH.name}\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"APEX Telecom Buildkite reconciliation failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
