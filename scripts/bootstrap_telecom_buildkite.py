#!/usr/bin/env python3
"""Bootstrap and terminally verify Telecom on the existing APEX Buildkite fabric."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "reconcile_genius_buildkite.py"
RECEIPT_PATH = ROOT / "artifacts" / "buildkite" / "telecom-bootstrap.json"
RECEIPT_SHA_PATH = RECEIPT_PATH.with_suffix(RECEIPT_PATH.suffix + ".sha256")

TELECOM_BRANCH = "feat/telecom-foundation-boot-v1"
TELECOM_COMMIT = "651e51e2adc2e52e046e65362aa7c648c897fdd1"
TELECOM_SPEC = {
    "name": "Telecom-valley-atlas-cabin-solar",
    "slug": "telecom-valley-atlas-cabin-solar",
    "repository": "git@github.com:GlacierEQ/Telecom-valley-atlas-cabin-solar.git",
    "github_repository": "GlacierEQ/Telecom-valley-atlas-cabin-solar",
    "status_context": "buildkite/telecom-valley-atlas-cabin-solar",
    "pipeline_file": ".buildkite/pipeline.yml",
    "role": "telecommunications-domain",
}


def load_reconciler():
    spec = importlib.util.spec_from_file_location("apex_buildkite_reconciler", MODULE_PATH)
    if not spec or not spec.loader:
        raise RuntimeError("unable to load APEX Buildkite reconciler")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def await_build(api, module, slug: str, number: int) -> dict:
    policy = module.REGISTRY["verification_policy"]
    success = {str(value) for value in policy["build_success_states"]}
    failure = {str(value) for value in policy["build_failure_states"]}
    deadline = time.monotonic() + float(policy["build_timeout_seconds"])
    interval = max(1.0, float(policy["poll_interval_seconds"]))
    path = (
        f"/organizations/{urllib.parse.quote(module.ORG)}/pipelines/"
        f"{urllib.parse.quote(slug)}/builds/{number}"
    )
    while True:
        build = api.request("GET", path)
        if not isinstance(build, dict):
            raise RuntimeError(f"invalid Buildkite build readback for {slug} #{number}")
        state = str(build.get("state") or "")
        if state in success:
            module.verify_returned_build_commit(build, TELECOM_COMMIT)
            if str(build.get("branch") or "") != TELECOM_BRANCH:
                raise RuntimeError(
                    f"Telecom Buildkite branch mismatch: {build.get('branch')!r}"
                )
            return build
        if state in failure:
            raise RuntimeError(f"Telecom Buildkite build failed: state={state}")
        if time.monotonic() >= deadline:
            raise RuntimeError(f"timed out waiting for Telecom Buildkite build #{number}")
        time.sleep(interval)


def write_receipt(data: dict) -> None:
    RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")
    RECEIPT_PATH.write_bytes(encoded)
    digest = hashlib.sha256(encoded).hexdigest()
    RECEIPT_SHA_PATH.write_text(
        f"{digest}  {RECEIPT_PATH.name}\n",
        encoding="utf-8",
    )


def main() -> int:
    module = load_reconciler()
    module.DEFAULT_BRANCH = TELECOM_BRANCH

    token, token_source = module.resolve_buildkite_token()
    api = module.BuildkiteAPI(token)
    token_meta = module.inspect_api_token(api)
    cluster_id, cluster_source = module.resolve_cluster_id(api, token_meta)
    org_path = f"/organizations/{urllib.parse.quote(module.ORG)}"
    pipelines = module.list_all(api, f"{org_path}/pipelines")

    pipeline, mutation = module.reconcile_pipeline(
        api, pipelines, TELECOM_SPEC, cluster_id
    )
    slug = str(pipeline["slug"])
    webhook = module.ensure_webhook(api, slug)
    readback = api.request("GET", f"{org_path}/pipelines/{urllib.parse.quote(slug)}")
    if not isinstance(readback, dict):
        raise RuntimeError("Telecom Buildkite pipeline readback failed")
    module.verify_pipeline_readback(readback, TELECOM_SPEC, cluster_id)

    build = module.trigger_build(
        api,
        slug,
        TELECOM_SPEC["github_repository"],
        TELECOM_COMMIT,
    )
    if not isinstance(build, dict) or build.get("number") is None:
        raise RuntimeError("Telecom Buildkite trigger returned no build number")
    module.verify_returned_build_commit(build, TELECOM_COMMIT)
    terminal = await_build(api, module, slug, int(build["number"]))

    receipt = {
        "schema": "glaciereq.apex.telecom-buildkite-bootstrap.v1",
        "status": "VERIFIED_TERMINAL_SUCCESS",
        "generated_at": module.utc_now(),
        "organization": module.ORG,
        "repository": TELECOM_SPEC["github_repository"],
        "branch": TELECOM_BRANCH,
        "source_commit": TELECOM_COMMIT,
        "mutation": mutation,
        "pipeline": module.compact_pipeline(readback),
        "webhook": webhook,
        "terminal_build": module.compact_build(terminal),
        "cluster": {
            "id": cluster_id,
            "source": cluster_source,
            "queue": module.DEFAULT_QUEUE,
        },
        "api_token": {
            "uuid": token_meta.get("uuid"),
            "description": token_meta.get("description"),
            "expires_at": token_meta.get("expires_at"),
            "source": token_source,
            "value_recorded": False,
        },
        "credentials_recorded": False,
    }
    write_receipt(receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"APEX Telecom Buildkite bootstrap failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
